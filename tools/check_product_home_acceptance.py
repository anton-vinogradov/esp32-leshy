#!/usr/bin/env python3
"""Fail closed unless the exact 0.93 product Home proof remains intact."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-product-home-0.93.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-home-0.93"
VERSION = "0.93.0-product-menu"
SOURCE = "c50dcccfb5f650f46666b759072fe3722a1c22f5"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "d2d134223a52cae5e6685bb83da5de8406602c5da088a76bfd394aa73f5c0ca7"
FACTORY = "d3f0ef3a4ad8975910059c563430cd1a2d2947b545fed2106ba6234bc810c3ff"
APP = "fc06986e09e1629710c30aec40789211dea907e169c0639c09896bee27e1a460"
MAP = "256fdd76183df4746709bbc2bd3f39294f9bd4e210b0604d43dc09a17a825ee9"
RUNNER = "fb8c35e71d3a12db73ddfcffe40e42a8f9e2b8f03c38fab645f556e3e9705a37"
CHECKER = "215b90b1fa67931d678f28016622eb54a2e183ed9d18b90e0b9145b07dcd71fa"
GATE = "990f8deb3857ae0b700c0dee7b2fc7edbaeaf3a5ea239fcdcd1e0a3c1be86caa"
INDEX = "6971308513144841ca8c3c55b4efced74e17a3987717474dd932bc21690e838b"
PROVENANCE = "91343d7b07313a94aaa907eee5aeb9876c2bf1df71a0f53d61a677c7c2649487"
RUN = "765583240b0a0ea9f0cd344c36f0091f620b726b8397fdd2a7ae6df872bac93a"
HOME_ITEMS = [
    "wifi", "ble", "spectrum24", "subghz", "capture", "library", "device",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tracked-only", action="store_true",
        help="verify Git-retained evidence/source contracts without ignored binaries",
    )
    args = parser.parse_args()
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.93 product Home evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.product_home_acceptance.v1" and
            summary.get("status") == "pass_product_home_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-094", "E-AUTO-058", "E-HIL-118",
                 "E-UX-017", "E-RADIO-006"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("checker_sha256") == CHECKER and
            candidate.get("gate_sha256") == GATE and
            [candidate.get("firmware_bytes"), candidate.get("factory_bytes"),
             candidate.get("static_ram_bytes"),
             candidate.get("linked_flash_bytes")] ==
                [1506384, 1571920, 159856, 1505972],
            "candidate identity/size mismatch")
    require(failures,
            evidence == {
                "artifact_index_sha256": INDEX,
                "files": 49,
                "provenance_sha256": PROVENANCE,
                "run_sha256": RUN,
                "tft_states": 13,
            }, "evidence summary mismatch")
    require(failures,
            digest(BUNDLE / "artifacts.sha256") == INDEX and
            digest(BUNDLE / "provenance.json") == PROVENANCE and
            digest(BUNDLE / "run.json") == RUN and
            digest(BUNDLE / "runner.py") == RUNNER and
            digest(BUNDLE / "checker.py") == CHECKER and
            digest(BUNDLE / "connected-candidate-gate.sh") == GATE,
            "Git-retained artifact binding mismatch")

    if not args.tracked_only:
        require(failures,
                digest(BUNDLE / "firmware.bin") == FIRMWARE and
                digest(BUNDLE / "firmware.factory.bin") == FACTORY and
                digest(BUNDLE / "firmware.elf") == APP and
                digest(BUNDLE / "firmware.map") == MAP and
                app_elf_sha256(BUNDLE / "firmware.bin") == APP,
                "local opaque candidate binding mismatch")
        generic = subprocess.run(
            [str(ROOT / "tools/check_product_home_run.py"),
             "--run", str(BUNDLE), "--expected-version", VERSION,
             "--expected-cid", CID, "--source-commit", SOURCE],
            cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        require(failures, generic.returncode == 0,
                f"independent run verification failed: {generic.stdout}")

    catalog = git_blob("firmware/leshy1/src/domain/apps/AppCatalog.cpp")
    source_controller = git_blob(
        "firmware/leshy1/src/apps/survey/SurveySourceController.cpp")
    entry = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    runner = git_blob("tools/run_1x_product_home_hil.py")
    gate = git_blob("tools/verify_connected_candidate.sh")
    require(failures, catalog is not None and all(token in catalog for token in (
        b'"wifi"', b'"ble"', b'"spectrum24"', b'"subghz"',
        b'"capture"', b'"library"', b'"device"')) and
        b'"targets"' not in catalog and b'"lab"' not in catalog,
        "implemented-only product catalog mismatch")
    require(failures, source_controller is not None and all(
        token in source_controller for token in (
            b"SurveySourceScope::WifiOnly", b"SurveySourceScope::BleOnly",
            b"SurveySetupActivation::StartRequested")),
        "single-source entry contract mismatch")
    require(failures, entry is not None and all(token in entry for token in (
        b'std::strcmp(selected->id, "spectrum24")',
        b'lastRuntimeEvent = "cc1101_spectrum_band_menu"',
        b"startNrf24Spectrum()", b"surveySourceController.planItemCount()")),
        "direct radio navigation source contract mismatch")
    require(failures, runner is not None and
            hashlib.sha256(runner).hexdigest() == RUNNER and
            all(token in runner for token in (
                b"HOME_ITEMS", b"manual_button_presses", b"screenshots_automatic",
                b"nrf_waterfall", b"cc_waterfall")),
            "runner Git binding/coverage mismatch")
    require(failures, gate is not None and
            hashlib.sha256(gate).hexdigest() == GATE and
            all(token in gate for token in (
                b"tools/test.sh", b"tools/check_docs.py", b"pio_bin",
                b"run_1x_product_home_hil.py", b"check_product_home_run.py")),
            "one-command gate source contract mismatch")
    require(failures,
            verified == {
                "automatic_screenshots": True,
                "cc_history_rows": 8,
                "final_lease_mask": 0,
                "final_owner": "none",
                "heap": [221852, 156892, 137540],
                "home_items": HOME_ITEMS,
                "manual_button_presses": 0,
                "nrf_history_rows": 16,
                "physical_rf_silence_measured": False,
                "single_flash": True,
                "software_rx_only": True,
                "storage_generation": 95,
                "storage_observations": 0,
            }, "verified claims mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "files": 49,
        "tft_states": 13, "home_items": HOME_ITEMS,
        "nrf_history_rows": 16, "cc_history_rows": 8,
        "single_flash": True, "manual_button_presses": 0,
        "final_lease_mask": 0,
        "evidence_mode": "tracked" if args.tracked_only else "full",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
