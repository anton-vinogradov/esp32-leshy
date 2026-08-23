#!/usr/bin/env python3
"""Verify retained board-01 all-channel Wi-Fi choice evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-channel-choice-0.120"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-channel-choice-0.120.json"
VERSION = "0.120.0-wifi-channel-choice"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "7b0b85cce3faa4fdb41f3f034ec29f11ce3860a1"
FIRMWARE_SHA256 = "c35350fc51638ffd8a855f2f7593a0b2bc9765893ba67365d8f39259108a085e"
FACTORY_SHA256 = "bcc017716ca2b74762be3f7408d6ca8624ec32f28eff56070e34a876a29771b7"
ELF_SHA256 = "d6c8fbcea09e2fe93c24749c4ee7ce5a17024d0bae815de1f410f40e6b487fd5"
MAP_SHA256 = "57db3be2a601d4db91d349007b11dc919c9c2aa918ef0bb9fe94b7c7a044fb9c"
EVIDENCE_IDS = {"E-BUILD-120", "E-AUTO-084", "E-HIL-144", "E-UX-039"}
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
    load_cpp = files["load_cpp"].read_text(encoding="utf-8")
    strings = files["strings"].read_text(encoding="utf-8")
    native = files["native_tests"].read_text(encoding="utf-8")
    for token in (
            "required = (1U << kLastChannel) - 1U",
            "candidateMean < bestMean",
            "candidateMean == bestMean && candidatePressure < bestPressure"):
        require(token in load_cpp, f"all-channel ranking token missing: {token}")
    require("renderWifiChannelAxisLabel(best, Palette::Focus)" in renderer,
            "recommended channel highlight missing")
    require('"FREER: %u"' in strings and "СВОБОДНЕЕ: %u" in strings,
            "unrestricted recommendation label missing")
    require("CHECK(load.bestPrimaryChannel() == 13);" in native and
            "adjacent-channel pressure" in native,
            "12/13 recommendation regression missing")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_channel_choice.acceptance.v1" and
            summary.get("status") == "pass_all_channel_wifi_choice",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_channel_choice_hil.provenance.v1" and
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
            provenance.get("app_image_bytes") == 2892048 and
            provenance.get("factory_image_bytes") == 2957584 and
            provenance.get("static_ram_bytes") == 209464 and
            provenance.get("linked_flash_bytes") == 2891648 and
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
    runner = BUNDLE / "tools/run_1x_wifi_channels_hil.py"
    checker = BUNDLE / "tools/check_wifi_channels_run.py"
    require(digest(runner) == provenance["runner_sha256"] ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance["checker_sha256"],
            "checker hash mismatch")
    if (BUNDLE / "run/firmware.bin").is_file():
        checked = subprocess.run(
            [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        require(checked.returncode == 0,
                f"independent retained run check failed: {checked.stdout}")

    require(summary.get("verified") == {
        "adjacent_overlap_tie_break": True,
        "average_gray_pixels_first": 1102,
        "average_gray_pixels_second": 1108,
        "best_channel_first": 13,
        "best_channel_second": 13,
        "buzzer_inactive": True,
        "channels_measured": list(range(1, 14)),
        "dynamic_changed_pixels": 1195,
        "final_lease_mask": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "first_frames": 95,
        "first_sweeps": 2,
        "fresh_flashes": 1,
        "heap_free_bytes": 104460,
        "heap_min_free_bytes": 40464,
        "heap_total_bytes": 171988,
        "library_generation": 95,
        "library_observations": 0,
        "manual_button_presses": 0,
        "physical_sd_write_calls": 0,
        "recommended_axis_label_highlighted": True,
        "second_frames": 158,
        "second_sweeps": 3,
        "static_changed_pixels": 0,
        "visible_session_average_primary": True,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Wi-Fi channel-choice acceptance passed: all 13 visible means, "
        "channel 13 selected, highlighted axis and final lease 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
