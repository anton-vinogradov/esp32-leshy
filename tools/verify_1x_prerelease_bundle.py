#!/usr/bin/env python3
"""Fail-closed verifier for an ESP32-Leshy pre-release HIL evidence bundle."""

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


def verify_bundle(
    bundle: Path,
    candidate: Path,
    suite_id: str,
    suite_revision: int,
    expected_version: str,
    allow_unsigned_development: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    local_result_name = (
        "runner-result.json" if (bundle / "runner-result.json").is_file()
        else "attestation.json"
    )
    required = {"run.json", "candidate-manifest.json", "artifacts.sha256",
                local_result_name}
    missing = sorted(name for name in required if not (bundle / name).is_file())
    if missing:
        return {"verified": False, "release_eligible": False,
                "failures": [f"missing required files: {missing}"]}

    try:
        hashes = parse_hash_index(bundle / "artifacts.sha256")
    except ValueError as error:
        return {"verified": False, "release_eligible": False,
                "failures": [str(error)]}

    indexed_paths = set(hashes)
    actual_paths = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name not in {"artifacts.sha256", local_result_name}
    }
    if indexed_paths != actual_paths:
        failures.append(
            f"artifact index mismatch: missing={sorted(actual_paths - indexed_paths)}, "
            f"extra={sorted(indexed_paths - actual_paths)}"
        )
    for relative, expected_hash in hashes.items():
        path = bundle / relative
        if not path.is_file():
            failures.append(f"indexed artifact missing: {relative}")
        elif sha256_file(path) != expected_hash:
            failures.append(f"artifact hash mismatch: {relative}")

    run = load_object(bundle / "run.json")
    manifest = load_object(bundle / "candidate-manifest.json")
    local_result = load_object(bundle / local_result_name)
    candidate_hash = sha256_file(candidate)
    try:
        candidate_app_elf_sha = app_elf_sha256(candidate)
    except ValueError as error:
        failures.append(f"invalid candidate app identity: {error}")
        candidate_app_elf_sha = None
    run_schema = run.get("schema")
    if run_schema not in {"leshy.prerelease.run.v1", "leshy.prerelease.run.v2"}:
        failures.append("invalid run schema")
    if not run.get("passed") or not run.get("gate_eligible"):
        failures.append("run is not passed and gate-eligible")
    if run.get("suite_id") != suite_id or run.get("suite_revision") != suite_revision:
        failures.append("run suite identity mismatch")
    ready = run.get("boot", {}).get("ready", {})
    if not isinstance(ready, dict) or ready.get("version") != expected_version:
        failures.append("firmware-reported version mismatch")
    if (candidate_app_elf_sha is None or
            not isinstance(ready, dict) or
            ready.get("app_elf_sha256") != candidate_app_elf_sha):
        failures.append("firmware-reported app ELF SHA-256 mismatch")
    if manifest.get("firmware_sha256") != candidate_hash:
        failures.append("candidate file does not match candidate manifest")
    if run.get("candidate_sha256") != candidate_hash:
        failures.append("candidate file does not match run")
    if run.get("candidate_app_elf_sha256") != candidate_app_elf_sha:
        failures.append("candidate app identity does not match run")
    if manifest.get("app_elf_sha256") != candidate_app_elf_sha:
        failures.append("candidate app identity does not match candidate manifest")
    if run_schema == "leshy.prerelease.run.v2":
        run_id = run.get("run_id")
        if (not isinstance(run_id, str) or len(run_id) != 32 or
                any(character not in "0123456789abcdef" for character in run_id)):
            failures.append("invalid run session id")
        if manifest.get("schema") != "leshy.prerelease.candidate.v2":
            failures.append("invalid session-bound candidate manifest schema")
        embedded_candidate = bundle / "candidate" / "firmware.bin"
        if manifest.get("firmware") != "candidate/firmware.bin":
            failures.append("candidate manifest does not use the bundled firmware")
        if not embedded_candidate.is_file():
            failures.append("bundled candidate firmware is missing")
        else:
            try:
                embedded_identity = app_elf_sha256(embedded_candidate)
            except ValueError as error:
                failures.append(f"invalid bundled candidate app identity: {error}")
            else:
                if (sha256_file(embedded_candidate) != candidate_hash or
                        embedded_identity != candidate_app_elf_sha):
                    failures.append("bundled candidate identity mismatch")
        if manifest.get("run_id") != run_id:
            failures.append("candidate manifest session mismatch")
        if local_result.get("schema") not in {
            "leshy.prerelease.runner_result.v1",
            "leshy.prerelease.attestation.v2",
        }:
            failures.append("invalid session-bound local-result schema")
        if local_result.get("run_id") != run_id:
            failures.append("local-result session mismatch")
        hil_session = run.get("hil_session", {})
        begin = hil_session.get("begin", {}) if isinstance(hil_session, dict) else {}
        end = hil_session.get("end", {}) if isinstance(hil_session, dict) else {}
        if (not isinstance(begin, dict) or begin.get("status") != "begun" or
                begin.get("session_id") != run_id or begin.get("active") is not True or
                begin.get("app_elf_sha256") != candidate_app_elf_sha):
            failures.append("HIL session begin binding mismatch")
        if (not isinstance(end, dict) or end.get("status") != "ended" or
                end.get("session_id") != run_id or end.get("active") is not False or
                end.get("app_elf_sha256") != candidate_app_elf_sha):
            failures.append("HIL session end binding mismatch")
    else:
        run_id = None
    if not manifest.get("flashed_by_runner"):
        failures.append("candidate was not flashed by the runner")
    hash_index_sha = hashlib.sha256(
        (bundle / "artifacts.sha256").read_bytes()
    ).hexdigest()
    if local_result.get("bundle_sha256") != hash_index_sha:
        failures.append("local-result bundle hash mismatch")
    if local_result.get("candidate_sha256") != candidate_hash:
        failures.append("local-result candidate mismatch")
    if local_result.get("app_elf_sha256") != candidate_app_elf_sha:
        failures.append("local-result app identity mismatch")
    if (local_result.get("suite_id") != suite_id or
            local_result.get("suite_revision") != suite_revision):
        failures.append("local-result suite identity mismatch")
    if not local_result.get("passed"):
        failures.append("local result does not report pass")

    trust_status = local_result.get(
        "trust_status", local_result.get("signature_status")
    )
    development_verified = False
    if trust_status in {"unsigned_local_result", "unsigned_development"}:
        if allow_unsigned_development:
            development_verified = not failures
        else:
            failures.append("unsigned local runner result is not accepted by itself")
    else:
        failures.append(f"unsupported local-result trust status: {trust_status!r}")

    return {
        "schema": "leshy.prerelease.bundle_verification.v1",
        "verified": not failures,
        "development_verified": development_verified,
        "release_eligible": False,
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": candidate_app_elf_sha,
        "suite_id": suite_id,
        "suite_revision": suite_revision,
        "trust_status": trust_status,
        "release_trust": "requires_verified_github_artifact_attestation",
        "run_id": run_id,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--candidate", type=Path,
                        help="candidate to promote; defaults to bundle candidate")
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--suite-revision", required=True, type=int)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--allow-unsigned-local-result", "--allow-unsigned-development",
        dest="allow_unsigned_development", action="store_true",
        help=(
            "accept local bundle integrity without release trust; the legacy "
            "--allow-unsigned-development spelling remains supported"
        ),
    )
    args = parser.parse_args()
    if not args.bundle.is_dir():
        parser.error(f"bundle directory not found: {args.bundle}")
    candidate = (args.candidate if args.candidate is not None else
                 args.bundle / "candidate" / "firmware.bin")
    if not candidate.is_file():
        parser.error(f"candidate not found: {candidate}")
    result = verify_bundle(
        args.bundle.resolve(), candidate.resolve(), args.suite_id,
        args.suite_revision, args.expected_version,
        args.allow_unsigned_development,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
