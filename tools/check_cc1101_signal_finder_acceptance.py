#!/usr/bin/env python3
"""Fail closed unless exact 0.124.1 CC1101 finder evidence is intact."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-cc1101-signal-finder-0.124"
SUMMARY = ROOT / "tests/hil/evidence/board-01-cc1101-signal-finder-0.124.json"
VERSION = "0.124.1-cc1101-frequency-finder"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "7219af540b3ab67ee2fbc5a088b7b7b2215c25a8"
FAILED_SOURCE_COMMIT = "fca18717a0c9b30df2da4ad8814e59bfbbf655df"
FIRMWARE_SHA256 = "17981885bb0e39d9ed020b15674e2e70a6aab8c2d4aa06bf76068a85ac272b04"
ELF_SHA256 = "5111bf56b8ddc6ddc08937929aa0ec25c61739353638dae39f783f26d969f482"
FACTORY_SHA256 = "de382ff8de0231f5def77aab4a1b7411cd005d5b3d1384d94474f35d0e37fb0f"
MAP_SHA256 = "79ed0a35e137478bf5c7722eedad1bd9b4cf02df3cfdcea25bb61ae30946a38e"
RUN_SHA256 = "1b2d4df181960f923f3ce7b105c1bb702c9ea5efe35838b1956b1819af4e4d18"
QUIET_RUN_SHA256 = "fd76f132e0dc5d40fdca0e998e103af0af706d1d6e9c5b7b6ccb26cae4aee162"
FAILED_FRESH_SHA256 = "d5c266b461b9cff0d9cabc1b43c5f253f2244fac55de01e0915d2d4e9e9b3cd2"
FAILED_REUSE_SHA256 = "371e01f30579b087bc90df18d87a4779686b9dde424d31d6940f1495f88257a6"
INDEX_SHA256 = "f3a90dce361f9edc523db98c8a640ea974f4b3c020bd0849658c933984122388"
RUNNER_SHA256 = "f960a96688e2e7d8e91e65eb3d0ab3a4d389ef93f9c31fe59b513f0053bc95a0"
CHECKER_SHA256 = "a9eb8d18408ee5688fafe810018646653730e580e42c0363a48eda1ba144a8fd"
CONTRACT_SHA256 = "8068aa74f6b8121f1e44409fe08fc29ab52d99f61ceb5735576e6e98661382e8"
EVIDENCE_IDS = {"E-BUILD-124", "E-AUTO-088", "E-HIL-148", "E-UX-043"}
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")
SOURCE_FILES = {
    "finder_h": "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.h",
    "finder_cpp": "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.cpp",
    "adapter_h": "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.h",
    "adapter_cpp": "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp",
    "passive_h": "firmware/leshy1/src/drivers/radio/Cc1101PassiveSpectrum.h",
    "passive_cpp": "firmware/leshy1/src/drivers/radio/Cc1101PassiveSpectrum.cpp",
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "catalog": "firmware/leshy1/src/domain/apps/AppCatalog.cpp",
    "platform": "firmware/leshy1/platformio.ini",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "source_contract": "tools/check_cc1101_signal_finder_contract.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(completed.returncode == 0, f"source blob missing: {path}")
    return completed.stdout


def verify_manifest() -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(manifest.is_file() and digest(manifest) == INDEX_SHA256,
            "artifact index identity mismatch")
    indexed_present: set[Path] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        require(len(parts) == 2 and len(parts[0]) == 64 and parts[1],
                f"invalid artifact-index line {number}")
        expected, relative = parts
        artifact = BUNDLE / relative
        if not artifact.is_file():
            require(relative.endswith(OPAQUE_SUFFIXES),
                    f"tracked artifact missing: {relative}")
            continue
        require(digest(artifact) == expected,
                f"artifact hash mismatch: {relative}")
        indexed_present.add(Path(relative))
    present = {
        path.relative_to(BUNDLE) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed_present == present, "artifact index coverage mismatch")


def main() -> int:
    require(SUMMARY.is_file() and BUNDLE.is_dir(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    verify_manifest()
    require(summary.get("schema") ==
                "leshy.cc1101_signal_finder.acceptance.v1" and
            summary.get("status") ==
                "pass_after_false_positive_regression" and
            summary.get("board") == "board-01" and
            set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "summary identity mismatch")
    candidate = summary.get("candidate", {})
    require(candidate == provenance and
            provenance.get("schema") ==
                "leshy.cc1101_signal_finder_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("failed_source_commit") ==
                FAILED_SOURCE_COMMIT and
            provenance.get("runner_commit") == SOURCE_COMMIT and
            provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("run_sha256") == RUN_SHA256 and
            provenance.get("quiet_regression_run_sha256") ==
                QUIET_RUN_SHA256 and
            provenance.get("failed_fresh_run_sha256") ==
                FAILED_FRESH_SHA256 and
            provenance.get("failed_reuse_run_sha256") ==
                FAILED_REUSE_SHA256 and
            provenance.get("runner_sha256") == RUNNER_SHA256 and
            provenance.get("checker_sha256") == CHECKER_SHA256 and
            provenance.get("source_guard_sha256") == CONTRACT_SHA256 and
            provenance.get("static_ram_bytes") == 233288 and
            provenance.get("linked_flash_bytes") == 3060648 and
            provenance.get("tft_states") == 8,
            "candidate provenance mismatch")
    evidence = summary.get("evidence", {})
    require(evidence.get("artifact_index_sha256") == INDEX_SHA256 and
            evidence.get("files") == 128 and
            evidence.get("tft_states") == 8,
            "evidence inventory mismatch")
    require(summary.get("verified") == {
        "bins": 1099, "calibration_passes": 3,
        "failed_fresh_frequency_khz": 335000,
        "failed_fresh_response_db": 21,
        "failed_reuse_frequency_khz": 346250,
        "failed_reuse_response_db": 19,
        "final_lease_mask": 0, "fresh_ambient_found": False,
        "fresh_ambient_response_db": 13, "generation": 95,
        "graph_changed_pixels": 1455, "heap_free_after": 77932,
        "heap_min_after": 63700, "observations": 0,
        "physical_write_calls": 0, "response_threshold_db": 18,
        "reuse_ambient_found": False, "reuse_ambient_response_db": 15,
        "static_changed_pixels": 0, "step_khz": 250,
    }, "verified physical facts mismatch")
    regression = summary.get("regression", {})
    limits = summary.get("limits", {})
    require(regression.get("failed_version") ==
                "0.124.0-cc1101-frequency-finder" and
            regression.get("symptom") ==
                "nonrepeatable ambient false frequency" and
            limits.get("known_signal_physical_source") is False and
            limits.get("found_branch") == "deterministic native injection" and
            limits.get("physical_rf_silence") is False and
            limits.get("calibrated_power_or_distance") is False,
            "regression or evidence limits are not explicit")

    for name, expected in (
        ("run/run.json", RUN_SHA256),
        ("quiet-regression/run.json", QUIET_RUN_SHA256),
        ("failed-predecessor/fresh/run.json", FAILED_FRESH_SHA256),
        ("failed-predecessor/reuse/run.json", FAILED_REUSE_SHA256),
        ("run/firmware.bin", FIRMWARE_SHA256),
        ("firmware.elf", ELF_SHA256),
        ("firmware.factory.bin", FACTORY_SHA256),
        ("firmware.map", MAP_SHA256),
    ):
        path = BUNDLE / name
        if path.is_file():
            require(digest(path) == expected, f"artifact mismatch: {name}")
    require(digest(BUNDLE / "tools/run_1x_cc1101_signal_finder_hil.py") ==
                RUNNER_SHA256 and
            digest(BUNDLE / "tools/check_cc1101_signal_finder_run.py") ==
                CHECKER_SHA256 and
            digest(BUNDLE / "tools/check_cc1101_signal_finder_contract.py") ==
                CONTRACT_SHA256,
            "retained tool identity mismatch")
    require(hashlib.sha256(git_blob(
                SOURCE_COMMIT,
                "tools/run_1x_cc1101_signal_finder_hil.py")).hexdigest() ==
                RUNNER_SHA256,
            "committed runner identity mismatch")
    for label, relative in SOURCE_FILES.items():
        require(hashlib.sha256(git_blob(SOURCE_COMMIT, relative)).hexdigest() ==
                    provenance["source_sha256"][label],
                f"source-commit binding mismatch: {label}")

    checker = BUNDLE / "tools/check_cc1101_signal_finder_run.py"
    completed = subprocess.run(
        [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT,
         "--require-ambient-below-threshold"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")})
    require(completed.returncode == 0,
            f"independent run verification failed: {completed.stdout}")
    print("CC1101 signal-finder acceptance passed: failed 0.124.0 "
          "false peaks retained; median 0.124.1 stayed below threshold twice, "
          "used RX only, and returned final lease 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
