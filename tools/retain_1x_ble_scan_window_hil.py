#!/usr/bin/env python3
"""Validate and retain exact BLE scan-window/re-entry HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.343"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "a6617692d32913b281e23950831fdee53894b0e3"
FIRMWARE_SHA256 = (
    "ecc5d198cce1a2ccf5a2898f8f0b1f1976ab523791f79ba573fad7a4f97a1f97")
APP_ELF_SHA256 = (
    "abe53484218146b6cd9f4aa9329202cd418313b842490889d6ec254ef116a2d6")
FACTORY_SHA256 = (
    "b8097fda6cea90a910456c91332dd2f8cefcbf39f3337e96cfb90793264c80cd")
MAP_SHA256 = (
    "5c31aa7f7b1569f6168d9d3ae69531629ad99f5fc87d8892cf3089f9c51666bd")
EVIDENCE_IDS = ["E-BUILD-222", "E-AUTO-198", "E-HIL-226"]
SOURCE_FILES = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp",
    "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.h",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    map_file = args.map.resolve()
    runner = ROOT / "tools/run_1x_ble_nearby_hil.py"
    checker = ROOT / "tools/check_ble_nearby_run.py"
    source_guard = ROOT / "tools/check_ble_nearby_contract.py"

    require(source.is_dir() and not source.is_symlink(),
            "regular source directory required")
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(destination.parent == summary.parent,
            "destination and summary must share a parent")
    for item in source.rglob("*"):
        require(not item.is_symlink(), f"symlink rejected: {item}")
    for required in (source / "run.json", source / "firmware.bin",
                     source / "artifacts.sha256", factory, elf, map_file,
                     runner, checker, source_guard):
        require(required.is_file(), f"missing artifact: {required}")

    require(digest(source / "firmware.bin") == FIRMWARE_SHA256,
            "firmware hash mismatch")
    require(digest(factory) == FACTORY_SHA256, "factory hash mismatch")
    require(digest(elf) == APP_ELF_SHA256, "ELF hash mismatch")
    require(digest(map_file) == MAP_SHA256, "map hash mismatch")
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.ble_nearby_hil.run.v2" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == APP_ELF_SHA256 and
            candidate.get("flash_mode") == "fresh" and
            run.get("expected_cid") == CID,
            "exact candidate binding mismatch")

    environment = dict(os.environ, PYTHONPATH=str(ROOT / "tools"))
    for command in (
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT],
        [sys.executable, str(source_guard)],
    ):
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        require(result.returncode == 0, result.stdout.strip())

    scope = run["scope"]
    cadence = run["list_cadence_window"]
    list_first = run["list_render_first"]
    list_second = run["list_render_second"]
    detail = run["detail_stability_window"]
    pixels = run["detail_pixel_changes"]
    final = run["cleanup_after"]["final_state"]
    recovery_before = run["recovery_before"]
    recovery_after = run["recovery_after"]

    require(scope.get("passive_ble_only") is True and
            scope.get("active_scan") is False and
            scope.get("manual_button_presses") == 0 and
            scope.get("single_flash") is True and
            scope.get("two_complete_ble_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "passive two-lifecycle scope proof missing")
    require(cadence.get("elapsed_ms", 0) >= 2000 and
            0 < cadence.get("refreshes", 0) <=
                cadence.get("maximum_refreshes", 0) and
            cadence.get("content_clears") == 0 and
            cadence.get("refreshes_deferred", 0) > 0,
            "scan-window list cadence proof missing")
    require(list_second["list_content_clears"] ==
                list_first["list_content_clears"] and
            list_second["list_row_full_repaints"] ==
                list_first["list_row_full_repaints"] and
            list_second["list_signal_delta_repaints"] >
                list_first["list_signal_delta_repaints"],
            "changed-signal-only list proof missing")
    require(detail.get("scan_cycles", 0) >= 2 and
            detail.get("content_clears") == 0 and
            detail.get("radar_full_repaints") == 0 and
            pixels.get("radar_changed_pixels", 0) > 0 and
            pixels.get("static_changed_pixels") == 0 and
            pixels.get("chrome_changed_pixels") == 0,
            "stable detail/radar proof missing")
    require(run["metrics_after_first"]["heap_free"] ==
                run["metrics_after"]["heap_free"] and
            final["ble_begin_stage"] == "ready" and
            final["ble_begin_error"] == 0 and
            final["ble_begin_heap_free_before"] >= 73000 and
            final["ble_begin_heap_largest_before"] >= 28000,
            "BLE teardown/re-entry contiguous-headroom proof missing")
    require(run["cleanup_after"]["complete"] is True and
            final["page"] == "home" and
            final["runtime_owner"] == "none" and
            final["lease_mask"] == 0,
            "final cleanup mismatch")
    require(recovery_before == recovery_after and
            recovery_after["generation"] == 8 and
            recovery_after["observations"] == 54 and
            recovery_after["physical_write_calls"] == 0 and
            recovery_after["blocked_write_attempts"] == 0 and
            recovery_after["owned_after"] == 0,
            "read-only storage continuity mismatch")

    parent = destination.parent
    staging = Path(tempfile.mkdtemp(prefix=".ble-scan-window-retain-",
                                    dir=parent))
    staged_bundle = staging / destination.name
    staged_summary = staging / summary.name
    try:
        shutil.copytree(source, staged_bundle, copy_function=shutil.copy2)
        for tool, name in ((runner, "runner.py"), (checker, "checker.py"),
                           (source_guard, "source-guard.py")):
            shutil.copy2(tool, staged_bundle / name)
        for artifact, name in ((factory, "firmware.factory.bin"),
                               (elf, "firmware.elf"),
                               (map_file, "firmware.map")):
            shutil.copy2(artifact, staged_bundle / name)
        source_dir = staged_bundle / "source"
        source_dir.mkdir()
        for relative in SOURCE_FILES:
            original = ROOT / relative
            shutil.copy2(original, source_dir / original.name)

        indexed = sorted(path for path in staged_bundle.rglob("*")
                         if path.is_file() and
                         path.name != "artifacts.sha256")
        manifest = staged_bundle / "artifacts.sha256"
        manifest.write_text("".join(
            f"{digest(path)}  {path.relative_to(staged_bundle)}\n"
            for path in indexed), encoding="utf-8")
        summary_value = {
            "schema": "leshy.ble_scan_window_hil.acceptance.v1",
            "status": "pass_bluetooth_scan_window_and_reentry",
            "board": "board-01",
            "evidence_ids": EVIDENCE_IDS,
            "exact_cid": CID,
            "candidate": {
                "version": VERSION,
                "source_commit": SOURCE_COMMIT,
                "firmware_sha256": FIRMWARE_SHA256,
                "app_elf_sha256": APP_ELF_SHA256,
                "factory_sha256": FACTORY_SHA256,
                "map_sha256": MAP_SHA256,
                "static_ram_bytes": 233592,
                "linked_flash_bytes": 3600812,
            },
            "evidence": {
                "run_id": run["run_id"],
                "run_sha256": digest(staged_bundle / "run.json"),
                "artifact_index_sha256": digest(manifest),
            },
            "verified": {
                "list_window_elapsed_ms": cadence["elapsed_ms"],
                "list_window_refreshes": cadence["refreshes"],
                "list_window_deferred": cadence["refreshes_deferred"],
                "list_window_content_clears": 0,
                "list_full_row_repaints": 0,
                "list_signal_delta_repaints":
                    list_second["list_signal_delta_repaints"] -
                    list_first["list_signal_delta_repaints"],
                "detail_scan_cycles": detail["scan_cycles"],
                "detail_refreshes": detail["refreshes"],
                "detail_deferred": detail["refreshes_deferred"],
                "detail_content_clears": 0,
                "detail_full_repaints": 0,
                "detail_radar_changed_pixels":
                    pixels["radar_changed_pixels"],
                "detail_static_changed_pixels": 0,
                "detail_chrome_changed_pixels": 0,
                "two_complete_ble_lifecycles": True,
                "reentry_heap_free": final["ble_begin_heap_free_before"],
                "reentry_heap_largest":
                    final["ble_begin_heap_largest_before"],
                "warm_heap_free_first":
                    run["metrics_after_first"]["heap_free"],
                "warm_heap_free_second": run["metrics_after"]["heap_free"],
                "physical_storage_writes": 0,
                "passive_only": True,
                "active_scan": False,
                "manual_button_presses": 0,
                "human_visual_acceptance": False,
                "final_page": "home",
                "final_runtime_owner": "none",
                "final_lease_mask": 0,
            },
        }
        write(staged_summary, summary_value)
        staged_bundle.replace(destination)
        staged_summary.replace(summary)
        shutil.rmtree(staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(json.dumps({"status": "retained",
                      "destination": str(destination),
                      "summary": str(summary)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
