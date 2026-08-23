#!/usr/bin/env python3
"""Verify retained board-01 mean-based Wi-Fi channel evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-channel-average-0.116"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-channel-average-0.116.json"
VERSION = "0.116.0-wifi-channel-average"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "fd099cd2107cf0cdc2ab0bfd0af18512cae937d6"
FIRMWARE_SHA256 = "1819e58121fa7c8f8938a63a08eafb7e17f6a83b3132eb735a6291866955c36f"
FACTORY_SHA256 = "276f7507bd8ca03c7d1c6eb0980d604e8955a0302cc8c7e3f0f2281ccee48a90"
ELF_SHA256 = "88a060291d092c9746f2485107432bc42a548d9fb48a1549e39f46b2e3988c70"
MAP_SHA256 = "20632c2545d0759258e4d0bfb19422b1de67e80eef4e503cc57a86e24b951a96"
EVIDENCE_IDS = {"E-BUILD-116", "E-AUTO-080", "E-HIL-140", "E-UX-035"}
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    indexed_present: set[Path] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        artifact = root / relative
        if not artifact.is_file():
            require(relative.endswith(OPAQUE_SUFFIXES),
                    f"tracked artifact missing: {relative}")
            continue
        require(digest(artifact) == expected,
                f"artifact hash mismatch: {relative}")
        indexed_present.add(Path(relative))
    present = {
        path.relative_to(root) for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed_present == present, "artifact index coverage mismatch")


def verify_source(provenance: dict[str, Any]) -> None:
    source = BUNDLE / "source"
    files = {
        "renderer": source / "ArduinoEntry.cpp",
        "load_h": source / "WifiChannelLoad.h",
        "load_cpp": source / "WifiChannelLoad.cpp",
        "strings": source / "UiStrings.def",
        "native_tests": source / "clean_target_tests.cpp",
        "contract": source / "check_wifi_channels_contract.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    renderer = files["renderer"].read_text(encoding="utf-8")
    load_h = files["load_h"].read_text(encoding="utf-8")
    load_cpp = files["load_cpp"].read_text(encoding="utf-8")
    strings = files["strings"].read_text(encoding="utf-8")
    native = files["native_tests"].read_text(encoding="utf-8")
    for token in (
            "kWifiChannelAverageTone", "wifiChannelRenderedAverages",
            "kWifiChannelCurrentBarWidth", "bin.averageBusyPermille"):
        require(token in renderer, f"average renderer contract missing: {token}")
    for token in ("averageBusyPermille", "cumulativeBusyPermille_", "dwells"):
        require(token in load_h + load_cpp,
                f"average aggregation contract missing: {token}")
    require("snapshot_.channels[index(candidate)].averageBusyPermille" in load_cpp,
            "free-channel recommendation does not use the average")
    require("WifiChannelsAverageLegend" in strings and "СРЕД" in strings,
            "gray-average legend missing")
    require("CHECK(load.bestPrimaryChannel() == 11);" in native and
            "averageBusyPermille == 44" in native,
            "instantaneous-versus-average regression missing")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_channel_average.acceptance.v1" and
            summary.get("status") == "pass_mean_based_wifi_channel_choice",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_channel_average_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == SOURCE_COMMIT,
            "candidate provenance mismatch")
    require(provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("app_image_bytes") == 2875296 and
            provenance.get("factory_image_bytes") == 2940832 and
            provenance.get("static_ram_bytes") == 198800 and
            provenance.get("linked_flash_bytes") == 2874896 and
            provenance.get("tft_states") == 4,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)

    run = load(BUNDLE / "run/run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_channels_hil.run.v2" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID,
            "run status mismatch")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == ELF_SHA256 and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flashed") is True,
            "exact fresh-flash binding mismatch")
    firmware = BUNDLE / "run/firmware.bin"
    if firmware.is_file():
        require(digest(firmware) == FIRMWARE_SHA256,
                "retained firmware mismatch")
    runner = BUNDLE / "tools/run_1x_wifi_channels_hil.py"
    checker = BUNDLE / "tools/check_wifi_channels_run.py"
    require(digest(runner) == provenance["runner_sha256"] ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance["checker_sha256"],
            "checker hash mismatch")
    if firmware.is_file():
        checked = subprocess.run(
            [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        require(checked.returncode == 0,
                f"independent retained run check failed: {checked.stdout}")

    require(summary.get("verified") == {
        "average_gray_pixels_first": 691,
        "average_gray_pixels_second": 680,
        "best_primary_first": 11,
        "best_primary_second": 11,
        "buzzer_inactive": True,
        "channels_measured": list(range(1, 14)),
        "dynamic_changed_pixels": 509,
        "final_lease_mask": 0,
        "first_frames": 61,
        "first_sweeps": 2,
        "fresh_flashes": 1,
        "heap_minimum_floor_bytes": 54724,
        "instantaneous_load_remains_visible": True,
        "manual_button_presses": 0,
        "physical_sd_write_calls": 0,
        "recommendation_uses_session_average": True,
        "second_frames": 109,
        "second_sweeps": 3,
        "static_changed_pixels": 0,
        "two_complete_wifi_lifecycles": True,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Wi-Fi channel-average acceptance passed: gray session mean, "
        "mean-based 1/6/11 choice, live-only redraw and final lease 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
