#!/usr/bin/env python3
"""Verify combined product + isolated generic 1.x release HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from verify_1x_prerelease_bundle import parse_hash_index, verify_bundle
from verify_1x_product_survey_bundle import verify_product_bundle


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_release_bundle(bundle: Path, candidate: Path, suite_id: str,
                          suite_revision: int,
                          expected_version: str) -> dict[str, Any]:
    failures: list[str] = []
    required = ("run.json", "runner-result.json", "artifacts.sha256")
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        return {"verified": False, "release_eligible": False,
                "failures": [f"missing required files: {missing}"]}
    try:
        hashes = parse_hash_index(bundle / "artifacts.sha256")
    except ValueError as error:
        return {"verified": False, "release_eligible": False,
                "failures": [str(error)]}
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name not in {
            "artifacts.sha256", "runner-result.json"
        }
    }
    if set(hashes) != actual:
        failures.append(
            f"artifact index mismatch: missing={sorted(actual - set(hashes))}, "
            f"extra={sorted(set(hashes) - actual)}"
        )
    for relative, expected in hashes.items():
        path = bundle / relative
        if not path.is_file():
            failures.append(f"indexed artifact missing: {relative}")
        elif sha256_file(path) != expected:
            failures.append(f"artifact hash mismatch: {relative}")

    run = load_object(bundle / "run.json")
    local = load_object(bundle / "runner-result.json")
    candidate_hash = sha256_file(candidate)
    try:
        candidate_app = app_elf_sha256(candidate)
    except ValueError as error:
        candidate_app = None
        failures.append(f"invalid candidate app identity: {error}")
    if run.get("schema") != "leshy.release_hil.run.v1":
        failures.append("invalid combined release HIL schema")
    if run.get("passed") is not True or run.get("gate_eligible") is not True:
        failures.append("combined release HIL is not passed and gate-eligible")
    for field, expected in {
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": candidate_app,
        "expected_version": expected_version,
        "candidate_flashed": True,
    }.items():
        if run.get(field) != expected:
            failures.append(f"combined candidate mismatch: {field}")

    product = verify_product_bundle(
        bundle / "product", candidate, expected_version
    )
    if not product.get("verified"):
        failures.extend(
            f"product: {failure}" for failure in product.get("failures", [])
        )
    generic = verify_bundle(
        bundle / "generic", candidate, suite_id, suite_revision,
        expected_version, True,
    )
    if not generic.get("verified"):
        failures.extend(
            f"generic: {failure}" for failure in generic.get("failures", [])
        )
    product_summary = run.get("product", {})
    generic_summary = run.get("generic", {})
    for field, expected in {
        "run_id": product.get("run_id"), "return_code": 0,
        "passed": True, "gate_eligible": True,
        "expected_cid": product.get("expected_cid"),
        "generation": product.get("generation"),
        "observations": product.get("observations"),
    }.items():
        if product_summary.get(field) != expected:
            failures.append(f"product summary mismatch: {field}")
    for field, expected in {
        "run_id": generic.get("run_id"), "return_code": 0,
        "passed": True, "gate_eligible": True,
        "suite_id": suite_id, "suite_revision": suite_revision,
    }.items():
        if generic_summary.get(field) != expected:
            failures.append(f"generic summary mismatch: {field}")

    cid = product.get("expected_cid")
    generation = product.get("generation")
    observations = product.get("observations")
    isolation = run.get("state_isolation", {})
    unenroll = isolation.get("unenroll", {})
    for field, expected in {
        "mode": "unenroll", "status": "valid", "was_enrolled": True,
        "cleared_fingerprint": cid, "nvs_key_removed": True,
        "sd_accessed": False, "sd_data_untouched": True,
        "active_catalog_unchanged": True, "reboot_required": True,
        "physical_write_calls": 0,
    }.items():
        if unenroll.get(field) != expected:
            failures.append(f"unenroll mismatch: {field}")
    reenroll = isolation.get("reenroll", {})
    for field, expected in {
        "mode": "enroll", "status": "valid",
        "expected_fingerprint": cid, "observed_fingerprint": cid,
        "fingerprint_matched": True, "mounted_read_only": True,
        "read_only_guaranteed": True, "write_enabled": False,
        "blocked_write_attempts": 0, "catalog_status": "admitted",
        "catalog_admitted": True, "generation": generation,
        "observations": observations, "enrollment_saved": True,
        "owned_after": 0, "cleanup_complete": True,
        "physical_write_calls": 0,
    }.items():
        if reenroll.get(field) != expected:
            failures.append(f"reenroll mismatch: {field}")
    final = isolation.get("final_boot", {})
    ready = final.get("ready", {})
    recovery = final.get("recovery", {})
    state = final.get("state", {})
    for field, expected in {
        "version": expected_version, "app_elf_sha256": candidate_app,
        "buzzer_inactive": True, "input_detected": True,
    }.items():
        if ready.get(field) != expected:
            failures.append(f"final ready mismatch: {field}")
    for field, expected in {
        "status": "admitted", "enrolled": True,
        "expected_fingerprint": cid, "observed_fingerprint": cid,
        "fingerprint_matched": True, "mounted_read_only": True,
        "read_only_guaranteed": True, "blocked_write_attempts": 0,
        "catalog_status": "admitted", "catalog_admitted": True,
        "generation": generation, "observations": observations,
        "integrity": "valid", "owned_after": 0,
        "cleanup_complete": True, "physical_write_calls": 0,
    }.items():
        if recovery.get(field) != expected:
            failures.append(f"final recovery mismatch: {field}")
    for field, expected in {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_persistent": True, "library_simulated": False,
        "library_generation": generation,
    }.items():
        if state.get(field) != expected:
            failures.append(f"final state mismatch: {field}")

    index_hash = hashlib.sha256(
        (bundle / "artifacts.sha256").read_bytes()
    ).hexdigest()
    for field, expected in {
        "schema": "leshy.release_hil.runner_result.v1",
        "candidate_sha256": candidate_hash,
        "app_elf_sha256": candidate_app,
        "product_run_id": product.get("run_id"),
        "generic_run_id": generic.get("run_id"),
        "suite_id": suite_id, "suite_revision": suite_revision,
        "passed": True, "gate_eligible": False,
        "bundle_sha256": index_hash,
        "trust_status": "unsigned_local_result",
    }.items():
        if local.get(field) != expected:
            failures.append(f"combined local result mismatch: {field}")

    return {
        "schema": "leshy.release_hil.bundle_verification.v1",
        "verified": not failures,
        "development_verified": not failures,
        "release_eligible": False,
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": candidate_app,
        "product_run_id": product.get("run_id"),
        "generic_run_id": generic.get("run_id"),
        "suite_id": suite_id, "suite_revision": suite_revision,
        "release_trust": "requires_verified_github_artifact_attestation",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--suite-revision", required=True, type=int)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    if not args.bundle.is_dir():
        parser.error(f"bundle directory not found: {args.bundle}")
    if not args.candidate.is_file():
        parser.error(f"candidate not found: {args.candidate}")
    result = verify_release_bundle(
        args.bundle.resolve(), args.candidate.resolve(), args.suite_id,
        args.suite_revision, args.expected_version,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
