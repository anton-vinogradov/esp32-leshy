#!/usr/bin/env python3
"""Retain one exact-flash, three-radio descending-signal HIL checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.112.0-signal-order"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-112", "E-AUTO-076", "E-HIL-136", "E-UX-031"]
RADIOS = {
    "ble": ("run_1x_ble_nearby_hil.py", "check_ble_nearby_run.py"),
    "wifi-networks": (
        "run_1x_wifi_networks_hil.py", "check_wifi_networks_run.py"),
    "wifi-devices": (
        "run_1x_wifi_devices_hil.py", "check_wifi_devices_run.py"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_run(source: Path, checker: Path, source_commit: str) -> dict[str, Any]:
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], f"{source.name}: run is not a pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == source_commit and
            run.get("expected_cid") == CID,
            f"{source.name}: exact candidate binding mismatch")
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

    runs: dict[str, dict[str, Any]] = {}
    for radio, (_, checker_name) in RADIOS.items():
        runs[radio] = verify_run(
            sources[radio], ROOT / "tools" / checker_name,
            args.firmware_source_commit)
    modes = [runs[radio]["candidate"]["flash_mode"] for radio in RADIOS]
    require(modes == ["fresh", "reuse_exact", "reuse_exact"],
            f"one-flash sequence mismatch: {modes}")
    firmware_hashes = {
        run["candidate"]["firmware_sha256"] for run in runs.values()}
    app_hashes = {
        run["candidate"]["app_elf_sha256"] for run in runs.values()}
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

    ble_run = runs["ble"]
    network_run = runs["wifi-networks"]
    device_run = runs["wifi-devices"]
    firmware = sources["ble"] / "firmware.bin"
    provenance = {
        "schema": "leshy.signal_order_hil.provenance.v1",
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
        "schema": "leshy.signal_order.acceptance.v1",
        "status": "pass_descending_signal_checkpoint",
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
            "ble_unique_first": ble_run["live_first"]["ble_devices_unique"],
            "ble_unique_second": ble_run["live_second"]["ble_devices_unique"],
            "wifi_networks_unique_first": network_run["live_first"]["wifi_networks_unique"],
            "wifi_networks_unique_second": network_run["live_second"]["wifi_networks_unique"],
            "wifi_devices_unique_first": device_run["live_first"]["wifi_devices_unique"],
            "wifi_devices_unique_second": device_run["live_second"]["wifi_devices_unique"],
            "ble_strongest_first": True,
            "wifi_networks_strongest_first": True,
            "wifi_devices_strongest_first": True,
            "stable_equal_signal_order": True,
            "selection_anchored_to_identity": True,
            "radio_drops": 0,
            "live_chrome_changed_pixels": 0,
            "detail_changed_pixels": 0,
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
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
