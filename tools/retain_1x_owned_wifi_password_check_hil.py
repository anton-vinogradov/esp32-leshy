#!/usr/bin/env python3
"""Retain a privacy-safe acceptance from the completed WF11 physical run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import check_wifi_authentication_persistence_hil_run as device_checker
import run_1x_owned_wifi_password_check_hil as coordinator


SCHEMA = "leshy.owned_wifi_password_check_hil.acceptance.v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def private_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": report.get("schema"),
        "status": report.get("status"),
        "outcome": report.get("outcome"),
        "evidence": report.get("evidence", {}),
        "corpus": report.get("corpus", {}),
        "budget": report.get("budget", {}),
        "result": report.get("result", {}),
        "privacy": report.get("privacy", {}),
        "side_effects": report.get("side_effects", {}),
    }


def retain(source_path: Path, precursor_paths: list[Path],
           output: Path) -> dict[str, Any]:
    require(source_path.is_file() and not source_path.is_symlink(),
            "regular physical source run required")
    require(not output.exists(), "acceptance output already exists")
    source = load(source_path)
    child_path = source_path.parent / "device" / "run.json"
    child = load(child_path)
    candidate = child.get("candidate", {})
    marker = {
        "version": candidate.get("version"),
        "source_commit": candidate.get("source_commit"),
        "firmware_sha256": candidate.get("firmware_sha256"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "runner_source_sha256": child.get("runner_source_sha256"),
        "expected_cid": child.get("board", {}).get("expected_cid"),
    }
    failures: list[str] = []
    device_checker.verify_run(child, marker, failures)
    device_checker.verify_manifest(child_path.parent, failures)
    device_checker.verify_private_absent(failures, child)
    require(not failures, "physical child rejected: " + "; ".join(failures))

    require(source.get("schema") == coordinator.RUN_SCHEMA,
            "coordinator schema mismatch")
    require(source.get("passed") is False and source.get("failures") ==
            ["guided_verification_contract_failed"],
            "only the obsolete positive-outcome oracle may be reassessed")
    require(source.get("candidate") == candidate,
            "coordinator/device candidate mismatch")
    device = source.get("device_chain", {})
    export = device.get("export", {})
    require(device.get("run_sha256") == digest(child_path) and
            device.get("atomic_save") is True and
            device.get("cold_reopen") is True and
            device.get("final_cleanup") is True and
            device.get("public_fixture_only") is True and
            device.get("fresh_flash") is False and
            export.get("format") == "WPA*02" and
            export.get("records") == 1,
            "physical export chain mismatch")
    physical = source.get("computer_check", {})
    require(coordinator.physical_export_contract(
                physical, export.get("sha256")),
            "physical negative-control report mismatch")
    positive = coordinator.run_guided_check(
        coordinator.PUBLIC_POSITIVE_EVIDENCE)
    require(coordinator.positive_control_contract(positive),
            "public positive control mismatch")

    precursor_values: list[dict[str, Any]] = []
    previous = source
    for path in precursor_paths:
        value = load(path)
        expected = previous.get("precursor", {}).get("run_sha256")
        require(expected == digest(path),
                f"broken precursor link: {path}")
        precursor_values.append({
            "schema": value.get("schema"),
            "run_sha256": expected,
            "passed": value.get("passed"),
            "failures": value.get("failures", []),
        })
        previous = value
    require(len(precursor_values) == 5 and
            all(item["passed"] is False for item in precursor_values),
            "exact five-run fail-closed audit chain required")

    root = Path(__file__).resolve().parents[1]
    result = {
        "schema": SCHEMA,
        "passed": True,
        "candidate": candidate,
        "board": child.get("board", {}),
        "physical": {
            "source_run_sha256": digest(source_path),
            "device_run_sha256": digest(child_path),
            "atomic_save": True, "cold_reopen": True,
            "final_cleanup": True, "public_fixture_only": True,
            "export": export,
        },
        "computer": {
            "physical_negative_control": private_report(physical),
            "public_positive_control": private_report(positive),
        },
        "reassessment": {
            "source_run_passed": False,
            "source_failure": "guided_verification_contract_failed",
            "reason": "anonymized_fixture_is_negative_control",
            "device_run_passed": True,
            "computer_report_passed": True,
        },
        "precursors": precursor_values,
        "privacy": {
            "raw_export_retained": False,
            "candidate_plaintext_retained": False,
            "private_network_identity_retained": False,
            "network_operations": 0,
            "device_writes_by_computer_check": 0,
            "radio_operations_by_computer_check": 0,
        },
        "tooling": {
            "coordinator_sha256": digest(
                root / "tools/run_1x_owned_wifi_password_check_hil.py"),
            "journey_sha256": digest(root / "tools/check_my_wifi_password.py"),
            "verifier_sha256": digest(
                root / "tools/owned_wifi_evidence_verifier.py"),
            "persistence_runner_sha256": digest(
                root / "tools/run_1x_wifi_authentication_persistence_hil.py"),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--precursor", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = retain(args.source, args.precursor, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 2
    print(json.dumps({"schema": SCHEMA, "passed": result["passed"],
                      "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
