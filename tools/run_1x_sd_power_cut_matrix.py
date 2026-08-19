#!/usr/bin/env python3
"""Run the explicitly authorized six-boundary physical SD power-cut matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

import serial
from serial.tools import list_ports

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.storage.sd.session_store_reset.v1"
BOOT_SCHEMA = "leshy.boot.v1"
POWER_ON_RESET_REASON = 1


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def usb_identity(port: str) -> dict[str, Any]:
    for candidate in list_ports.comports():
        if candidate.device == port:
            identity = {
                "device": candidate.device,
                "serial_number": candidate.serial_number,
                "vid": candidate.vid,
                "pid": candidate.pid,
                "location": candidate.location,
            }
            if not identity["serial_number"] or identity["vid"] is None or \
                    identity["pid"] is None:
                raise RuntimeError(
                    "USB serial/VID/PID are required for physical power-cut identity")
            return identity
    raise RuntimeError(f"serial device is not enumerated: {port}")


def matching_port(identity: dict[str, Any]) -> str | None:
    matches = [
        candidate.device for candidate in list_ports.comports()
        if candidate.serial_number == identity.get("serial_number") and
        candidate.vid == identity.get("vid") and
        candidate.pid == identity.get("pid")
    ]
    if len(matches) > 1 and identity.get("location"):
        matches = [
            candidate.device for candidate in list_ports.comports()
            if candidate.serial_number == identity.get("serial_number") and
            candidate.vid == identity.get("vid") and
            candidate.pid == identity.get("pid") and
            candidate.location == identity.get("location")
        ]
    return matches[0] if len(matches) == 1 else None


def open_synchronized(identity: dict[str, Any], timeout: float) -> PassiveSerial:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        port = matching_port(identity)
        if port is None:
            time.sleep(0.1)
            continue
        device = PassiveSerial()
        device.port = port
        device.baudrate = 115200
        device.timeout = 0.25
        try:
            device.open()
            synchronize_console(
                device, timeout=min(5.0, max(0.5, deadline - time.monotonic())))
            return device
        except (OSError, serial.SerialException, TimeoutError) as error:
            last_error = error
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass
            time.sleep(0.25)
    raise TimeoutError(f"device did not return: {last_error}")


def read_boot(device: PassiveSerial) -> dict[str, Any]:
    device.write(b"metrics\n")
    device.flush()
    return read_json(device, BOOT_SCHEMA, "ready", timeout=10.0)


def exact_boot_mismatches(boot: dict[str, Any], version: str,
                          app_hash: str,
                          require_power_on: bool) -> dict[str, dict[str, Any]]:
    expected: dict[str, Any] = {
        "version": version,
        "app_elf_sha256": app_hash,
        "input_detected": True,
        "buzzer_inactive": True,
        "buzzer_safety_configured": True,
    }
    if require_power_on:
        expected["reset_reason_code"] = POWER_ON_RESET_REASON
    return {
        key: {"expected": value, "actual": boot.get(key)}
        for key, value in expected.items() if boot.get(key) != value
    }


def arm_mismatches(record: dict[str, Any], run_id: str,
                   boundary: int) -> dict[str, dict[str, Any]]:
    expected = {
        "schema": SCHEMA,
        "kind": "armed",
        "status": "ready",
        "run_id": run_id,
        "boundary": boundary,
        "fingerprint_matched": True,
        "initial_generation": 1,
        "initial_observations": 3,
        "format_allowed": False,
        "writes_bounded_to_scratch": True,
        "reset_injection": False,
        "physical_power_cut": True,
        "radio_tx_commands": 0,
    }
    return {
        key: {"expected": value, "actual": record.get(key)}
        for key, value in expected.items() if record.get(key) != value
    }


def trigger_mismatches(record: dict[str, Any], run_id: str,
                       boundary: int) -> dict[str, dict[str, Any]]:
    expected = {
        "schema": SCHEMA,
        "kind": "reset_trigger",
        "status": "boundary_reached",
        "run_id": run_id,
        "boundary": boundary,
        "reset_injection": False,
        "physical_power_cut": True,
    }
    return {
        key: {"expected": value, "actual": record.get(key)}
        for key, value in expected.items() if record.get(key) != value
    }


def recovery_mismatches(record: dict[str, Any], run_id: str,
                        boundary: int) -> dict[str, dict[str, Any]]:
    expected = {
        "schema": SCHEMA,
        "kind": "result",
        "mode": "recovery",
        "status": "valid",
        "run_id": run_id,
        "boundary": boundary,
        "reset_reason_code": POWER_ON_RESET_REASON,
        "software_reset": False,
        "power_on_reset": True,
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
        "reset_injection": False,
        "physical_power_cut": True,
        "radio_tx_commands": 0,
    }
    return {
        key: {"expected": value, "actual": record.get(key)}
        for key, value in expected.items() if record.get(key) != value
    }


def retryable_media_readiness(record: dict[str, Any], run_id: str,
                              boundary: int) -> bool:
    expected = {
        "schema": SCHEMA,
        "kind": "result",
        "mode": "recovery",
        "status": "failed",
        "run_id": run_id,
        "boundary": boundary,
        "reset_reason_code": POWER_ON_RESET_REASON,
        "software_reset": False,
        "power_on_reset": True,
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
        "reset_injection": False,
        "physical_power_cut": True,
        "radio_tx_commands": 0,
    }
    return all(record.get(key) == value for key, value in expected.items())


def emit_progress(event: str, boundary: int, **extra: Any) -> None:
    print(json.dumps({
        "schema": "leshy.host.physical_power_cut.v1",
        "event": event,
        "boundary": boundary,
        **extra,
    }, sort_keys=True), flush=True)


def wait_for_power_cycle(identity: dict[str, Any], boundary: int,
                         disconnect_timeout: float,
                         minimum_blackout: float,
                         reconnect_timeout: float) -> dict[str, Any]:
    emit_progress("disconnect_power_now", boundary,
                  minimum_blackout_seconds=minimum_blackout)
    deadline = time.monotonic() + disconnect_timeout
    while matching_port(identity) is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    if matching_port(identity) is not None:
        raise TimeoutError("USB device never disappeared; physical cut not observed")
    disconnected_at = time.monotonic()
    emit_progress("power_absent", boundary)

    while time.monotonic() - disconnected_at < minimum_blackout:
        if matching_port(identity) is not None:
            raise RuntimeError("USB returned before the minimum blackout interval")
        time.sleep(0.05)
    blackout_floor_at = time.monotonic()
    emit_progress("minimum_blackout_satisfied_reconnect_now", boundary)

    deadline = time.monotonic() + reconnect_timeout
    port: str | None = None
    while time.monotonic() < deadline:
        port = matching_port(identity)
        if port is not None:
            break
        time.sleep(0.1)
    if port is None:
        raise TimeoutError("USB device did not return after physical cut")
    reconnected_at = time.monotonic()
    return {
        "disconnect_observed": True,
        "reconnect_observed": True,
        "minimum_blackout_seconds": minimum_blackout,
        "blackout_seconds": reconnected_at - disconnected_at,
        "reconnect_after_floor_seconds": reconnected_at - blackout_floor_at,
        "reconnected_port": port,
        "same_usb_identity": True,
    }


def read_recovery(identity: dict[str, Any], command: str,
                  reconnect_timeout: float, version: str,
                  app_hash: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    device = open_synchronized(identity, reconnect_timeout)
    try:
        port = str(device.port)
        boot = read_boot(device)
        boot_mismatches = exact_boot_mismatches(
            boot, version, app_hash, require_power_on=True)
        if boot_mismatches:
            raise RuntimeError(f"post-cut boot identity mismatch: {boot_mismatches}")
        device.write((command + "\n").encode("ascii"))
        device.flush()
        recovery = read_json(device, SCHEMA, "result", timeout=30.0)
        return boot, recovery, port
    finally:
        device.close()


def recover_with_retry(identity: dict[str, Any], command: str, run_id: str,
                       boundary: int, reconnect_timeout: float, attempts: int,
                       backoff: float, version: str,
                       app_hash: str) -> tuple[dict[str, Any],
                                                dict[str, dict[str, Any]],
                                                list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        boot, recovery, port = read_recovery(
            identity, command, reconnect_timeout, version, app_hash)
        mismatches = recovery_mismatches(recovery, run_id, boundary)
        retryable = bool(mismatches) and retryable_media_readiness(
            recovery, run_id, boundary)
        records.append({
            "attempt": attempt,
            "port": port,
            "boot": boot,
            "record": recovery,
            "valid": not mismatches,
            "retryable_media_readiness": retryable,
            "mismatches": mismatches,
        })
        if not mismatches or not retryable or attempt == attempts:
            return recovery, mismatches, records
        time.sleep(backoff * (2 ** (attempt - 1)))
    raise AssertionError("bounded recovery loop returned no record")


def run_boundary(identity: dict[str, Any], cid: str, run_id: str,
                 boundary: int, version: str, app_hash: str,
                 disconnect_timeout: float, minimum_blackout: float,
                 reconnect_timeout: float, recovery_attempts: int,
                 recovery_backoff: float,
                 trigger_checkpoint: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    arm_command = (
        f"storage.sd.session-store power-cut disposable-write "
        f"{cid} {run_id} {boundary}"
    )
    device = open_synchronized(identity, reconnect_timeout)
    try:
        preflight_boot = read_boot(device)
        boot_mismatches = exact_boot_mismatches(
            preflight_boot, version, app_hash, require_power_on=False)
        if boot_mismatches:
            raise RuntimeError(f"preflight boot identity mismatch: {boot_mismatches}")
        device.write((arm_command + "\n").encode("ascii"))
        device.flush()
        armed = read_json(device, SCHEMA, "armed", timeout=30.0)
        armed_mismatches = arm_mismatches(armed, run_id, boundary)
        if armed_mismatches:
            raise RuntimeError(f"power-cut arm mismatch: {armed_mismatches}")
        trigger = read_json(device, SCHEMA, "reset_trigger", timeout=30.0)
        trigger_errors = trigger_mismatches(trigger, run_id, boundary)
        if trigger_errors:
            raise RuntimeError(f"power-cut trigger mismatch: {trigger_errors}")
    finally:
        try:
            device.close()
        except (OSError, serial.SerialException):
            pass

    trigger_checkpoint({
        "boundary": boundary,
        "run_id": run_id,
        "phase": "awaiting_physical_power_cut",
        "arm_command": arm_command,
        "preflight_boot": preflight_boot,
        "armed": armed,
        "trigger": trigger,
    })
    power_cycle = wait_for_power_cycle(
        identity, boundary, disconnect_timeout, minimum_blackout,
        reconnect_timeout)
    recovery_command = (
        f"storage.sd.session-store power-cut-recover disposable-read-only "
        f"{cid} {run_id} {boundary}"
    )
    recovery, mismatches, attempts = recover_with_retry(
        identity, recovery_command, run_id, boundary, reconnect_timeout,
        recovery_attempts, recovery_backoff, version, app_hash)
    return {
        "boundary": boundary,
        "run_id": run_id,
        "phase": "complete" if not mismatches else "failed",
        "arm_command": arm_command,
        "preflight_boot": preflight_boot,
        "armed": armed,
        "trigger": trigger,
        "power_cycle": power_cycle,
        "recovery_command": recovery_command,
        "recovery": recovery,
        "recovery_attempt_count": len(attempts),
        "recovery_attempts": attempts,
        "valid": not mismatches,
        "mismatches": mismatches,
    }


def write_evidence(output: Path, candidate: dict[str, Any],
                   identity: dict[str, Any], cid: str, run_prefix: str,
                   boundaries: list[int], runs: list[dict[str, Any]],
                   status: str, active: dict[str, Any] | None = None) -> str:
    evidence = {
        "schema": "leshy.storage.sd.physical_power_cut_matrix.v1",
        "kind": "result",
        "status": status,
        "candidate": candidate,
        "usb_identity": identity,
        "cid": cid,
        "run_prefix": run_prefix,
        "boundaries_requested": boundaries,
        "boundaries_completed": len(runs),
        "all_valid": len(runs) == len(boundaries) and
            all(run.get("valid") for run in runs),
        "physical_power_cut": True,
        "manual_power_cycles_required": len(boundaries),
        "active": active,
        "runs": runs,
    }
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--cid", required=True)
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundaries", default="1,2,3,4,5,6")
    parser.add_argument("--disconnect-timeout", type=float, default=90.0)
    parser.add_argument("--minimum-blackout", type=float, default=3.0)
    parser.add_argument("--reconnect-timeout", type=float, default=120.0)
    parser.add_argument("--recovery-attempts", type=int, default=3)
    parser.add_argument("--recovery-backoff", type=float, default=1.0)
    parser.add_argument(
        "--execute-physical-power-cut-matrix", action="store_true",
        help="required acknowledgement for six destructive-fixture power cycles")
    args = parser.parse_args()

    if not args.execute_physical_power_cut_matrix:
        parser.error("--execute-physical-power-cut-matrix is required")
    if args.output.exists():
        parser.error("--output must not already exist")
    if not args.firmware.is_file():
        parser.error("--firmware must be an existing exact candidate")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full 40-character commit")
    if len(args.cid) != 32 or any(value not in "0123456789ABCDEF" for value in args.cid):
        parser.error("--cid must be exactly 32 uppercase hexadecimal characters")
    if not args.run_prefix or len(args.run_prefix) > 29 or any(
        not (value.isalnum() or value in "-_") for value in args.run_prefix
    ):
        parser.error("--run-prefix must be a 1..29 character safe token")
    if args.minimum_blackout < 2.0 or args.minimum_blackout > 30.0:
        parser.error("--minimum-blackout must be in 2..30 seconds")
    if args.recovery_attempts < 1 or args.recovery_attempts > 5:
        parser.error("--recovery-attempts must be in 1..5")

    try:
        boundaries = [int(value) for value in args.boundaries.split(",")]
    except ValueError:
        parser.error("--boundaries must be a comma-separated subset of 1..6")
    if not boundaries or len(set(boundaries)) != len(boundaries) or any(
            value < 1 or value > 6 for value in boundaries):
        parser.error("--boundaries must be a unique comma-separated subset of 1..6")

    identity = usb_identity(args.port)
    candidate = {
        "version": args.expected_version,
        "source_commit": args.source_commit,
        "firmware_sha256": digest(args.firmware),
        "app_elf_sha256": app_elf_sha256(args.firmware),
        "firmware_bytes": args.firmware.stat().st_size,
    }
    runs: list[dict[str, Any]] = []
    write_evidence(args.output, candidate, identity, args.cid, args.run_prefix,
                   boundaries, runs, "in_progress")
    for boundary in boundaries:
        run_id = f"{args.run_prefix}-b{boundary}"

        def checkpoint(active: dict[str, Any]) -> None:
            write_evidence(
                args.output, candidate, identity, args.cid, args.run_prefix,
                boundaries, runs, "awaiting_physical_power_cut", active)

        try:
            run = run_boundary(
                identity, args.cid, run_id, boundary, args.expected_version,
                candidate["app_elf_sha256"], args.disconnect_timeout,
                args.minimum_blackout, args.reconnect_timeout,
                args.recovery_attempts, args.recovery_backoff, checkpoint)
        except Exception as error:
            sha256 = write_evidence(
                args.output, candidate, identity, args.cid, args.run_prefix,
                boundaries, runs, "failed", {
                    "boundary": boundary,
                    "run_id": run_id,
                    "error": f"{type(error).__name__}: {error}",
                })
            print(json.dumps({
                "status": "failed", "boundary": boundary,
                "error": f"{type(error).__name__}: {error}",
                "output": str(args.output), "sha256": sha256,
            }, sort_keys=True))
            return 2
        runs.append(run)
        status = "in_progress" if run["valid"] else "failed"
        sha256 = write_evidence(
            args.output, candidate, identity, args.cid, args.run_prefix,
            boundaries, runs, status)
        if not run["valid"]:
            print(json.dumps({
                "status": "failed", "boundary": boundary,
                "mismatches": run["mismatches"],
                "output": str(args.output), "sha256": sha256,
            }, sort_keys=True))
            return 2

    sha256 = write_evidence(
        args.output, candidate, identity, args.cid, args.run_prefix,
        boundaries, runs, "valid")
    print(json.dumps({
        "status": "valid", "boundaries_completed": len(runs),
        "output": str(args.output), "sha256": sha256,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
