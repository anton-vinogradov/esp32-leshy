#!/usr/bin/env python3
"""Run six software-reset boundaries on disposable OTA1 LittleFS, then restore it."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_littlefs_parity_hil import (
    OTA1_OFFSET,
    OTA1_SIZE,
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    READ_ATTEMPTS,
    esptool,
    read_flash_with_retry,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    expect,
    query,
    reset_capture,
    resolve_expected_cid,
    valid_cid,
)


RUN_SCHEMA = "leshy.storage.littlefs_reset_matrix_hil.run.v1"
DEVICE_SCHEMA = "leshy.storage.littlefs.reset.v1"
BOUNDARIES = (1, 2, 3, 4, 5, 6)
RESTORE_WRITE_ATTEMPTS = 1
RESTORE_READ_ATTEMPTS = 6
RESTORE_READ_BACKOFF_SECONDS = 5.0
RESTORE_SETTLE_SECONDS = 5.0


def restore_flash_single_write(
        port: str, baud: int, offset: int, backup: Path, readback: Path,
        stats: dict[str, int], *, settle: float = RESTORE_SETTLE_SECONDS,
        read_attempts: int = RESTORE_READ_ATTEMPTS,
        read_backoff: float = RESTORE_READ_BACKOFF_SECONDS,
        ) -> tuple[str, str]:
    """Restore once, then retry only the non-mutating verification read."""
    if settle < 0:
        raise ValueError("restore settle must not be negative")
    if read_attempts < 1:
        raise ValueError("restore read attempts must be positive")
    expected = sha256_file(backup)
    stats["write_attempts"] = 1
    esptool(port, baud, ["write-flash", hex(offset), str(backup)])
    if settle:
        time.sleep(settle)
    try:
        observed, attempts_used = read_flash_with_retry(
            port, baud, offset, backup.stat().st_size, readback,
            attempts=read_attempts, backoff=read_backoff,
        )
        stats["read_attempts"] = attempts_used
    except Exception:
        stats["read_attempts"] = read_attempts
        raise
    if observed != expected:
        raise RuntimeError(
            f"restore hash {observed} != backup hash {expected}"
        )
    return expected, observed


def open_synchronized(port: str, timeout: float) -> Any:
    import serial
    from capture_1x_ui import PassiveSerial, synchronize_console

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        device = PassiveSerial()
        device.port = port
        device.baudrate = 115200
        device.timeout = 0.25
        try:
            device.open()
            synchronize_console(
                device,
                timeout=min(5.0, max(0.5, deadline - time.monotonic())),
            )
            return device
        except (OSError, serial.SerialException, TimeoutError) as error:
            last_error = error
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass
            time.sleep(0.25)
    raise TimeoutError(f"device did not return on {port}: {last_error}")


def arm_failures(record: dict[str, Any], fingerprint: str, run_id: str,
                 boundary: int) -> list[str]:
    return expect(record, {
        "status": "ready",
        "run_id": run_id,
        "boundary": boundary,
        "expected_fingerprint": fingerprint,
        "observed_fingerprint": fingerprint,
        "fingerprint_matched": True,
        "target": "ota1",
        "target_address": OTA1_OFFSET,
        "target_size": OTA1_SIZE,
        "target_inactive": True,
        "initial_generation": 1,
        "initial_observations": 3,
        "continuity_armed": True,
        "format_performed": True,
        "writes_bounded_to_scratch": True,
        "ota1_restore_required": True,
        "product_partition_touched": False,
        "sd_accessed": False,
        "nvs_touched": False,
        "radio_touched": False,
        "reset_injection": True,
        "physical_power_cut": False,
    }, "armed")


def trigger_failures(record: dict[str, Any], run_id: str,
                     boundary: int) -> list[str]:
    return expect(record, {
        "status": "boundary_reached",
        "run_id": run_id,
        "boundary": boundary,
        "continuity_armed": True,
        "reset_injection": True,
        "physical_power_cut": False,
    }, "trigger")


def recovery_failures(record: dict[str, Any], run_id: str,
                      boundary: int) -> list[str]:
    failures = expect(record, {
        "mode": "recovery",
        "status": "valid",
        "run_id": run_id,
        "boundary": boundary,
        "software_reset": True,
        "continuity_valid": True,
        "target": "ota1",
        "target_address": OTA1_OFFSET,
        "target_size": OTA1_SIZE,
        "target_inactive": True,
        "read_permit_status": "permitted",
        "scratch_exists": True,
        "mounted_read_only": True,
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
        "mount_on_boot": False,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "ota1_restore_required": True,
        "product_partition_touched": False,
        "sd_accessed": False,
        "nvs_touched": False,
        "radio_touched": False,
        "reset_injection": True,
        "physical_power_cut": False,
    }, "recovery")
    generation = record.get("recovered_generation")
    allowed = (
        generation == 1 if boundary <= 4 else
        generation in (1, 2) if boundary == 5 else
        generation == 2
    )
    if not allowed:
        failures.append(
            f"recovery.recovered_generation: {generation!r} not allowed "
            f"for boundary {boundary}"
        )
    return failures


def run_boundary(port: str, fingerprint: str, run_id: str, boundary: int,
                 reconnect_timeout: float) -> dict[str, Any]:
    from capture_1x_ui import read_json

    arm_command = (
        f"storage.littlefs.reset disposable-ota1 "
        f"{fingerprint} {run_id} {boundary}"
    )
    device = open_synchronized(port, reconnect_timeout)
    try:
        device.write((arm_command + "\n").encode("ascii"))
        device.flush()
        armed = read_json(device, DEVICE_SCHEMA, "armed", timeout=60.0)
        trigger = read_json(
            device, DEVICE_SCHEMA, "reset_trigger", timeout=60.0
        )
    finally:
        try:
            device.close()
        except Exception:
            pass

    failures = arm_failures(armed, fingerprint, run_id, boundary)
    failures.extend(trigger_failures(trigger, run_id, boundary))
    recovery_command = (
        f"storage.littlefs.reset recover read-only "
        f"{fingerprint} {run_id} {boundary}"
    )
    recovery: dict[str, Any] = {}
    if not failures:
        device = open_synchronized(port, reconnect_timeout)
        try:
            recovery = query(
                device, recovery_command.encode("ascii"), DEVICE_SCHEMA,
                "result", timeout=30.0,
            )
        finally:
            device.close()
        failures.extend(recovery_failures(recovery, run_id, boundary))
    return {
        "boundary": boundary,
        "run_id": run_id,
        "target_fingerprint_before": fingerprint,
        "arm_command": arm_command,
        "armed": armed,
        "trigger": trigger,
        "recovery_command": recovery_command,
        "recovery": recovery,
        "valid": not failures,
        "failures": failures,
    }


def unchanged_recovery_failures(before: dict[str, Any],
                                after: dict[str, Any],
                                expected_cid: str) -> list[str]:
    failures: list[str] = []
    for name, record in (("before", before), ("after", after)):
        failures.extend(expect(record, {
            "status": "admitted",
            "expected_fingerprint": expected_cid,
            "observed_fingerprint": expected_cid,
            "fingerprint_matched": True,
            "mounted_read_only": True,
            "read_only_guaranteed": True,
            "catalog_admitted": True,
            "physical_write_calls": 0,
            "cleanup_complete": True,
            "owned_after": 0,
        }, f"product_{name}"))
    for field in ("generation", "observations"):
        if before.get(field) != after.get(field):
            failures.append(
                f"product_after.{field}: {after.get(field)!r} != "
                f"{before.get(field)!r}"
            )
    return failures


def checkpoint(path: Path, result: dict[str, Any]) -> None:
    write_json(path / "run.json", result)


def main() -> int:
    from capture_1x_ui import PassiveSerial, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=230400)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    parser.add_argument("--post-flash-settle", type=float, default=1.0)
    parser.add_argument("--reconnect-timeout", type=float, default=30.0)
    parser.add_argument("--restore-settle", type=float,
                        default=RESTORE_SETTLE_SECONDS)
    parser.add_argument("--restore-read-attempts", type=int,
                        default=RESTORE_READ_ATTEMPTS)
    parser.add_argument("--restore-read-backoff", type=float,
                        default=RESTORE_READ_BACKOFF_SECONDS)
    parser.add_argument("--boundaries", default="1,2,3,4,5,6")
    parser.add_argument(
        "--execute-reset-matrix", action="store_true",
        help="required acknowledgement for six destructive OTA1 formats/resets",
    )
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.expected_cid is not None and not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if not args.execute_reset_matrix:
        parser.error("--execute-reset-matrix is required")
    if args.restore_settle < 0:
        parser.error("--restore-settle must not be negative")
    if args.restore_read_attempts < 1:
        parser.error("--restore-read-attempts must be positive")
    if args.restore_read_backoff < 0:
        parser.error("--restore-read-backoff must not be negative")
    try:
        boundaries = [int(value) for value in args.boundaries.split(",")]
    except ValueError:
        parser.error("--boundaries must be a comma-separated subset of 1..6")
    if (not boundaries or len(set(boundaries)) != len(boundaries) or
            any(value not in BOUNDARIES for value in boundaries)):
        parser.error("--boundaries must be a unique comma-separated subset of 1..6")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    backup = args.output / "ota1-private-backup.bin"
    backup_check = args.output / "ota1-private-backup-second-read.bin"
    restore_check = args.output / "ota1-private-restore-readback.bin"
    table_before = args.output / "partition-table-before.bin"
    table_after = args.output / "partition-table-after.bin"
    target_read = args.output / "ota1-current-private-read.bin"
    run_id = f"lfsr-{secrets.token_hex(6)}"
    runner_source_sha256 = sha256_file(Path(__file__).resolve())
    failures: list[str] = []
    runs: list[dict[str, Any]] = []
    firmware_sha = ""
    app_identity = ""
    expected_cid = args.expected_cid or ""
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    timing_before: dict[str, Any] = {}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    timing_after: dict[str, Any] = {}
    cleanup_final: dict[str, Any] = {"attempted": False}
    ota1_before_sha = ""
    ota1_second_sha = ""
    ota1_after_sha = ""
    table_before_sha = ""
    table_after_sha = ""
    backup_ready = False
    restore_attempted = False
    restore_verified = False
    restore_stats = {"write_attempts": 0, "read_attempts": 0}
    backup_deleted = False

    result: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": runner_source_sha256,
        "status": "in_progress",
        "passed": False,
        "gate_eligible": False,
        "boundaries_requested": boundaries,
        "boundaries_completed": 0,
        "runs": runs,
        "failures": failures,
    }
    checkpoint(args.output, result)
    try:
        shutil.copyfile(args.firmware, candidate)
        firmware_sha = sha256_file(candidate)
        app_identity = app_elf_sha256(candidate)
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(args.post_flash_settle)

        boot_before, recovery_before, timing_before = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        expected_cid = resolve_expected_cid(args.expected_cid, recovery_before)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
            synchronize_console(device)
            recovery_before = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
        failures.extend(boot_failures(
            boot_before, recovery_before, args.expected_version,
            app_identity, expected_cid,
        ))

        if not failures:
            ota1_before_sha, _ = read_flash_with_retry(
                args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE, backup
            )
            ota1_second_sha, _ = read_flash_with_retry(
                args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE,
                backup_check,
            )
            table_before_sha, _ = read_flash_with_retry(
                args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                PARTITION_TABLE_SIZE, table_before,
            )
            backup_ready = ota1_before_sha == ota1_second_sha
            if not backup_ready:
                failures.append("ota1_backup: two independent reads differ")
            backup_check.unlink(missing_ok=True)

        for boundary in boundaries:
            if failures:
                break
            if boundary == boundaries[0]:
                target_fingerprint = ota1_before_sha
            else:
                target_fingerprint, _ = read_flash_with_retry(
                    args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE,
                    target_read,
                )
                target_read.unlink(missing_ok=True)
            boundary_run = run_boundary(
                args.port, target_fingerprint,
                f"{run_id}-b{boundary}", boundary, args.reconnect_timeout,
            )
            runs.append(boundary_run)
            failures.extend(boundary_run["failures"])
            result.update({
                "boundaries_completed": len(runs),
                "runs": runs,
                "failures": failures,
            })
            checkpoint(args.output, result)
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")
    finally:
        if backup_ready and backup.is_file():
            restore_attempted = True
            try:
                _, ota1_after_sha = restore_flash_single_write(
                    args.port, args.flash_baud, OTA1_OFFSET, backup,
                    restore_check, restore_stats,
                    settle=args.restore_settle,
                    read_attempts=args.restore_read_attempts,
                    read_backoff=args.restore_read_backoff,
                )
                table_after_sha, _ = read_flash_with_retry(
                    args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                    PARTITION_TABLE_SIZE, table_after,
                )
                restore_verified = (
                    ota1_after_sha == ota1_before_sha and
                    table_after_sha == table_before_sha
                )
                if not restore_verified:
                    failures.append("restore: OTA1 or partition table hash mismatch")
            except Exception as error:
                failures.append(f"restore: {type(error).__name__}: {error}")
            if restore_verified:
                for private in (backup, restore_check, table_before,
                                table_after, target_read):
                    private.unlink(missing_ok=True)
                backup_deleted = True

    if restore_verified:
        try:
            boot_after, recovery_after, timing_after = reset_capture(
                args.port, args.output, "boot-after", args.boot_seconds
            )
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
                synchronize_console(device)
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                cleanup_final = best_effort_cleanup(device)
            failures.extend(boot_failures(
                boot_after, recovery_after, args.expected_version,
                app_identity, expected_cid,
            ))
            failures.extend(unchanged_recovery_failures(
                recovery_before, recovery_after, expected_cid,
            ))
            if not cleanup_final.get("complete"):
                failures.append("final_cleanup: Home/zero lease unproven")
        except Exception as error:
            failures.append(f"post_restore: {type(error).__name__}: {error}")
    elif backup_ready:
        failures.append(f"restore_unverified: retain private backup at {backup}")

    passed = (
        not failures and args.flash and len(runs) == len(boundaries) and
        all(run["valid"] for run in runs) and restore_verified
    )
    gate_eligible = passed and boundaries == list(BOUNDARIES)
    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": runner_source_sha256,
        "status": "pass" if passed else "failed",
        "passed": passed,
        "gate_eligible": gate_eligible,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "flashed": args.flash,
        },
        "expected_cid": expected_cid,
        "boot_before": {
            "ready": boot_before,
            "recovery": recovery_before,
            "timing": timing_before,
        },
        "boundaries_requested": boundaries,
        "boundaries_completed": len(runs),
        "runs": runs,
        "disposable_target": {
            "kind": "inactive_ota1_littlefs",
            "offset": OTA1_OFFSET,
            "size": OTA1_SIZE,
            "two_read_backup_verified": backup_ready,
            "before_sha256": ota1_before_sha,
            "second_read_sha256": ota1_second_sha,
            "read_attempt_limit": READ_ATTEMPTS,
            "restore_attempted": restore_attempted,
            "restore_write_attempts": restore_stats["write_attempts"],
            "restore_write_attempt_limit": RESTORE_WRITE_ATTEMPTS,
            "restore_read_attempts": restore_stats["read_attempts"],
            "restore_read_attempt_limit": args.restore_read_attempts,
            "restore_settle_seconds": args.restore_settle,
            "restore_read_backoff_seconds": args.restore_read_backoff,
            "after_sha256": ota1_after_sha,
            "restore_verified": restore_verified,
            "private_backup_deleted_after_verified_restore": backup_deleted,
            "partition_table_before_sha256": table_before_sha,
            "partition_table_after_sha256": table_after_sha,
            "partition_table_unchanged": bool(table_before_sha) and
                table_before_sha == table_after_sha,
        },
        "boot_after": {
            "ready": boot_after,
            "recovery": recovery_after,
            "timing": timing_after,
        },
        "cleanup_final": cleanup_final,
    }
    checkpoint(args.output, result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
