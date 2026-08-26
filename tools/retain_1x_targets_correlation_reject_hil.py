#!/usr/bin/env python3
"""Retain compact machine-checked exact 0.156 Targets Reject evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-correlation-reject-0.156"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-correlation-reject-0.156.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
FAILURE_SOURCE = "1f2c7b6647a84a2b5c5f6063b0395e4c8746b0cf"
FIRMWARE_SOURCE = "0559fc632f8a1dc856000d57113d24b61ab801aa"
VERSION = "0.156.0-targets-reject-rebuild"
FIRMWARE = "68c809d0a529c76b629c2723c5f918c5288413fe7791d68e98b67dcab74c98b9"
ELF = "e0bffd74505ed266cb6a48d9646fdf47c0290b462c9fb5234b5a4b010c8a50a7"
MAP = "37e6fa1e70d3fe210324b13b3deb302741ec29ff36a2aff8b78a66c47ee50750"
TARGET_ID = "D232CBB7B4489ABAABFAFD7163BB1D51"
PROPOSAL_ID = "57C9339425F9BD8F205B604236540911"
CANDIDATE_IDENTITY = "603E5F4AC819"
MAC_FIXTURE_SHA256 = "da3cec0a11116e563b8d34d7c3ef042b5aeba0978db069b2b7c89bce6d64106d"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/run_1x_targets_correlation_hil.py",
)
FRAMES = {
    "proposal-list": "targets-correlation-list",
    "proposal-review": "targets-correlation-review",
    "known-evidence": "targets-correlation-known-evidence",
    "candidate-evidence": "targets-correlation-candidate-evidence",
    "reject-selected": "targets-correlation-reject-selected",
    "reject-saved": "targets-correlation-reject",
    "cold-reopened": "targets-correlation-cold-reopened",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_git_blob(commit: str, relative: str) -> str:
    blob = subprocess.check_output(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT)
    return hashlib.sha256(blob).hexdigest()


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def validate_candidate(candidate: dict[str, Any]) -> None:
    require(candidate.get("version") == VERSION and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("elf_sha256") == ELF and
            candidate.get("app_elf_sha256") == ELF and
            candidate.get("map_sha256") == MAP and
            candidate.get("firmware_bytes") == 3135600,
            "exact 0.156 candidate mismatch")
    frames = candidate.get("checked_stack_frames", {})
    require(frames.get("CorrelationService::propose(") == 416 and
            frames.get("buildSessionCorrelationReview(") == 816 and
            frames.get("TargetsController::loadBindings(") == 432,
            "bounded stack preflight mismatch")


def validate_fixture(run: dict[str, Any]) -> None:
    fixture = run.get("external_fixture", {})
    states = fixture.get("states", [])
    require(fixture.get("kind") == "macos_corebluetooth" and
            fixture.get("label") == "Keenetic-5070" and
            fixture.get("port") is None and
            fixture.get("executable_sha256") == MAC_FIXTURE_SHA256 and
            fixture.get("dut_remained_passive") is True and
            len(states) == 1 and states[0].get("state") == "advertising",
            "bounded port-free Mac fixture mismatch")


def validate_failure(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_correlation_hil.run.v1" and
            run.get("status") == "failed" and
            run.get("source_commit") == FAILURE_SOURCE and
            run.get("cleanup", {}).get("complete") is True,
            "exact fail-closed precursor required")
    error = str(run.get("error", ""))
    require("atomic correlation reject" in error and
            "'mutation_status': 'saved'" in error and
            "'mutation_correlation_status': 'rejected'" in error and
            "'mutation_persisted': True" in error and
            "'mutation_generation': 10" in error and
            "'correlation_decision_count': 0" in error,
            "precursor must expose only immediate rebuild failure")
    final = run.get("cleanup", {}).get("final_state", {})
    require(final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "fail-closed precursor cleanup mismatch")
    validate_fixture(run)


def validate_pass(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_correlation_hil.run.v1" and
            run.get("status") == "pass" and
            run.get("source_commit") == FIRMWARE_SOURCE and
            run.get("exact_cid") == EXPECTED_CID and
            run.get("decision") == "reject" and
            run.get("flash_count") == 1 and
            run.get("radio_tx_commands") == 0,
            "passing exact Reject run required")
    validate_candidate(run.get("candidate", {}))
    validate_fixture(run)
    require(run.get("proposal_id") == PROPOSAL_ID and
            run.get("target_id") == TARGET_ID and
            run.get("candidate_identity_hex") == CANDIDATE_IDENTITY and
            run.get("target_revision_before") == 5 and
            run.get("target_revision_after") == 5 and
            run.get("target_count_before") == 4 and
            run.get("target_count_after") == 4 and
            run.get("catalog_count_before") == 16 and
            run.get("catalog_count_after") == 16 and
            run.get("catalog_capacity") == 16 and
            run.get("catalog_bounded") is True and
            run.get("target_state_generation_before") == 10 and
            run.get("target_state_generation_after") == 11 and
            run.get("decision_count_before") == 2 and
            run.get("decision_count_after") == 3,
            "Reject transition or bounded catalog mismatch")
    mutation = run.get("states", {}).get("mutation_result", {})
    require(mutation.get("status") == "ready" and
            mutation.get("mutation_state") == "saved" and
            mutation.get("mutation_status") == "saved" and
            mutation.get("mutation_correlation") is True and
            mutation.get("mutation_correlation_kind") == "reject" and
            mutation.get("mutation_correlation_status") == "rejected" and
            mutation.get("mutation_persisted") is True and
            mutation.get("mutation_generation") == 11 and
            mutation.get("correlation_decision_count") == 3 and
            mutation.get("catalog_count") == 16 and
            mutation.get("catalog_capacity") == 16 and
            mutation.get("target_count") == 4 and
            mutation.get("truncated") is True and
            mutation.get("admission_target_status") == "catalog_full" and
            mutation.get("admission_capacity_skipped") == 7 and
            mutation.get("mutation_write_calls") == 3 and
            mutation.get("mutation_file_syncs") == 3 and
            mutation.get("mutation_directory_syncs") == 3 and
            mutation.get("mutation_expected_cid") == EXPECTED_CID and
            mutation.get("mutation_observed_cid") == EXPECTED_CID and
            mutation.get("cleanup_complete") is True,
            "atomic Reject result mismatch")
    reopened = run.get("states", {}).get("reopened", {})
    require(reopened.get("status") == "ready" and
            reopened.get("target_state_generation") == 11 and
            reopened.get("correlation_decision_count") == 3 and
            reopened.get("catalog_count") == 16 and
            reopened.get("catalog_capacity") == 16 and
            reopened.get("target_count") == 4 and
            reopened.get("source_identity_count") == 84 and
            reopened.get("truncated") is True and
            reopened.get("admission_capacity_skipped") == 7 and
            reopened.get("correlation_proposal_present") is False and
            reopened.get("cleanup_complete") is True,
            "cold reopened Reject mismatch")
    released = run.get("released", {})
    final = run.get("cleanup", {}).get("final_state", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("lease_mask") == 0 and
            released.get("cleanup_complete") is True and
            released.get("heap_free_now") ==
                released.get("heap_free_after_release") and
            run.get("cleanup", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "terminal heap/runtime cleanup mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--passed", required=True, type=Path)
    parser.add_argument("--failure", required=True, type=Path)
    parser.add_argument("--dut-port", default="/dev/cu.usbmodem2101")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        passed_dir = args.passed.resolve()
        failure_dir = args.failure.resolve()
        passed = load(passed_dir / "run.json")
        failure = load(failure_dir / "run.json")
        require(args.dut_port == "/dev/cu.usbmodem2101",
                "evidence is scoped only to original board-01")
        validate_pass(passed)
        validate_failure(failure)
        runner = (ROOT / "tools/run_1x_targets_correlation_hil.py").read_text()
        require("serial.tools.list_ports" not in runner,
                "runner must not enumerate unrelated USB ports")
    except (KeyError, TypeError, ValueError,
            subprocess.CalledProcessError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(passed_dir / "run.json", args.bundle / "run.json")
    precursors = args.bundle / "precursors"
    precursors.mkdir()
    shutil.copyfile(failure_dir / "run.json",
                    precursors / "immediate-rebuild-failure.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(passed_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")

    provenance = {
        "schema": "leshy.targets_correlation_reject_hil.provenance.v1",
        "firmware_source_commit": FIRMWARE_SOURCE,
        "failure_source_commit": FAILURE_SOURCE,
        "candidate": passed["candidate"],
        "source_blob_sha256": {
            path: digest_git_blob(FIRMWARE_SOURCE, path)
            for path in SOURCE_PATHS
        },
        "source_paths": list(SOURCE_PATHS),
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "retention_script_sha256": digest(Path(__file__).resolve()),
        "raw": {
            "passed": {
                "run_sha256": digest(passed_dir / "run.json"),
                "artifacts_manifest_sha256":
                    digest(passed_dir / "artifacts.sha256"),
            },
            "failure": {
                "run_sha256": digest(failure_dir / "run.json"),
                "artifacts_manifest_sha256":
                    digest(failure_dir / "artifacts.sha256"),
            },
        },
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {str(path.relative_to(args.bundle)): digest(path)
                for path in sorted(args.bundle.rglob("*")) if path.is_file()}
    write_json(args.bundle / "manifest.json", manifest)

    mutation = passed["states"]["mutation_result"]
    reopened = passed["states"]["reopened"]
    summary = {
        "schema": "leshy.targets_correlation_reject_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-114", "E-HIL-174", "E-UX-051"],
        "board": {"id": "board-01", "dut_port": args.dut_port},
        "usb_scope": {
            "ports_opened_by_runner": [args.dut_port],
            "port_enumeration_by_runner": False,
            "external_fixture_port": None,
            "cardputer_ports_opened": 0,
        },
        "firmware_source_commit": FIRMWARE_SOURCE,
        "failure_source_commit": FAILURE_SOURCE,
        "candidate": passed["candidate"],
        "exact_cid": EXPECTED_CID,
        "proposal": {
            "id": PROPOSAL_ID,
            "target_id": TARGET_ID,
            "candidate_identity_hex": CANDIDATE_IDENTITY,
            "decision": "reject",
        },
        "transition": {
            "target_revision": [5, 5],
            "target_count": [4, 4],
            "catalog_count": [16, 16],
            "catalog_capacity": 16,
            "target_state_generation": [10, 11],
            "decision_count": [2, 3],
        },
        "atomic_reject": {key: mutation[key] for key in (
            "mutation_action_us", "mutation_elapsed_us",
            "mutation_bytes_written", "mutation_write_calls",
            "mutation_file_syncs", "mutation_directory_syncs",
            "mutation_heap_free_before_mount",
            "mutation_heap_largest_before_mount",
            "mutation_identity_attempts",
            "mutation_identity_transient_retries",
        )},
        "cold_reopened": {
            "target_state_generation": reopened["target_state_generation"],
            "decision_count": reopened["correlation_decision_count"],
            "catalog_count": reopened["catalog_count"],
            "catalog_capacity": reopened["catalog_capacity"],
            "visible_target_count": reopened["target_count"],
            "source_identity_count": reopened["source_identity_count"],
            "truncated": reopened["truncated"],
            "capacity_skipped": reopened["admission_capacity_skipped"],
        },
        "fixture": passed["external_fixture"],
        "flash_count": 1,
        "radio_tx_commands_from_dut": 0,
        "final": {"page": "home", "runtime_owner": "none",
                  "lease_mask": 0},
        "screens": {name: {
            "png": f"frames/{name}.png",
            "png_sha256": digest(frames / f"{name}.png"),
        } for name in FRAMES},
        "precursor": "precursors/immediate-rebuild-failure.json",
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
