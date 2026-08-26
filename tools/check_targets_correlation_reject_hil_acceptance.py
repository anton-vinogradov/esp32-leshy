#!/usr/bin/env python3
"""Fail closed unless compact exact 0.156 Targets Reject HIL is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-correlation-reject-0.156.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_git_blob(commit: str, relative: str) -> str | None:
    try:
        blob = subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
            stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(blob).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    bundle = ROOT / summary.get("bundle", "missing")
    manifest_path = bundle / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {})
    require(failures, manifest_path.is_file() and
            digest(manifest_path) == summary.get("manifest_sha256"),
            "manifest missing or hash mismatch")
    for relative, expected in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected,
                f"retained file mismatch: {relative}")
    require(failures,
            summary.get("schema") ==
                "leshy.targets_correlation_reject_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
                ["E-AUTO-114", "E-HIL-174", "E-UX-051"],
            "summary identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            summary.get("firmware_source_commit") ==
                "0559fc632f8a1dc856000d57113d24b61ab801aa" and
            candidate.get("version") == "0.156.0-targets-reject-rebuild" and
            candidate.get("firmware_sha256") ==
                "68c809d0a529c76b629c2723c5f918c5288413fe7791d68e98b67dcab74c98b9" and
            candidate.get("elf_sha256") ==
                "e0bffd74505ed266cb6a48d9646fdf47c0290b462c9fb5234b5a4b010c8a50a7" and
            candidate.get("map_sha256") ==
                "37e6fa1e70d3fe210324b13b3deb302741ec29ff36a2aff8b78a66c47ee50750",
            "exact candidate mismatch")
    require(failures,
            summary.get("exact_cid") ==
                "FE343253440000002000000055019CB7" and
            summary.get("proposal", {}).get("decision") == "reject" and
            summary.get("transition") == {
                "catalog_capacity": 16,
                "catalog_count": [16, 16],
                "decision_count": [2, 3],
                "target_count": [4, 4],
                "target_revision": [5, 5],
                "target_state_generation": [10, 11],
            }, "Reject transition mismatch")
    cold = summary.get("cold_reopened", {})
    require(failures,
            cold.get("target_state_generation") == 11 and
            cold.get("decision_count") == 3 and
            cold.get("catalog_count") == 16 and
            cold.get("catalog_capacity") == 16 and
            cold.get("visible_target_count") == 4 and
            cold.get("source_identity_count") == 84 and
            cold.get("truncated") is True and
            cold.get("capacity_skipped") == 7,
            "cold reopened bounded state mismatch")
    scope = summary.get("usb_scope", {})
    require(failures,
            scope.get("ports_opened_by_runner") ==
                ["/dev/cu.usbmodem2101"] and
            scope.get("port_enumeration_by_runner") is False and
            scope.get("external_fixture_port") is None and
            scope.get("cardputer_ports_opened") == 0 and
            summary.get("radio_tx_commands_from_dut") == 0 and
            summary.get("final") == {
                "page": "home", "runtime_owner": "none", "lease_mask": 0},
            "USB/radio/terminal scope mismatch")
    provenance_path = bundle / "provenance.json"
    provenance = (json.loads(provenance_path.read_text(encoding="utf-8"))
                  if provenance_path.is_file() else {})
    for relative, expected in provenance.get("source_blob_sha256", {}).items():
        require(failures,
                digest_git_blob(summary["firmware_source_commit"], relative)
                    == expected,
                f"source blob mismatch: {relative}")
    run = json.loads((bundle / "run.json").read_text(encoding="utf-8"))
    precursor = json.loads((bundle / summary.get("precursor", "missing"))
                           .read_text(encoding="utf-8"))
    require(failures,
            run.get("status") == "pass" and run.get("decision") == "reject" and
            run.get("states", {}).get("mutation_result", {}).get(
                "mutation_correlation_status") == "rejected" and
            precursor.get("status") == "failed" and
            "atomic correlation reject" in str(precursor.get("error")) and
            precursor.get("cleanup", {}).get("complete") is True,
            "retained pass/fail-closed pair mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: exact 0.156 Targets Reject HIL evidence accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
