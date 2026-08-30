#!/usr/bin/env python3
"""Fail-closed verifier for one exact-candidate product Survey HIL bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from esp_app_identity import app_elf_sha256


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


def parse_hash_index(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"invalid hash-index line {number}")
        digest, relative = parts
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError(f"invalid digest on line {number}") from error
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative in entries:
            raise ValueError(f"unsafe or duplicate path on line {number}: {relative}")
        entries[relative] = digest
    if not entries:
        raise ValueError("empty artifact hash index")
    return entries


def verify_product_bundle(bundle: Path, candidate: Path,
                          expected_version: str) -> dict[str, Any]:
    failures: list[str] = []
    required = ("run.json", "artifacts.sha256", "firmware.bin")
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        return {
            "verified": False, "release_eligible": False,
            "failures": [f"missing required files: {missing}"],
        }
    try:
        hashes = parse_hash_index(bundle / "artifacts.sha256")
    except ValueError as error:
        return {"verified": False, "release_eligible": False,
                "failures": [str(error)]}
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
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
    candidate_hash = sha256_file(candidate)
    try:
        candidate_app = app_elf_sha256(candidate)
    except ValueError as error:
        candidate_app = None
        failures.append(f"invalid candidate app identity: {error}")
    bundled_candidate = bundle / "firmware.bin"
    if sha256_file(bundled_candidate) != candidate_hash:
        failures.append("bundled product candidate differs from promoted candidate")
    else:
        try:
            if app_elf_sha256(bundled_candidate) != candidate_app:
                failures.append("bundled product app identity mismatch")
        except ValueError as error:
            failures.append(f"invalid bundled product app identity: {error}")

    if run.get("schema") != "leshy.product_survey_hil.run.v1":
        failures.append("invalid product run schema")
    if run.get("passed") is not True or run.get("gate_eligible") is not True:
        failures.append("product run is not passed and gate-eligible")
    run_id = run.get("run_id")
    if (not isinstance(run_id, str) or len(run_id) != 32 or
            any(character not in "0123456789abcdef" for character in run_id)):
        failures.append("invalid product run ID")
    candidate_record = run.get("candidate", {})
    flash_mode = candidate_record.get("flash_mode")
    if flash_mode is None:
        # Historical bundles predate explicit exact-reuse accounting and were
        # accepted only when the runner itself completed a fresh flash.
        expected_flashed = True
    elif flash_mode == "fresh":
        expected_flashed = True
    elif flash_mode == "reuse_exact":
        expected_flashed = False
        source_commit = candidate_record.get("source_commit")
        if (not isinstance(source_commit, str) or len(source_commit) != 40 or
                any(character not in "0123456789abcdef"
                    for character in source_commit)):
            failures.append("exact-reuse candidate source commit is invalid")
    else:
        expected_flashed = False
        failures.append(f"unsupported product candidate flash mode: {flash_mode!r}")
    expected_candidate = {
        "firmware_sha256": candidate_hash,
        "app_elf_sha256": candidate_app,
        "version": expected_version,
        "flashed": expected_flashed,
    }
    for field, expected in expected_candidate.items():
        if candidate_record.get(field) != expected:
            failures.append(f"product candidate mismatch: {field}")
    cid = run.get("expected_cid")
    if (not isinstance(cid, str) or len(cid) != 32 or cid.upper() != cid or
            any(character not in "0123456789ABCDEF" for character in cid)):
        failures.append("invalid product media CID")

    for name in ("boot_before", "boot_after"):
        boot = run.get(name, {})
        ready = boot.get("ready", {})
        recovery = boot.get("recovery", {})
        for field, expected in {
            "version": expected_version, "app_elf_sha256": candidate_app,
            "buzzer_inactive": True, "input_detected": True,
        }.items():
            if ready.get(field) != expected:
                failures.append(f"{name}.ready mismatch: {field}")
        for field, expected in {
            "status": "admitted", "enrolled": True,
            "expected_fingerprint": cid, "observed_fingerprint": cid,
            "fingerprint_matched": True, "read_only_guaranteed": True,
            "blocked_write_attempts": 0, "catalog_admitted": True,
            "cleanup_complete": True, "physical_write_calls": 0,
        }.items():
            if recovery.get(field) != expected:
                failures.append(f"{name}.recovery mismatch: {field}")

    committed = run.get("committed", {})
    before_generation = run.get("boot_before", {}).get("recovery", {}).get("generation")
    if (not isinstance(before_generation, int) or
            committed.get("survey_generation") != before_generation + 1 or
            committed.get("survey_workflow_status") != "committed" or
            committed.get("survey_product_status") != "committed" or
            committed.get("survey_product_cleanup_complete") is not True):
        failures.append("product commit is not one clean next generation")
    observations = committed.get("survey_observations")
    after_recovery = run.get("boot_after", {}).get("recovery", {})
    if (not isinstance(observations, int) or observations < 1 or
            after_recovery.get("generation") != committed.get("survey_generation") or
            after_recovery.get("observations") != observations or
            after_recovery.get("integrity") != "valid"):
        failures.append("product cold recovery does not match committed Session")

    export = run.get("library_export", {})
    session = export.get("session", {})
    if (export.get("status") != "valid" or export.get("persistent") is not True or
            export.get("simulated") is not False or
            export.get("storage_backend") != "persistent_media" or
            export.get("generation") != committed.get("survey_generation") or
            session.get("id") != "product-wifi-live" or
            session.get("observations") != observations or
            run.get("final_state", {}).get("lease_mask") != 0):
        failures.append("persistent Library export/final cleanup is incomplete")
    captures = run.get("captures", {})
    if set(captures) != {"setup", "running", "committed", "export"}:
        failures.append("product TFT capture set is incomplete")

    return {
        "schema": "leshy.product_survey.bundle_verification.v1",
        "verified": not failures,
        "release_eligible": False,
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": candidate_app,
        "expected_version": expected_version,
        "expected_cid": cid,
        "run_id": run_id,
        "generation": committed.get("survey_generation"),
        "observations": observations,
        "release_trust": "requires_verified_github_artifact_attestation",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    if not args.bundle.is_dir():
        parser.error(f"bundle directory not found: {args.bundle}")
    if not args.candidate.is_file():
        parser.error(f"candidate not found: {args.candidate}")
    result = verify_product_bundle(
        args.bundle.resolve(), args.candidate.resolve(), args.expected_version
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
