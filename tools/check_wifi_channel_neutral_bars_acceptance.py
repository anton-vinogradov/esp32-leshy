#!/usr/bin/env python3
"""Verify retained board-01 evidence for channel-neutral Wi-Fi bars."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-channel-neutral-bars-0.121"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-channel-neutral-bars-0.121.json"
VERSION = "0.121.0-wifi-channel-neutral-bars"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "4a9565d48f3497ddb542c1f34e3953b966066443"
FIRMWARE_SHA256 = "b10a1d322ed3387aa5b3c8e0be0f316331ab10ff14bfa0601c6a85d9390c9766"
FACTORY_SHA256 = "5540e051500825b7d94c10492965e14ac2d22a41e9a5e79be63641878d2c4328"
ELF_SHA256 = "4f07a226f93287173c851e1d0e1a37514687571c41df62dddd11513c7a9e6782"
MAP_SHA256 = "a17014b4f0f304a3ff5d6ae94af763dba469f6cd79ef83a8076c6df0412e35a5"
EVIDENCE_IDS = {"E-BUILD-121", "E-AUTO-085", "E-HIL-145", "E-UX-040"}
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


def verify_source(provenance: dict) -> None:
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
    contract = files["contract"].read_text(encoding="utf-8")
    require("wifiChannelBarTone(std::uint16_t busyPermille)" in renderer,
            "channel-neutral bar-tone signature missing")
    require("return Palette::Positive;" in renderer,
            "neutral low-load bar tone missing")
    legacy = "channel == 1U || channel == 6U || channel == 11U"
    require(legacy not in renderer and legacy in contract,
            "legacy primary-channel tint was not rejected")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_channel_neutral_bars.acceptance.v1" and
            summary.get("status") == "pass_wifi_channel_neutral_bars",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_channel_neutral_bars_hil.provenance.v1" and
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
            provenance.get("linked_flash_bytes") == 2891644 and
            provenance.get("tft_states") == 4,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)

    run = load(BUNDLE / "run/run.json")
    candidate = run.get("candidate", {})
    scope = run.get("scope", {})
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
    require(scope.get("current_bar_tone_channel_neutral") is True and
            scope.get("recommended_primary_channels") == list(range(1, 14)) and
            scope.get("recommended_axis_label_highlighted") is True,
            "neutral visual/recommendation scope mismatch")
    require(run.get("pixel_changes") == {
                "dynamic_changed_pixels": 998,
                "static_changed_pixels": 0,
            }, "live/static pixel isolation mismatch")
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

    verified = summary.get("verified", {})
    require(verified.get("current_bar_tone_channel_neutral") is True and
            verified.get("best_channel_first") == 13 and
            verified.get("best_channel_second") == 13 and
            verified.get("first_sweeps") == 2 and
            verified.get("second_sweeps") == 3 and
            verified.get("first_frames") == 82 and
            verified.get("second_frames") == 229 and
            verified.get("static_changed_pixels") == 0 and
            verified.get("heap_total_bytes") == 171988 and
            verified.get("heap_free_bytes") == 104460 and
            verified.get("heap_min_free_bytes") == 34996 and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_page") == "home" and
            verified.get("final_runtime_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified claims mismatch")
    print(
        "Wi-Fi channel neutral-bars acceptance passed: no 1/6/11 tint, "
        "channel 13 selected and final lease 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
