#!/usr/bin/env python3
"""Retain one exact-flash, three-radio dense-detail HIL checkpoint."""

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
VERSION = "0.113.0-dense-details"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-113", "E-AUTO-077", "E-HIL-137", "E-UX-032"]
RADIOS = {
    "ble": ("run_1x_ble_nearby_hil.py", "check_ble_nearby_run.py"),
    "wifi-networks": (
        "run_1x_wifi_networks_hil.py", "check_wifi_networks_run.py"),
    "wifi-devices": (
        "run_1x_wifi_devices_hil.py", "check_wifi_devices_run.py"),
}
SOURCE_FILES = {
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "content_guard": "tools/check_product_ui_content.py",
    "ble_guard": "tools/check_ble_nearby_contract.py",
    "wifi_networks_guard": "tools/check_wifi_networks_contract.py",
    "wifi_devices_guard": "tools/check_wifi_devices_contract.py",
}


def verify_run(source: Path, checker: Path, source_commit: str) -> dict[str, Any]:
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], f"{source.name}: run is not a pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == source_commit and
            run.get("expected_cid") == CID,
            f"{source.name}: exact candidate binding mismatch")
    require(run.get("detail_pixel_changes") == {
        "content_changed_pixels": 0, "chrome_changed_pixels": 0},
        f"{source.name}: open detail is not pixel-stable")
    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", source_commit], cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"{source.name}: independent check failed: {checked.stdout}")
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ble-source", required=True, type=Path)
    parser.add_argument("--wifi-networks-source", required=True, type=Path)
    parser.add_argument("--wifi-devices-source", required=True, type=Path)
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

    destination = args.destination.resolve()
    summary = args.summary.resolve()
    sources = {
        "ble": args.ble_source.resolve(),
        "wifi-networks": args.wifi_networks_source.resolve(),
        "wifi-devices": args.wifi_devices_source.resolve(),
    }
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40, "commits must be full IDs")
    for source in sources.values():
        require((source / "run.json").is_file() and
                (source / "firmware.bin").is_file(),
                f"source run missing: {source}")
    for build in (args.factory, args.elf, args.map):
        require(build.resolve().is_file(), f"build artifact missing: {build}")

    runs = {
        radio: verify_run(sources[radio], ROOT / "tools" / checker,
                          args.firmware_source_commit)
        for radio, (_, checker) in RADIOS.items()
    }
    modes = [runs[radio]["candidate"]["flash_mode"] for radio in RADIOS]
    require(modes == ["fresh", "reuse_exact", "reuse_exact"],
            f"one-flash sequence mismatch: {modes}")
    firmware_hashes = {
        run["candidate"]["firmware_sha256"] for run in runs.values()}
    app_hashes = {run["candidate"]["app_elf_sha256"] for run in runs.values()}
    require(len(firmware_hashes) == 1 and len(app_hashes) == 1,
            "radio runs do not bind the same exact candidate")

    destination.mkdir(parents=True)
    for radio, source in sources.items():
        shutil.copytree(source, destination / radio)
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    runner_hashes: dict[str, str] = {}
    checker_hashes: dict[str, str] = {}
    for radio, (runner_name, checker_name) in RADIOS.items():
        runner = ROOT / "tools" / runner_name
        checker = ROOT / "tools" / checker_name
        shutil.copy2(runner, tools_dir / runner_name)
        shutil.copy2(checker, tools_dir / checker_name)
        runner_hashes[radio] = digest(tools_dir / runner_name)
        checker_hashes[radio] = digest(tools_dir / checker_name)
        require(runs[radio].get("runner_source_sha256") == runner_hashes[radio],
                f"{radio}: runner source hash mismatch")
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        source = ROOT / relative
        target = source_dir / Path(relative).name
        shutil.copy2(source, target)
        source_hashes[label] = digest(target)

    firmware = sources["ble"] / "firmware.bin"
    provenance = {
        "schema": "leshy.dense_details_hil.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(firmware),
        "factory_sha256": digest(args.factory.resolve()),
        "elf_file_sha256": digest(args.elf.resolve()),
        "map_sha256": digest(args.map.resolve()),
        "app_elf_sha256": next(iter(app_hashes)),
        "app_image_bytes": firmware.stat().st_size,
        "factory_image_bytes": args.factory.resolve().stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "runner_sha256": runner_hashes,
        "checker_sha256": checker_hashes,
        "source_sha256": source_hashes,
        "run_sha256": {
            radio: digest(destination / radio / "run.json") for radio in RADIOS
        },
        "tft_states": sum(len(run.get("screens", {})) for run in runs.values()),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    summary_value = {
        "schema": "leshy.dense_details.acceptance.v1",
        "status": "pass_dense_radio_details_checkpoint",
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
            "exact_flash_reuse_runs": 2,
            "manual_button_presses": 0,
            "dense_detail_screens": 3,
            "shared_signal_card": True,
            "qualitative_signal": True,
            "numeric_dbm": True,
            "channel_or_passive_context": True,
            "implementation_counters_visible": 0,
            "detail_changed_pixels": 0,
            "live_chrome_changed_pixels": 0,
            "zero_heap_drift_after_warmup": True,
            "radio_drops": 0,
            "physical_sd_write_calls": 0,
            "buzzer_inactive": True,
            "final_lease_mask": 0,
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "retained", "files": len(indexed) + 1,
        "tft_states": provenance["tft_states"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
