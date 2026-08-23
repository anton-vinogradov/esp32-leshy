#!/usr/bin/env python3
"""Retain machine-checked Bluetooth device-intelligence evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.122.1-ble-device-intelligence"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-122", "E-AUTO-086", "E-HIL-146", "E-UX-041"]
SOURCE_FILES = {
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "observation": "firmware/leshy1/src/domain/observations/Observation.h",
    "passive_h": "firmware/leshy1/src/drivers/ble/BlePassiveContract.h",
    "passive_cpp": "firmware/leshy1/src/drivers/ble/BlePassiveContract.cpp",
    "adapter": "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp",
    "catalog_h": "firmware/leshy1/src/apps/ble/BleDeviceCatalog.h",
    "catalog_cpp": "firmware/leshy1/src/apps/ble/BleDeviceCatalog.cpp",
    "navigation": "firmware/leshy1/src/apps/ble/BleDeviceNavigationOrder.h",
    "intelligence_h": "firmware/leshy1/src/apps/ble/BleDeviceIntelligence.h",
    "intelligence_cpp": "firmware/leshy1/src/apps/ble/BleDeviceIntelligence.cpp",
    "company_h": "firmware/leshy1/src/apps/ble/BleCompanyDatabase.h",
    "company_cpp": "firmware/leshy1/src/apps/ble/BleCompanyDatabase.cpp",
    "company_metadata": "firmware/leshy1/assets/bluetooth_companies.json",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "platform": "firmware/leshy1/platformio.ini",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "contract": "tools/check_ble_nearby_contract.py",
    "generator": "tools/make_ble_company_asset.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_ble_nearby_hil.py"
    checker = ROOT / "tools/check_ble_nearby_run.py"
    source_guard = ROOT / "tools/check_ble_nearby_contract.py"
    required = (source / "run.json", source / "firmware.bin",
                source / "artifacts.sha256",
                args.factory.resolve(), args.elf.resolve(),
                args.map.resolve(), runner, checker, source_guard)
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(all(path.is_file() for path in required),
            "source/build/tool artifact missing")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40, "commits must be full IDs")
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.ble_nearby_hil.run.v2" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "fresh" and
            run.get("expected_cid") == CID,
            "source is not the exact fresh-flash pass")
    require(run.get("runner_source_sha256") == digest(runner),
            "runner hash mismatch")
    verification = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", args.firmware_source_commit],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    require(verification.returncode == 0,
            f"independent run verification failed: {verification.stdout}")
    source_check = subprocess.run(
        [sys.executable, str(source_guard)], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(source_check.returncode == 0,
            f"source contract failed: {source_check.stdout}")
    detail_first = run.get("detail_oracle_first", {})
    detail_second = run.get("detail_oracle_second", {})
    detail_changes = run.get("detail_pixel_changes", {})
    require(detail_first.get("active") is True and
            detail_first.get("passive") is True and
            detail_first.get("active_probe_allowed") is False and
            detail_first.get("facts_known") is True and
            detail_first.get("company_database_records") == 4012 and
            detail_first.get("payload_length", 0) > 0 and
            detail_second.get("identity_hash") ==
                detail_first.get("identity_hash") and
            detail_changes.get("radar_changed_pixels", 0) > 0 and
            detail_changes.get("static_changed_pixels") == 0 and
            detail_changes.get("chrome_changed_pixels") == 0,
            "live passive BLE intelligence proof missing")

    destination.mkdir(parents=True)
    main_dir = destination / "run"
    shutil.copytree(source, main_dir)
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    for tool in (runner, checker, source_guard):
        shutil.copy2(tool, tools_dir / tool.name)
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        original = ROOT / relative
        target = source_dir / Path(relative).name
        shutil.copy2(original, target)
        source_hashes[label] = digest(target)
    for path, name in (
        (args.factory.resolve(), "firmware.factory.bin"),
        (args.elf.resolve(), "firmware.elf"),
        (args.map.resolve(), "firmware.map"),
    ):
        shutil.copy2(path, destination / name)
    provenance = {
        "schema": "leshy.ble_device_intelligence_hil.provenance.v1",
        "version": VERSION, "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(main_dir / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "app_image_bytes": (main_dir / "firmware.bin").stat().st_size,
        "factory_image_bytes":
            (destination / "firmware.factory.bin").stat().st_size,
        "runner_sha256": digest(tools_dir / runner.name),
        "checker_sha256": digest(tools_dir / checker.name),
        "source_guard_sha256": digest(tools_dir / source_guard.name),
        "source_sha256": source_hashes,
        "run_sha256": digest(main_dir / "run.json"),
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "tft_states": len(run.get("screens", {})),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")
    summary_value = {
        "schema": "leshy.ble_device_intelligence.acceptance.v1",
        "status": "pass_ble_device_intelligence",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {"artifact_index_sha256": digest(manifest),
                     "files": len(indexed) + 1,
                     "tft_states": len(run.get("screens", {}))},
        "verified": {
            "fresh_flash_pass": True, "manual_button_presses": 0,
            "unique_devices_first": run["live_first"]["ble_devices_unique"],
            "unique_devices_second": run["live_second"]["ble_devices_unique"],
            "scan_drops": 0, "active_scan": False,
            "live_content_changed_pixels": run["list_pixel_changes"][
                "content_changed_pixels"],
            "live_chrome_changed_pixels": 0,
            "company_database_records": 4012,
            "advertisement_payload_bytes": detail_first["payload_length"],
            "vendor_known": detail_first["vendor_known"],
            "service": detail_first["service"],
            "tracker": detail_first["tracker"],
            "signal_samples_first": detail_first["signal_samples"],
            "signal_samples_second": detail_second["signal_samples"],
            "radar_changed_pixels": detail_changes["radar_changed_pixels"],
            "detail_static_changed_pixels": 0,
            "detail_chrome_changed_pixels": 0,
            "identity_stable": True,
            "passive_receive_only": True,
            "active_probe_allowed": False,
            "two_complete_ble_lifecycles": True,
            "zero_heap_drift_after_warmup": True,
            "persistent_generation_unchanged": True,
            "physical_sd_write_calls": 0,
            "heap_total_bytes": run["metrics_after"]["heap_total"],
            "heap_free_bytes": run["metrics_after"]["heap_free"],
            "heap_min_free_bytes": run["metrics_after"]["heap_min_free"],
            "buzzer_inactive": True,
            "final_page": run["cleanup_after"]["final_state"]["page"],
            "final_runtime_owner":
                run["cleanup_after"]["final_state"]["runtime_owner"],
            "final_lease_mask": 0,
        },
    }
    write(summary, summary_value)
    print(json.dumps({"status": "retained", "files": len(indexed) + 1,
                      "tft_states": len(run.get("screens", {}))},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
