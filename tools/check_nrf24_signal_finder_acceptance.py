#!/usr/bin/env python3
"""Fail closed unless exact 0.123 signal-finder evidence is intact."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-nrf24-signal-finder-0.123"
SUMMARY = ROOT / "tests/hil/evidence/board-01-nrf24-signal-finder-0.123.json"
VERSION = "0.123.0-nrf24-signal-finder"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "07b551f3876b26d48c1d4a25b9730e2ff4e1e056"
FIRMWARE_SHA256 = "3d9900439f41d61bd659947c7a27553b04e86cf210cbca76be3b82c70be66b36"
ELF_SHA256 = "9bc9ea783dd100699dcff92ffd218a483b5c2f22f5731cb48205960cb995fb98"
FACTORY_SHA256 = "78bae21499aff24fd675ec14a5b38570440a4bb9370f39501eb3f610597f1f6e"
MAP_SHA256 = "83b2bb241e29c0f33a97d61e6d3ac79612b7c1376553cc7721332e59161a1869"
RUN_SHA256 = "a141ffc44eec23261498736bb41072765868a4537bb4c6bbcaf44df61d731ac6"
INDEX_SHA256 = "3aa01953c7fe6cbed5adfd546afea26b5ee11e0d6ad5e5e9b8bf0a9ad374a7ff"
RUNNER_SHA256 = "dabc4dd10cd473eac5e4032b5d345173bfa2b4c14d08038545623aaf0eb33d1b"
CHECKER_SHA256 = "e79e719d5aabcd5e543de2c7c35ec57b7cfb20cb0ac51e0c89389f81e7980d49"
CONTRACT_SHA256 = "a82e086768d6e0222ccb0ff9e36096d542802e0b2c3dfa74d75cd3a6f5d67367"
EVIDENCE_IDS = {"E-BUILD-123", "E-AUTO-087", "E-HIL-147", "E-UX-042"}
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")
SOURCE_FILES = {
    "finder_h": "firmware/leshy1/src/apps/spectrum/Nrf24SignalFinder.h",
    "finder_cpp": "firmware/leshy1/src/apps/spectrum/Nrf24SignalFinder.cpp",
    "adapter_h": "firmware/leshy1/src/platform/arduino/BoardNrf24PassiveSpectrum.h",
    "adapter_cpp": "firmware/leshy1/src/platform/arduino/BoardNrf24PassiveSpectrum.cpp",
    "passive_h": "firmware/leshy1/src/drivers/radio/Nrf24PassiveSpectrum.h",
    "passive_cpp": "firmware/leshy1/src/drivers/radio/Nrf24PassiveSpectrum.cpp",
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "catalog": "firmware/leshy1/src/domain/apps/AppCatalog.cpp",
    "platform": "firmware/leshy1/platformio.ini",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "source_contract": "tools/check_nrf24_signal_finder_contract.py",
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
                "leshy.nrf24_signal_finder.acceptance.v1" and
            summary.get("status") == "pass_passive_signal_finder" and
            summary.get("board") == "board-01" and
            set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "summary identity mismatch")
    candidate = summary.get("candidate", {})
    require(candidate == provenance and
            provenance.get("schema") ==
                "leshy.nrf24_signal_finder_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == SOURCE_COMMIT and
            provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("run_sha256") == RUN_SHA256 and
            provenance.get("runner_sha256") == RUNNER_SHA256 and
            provenance.get("checker_sha256") == CHECKER_SHA256 and
            provenance.get("source_guard_sha256") == CONTRACT_SHA256 and
            provenance.get("static_ram_bytes") == 229448 and
            provenance.get("linked_flash_bytes") == 3055192 and
            provenance.get("tft_states") == 8,
            "candidate provenance mismatch")
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    limits = summary.get("limits", {})
    require(evidence.get("artifact_index_sha256") == INDEX_SHA256 and
            evidence.get("files") == 47 and evidence.get("tft_states") == 8,
            "evidence inventory mismatch")
    require(verified == {
        "active_slot_mask": 7, "ambient_found": False,
        "ambient_response": 3, "calibration_windows": 2,
        "final_lease_mask": 0, "generation": 95,
        "graph_changed_pixels": 720, "heap_free_after": 81772,
        "heap_min_after": 67540, "measured_windows": 3,
        "modules": 3, "observations": 0, "physical_write_calls": 0,
        "response_threshold": 8, "static_changed_pixels": 0,
    }, "verified physical facts mismatch")
    require(limits.get("known_signal_physical_source") is False and
            limits.get("found_branch") == "deterministic host injection" and
            limits.get("physical_rf_silence") is False and
            limits.get("calibrated_power_or_distance") is False,
            "evidence limits are not explicit")

    require(digest(BUNDLE / "run/run.json") == RUN_SHA256,
            "run binding mismatch")
    for name, expected in (
        ("run/firmware.bin", FIRMWARE_SHA256),
        ("firmware.elf", ELF_SHA256),
        ("firmware.factory.bin", FACTORY_SHA256),
        ("firmware.map", MAP_SHA256),
    ):
        path = BUNDLE / name
        if path.is_file():
            require(digest(path) == expected, f"opaque artifact mismatch: {name}")
    require(digest(BUNDLE / "tools/run_1x_nrf24_signal_finder_hil.py") ==
                RUNNER_SHA256 and
            digest(BUNDLE / "tools/check_nrf24_signal_finder_run.py") ==
                CHECKER_SHA256 and
            digest(BUNDLE / "tools/check_nrf24_signal_finder_contract.py") ==
                CONTRACT_SHA256,
            "retained tool identity mismatch")
    require(hashlib.sha256(git_blob(
                SOURCE_COMMIT,
                "tools/run_1x_nrf24_signal_finder_hil.py")).hexdigest() ==
                RUNNER_SHA256,
            "committed runner identity mismatch")
    for label, relative in SOURCE_FILES.items():
        require(hashlib.sha256(git_blob(SOURCE_COMMIT, relative)).hexdigest() ==
                    provenance["source_sha256"][label],
                f"source-commit binding mismatch: {label}")

    checker = BUNDLE / "tools/check_nrf24_signal_finder_run.py"
    completed = subprocess.run(
        [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")})
    require(completed.returncode == 0,
            f"independent run verification failed: {completed.stdout}")
    print("nRF24 signal-finder acceptance passed: three RX antennas, "
          "ambient calibration, graph-only live redraw and final lease 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
