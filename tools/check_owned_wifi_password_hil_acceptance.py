#!/usr/bin/env python3
"""Fail-closed checker for retained WF11 physical/computer acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "leshy.owned_wifi_password_check_hil.acceptance.v1"
VERSION = "1.0.0-dev.369"
SOURCE_COMMIT = "ec316a42a9a53f53da2c92078ff0c7a5d9064f5a"
FIRMWARE_SHA256 = \
    "9591e4555dcab9ba26e3e7f3aa33a8454feef63baa6ed21b2a9be27f3f3e65a9"
APP_SHA256 = \
    "7203f50d0bd02d1a95a86f8e3bf4cbf577e08b71e17b0dded5adcf1151dd4b7e"
CID = "FE343253440000002000000055019CB7"
EXPORT_SHA256 = \
    "30572a0ede9b5c969a8d018967593026c00a9d484f2045e62dd9e251a370fb72"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check(path: Path) -> list[str]:
    failures: list[str] = []
    try:
        value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [str(error)]
    require(failures, value.get("schema") == SCHEMA and
            value.get("passed") is True, "clean acceptance required")
    require(failures, value.get("candidate") == {
        "version": VERSION, "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256, "app_elf_sha256": APP_SHA256,
        "flashed": False, "reused_exact_flash": True,
    }, "exact candidate mismatch")
    require(failures, value.get("board") == {
        "id": "board-01", "expected_cid": CID}, "board/CID mismatch")
    physical = value.get("physical", {})
    export = physical.get("export", {})
    require(failures,
            physical.get("atomic_save") is True and
            physical.get("cold_reopen") is True and
            physical.get("final_cleanup") is True and
            physical.get("public_fixture_only") is True and
            export.get("sha256") == EXPORT_SHA256 and
            export.get("format") == "WPA*02" and
            export.get("records") == 1,
            "physical chain mismatch")
    computer = value.get("computer", {})
    negative = computer.get("physical_negative_control", {})
    positive = computer.get("public_positive_control", {})
    side_effects = {"device_writes": 0, "network_operations": 0,
                    "radio_operations": 0}
    require(failures, negative.get("status") == "pass" and
            negative.get("outcome") == "complete_no_match" and
            negative.get("evidence", {}).get("sha256") == EXPORT_SHA256 and
            negative.get("result", {}).get("matched_rank") is None and
            negative.get("result", {}).get("candidates_examined") == 2 and
            negative.get("side_effects") == side_effects,
            "physical negative control mismatch")
    require(failures, positive.get("status") == "pass" and
            positive.get("outcome") == "weak_password_match" and
            positive.get("result", {}).get("matched_rank") == 2 and
            positive.get("side_effects") == side_effects,
            "public positive control mismatch")
    for label, report in (("negative", negative), ("positive", positive)):
        privacy = report.get("privacy", {})
        require(failures,
                privacy.get("plaintext_retained") is False and
                privacy.get("raw_evidence_retained") is False and
                privacy.get("identity_linked_leak_corpus_bundled") is False,
                f"{label} privacy boundary mismatch")
    reassessment = value.get("reassessment", {})
    require(failures,
            reassessment == {
                "source_run_passed": False,
                "source_failure": "guided_verification_contract_failed",
                "reason": "anonymized_fixture_is_negative_control",
                "device_run_passed": True,
                "computer_report_passed": True,
            }, "transparent reassessment missing")
    precursors = value.get("precursors", [])
    require(failures, len(precursors) == 5 and
            all(item.get("passed") is False and item.get("failures")
                for item in precursors), "fail-closed precursor chain missing")
    privacy = value.get("privacy", {})
    require(failures, privacy == {
        "raw_export_retained": False,
        "candidate_plaintext_retained": False,
        "private_network_identity_retained": False,
        "network_operations": 0,
        "device_writes_by_computer_check": 0,
        "radio_operations_by_computer_check": 0,
    }, "retained privacy boundary mismatch")
    tooling = value.get("tooling", {})
    files = {
        "coordinator_sha256":
            ROOT / "tools/run_1x_owned_wifi_password_check_hil.py",
        "journey_sha256": ROOT / "tools/check_my_wifi_password.py",
        "verifier_sha256": ROOT / "tools/owned_wifi_evidence_verifier.py",
        "persistence_runner_sha256":
            ROOT / "tools/run_1x_wifi_authentication_persistence_hil.py",
    }
    for field, source in files.items():
        require(failures, tooling.get(field) == digest(source),
                f"tool hash mismatch: {field}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    failures = check(args.evidence)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 2
    print("owned Wi-Fi password-check HIL acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
