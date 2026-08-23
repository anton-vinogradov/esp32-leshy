#!/usr/bin/env python3
"""Retain exact physical evidence for mean-based Wi-Fi channel choice."""

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
VERSION = "0.116.0-wifi-channel-average"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-116", "E-AUTO-080", "E-HIL-140", "E-UX-035"]
SOURCE_FILES = {
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "load_h": "firmware/leshy1/src/apps/wifi/WifiChannelLoad.h",
    "load_cpp": "firmware/leshy1/src/apps/wifi/WifiChannelLoad.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "contract": "tools/check_wifi_channels_contract.py",
}


def verify_average(run: dict[str, Any]) -> None:
    first = run.get("live_first", {})
    second = run.get("live_second", {})
    gray = run.get("average_gray_pixels", {})
    scope = run.get("scope", {})
    require(first.get("wifi_channel_completed_sweeps", 0) >= 2 and
            second.get("wifi_channel_completed_sweeps", 0) >
            first.get("wifi_channel_completed_sweeps", 0),
            "at least two per-channel samples were not proven")
    require(gray.get("first", 0) > 0 and gray.get("second", 0) > 0,
            "gray session-average bars are not visible")
    require(scope.get("average_load_rendered_gray") is True and
            scope.get("recommendation_uses_session_average") is True and
            scope.get("minimum_average_dwells_per_channel") == 2,
            "mean display/recommendation scope missing")


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
    runner = ROOT / "tools/run_1x_wifi_channels_hil.py"
    checker = ROOT / "tools/check_wifi_channels_run.py"
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
    require(run.get("schema") == "leshy.wifi_channels_hil.run.v2" and
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
    verify_average(run)
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
        "schema": "leshy.wifi_channel_average_hil.provenance.v1",
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

    summary_value = {
        "schema": "leshy.wifi_channel_average.acceptance.v1",
        "status": "pass_mean_based_wifi_channel_choice",
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
            "channels_measured": list(range(1, 14)),
            "first_sweeps": run["live_first"]["wifi_channel_completed_sweeps"],
            "second_sweeps": run["live_second"]["wifi_channel_completed_sweeps"],
            "first_frames": run["live_first"]["wifi_channel_frames_reported"],
            "second_frames": run["live_second"]["wifi_channel_frames_reported"],
            "best_primary_first": run["live_first"]["wifi_channel_best_primary"],
            "best_primary_second": run["live_second"]["wifi_channel_best_primary"],
            "average_gray_pixels_first": run["average_gray_pixels"]["first"],
            "average_gray_pixels_second": run["average_gray_pixels"]["second"],
            "recommendation_uses_session_average": True,
            "instantaneous_load_remains_visible": True,
            "dynamic_changed_pixels": run["pixel_changes"]["dynamic_changed_pixels"],
            "static_changed_pixels": 0,
            "two_complete_wifi_lifecycles": True,
            "zero_heap_drift_after_warmup": True,
            "heap_minimum_floor_bytes": min(
                run["metrics_after_first"]["heap_min_free"],
                run["metrics_after"]["heap_min_free"]),
            "physical_sd_write_calls": 0,
            "buzzer_inactive": True,
            "final_lease_mask": 0,
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "retained", "files": len(indexed) + 1,
        "tft_states": provenance["tft_states"],
        "average_gray_pixels": run["average_gray_pixels"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
