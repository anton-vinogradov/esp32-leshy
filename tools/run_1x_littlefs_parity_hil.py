#!/usr/bin/env python3
"""Measure SessionStore on disposable OTA1 LittleFS and restore OTA1 exactly."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
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


RUN_SCHEMA = "leshy.storage.littlefs_parity_hil.run.v1"
DEVICE_SCHEMA = "leshy.storage.littlefs.parity.v1"
OTA1_OFFSET = 0x410000
OTA1_SIZE = 0x400000
PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0x1000
RESTORE_ATTEMPTS = 3
RESTORE_BACKOFF_SECONDS = 1.0
READ_ATTEMPTS = 3
READ_BACKOFF_SECONDS = 1.0


def esptool(port: str, baud: int, arguments: list[str]) -> None:
    operations = {
        "read-flash", "write-flash", "verify-flash", "erase-region",
        "erase-flash", "read-mac", "chip-id", "flash-id",
        "get-security-info",
    }
    normalized = [
        value.replace("-", "_") if value in operations else value
        for value in arguments
    ]
    subprocess.run([
        sys.executable, "-m", "esptool", "--chip", "esp32s3",
        "--port", port, "--baud", str(baud), *normalized,
    ], check=True)


def read_flash(port: str, baud: int, offset: int, size: int,
               output: Path) -> str:
    esptool(port, baud, [
        "read-flash", hex(offset), hex(size), str(output),
    ])
    if output.stat().st_size != size:
        raise RuntimeError(
            f"readback size {output.stat().st_size} != {size} at {offset:#x}"
        )
    return sha256_file(output)


def read_flash_with_retry(port: str, baud: int, offset: int, size: int,
                          output: Path, attempts: int = READ_ATTEMPTS,
                          backoff: float = READ_BACKOFF_SECONDS,
                          ) -> tuple[str, int]:
    if attempts < 1:
        raise ValueError("read attempts must be positive")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        output.unlink(missing_ok=True)
        try:
            return read_flash(port, baud, offset, size, output), attempt
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(backoff)
    raise RuntimeError(
        f"flash read at {offset:#x} failed after {attempts} attempts"
    ) from last_error


def restore_flash(port: str, baud: int, offset: int, backup: Path,
                  readback: Path, attempts: int = RESTORE_ATTEMPTS,
                  backoff: float = RESTORE_BACKOFF_SECONDS,
                  ) -> tuple[str, str, int]:
    if attempts < 1:
        raise ValueError("restore attempts must be positive")
    expected = sha256_file(backup)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            esptool(port, baud, ["write-flash", hex(offset), str(backup)])
            observed = read_flash(
                port, baud, offset, backup.stat().st_size, readback
            )
            if observed != expected:
                raise RuntimeError(
                    f"restore hash {observed} != backup hash {expected}"
                )
            return expected, observed, attempt
        except Exception as error:
            last_error = error
            readback.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(backoff)
    raise RuntimeError(
        f"OTA1 restore remained unverified after {attempts} attempts"
    ) from last_error


def parity_failures(record: dict[str, Any], expected_hash: str,
                    run_id: str) -> list[str]:
    failures = expect(record, {
        "status": "valid",
        "explicitly_disposable": True,
        "target": "ota1",
        "expected_fingerprint": expected_hash,
        "observed_fingerprint": expected_hash,
        "fingerprint_matched": True,
        "run_id": run_id,
        "target_address": OTA1_OFFSET,
        "target_size": OTA1_SIZE,
        "running_address": 0x10000,
        "boot_address": 0x10000,
        "target_inactive": True,
        "ota1_restore_required": True,
        "ota1_restored": False,
        "partition_table_modified": False,
        "product_partition_touched": False,
        "nvs_touched": False,
        "sd_accessed": False,
        "radio_touched": False,
        "format_allowed": True,
        "format_performed": True,
        "mounted_writable": True,
        "remounted_read_only": True,
        "reopened_read_only": True,
        "permit_status": "permitted",
        "scratch_preexisting_after_format": False,
        "byte_limit": 1024 * 1024,
        "file_syncs": 96,
        "directory_syncs": 96,
        "file_sync_covers_directory": True,
        "commit_samples_requested": 32,
        "commit_samples_completed": 32,
        "fixture_observations": 64,
        "storage_rate_target_met": True,
        "pre_remount_status": "valid",
        "pre_remount_generation": 32,
        "post_remount_status": "valid",
        "post_remount_generation": 32,
        "post_remount_observations": 64,
        "owned_during": 4,
        "owned_after": 0,
        "cleanup_complete": True,
        "reset_injection": False,
        "physical_power_cut": False,
    }, "littlefs")
    for field in (
        "filesystem_capacity_bytes", "free_before", "free_after",
        "bytes_written", "mount_us", "commit_total_us", "commit_min_us",
        "commit_p50_us", "commit_p95_us", "commit_p99_us", "commit_max_us",
        "fixture_segment_bytes", "encoded_payload_bytes_per_second",
        "required_encoded_bytes_per_second", "heap_free_before",
        "heap_free_after", "heap_min_free",
    ):
        value = record.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            failures.append(f"littlefs.{field}: expected positive integer")
    if (isinstance(record.get("free_before"), int) and
            isinstance(record.get("free_after"), int) and
            record["free_after"] >= record["free_before"]):
        failures.append("littlefs.free_after: expected committed image growth")
    if (isinstance(record.get("commit_min_us"), int) and
            isinstance(record.get("commit_p50_us"), int) and
            isinstance(record.get("commit_p95_us"), int) and
            isinstance(record.get("commit_p99_us"), int) and
            isinstance(record.get("commit_max_us"), int)):
        ordered = [record[field] for field in (
            "commit_min_us", "commit_p50_us", "commit_p95_us",
            "commit_p99_us", "commit_max_us",
        )]
        if ordered != sorted(ordered):
            failures.append("littlefs.commit_percentiles: not monotonic")
    if record.get("encoded_payload_bytes_per_second", 0) < record.get(
            "required_encoded_bytes_per_second", 1):
        failures.append("littlefs.storage_rate_target: measured rate below target")
    return failures


def unchanged_recovery_failures(before: dict[str, Any],
                                after: dict[str, Any],
                                expected_cid: str) -> list[str]:
    failures: list[str] = []
    for name, value in (("before", before), ("after", after)):
        failures.extend(expect(value, {
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
        }, f"recovery_{name}"))
    for field in ("generation", "observations"):
        if before.get(field) != after.get(field):
            failures.append(
                f"recovery_after.{field}: {after.get(field)!r} != "
                f"{before.get(field)!r}"
            )
    return failures


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
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    parser.add_argument("--post-flash-settle", type=float, default=1.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.expected_cid is not None and not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    backup = args.output / "ota1-private-backup.bin"
    backup_check = args.output / "ota1-private-backup-second-read.bin"
    restore_check = args.output / "ota1-private-restore-readback.bin"
    table_before = args.output / "partition-table-before.bin"
    table_after = args.output / "partition-table-after.bin"
    failures: list[str] = []
    run_id = f"lfs-{secrets.token_hex(8)}"
    runner_source_sha256 = sha256_file(Path(__file__).resolve())
    firmware_sha = ""
    app_identity = ""
    expected_cid = args.expected_cid or ""
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    timing_before: dict[str, Any] = {}
    parity: dict[str, Any] = {}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    timing_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    ota1_before_sha = ""
    ota1_second_sha = ""
    ota1_after_sha = ""
    ota1_backup_read_attempts = 0
    ota1_second_read_attempts = 0
    table_before_sha = ""
    table_after_sha = ""
    table_before_read_attempts = 0
    table_after_read_attempts = 0
    restore_attempted = False
    restore_attempts = 0
    restore_verified = False
    backup_deleted = False
    backup_ready = False

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
        try:
            expected_cid = resolve_expected_cid(
                args.expected_cid, recovery_before
            )
        except ValueError as error:
            failures.append(f"product_identity: {error}")
        if not failures:
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
                synchronize_console(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state"
                )
        failures.extend(boot_failures(
            boot_before, recovery_before, args.expected_version,
            app_identity, expected_cid
        ))

        if not failures:
            ota1_before_sha, ota1_backup_read_attempts = read_flash_with_retry(
                args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE, backup
            )
            ota1_second_sha, ota1_second_read_attempts = read_flash_with_retry(
                args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE,
                backup_check
            )
            table_before_sha, table_before_read_attempts = read_flash_with_retry(
                args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                PARTITION_TABLE_SIZE, table_before
            )
            backup_ready = ota1_before_sha == ota1_second_sha
            if not backup_ready:
                failures.append("ota1_backup: two independent reads differ")
            backup_check.unlink(missing_ok=True)

        if not failures:
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
                synchronize_console(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state"
                )
                failures.extend(boot_failures(
                    boot_before, recovery_before, args.expected_version,
                    app_identity, expected_cid
                ))
                if not failures:
                    command = (
                        f"storage.littlefs.parity disposable-ota1 "
                        f"{ota1_before_sha} {run_id}"
                    ).encode("ascii")
                    parity = query(
                        device, command, DEVICE_SCHEMA, "result", timeout=120.0
                    )
                    failures.extend(parity_failures(
                        parity, ota1_before_sha, run_id
                    ))
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    failures.append("pre_restore_cleanup: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")
    finally:
        if backup_ready and backup.is_file():
            restore_attempted = True
            restore_attempts = RESTORE_ATTEMPTS
            try:
                _, ota1_after_sha, restore_attempts = restore_flash(
                    args.port, args.flash_baud, OTA1_OFFSET, backup,
                    restore_check
                )
                table_after_sha, table_after_read_attempts = read_flash_with_retry(
                    args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                    PARTITION_TABLE_SIZE, table_after
                )
                restore_verified = (
                    ota1_after_sha == ota1_before_sha and
                    table_after_sha == table_before_sha
                )
                if not restore_verified:
                    failures.append(
                        "restore: OTA1 or partition table hash mismatch"
                    )
            except Exception as error:
                failures.append(
                    f"restore: {type(error).__name__}: {error}"
                )
            if restore_verified:
                backup.unlink(missing_ok=True)
                restore_check.unlink(missing_ok=True)
                table_before.unlink(missing_ok=True)
                table_after.unlink(missing_ok=True)
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
                    "leshy.storage.product_boot_recovery.v1", "state"
                )
                failures.extend(boot_failures(
                    boot_after, recovery_after, args.expected_version,
                    app_identity, expected_cid
                ))
                failures.extend(unchanged_recovery_failures(
                    recovery_before, recovery_after, expected_cid
                ))
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("post_restore_cleanup: Home/zero lease unproven")
        except Exception as error:
            failures.append(f"post_restore: {type(error).__name__}: {error}")
    elif backup_ready:
        failures.append(
            f"restore_unverified: retain private backup at {backup}"
        )

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": runner_source_sha256,
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
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
        "disposable_target": {
            "kind": "inactive_ota1_littlefs",
            "offset": OTA1_OFFSET,
            "size": OTA1_SIZE,
            "two_read_backup_verified": backup_ready,
            "before_sha256": ota1_before_sha,
            "second_read_sha256": ota1_second_sha,
            "backup_read_attempts": ota1_backup_read_attempts,
            "second_read_attempts": ota1_second_read_attempts,
            "read_attempt_limit": READ_ATTEMPTS,
            "restore_attempted": restore_attempted,
            "restore_attempts": restore_attempts,
            "restore_attempt_limit": RESTORE_ATTEMPTS,
            "after_sha256": ota1_after_sha,
            "restore_verified": restore_verified,
            "private_backup_deleted_after_verified_restore": backup_deleted,
            "partition_table_before_sha256": table_before_sha,
            "partition_table_after_sha256": table_after_sha,
            "partition_table_before_read_attempts": table_before_read_attempts,
            "partition_table_after_read_attempts": table_after_read_attempts,
            "partition_table_unchanged": (
                bool(table_before_sha) and table_before_sha == table_after_sha
            ),
        },
        "parity": parity,
        "cleanup_before_restore": cleanup_before,
        "boot_after": {
            "ready": boot_after,
            "recovery": recovery_after,
            "timing": timing_after,
        },
        "cleanup_final": cleanup_after,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
