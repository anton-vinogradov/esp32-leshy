#!/usr/bin/env python3
"""Run the explicitly authorized six-boundary SD software-reset matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import serial

from capture_1x_ui import PassiveSerial, read_json, synchronize_console


SCHEMA = "leshy.storage.sd.session_store_reset.v1"


def open_synchronized(port: str, timeout: float) -> PassiveSerial:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        device = PassiveSerial()
        device.port = port
        device.baudrate = 115200
        device.timeout = 0.25
        try:
            device.open()
            synchronize_console(device, timeout=min(5.0, max(0.5, deadline - time.monotonic())))
            return device
        except (OSError, serial.SerialException, TimeoutError) as error:
            last_error = error
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass
            time.sleep(0.25)
    raise TimeoutError(f"device did not return on {port}: {last_error}")


def recovery_mismatches(record: dict[str, Any], run_id: str,
                        boundary: int) -> dict[str, dict[str, Any]]:
    expected = {
        "kind": "result",
        "mode": "recovery",
        "status": "valid",
        "run_id": run_id,
        "boundary": boundary,
        "software_reset": True,
        "fingerprint_matched": True,
        "read_permit_status": "permitted",
        "scratch_exists": True,
        "opened_read_only": True,
        "session_store_io_writable": False,
        "generation_allowed": True,
        "reopened_observations": 3,
        "prior_unchanged": True,
        "bytes_written": 0,
        "file_syncs": 0,
        "directory_syncs": 0,
        "owned_after": 0,
        "cleanup_complete": True,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "reset_injection": True,
        "physical_power_cut": False,
        "radio_tx_commands": 0,
    }
    return {
        key: {"expected": value, "actual": record.get(key)}
        for key, value in expected.items()
        if record.get(key) != value
    }


def retryable_media_readiness(record: dict[str, Any], run_id: str,
                              boundary: int) -> bool:
    """Allow retry only for the observed zero-write post-reset SD-not-ready case."""
    expected = {
        "schema": SCHEMA,
        "kind": "result",
        "mode": "recovery",
        "status": "failed",
        "run_id": run_id,
        "boundary": boundary,
        "software_reset": True,
        "fingerprint_matched": False,
        "read_permit_status": "missing_media",
        "session_store_io_writable": False,
        "bytes_written": 0,
        "file_syncs": 0,
        "directory_syncs": 0,
        "owned_after": 0,
        "cleanup_complete": True,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "reset_injection": True,
        "physical_power_cut": False,
        "radio_tx_commands": 0,
    }
    return all(record.get(key) == value for key, value in expected.items())


def read_recovery(port: str, command: str,
                  reconnect_timeout: float) -> dict[str, Any]:
    device = open_synchronized(port, reconnect_timeout)
    try:
        device.write((command + "\n").encode("ascii"))
        device.flush()
        return read_json(device, SCHEMA, "result", timeout=30.0)
    finally:
        device.close()


def recover_with_retry(port: str, command: str, run_id: str, boundary: int,
                       reconnect_timeout: float, attempts: int,
                       backoff: float) -> tuple[dict[str, Any],
                                                 dict[str, dict[str, Any]],
                                                 list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        recovery = read_recovery(port, command, reconnect_timeout)
        mismatches = recovery_mismatches(recovery, run_id, boundary)
        retryable = bool(mismatches) and retryable_media_readiness(
            recovery, run_id, boundary)
        records.append({
            "attempt": attempt,
            "record": recovery,
            "valid": not mismatches,
            "retryable_media_readiness": retryable,
            "mismatches": mismatches,
        })
        if not mismatches or not retryable or attempt == attempts:
            return recovery, mismatches, records
        time.sleep(backoff * (2 ** (attempt - 1)))
    raise AssertionError("bounded recovery loop returned no record")


def run_boundary(port: str, cid: str, run_id: str, boundary: int,
                 reconnect_timeout: float, recovery_attempts: int,
                 recovery_backoff: float) -> dict[str, Any]:
    arm_command = (
        f"storage.sd.session-store reset disposable-write "
        f"{cid} {run_id} {boundary}"
    )
    device = open_synchronized(port, reconnect_timeout)
    try:
        device.write((arm_command + "\n").encode("ascii"))
        device.flush()
        armed = read_json(device, SCHEMA, "armed", timeout=30.0)
        trigger = read_json(device, SCHEMA, "reset_trigger", timeout=30.0)
    finally:
        try:
            device.close()
        except (OSError, serial.SerialException):
            pass

    if armed.get("run_id") != run_id or armed.get("boundary") != boundary:
        raise RuntimeError(f"unexpected armed record: {armed}")
    if trigger.get("run_id") != run_id or trigger.get("boundary") != boundary:
        raise RuntimeError(f"unexpected reset trigger: {trigger}")

    recovery_command = (
        f"storage.sd.session-store recover disposable-read-only "
        f"{cid} {run_id} {boundary}"
    )
    recovery, mismatches, attempts = recover_with_retry(
        port, recovery_command, run_id, boundary, reconnect_timeout,
        recovery_attempts, recovery_backoff)
    return {
        "boundary": boundary,
        "run_id": run_id,
        "arm_command": arm_command,
        "armed": armed,
        "trigger": trigger,
        "recovery_command": recovery_command,
        "recovery": recovery,
        "recovery_attempt_count": len(attempts),
        "recovery_attempts": attempts,
        "valid": not mismatches,
        "mismatches": mismatches,
    }


def recover_existing_boundary(port: str, cid: str, run_id: str,
                              boundary: int,
                              reconnect_timeout: float,
                              recovery_attempts: int,
                              recovery_backoff: float) -> dict[str, Any]:
    recovery_command = (
        f"storage.sd.session-store recover disposable-read-only "
        f"{cid} {run_id} {boundary}"
    )
    recovery, mismatches, attempts = recover_with_retry(
        port, recovery_command, run_id, boundary, reconnect_timeout,
        recovery_attempts, recovery_backoff)
    return {
        "boundary": boundary,
        "run_id": run_id,
        "recovery_command": recovery_command,
        "recovery": recovery,
        "recovery_attempt_count": len(attempts),
        "recovery_attempts": attempts,
        "valid": not mismatches,
        "mismatches": mismatches,
    }


def write_evidence(output: Path, port: str, cid: str, run_prefix: str,
                   boundaries: list[int], runs: list[dict[str, Any]],
                   status: str, operation: str) -> str:
    evidence = {
        "schema": "leshy.storage.sd.session_store_reset_matrix.v1",
        "kind": "result",
        "status": status,
        "operation": operation,
        "port": port,
        "cid": cid,
        "run_prefix": run_prefix,
        "boundaries_requested": boundaries,
        "boundaries_completed": len(runs),
        "all_valid": bool(runs) and all(run["valid"] for run in runs),
        "physical_power_cut": False,
        "runs": runs,
    }
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--cid", required=True)
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundaries", default="1,2,3,4,5,6")
    parser.add_argument("--reconnect-timeout", type=float, default=30.0)
    parser.add_argument("--recovery-attempts", type=int, default=3)
    parser.add_argument("--recovery-backoff", type=float, default=1.0)
    parser.add_argument(
        "--execute-reset-matrix",
        action="store_true",
        help="required acknowledgement that six mid-commit software resets are authorized",
    )
    parser.add_argument(
        "--recover-existing",
        action="store_true",
        help="read-only audit of existing boundary namespaces; performs no reset or write",
    )
    args = parser.parse_args()

    if len(args.cid) != 32 or any(value not in "0123456789ABCDEF" for value in args.cid):
        parser.error("--cid must be exactly 32 uppercase hexadecimal characters")
    if not args.run_prefix or len(args.run_prefix) > 29 or any(
        not (value.isalnum() or value in "-_") for value in args.run_prefix
    ):
        parser.error("--run-prefix must be 1..29 safe token characters")
    if args.execute_reset_matrix == args.recover_existing:
        parser.error("select exactly one of --execute-reset-matrix or --recover-existing")
    if args.recovery_attempts < 1 or args.recovery_attempts > 5:
        parser.error("--recovery-attempts must be in 1..5")
    if args.recovery_backoff < 0.0 or args.recovery_backoff > 10.0:
        parser.error("--recovery-backoff must be in 0..10 seconds")

    try:
        boundaries = [int(value) for value in args.boundaries.split(",")]
    except ValueError:
        parser.error("--boundaries must be a comma-separated subset of 1..6")
    if (not boundaries or len(set(boundaries)) != len(boundaries) or
            any(value < 1 or value > 6 for value in boundaries)):
        parser.error("--boundaries must be a unique comma-separated subset of 1..6")

    runs: list[dict[str, Any]] = []
    operation = "reset_matrix" if args.execute_reset_matrix else "recovery_audit"
    for boundary in boundaries:
        run_id = f"{args.run_prefix}-b{boundary}"
        if args.execute_reset_matrix:
            runs.append(run_boundary(args.port, args.cid, run_id, boundary,
                                     args.reconnect_timeout,
                                     args.recovery_attempts,
                                     args.recovery_backoff))
        else:
            runs.append(recover_existing_boundary(
                args.port, args.cid, run_id, boundary, args.reconnect_timeout,
                args.recovery_attempts, args.recovery_backoff))
        status = "in_progress" if runs[-1]["valid"] else "failed"
        sha256 = write_evidence(args.output, args.port, args.cid,
                                args.run_prefix, boundaries, runs, status,
                                operation)
        if not runs[-1]["valid"]:
            print(json.dumps({
                "status": "failed",
                "boundary": boundary,
                "mismatches": runs[-1]["mismatches"],
                "output": str(args.output),
                "sha256": sha256,
            }, sort_keys=True))
            return 2

    sha256 = write_evidence(args.output, args.port, args.cid, args.run_prefix,
                            boundaries, runs, "valid", operation)
    print(json.dumps({
        "status": "valid",
        "boundaries_completed": len(runs),
        "output": str(args.output),
        "sha256": sha256,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
