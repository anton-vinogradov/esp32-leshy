#!/usr/bin/env python3
"""Validate and atomically stage exact dev.242 Airspace Guard evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import check_airspace_guard_hil_acceptance as acceptance
from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence"
CURRENT_RUNNER = ROOT / "tools/run_1x_airspace_guard_hil.py"
DEFAULT_POSITIVE = EVIDENCE / "board-01-airspace-guard-1.0.0-dev.242"
DEFAULT_NEGATIVE_239 = (
    EVIDENCE / "board-01-airspace-guard-1.0.0-dev.239-failed.json"
)
DEFAULT_NEGATIVE_241 = (
    EVIDENCE / "board-01-airspace-guard-1.0.0-dev.241-failed.json"
)
DEFAULT_EXPECTATIONS = (
    EVIDENCE / "board-01-airspace-guard-1.0.0-dev.242-acceptance.json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for field, value in expected.items():
        require(record.get(field) == value,
                f"{label}.{field}: {record.get(field)!r} != {value!r}")


def safe_input_tree(path: Path, label: str) -> Path:
    resolved = path.resolve()
    require(path.is_dir() and not path.is_symlink(),
            f"{label}: regular source directory required")
    for item in path.rglob("*"):
        require(not item.is_symlink(), f"{label}: symlink rejected: {item}")
    return resolved


def verify_artifact_index(bundle: Path, label: str) -> None:
    index = bundle / "artifacts.sha256"
    require(index.is_file() and not index.is_symlink(),
            f"{label}: artifacts.sha256 missing")
    entries: dict[str, str] = {}
    for number, line in enumerate(
            index.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None,
                f"{label}.artifacts.sha256:{number}: malformed")
        expected, name = match.groups()
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts and
                name not in entries and name != "artifacts.sha256",
                f"{label}.artifacts.sha256:{number}: unsafe/duplicate")
        artifact = bundle / relative
        require(artifact.is_file() and not artifact.is_symlink(),
                f"{label}: indexed artifact missing: {name}")
        require(digest(artifact) == expected,
                f"{label}: indexed artifact hash mismatch: {name}")
        entries[name] = expected
    actual = {
        str(item.relative_to(bundle)) for item in bundle.rglob("*")
        if item.is_file() and item != index
    }
    require(set(entries) == actual,
            f"{label}: artifact inventory mismatch")
    require("run.json" in entries and "firmware.bin" in entries,
            f"{label}: run/firmware not indexed")


def verify_firmware(bundle: Path, candidate: dict[str, Any],
                    label: str) -> None:
    firmware = bundle / "firmware.bin"
    require(digest(firmware) == candidate.get("firmware_sha256"),
            f"{label}: firmware hash mismatch")
    require(app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            f"{label}: embedded app identity mismatch")


def candidate(run: dict[str, Any], label: str) -> dict[str, Any]:
    value = run.get("candidate")
    require(isinstance(value, dict), f"{label}: candidate missing")
    return value


def cleanup_summary(run: dict[str, Any], label: str) -> dict[str, Any]:
    cleanup = run.get("cleanup_after")
    require(isinstance(cleanup, dict), f"{label}: cleanup_after missing")
    final = cleanup.get("final_state")
    require(isinstance(final, dict), f"{label}: final cleanup state missing")
    exact(cleanup, {"complete": True, "errors": []}, f"{label}.cleanup")
    exact(final, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "safety_state": "armed", "safety_latched": False,
    }, f"{label}.cleanup.final_state")
    return {
        "complete": True,
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "safety_state": "armed",
        "safety_latched": False,
    }


def verify_positive(source: Path, expected: dict[str, str]) -> dict[str, Any]:
    verify_artifact_index(source, "positive")
    run = load(source / "run.json")
    current = candidate(run, "positive")
    exact(run, {
        "schema": acceptance.RUN_SCHEMA,
        "passed": True,
        "gate_eligible": True,
        "failures": [],
        "expected_cid": acceptance.CID,
        "runner_source_sha256": expected["runner"],
    }, "positive")
    exact(current, {
        "version": acceptance.VERSION,
        "source_commit": expected["source"],
        "firmware_sha256": expected["firmware"],
        "app_elf_sha256": expected["app"],
        "flashed": True,
    }, "positive.candidate")
    require(current.get("flash_mode") in ("fresh", "reuse_exact"),
            "positive.candidate.flash_mode invalid")
    require(isinstance(run.get("run_id"), str) and
            acceptance.SESSION_ID.fullmatch(run["run_id"]) is not None,
            "positive.run_id invalid")
    verify_firmware(source, current, "positive")
    return run


def verify_dev239_delta(source: Path) -> dict[str, Any]:
    verify_artifact_index(source, "dev239_delta")
    run = load(source / "run.json")
    current = candidate(run, "dev239_delta")
    exact(run, {
        "schema": "leshy.airspace_guard_start_regression_hil.run.v1",
        "passed": True,
        "gate_eligible": False,
        "failures": [],
    }, "dev239_delta")
    exact(current, {
        "version": acceptance.FAILED_VERSION,
        "source_commit": acceptance.FAILED_SOURCE,
        "firmware_sha256": acceptance.FAILED_FIRMWARE,
        "app_elf_sha256": acceptance.FAILED_APP,
        "flashed": True,
        "flash_mode": "fresh",
    }, "dev239_delta.candidate")
    require(digest(source / "run.json") == acceptance.FAILED_DELTA_RUN,
            "dev239_delta: exact run hash mismatch")
    verify_firmware(source, current, "dev239_delta")
    return run


def verify_dev239_full(source: Path) -> dict[str, Any]:
    verify_artifact_index(source, "dev239_full")
    run = load(source / "run.json")
    current = candidate(run, "dev239_full")
    exact(run, {
        "schema": acceptance.RUN_SCHEMA,
        "passed": False,
        "gate_eligible": False,
    }, "dev239_full")
    exact(current, {
        "version": acceptance.FAILED_VERSION,
        "source_commit": acceptance.FAILED_SOURCE,
        "firmware_sha256": acceptance.FAILED_FIRMWARE,
        "app_elf_sha256": acceptance.FAILED_APP,
    }, "dev239_full.candidate")
    require(digest(source / "run.json") == acceptance.FAILED_FULL_RUN,
            "dev239_full: exact run hash mismatch")
    require(digest(source / "artifacts.sha256") == acceptance.FAILED_FULL_INDEX,
            "dev239_full: exact artifact index hash mismatch")
    verify_firmware(source, current, "dev239_full")
    failure = run.get("result_first")
    second = run.get("result_second")
    require(isinstance(failure, dict) and isinstance(second, dict),
            "dev239_full: result evidence missing")
    exact(failure, {
        "capture_state": "failed", "load_status": "invalid_report",
        "ble_worker_status": "complete", "ble_worker_valid": True,
        "ble_scan_status": "valid", "ble_retention_retained": 49,
        "ble_retention_dropped": 0, "findings_dropped": 0,
    }, "dev239_full.result_first")
    exact(second, {
        "capture_state": "result", "load_status": "ready",
        "ble_records": 53, "findings_dropped": 0,
    }, "dev239_full.result_second")
    cleanup_summary(run, "dev239_full")
    return run


def verify_dev241_full(source: Path) -> dict[str, Any]:
    verify_artifact_index(source, "dev241_full")
    run = load(source / "run.json")
    current = candidate(run, "dev241_full")
    exact(run, {
        "schema": acceptance.RUN_SCHEMA,
        "passed": False,
        "gate_eligible": False,
        "runner_source_sha256": acceptance.FAILED_241_RUNNER,
    }, "dev241_full")
    exact(current, {
        "version": acceptance.FAILED_241_VERSION,
        "source_commit": acceptance.FAILED_241_SOURCE,
        "firmware_sha256": acceptance.FAILED_241_FIRMWARE,
        "app_elf_sha256": acceptance.FAILED_241_APP,
    }, "dev241_full.candidate")
    require(digest(source / "run.json") == acceptance.FAILED_241_FULL_RUN,
            "dev241_full: exact run hash mismatch")
    require(digest(source / "artifacts.sha256") ==
            acceptance.FAILED_241_FULL_INDEX,
            "dev241_full: exact artifact index hash mismatch")
    verify_firmware(source, current, "dev241_full")
    first = run.get("result_first")
    second = run.get("result_second")
    require(isinstance(first, dict) and isinstance(second, dict),
            "dev241_full: result evidence missing")
    exact(first, {
        "capture_state": "result", "load_status": "ready",
        "ble_worker_status": "complete", "ble_worker_valid": True,
        "ble_scan_status": "valid", "ble_scan_dropped": 0,
        "ble_retention_retained": 54, "ble_retention_dropped": 0,
        "frames_available": 74, "findings_dropped": 0,
    }, "dev241_full.result_first")
    exact(second, {
        "capture_state": "failed", "load_status": "ready",
        "ble_worker_status": "incomplete_evidence",
        "ble_worker_valid": False, "ble_scan_status": "valid",
        "ble_scan_observed": 1296, "ble_scan_reported": 1296,
        "ble_scan_read": 1296, "ble_scan_accepted": 1295,
        "ble_scan_rejected": 0, "ble_scan_dropped": 1,
        "ble_retention_observed": 1296, "ble_retention_valid": 1296,
        "ble_retention_retained": 64, "ble_retention_dropped": 1,
        "ble_retention_malformed": 0, "evidence_incomplete": True,
        "outcome": "inconclusive", "source_frames_observed": 0,
        "source_frames_dropped": 0, "frames_available": 0,
        "ble_records": 0, "findings_dropped": 0,
    }, "dev241_full.result_second")
    cleanup_summary(run, "dev241_full")
    return run


def negative_dev239(full: dict[str, Any]) -> dict[str, Any]:
    first = full["result_first"]
    second = full["result_second"]
    return {
        "schema": acceptance.NEGATIVE_SCHEMA,
        "status": "failed", "gate_eligible": False,
        "candidate_rejected": True, "board": acceptance.BOARD,
        "port": acceptance.PORT, "rom_mac": acceptance.ROM_MAC,
        "expected_cid": acceptance.CID,
        "candidate": {
            "version": acceptance.FAILED_VERSION,
            "source_commit": acceptance.FAILED_SOURCE,
            "firmware_sha256": acceptance.FAILED_FIRMWARE,
            "app_elf_sha256": acceptance.FAILED_APP,
            "fresh_delta_run_sha256": acceptance.FAILED_DELTA_RUN,
            "failed_full_run_sha256": acceptance.FAILED_FULL_RUN,
            "failed_full_artifact_index_sha256":
                acceptance.FAILED_FULL_INDEX,
        },
        "failure": {
            "first_capture_state": first["capture_state"],
            "first_load_status": first["load_status"],
            "first_ble_worker_status": first["ble_worker_status"],
            "first_ble_worker_valid": first["ble_worker_valid"],
            "first_ble_scan_status": first["ble_scan_status"],
            "first_ble_retention_retained": first["ble_retention_retained"],
            "first_ble_retention_dropped": first["ble_retention_dropped"],
            "first_findings_dropped": first["findings_dropped"],
            "second_capture_state": second["capture_state"],
            "second_load_status": second["load_status"],
            "second_ble_records": second["ble_records"],
            "second_findings_dropped": second["findings_dropped"],
            "root_cause": acceptance.ROOT_CAUSE,
        },
        "post_failure_cleanup": cleanup_summary(full, "dev239_full"),
        "corrective_candidate": {
            "version": acceptance.FAILED_241_VERSION,
            "source_commit": acceptance.FAILED_241_SOURCE,
            "firmware_sha256": acceptance.FAILED_241_FIRMWARE,
            "app_elf_sha256": acceptance.FAILED_241_APP,
            "runner_source_sha256": acceptance.FAILED_241_RUNNER,
            "inspection_budget_records": 128,
            "source_local_wifi_records": 64,
            "source_local_ble_records": 64,
        },
        "cadence": {"accepted_deltas_unchanged": "9/15"},
    }


def negative_dev241(full: dict[str, Any],
                    expected: dict[str, str]) -> dict[str, Any]:
    first = full["result_first"]
    second = full["result_second"]
    fields = {
        "first_capture_state": first["capture_state"],
        "first_load_status": first["load_status"],
        "first_ble_worker_status": first["ble_worker_status"],
        "first_ble_worker_valid": first["ble_worker_valid"],
        "first_ble_scan_status": first["ble_scan_status"],
        "first_ble_scan_dropped": first["ble_scan_dropped"],
        "first_ble_retention_retained": first["ble_retention_retained"],
        "first_ble_retention_dropped": first["ble_retention_dropped"],
        "first_frames_available": first["frames_available"],
        "first_findings_dropped": first["findings_dropped"],
    }
    for output, source in (
            ("second_capture_state", "capture_state"),
            ("second_load_status", "load_status"),
            ("second_ble_worker_status", "ble_worker_status"),
            ("second_ble_worker_valid", "ble_worker_valid"),
            ("second_ble_scan_status", "ble_scan_status"),
            ("second_ble_scan_observed", "ble_scan_observed"),
            ("second_ble_scan_reported", "ble_scan_reported"),
            ("second_ble_scan_read", "ble_scan_read"),
            ("second_ble_scan_accepted", "ble_scan_accepted"),
            ("second_ble_scan_rejected", "ble_scan_rejected"),
            ("second_ble_scan_dropped", "ble_scan_dropped"),
            ("second_ble_retention_observed", "ble_retention_observed"),
            ("second_ble_retention_valid", "ble_retention_valid"),
            ("second_ble_retention_retained", "ble_retention_retained"),
            ("second_ble_retention_dropped", "ble_retention_dropped"),
            ("second_ble_retention_malformed", "ble_retention_malformed"),
            ("second_evidence_incomplete", "evidence_incomplete"),
            ("second_outcome", "outcome"),
            ("second_source_frames_observed", "source_frames_observed"),
            ("second_source_frames_dropped", "source_frames_dropped"),
            ("second_frames_available", "frames_available"),
            ("second_ble_records", "ble_records"),
            ("second_findings_dropped", "findings_dropped")):
        fields[output] = second[source]
    fields["root_cause"] = acceptance.ROOT_CAUSE_241
    return {
        "schema": acceptance.NEGATIVE_SCHEMA,
        "status": "failed", "gate_eligible": False,
        "candidate_rejected": True, "board": acceptance.BOARD,
        "port": acceptance.PORT, "rom_mac": acceptance.ROM_MAC,
        "expected_cid": acceptance.CID,
        "candidate": {
            "version": acceptance.FAILED_241_VERSION,
            "source_commit": acceptance.FAILED_241_SOURCE,
            "firmware_sha256": acceptance.FAILED_241_FIRMWARE,
            "app_elf_sha256": acceptance.FAILED_241_APP,
            "failed_full_run_sha256": acceptance.FAILED_241_FULL_RUN,
            "failed_full_artifact_index_sha256":
                acceptance.FAILED_241_FULL_INDEX,
        },
        "failure": fields,
        "post_failure_cleanup": cleanup_summary(full, "dev241_full"),
        "corrective_candidate": {
            "version": acceptance.VERSION,
            "source_commit": expected["source"],
            "firmware_sha256": expected["firmware"],
            "app_elf_sha256": expected["app"],
            "runner_source_sha256": expected["runner"],
            "inspection_budget_records": 128,
            "source_local_wifi_records": 64,
            "source_local_ble_records": 64,
        },
        "cadence": {"accepted_deltas_unchanged": "9/15"},
    }


def promote(staged: list[tuple[Path, Path]], staging: Path) -> None:
    completed: list[tuple[Path, Path]] = []
    try:
        for source, destination in staged:
            source.replace(destination)
            completed.append((source, destination))
    except OSError:
        for source, destination in reversed(completed):
            if destination.exists() and not source.exists():
                destination.replace(source)
        raise
    shutil.rmtree(staging)


def retain(args: argparse.Namespace) -> dict[str, Any]:
    sources = {
        "positive": safe_input_tree(args.positive, "positive"),
        "dev239_delta": safe_input_tree(args.dev239_delta, "dev239_delta"),
        "dev239_full": safe_input_tree(args.dev239_full, "dev239_full"),
        "dev241_full": safe_input_tree(args.dev241_full, "dev241_full"),
    }
    expected = {
        "source": args.expected_source_commit,
        "firmware": args.expected_firmware_sha256,
        "app": args.expected_app_elf_sha256,
        "runner": args.expected_runner_sha256,
    }
    require(COMMIT.fullmatch(expected["source"]) is not None,
            "expected source must be a full lowercase commit")
    for name in ("firmware", "app", "runner"):
        require(SHA256.fullmatch(expected[name]) is not None,
                f"expected {name} must be lowercase SHA-256")
    require(digest(CURRENT_RUNNER) == expected["runner"],
            "expected runner SHA-256 does not match current HIL runner")
    outputs = [
        args.destination.resolve(), args.negative_dev239.resolve(),
        args.negative_dev241.resolve(), args.expectations.resolve(),
    ]
    require(len(set(outputs)) == 4, "output paths must be distinct")
    parents = {path.parent for path in outputs}
    require(len(parents) == 1, "all outputs must share one parent")
    parent = next(iter(parents))
    require(parent.is_dir() and not parent.is_symlink(),
            "output parent must be an existing regular directory")
    for output in outputs:
        require(not output.exists(), f"destination already exists: {output}")
        for source in sources.values():
            require(output != source and source not in output.parents,
                    "outputs must not be inside source evidence")

    positive = verify_positive(sources["positive"], expected)
    verify_dev239_delta(sources["dev239_delta"])
    full239 = verify_dev239_full(sources["dev239_full"])
    full241 = verify_dev241_full(sources["dev241_full"])

    staging = Path(tempfile.mkdtemp(
        prefix=".airspace-guard-retain-", dir=parent))
    stage_positive = staging / "positive"
    stage_negative239 = staging / "negative-dev239.json"
    stage_negative241 = staging / "negative-dev241.json"
    stage_expectations = staging / "acceptance.json"
    try:
        shutil.copytree(sources["positive"], stage_positive,
                        copy_function=shutil.copy2)
        write(stage_negative239, negative_dev239(full239))
        write(stage_negative241, negative_dev241(full241, expected))
        marker = {
            "schema": acceptance.EXPECTATIONS_SCHEMA,
            "version": acceptance.VERSION,
            "expected_cid": acceptance.CID,
            "run_id": positive["run_id"],
            "source_commit": expected["source"],
            "firmware_sha256": expected["firmware"],
            "app_elf_sha256": expected["app"],
            "runner_source_sha256": expected["runner"],
            "positive_run_sha256": digest(stage_positive / "run.json"),
            "positive_artifact_index_sha256": digest(
                stage_positive / "artifacts.sha256"),
        }
        write(stage_expectations, marker)
        check_args = acceptance.parse_args([
            "--expectations", str(stage_expectations),
            "--positive", str(stage_positive),
            "--negative-dev239", str(stage_negative239),
            "--negative-dev241", str(stage_negative241),
            "--expected-source-commit", expected["source"],
            "--expected-firmware-sha256", expected["firmware"],
            "--expected-app-elf-sha256", expected["app"],
        ])
        failures = acceptance.check(check_args)
        require(not failures, "staged acceptance failed: " + "; ".join(failures))
        promote([
            (stage_positive, outputs[0]),
            (stage_negative239, outputs[1]),
            (stage_negative241, outputs[2]),
            (stage_expectations, outputs[3]),
        ], staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "schema": "leshy.airspace_guard_hil.retention.v1",
        "status": "retained",
        "positive": str(outputs[0]),
        "negative_dev239": str(outputs[1]),
        "negative_dev241": str(outputs[2]),
        "expectations": str(outputs[3]),
        "positive_run_sha256": digest(outputs[0] / "run.json"),
        "positive_artifact_index_sha256": digest(
            outputs[0] / "artifacts.sha256"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", required=True, type=Path)
    parser.add_argument("--dev239-delta", required=True, type=Path)
    parser.add_argument("--dev239-full", required=True, type=Path)
    parser.add_argument("--dev241-full", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-firmware-sha256", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--destination", type=Path, default=DEFAULT_POSITIVE)
    parser.add_argument("--negative-dev239", type=Path,
                        default=DEFAULT_NEGATIVE_239)
    parser.add_argument("--negative-dev241", type=Path,
                        default=DEFAULT_NEGATIVE_241)
    parser.add_argument("--expectations", type=Path,
                        default=DEFAULT_EXPECTATIONS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = retain(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
