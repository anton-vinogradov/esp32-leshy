#!/usr/bin/env python3
"""Retain exact physical evidence for passive Wi-Fi device intelligence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import digest, load, require, write


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.115.0-wifi-device-intelligence"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-115", "E-AUTO-079", "E-HIL-139", "E-UX-034"]
SOURCE_FILES = {
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "catalog_h": "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.h",
    "catalog_cpp": "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.cpp",
    "navigation": "firmware/leshy1/src/apps/wifi/WifiDeviceNavigationOrder.h",
    "oui_h": "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.h",
    "oui_cpp": "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.cpp",
    "oui_metadata": "firmware/leshy1/assets/oui.json",
    "oui_generator": "tools/make_wifi_oui_asset.py",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "contract": "tools/check_wifi_devices_contract.py",
}


def verify_intelligence(run: dict[str, Any]) -> None:
    detail_first = run.get("detail_first", {})
    detail_second = run.get("detail_second", {})
    radar_first = run.get("radar_first", {})
    radar_second = run.get("radar_second", {})
    require(detail_first.get("wifi_device_oui_database_available") is True and
            detail_first.get("wifi_device_oui_records") == 39984 and
            detail_first.get("wifi_device_navigation_locked") is True,
            "device intelligence/OUI/navigation state missing")
    require(detail_second.get("wifi_device_order_hash") ==
            detail_first.get("wifi_device_order_hash") and
            detail_second.get("wifi_device_selection") ==
            detail_first.get("wifi_device_selection"),
            "device identity changed behind passport")
    require(radar_first.get("wifi_device_channel_locked") is True and
            radar_second.get("wifi_device_channel_locked") is True and
            radar_second.get("wifi_device_channel_hops") ==
            radar_first.get("wifi_device_channel_hops") and
            radar_second.get("wifi_device_detail_last_seen_us", 0) >
            radar_first.get("wifi_device_detail_last_seen_us", 0) and
            radar_second.get("wifi_device_clients_accepted", 0) >
            radar_first.get("wifi_device_clients_accepted", 0),
            "selected-channel radar did not receive the selected client")


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
    runner = ROOT / "tools/run_1x_wifi_devices_hil.py"
    checker = ROOT / "tools/check_wifi_devices_run.py"
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40, "commits must be full IDs")
    for artifact in (
            source / "run.json", source / "firmware.bin",
            source / "artifacts.sha256", runner, checker,
            args.factory.resolve(), args.elf.resolve(), args.map.resolve()):
        require(artifact.is_file(), f"artifact missing: {artifact}")

    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_devices_hil.run.v2" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], "source run is not a clean v2 pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flashed") is True and
            run.get("expected_cid") == CID,
            "exact fresh-flash candidate binding mismatch")
    require(run.get("runner_source_sha256") == digest(runner),
            "runner source hash mismatch")
    verify_intelligence(run)
    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", args.firmware_source_commit],
        cwd=ROOT, text=True, env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"independent run check failed: {checked.stdout}")

    destination.mkdir(parents=True)
    shutil.copytree(source, destination / "run")
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    shutil.copy2(runner, tools_dir / runner.name)
    shutil.copy2(checker, tools_dir / checker.name)
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        original = ROOT / relative
        target = source_dir / Path(relative).name
        shutil.copy2(original, target)
        source_hashes[label] = digest(target)
    for artifact, name in (
        (args.factory.resolve(), "firmware.factory.bin"),
        (args.elf.resolve(), "firmware.elf"),
        (args.map.resolve(), "firmware.map"),
    ):
        shutil.copy2(artifact, destination / name)

    firmware = destination / "run/firmware.bin"
    provenance = {
        "schema": "leshy.wifi_device_intelligence_hil.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(firmware),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "app_image_bytes": firmware.stat().st_size,
        "factory_image_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "oui_records": run["detail_first"]["wifi_device_oui_records"],
        "runner_sha256": digest(tools_dir / runner.name),
        "checker_sha256": digest(tools_dir / checker.name),
        "source_sha256": source_hashes,
        "run_sha256": digest(destination / "run/run.json"),
        "tft_states": len(run.get("screens", {})),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    first = run["live_first"]
    second = run["live_second"]
    detail_first = run["detail_first"]
    detail_second = run["detail_second"]
    radar_first = run["radar_first"]
    radar_second = run["radar_second"]
    summary_value = {
        "schema": "leshy.wifi_device_intelligence.acceptance.v1",
        "status": "pass_passive_wifi_device_intelligence",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": provenance["tft_states"],
        },
        "verified": {
            "fresh_flashes": 1,
            "manual_button_presses": 0,
            "unique_devices_first": first["wifi_devices_unique"],
            "unique_devices_second": second["wifi_devices_unique"],
            "client_frames_accepted_second": second["wifi_device_clients_accepted"],
            "channel_hops_second": second["wifi_device_channel_hops"],
            "client_frames_dropped": 0,
            "embedded_ieee_oui_records": 39984,
            "passive_probe_association_wps_fingerprint": True,
            "private_mac_reported_honestly": True,
            "identity_stable_navigation": True,
            "selected_order_hash_stable": (
                detail_first["wifi_device_order_hash"] ==
                detail_second["wifi_device_order_hash"]),
            "selected_index_stable": (
                detail_first["wifi_device_selection"] ==
                detail_second["wifi_device_selection"]),
            "channel_locked_radar": True,
            "radar_channel": radar_first["wifi_device_current_channel"],
            "radar_client_updates": (
                radar_second["wifi_device_clients_accepted"] -
                radar_first["wifi_device_clients_accepted"]),
            "radar_last_seen_advanced": True,
            "list_content_changed_pixels": run["list_pixel_changes"][
                "content_changed_pixels"],
            "radar_content_changed_pixels": run["radar_pixel_changes"][
                "content_changed_pixels"],
            "live_chrome_changed_pixels": 0,
            "detail_changed_pixels": 0,
            "two_complete_wifi_lifecycles": True,
            "zero_heap_drift_after_warmup": True,
            "physical_sd_write_calls": 0,
            "buzzer_inactive": True,
            "final_lease_mask": 0,
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "retained", "files": len(indexed) + 1,
        "tft_states": provenance["tft_states"],
        "unique_devices": second["wifi_devices_unique"],
        "oui_records": provenance["oui_records"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
