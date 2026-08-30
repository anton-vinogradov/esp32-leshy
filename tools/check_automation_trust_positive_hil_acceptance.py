#!/usr/bin/env python3
"""Fail closed unless retained positive Automation trust evidence is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT / "tests/hil/evidence/board-01-automation-trust-positive-1.0.0-dev.308.json")
SOURCE = "c70ab42739faab639b65c2fb77905718921fa676"
RUNNER_COMMIT = "ae2ecbf88cfb3d10fb03739fb8591a844dc1d134"
RUNNER_SHA = "d5384fb30e80f6f38baec4ede93b61a034c63f86864274ae172ad8cef0d356c7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    expected = {
        "automation-owner.json", "automation-owner.lhak",
        "automation-trust-cold-restore.ndjson",
        "automation-trust-final-clean.ndjson", "provenance.json", "run.json",
    }
    expected.update({f"frames/{name}" for name in (
        "automation-trust-import-review-a.png",
        "automation-trust-import-review-b.png",
        "automation-trust-enrolled.png",
        "automation-trust-revoke-review-a.png",
        "automation-trust-revoke-review-b.png",
        "automation-trust-revoked.png",
    )})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.automation_trust_positive_hil.summary.v1" and
            summary.get("status") == "pass_with_retained_negative_predecessor" and
            summary.get("evidence_ids") ==
            ["E-BUILD-210", "E-AUTO-185", "E-HIL-218", "E-SEC-085",
             "E-STORAGE-068", "RB-M221"],
            "summary identity mismatch")
    require(failures, summary.get("firmware_source_commit") == SOURCE and
            summary.get("runner_commit") == RUNNER_COMMIT,
            "source/runner commit mismatch")
    require(failures, summary.get("candidate") == {
        "app_elf_sha256":
            "66e29c6337fddf89a3fe554def643c3cc167843c5a88125f765c952951e9c4c0",
        "elf_sha256":
            "66e29c6337fddf89a3fe554def643c3cc167843c5a88125f765c952951e9c4c0",
        "firmware_bytes": 3563504,
        "firmware_sha256":
            "d68155a47d47181547843d1ab2f89056fd98a5ce5863a05846604fae2637e866",
        "map_sha256":
            "96f803134e9dc83f849cdc6856a252be1035cb329c36dc3f873859b7d87e0128",
        "version": "1.0.0-dev.308",
    } and summary.get("factory_sha256") ==
        "658eb147d214ac8f0fdd0b8bfe40d9a15b6928167974b69efae0cb28e590522f",
            "candidate identity mismatch")
    require(failures, summary.get("lineage") == {
        "candidate_flashes": 1,
        "accepted_run_flashes": 0,
        "accepted_run_reused_installed_candidate": True,
        "accepted_run_hardware_resets": 2,
        "reset_capture_attempts": 2,
        "reset_capture_transient_retries": 0,
    }, "accepted lineage mismatch")
    require(failures, summary.get("public_bundle") == {
        "algorithm": "ecdsa_p256_sha256",
        "bundle_bytes": 128,
        "bundle_sha256":
            "426eb188dd0ba3f4386435c8bb59f7f250d87e8fb8a1402e3f250fbbe5986408",
        "contains_private_key": False,
        "key_id": "72b53a9dcfb4d96b",
        "label": "GitHub owner key",
        "public_key_sha256":
            "72b53a9dcfb4d96b9fabc1d0b80abc950be7649678d7c7d88f50bb0793d48407",
        "retained_bundle_sha256":
            "426eb188dd0ba3f4386435c8bb59f7f250d87e8fb8a1402e3f250fbbe5986408",
        "retained_metadata_sha256":
            "713cf315d8741dac99305aba7b4d856feabb6962a7bcbb8ee0a88b661342879d",
        "schema": "leshy.automation.trust_bundle.v1",
    }, "public-only bundle mismatch")
    storage = summary.get("storage", {})
    require(failures,
            storage.get("cid") == "FE343253440000002000000055019CB7" and
            storage.get("scratch_path", "").startswith("/leshy-hil/") and
            storage.get("bytes_written") == 128 and
            storage.get("write_calls") == storage.get("file_syncs") ==
            storage.get("directory_syncs") == 1 and
            storage.get("exact_entries") is True and
            storage.get("files_removed") == 1 and
            storage.get("namespace_cleared") is True,
            "durable scratch storage mismatch")
    require(failures, summary.get("trust_transition") == {
        "product_before": {"count": 0, "generation": 0},
        "isolated_before": {"count": 0, "generation": 0},
        "enrolled": {"count": 1, "generation": 1},
        "cold_restored": {"count": 1, "generation": 1},
        "revoked": {"count": 0, "generation": 2},
        "product_after": {"count": 0, "generation": 0},
        "final_cold_boot": {"count": 0, "generation": 0},
    }, "trust lifecycle mismatch")
    for name, screen in summary.get("stable_frames", {}).items():
        pair = screen.get("pair", [])
        require(failures, len(pair) == 2 and
                all((bundle / path).is_file() for path in pair) and
                digest(bundle / pair[0]) == digest(bundle / pair[1]) ==
                screen.get("png_sha256"), f"unstable screen pair: {name}")
    require(failures, set(summary.get("stable_frames", {})) ==
            {"import_review", "revoke_review"}, "stable screen set mismatch")
    require(failures, summary.get("safe") == {
        "action_invocations": 0,
        "hid_reports": 0,
        "rf_transmit_attempts": 0,
        "radio_tx_commands": 0,
        "private_key_used_or_stored": False,
        "product_trust_namespace_written_or_erased": False,
        "device_lock_product_restored": True,
        "wifi_host_touched": False,
        "forbidden_ports_touched": [],
    }, "safe-output boundary mismatch")
    cleanup = summary.get("cleanup", {})
    require(failures, cleanup.get("complete") is True and
            cleanup.get("final_cold_boot_clean") is True and
            cleanup.get("product_lock_restored") is True and
            cleanup.get("product_trust_restored") is True and
            cleanup.get("scratch_removed") is True and
            cleanup.get("hil_ended") is True and cleanup.get("errors") == [],
            "terminal cleanup mismatch")
    require(failures, summary.get("boot_captures") == [
        "automation-trust-cold-restore.ndjson",
        "automation-trust-final-clean.ndjson",
    ], "boot capture list mismatch")

    failure_ref = summary.get("predecessor_failure", {})
    failure_path = ROOT / failure_ref.get("path", "missing")
    failure = (json.loads(failure_path.read_text(encoding="utf-8"))
               if failure_path.is_file() else {})
    require(failures, failure_path.is_file() and
            digest(failure_path) == failure_ref.get("sha256") and
            failure.get("schema") ==
            "leshy.automation_trust_positive_hil.failure.v1" and
            failure.get("status") == "failed_as_expected_and_preserved" and
            failure.get("failure_class") ==
            "cold_restore_bundle_match_telemetry_false_negative" and
            failure.get("cleanup_complete") is True and
            failure.get("hil_ended") is True and
            failure.get("radio_tx_commands") == 0,
            "negative predecessor evidence mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    provenance_path = bundle / "provenance.json"
    provenance = (json.loads(provenance_path.read_text(encoding="utf-8"))
                  if provenance_path.is_file() else {})
    require(failures, provenance.get("firmware_source_commit") == SOURCE and
            provenance.get("runner_commit") == RUNNER_COMMIT and
            provenance.get("runner_sha256") == RUNNER_SHA and
            provenance.get("predecessor_failure_summary_sha256") ==
            failure_ref.get("sha256"), "provenance identity mismatch")
    try:
        runner = subprocess.check_output(
            ["git", "show",
             f"{RUNNER_COMMIT}:tools/run_1x_automation_trust_positive_hil.py"],
            cwd=ROOT)
        require(failures, hashlib.sha256(runner).hexdigest() == RUNNER_SHA,
                "runner blob mismatch")
        for path, expected_hash in provenance.get("source_sha256", {}).items():
            blob = subprocess.check_output(
                ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT)
            require(failures, hashlib.sha256(blob).hexdigest() == expected_hash,
                    f"source blob mismatch: {path}")
    except subprocess.CalledProcessError as error:
        failures.append(f"git provenance lookup failed: {error}")
    if failures:
        for failure_message in failures:
            print(f"FAIL: {failure_message}", file=sys.stderr)
        return 1
    print("Automation trust positive HIL acceptance passed: public-only enroll/cold-restore/revoke/cleanup, exact SD, zero output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
