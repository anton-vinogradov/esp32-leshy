#!/usr/bin/env python3
"""Validate a BLE Inspector run and retain a privacy-minimal acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.270"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "cd542afac79f696a2cdcf3d7abe4bd18f3bc4a82"
FIRMWARE_SHA256 = (
    "b4a97811ec6b36fd623e471e866b69dc2659a49c1dab6934c1b35dc156cb4c37")
APP_ELF_SHA256 = (
    "ea4321b7ff7e5ca31b1f58183fe821e18baa358e948d9fda90e50214ed848d62")
FACTORY_SHA256 = (
    "b504f9e68006bc0c4c26b29575fca771006a44b928da652f8ea5b3f1113d1b47")
MAP_SHA256 = (
    "db96451afd033fb264826ba413df4d70d276bb63fe0db010606cf7e01a094d7b")
EVIDENCE_IDS = ["E-BUILD-190", "E-AUTO-165", "E-HIL-203", "E-UX-060",
                "RB-M201"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    factory = args.factory.resolve()
    map_file = args.map.resolve()
    require(source.is_dir() and not source.is_symlink(),
            "regular source directory required")
    require(not destination.exists(), "destination must not exist")
    require(factory.is_file() and digest(factory) == FACTORY_SHA256,
            "factory hash mismatch")
    require(map_file.is_file() and digest(map_file) == MAP_SHA256,
            "map hash mismatch")
    checker = ROOT / "tools/check_ble_inspector_run.py"
    source_guard = ROOT / "tools/check_ble_inspector_contract.py"
    runner = ROOT / "tools/run_1x_ble_inspector_hil.py"
    for required in (checker, source_guard, runner, source / "run.json",
                     source / "firmware.bin", source / "artifacts.sha256"):
        require(required.is_file(), f"missing artifact: {required}")
    require(digest(source / "firmware.bin") == FIRMWARE_SHA256,
            "firmware hash mismatch")
    env = {"PYTHONPATH": str(ROOT / "tools")}
    for command in (
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT],
        [sys.executable, str(source_guard)],
    ):
        result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        require(result.returncode == 0, result.stdout.strip())

    run = load(source / "run.json")
    candidate = run["candidate"]
    require(candidate["firmware_sha256"] == FIRMWARE_SHA256 and
            candidate["app_elf_sha256"] == APP_ELF_SHA256,
            "exact candidate identity mismatch")
    frozen = run["frozen"]
    export = run["export"]
    stability = run["entry_stability"]
    final_state = run["cleanup"]["final_state"]
    screenshots = {
        label: {
            "png_sha256": value["png_sha256"],
            "rgb565_sha256": value["rgb565_sha256"],
        }
        for label, value in sorted(run["screens"].items())
    }
    summary = {
        "schema": "leshy.ble_inspector_hil.acceptance.v1",
        "status": "pass_ble_inspector_receive_capture",
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
        },
        "evidence": {
            "run_id": run["run_id"],
            "raw_run_sha256": digest(source / "run.json"),
            "raw_artifact_index_sha256": digest(
                source / "artifacts.sha256"),
            "runner_sha256": digest(runner),
            "checker_sha256": digest(checker),
            "source_guard_sha256": digest(source_guard),
            "screenshots": screenshots,
        },
        "verified": {
            "preflight_before_flash": True,
            "single_application_flash": True,
            "boot_heap_total": run["boot"]["heap_total"],
            "boot_heap_free": run["boot"]["heap_free"],
            "entry_stability_ms": stability["duration_ms"],
            "entry_stability_samples": stability["samples"],
            "entry_scan_cycles": stability["final_state"]
                ["survey_product_ble_scan_cycles"],
            "ble_begin_stage": "ready",
            "ble_begin_error": 0,
            "selected_target_stable": True,
            "records": frozen["records"],
            "payload_bytes": export["payload_bytes"],
            "content_clears": frozen["content_clears"],
            "atomic_row_pushes": frozen["atomic_row_pushes"],
            "atomic_row_allocation_failures": 0,
            "direct_row_fallbacks": 0,
            "invalid_records": 0,
            "dropped_records": 0,
            "gatt_started": False,
            "passive_only": True,
            "receive_only": True,
            "export_complete": True,
            "export_stream_sha256": export["stream_sha256"],
            "input_read_errors": 0,
            "input_queue_drops": 0,
            "buzzer_inactive": True,
            "final_page": final_state["page"],
            "final_runtime_owner": final_state["runtime_owner"],
            "final_lease_mask": final_state["lease_mask"],
            "final_safety_state": final_state["safety_state"],
        },
        "privacy": {
            "raw_ble_addresses_retained": False,
            "raw_payload_retained": False,
            "screenshots_retained": False,
            "screenshot_hashes_retained": True,
        },
        "scope": run["scope"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) +
                           "\n", encoding="utf-8")
    print(json.dumps({"status": "retained",
                      "destination": str(destination)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
