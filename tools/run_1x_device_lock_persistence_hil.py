#!/usr/bin/env python3
"""Exercise Device Lock persistence with an ephemeral PIN and restore NVS."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_device_lock_hil import (
    LOCK_SCHEMA,
    device_lock_page,
    home_device,
    read_only_query,
)
from run_1x_littlefs_parity_hil import read_flash_with_retry, restore_flash
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    reset_capture,
    valid_cid,
)


RUN_SCHEMA = "leshy.device_lock_persistence_hil.run.v1"
NVS_OFFSET = 0x9000
NVS_SIZE = 0x5000


def pin_weak(pin: bytearray) -> bool:
    if len(pin) != 6 or any(digit > 9 for digit in pin):
        return True
    repeated = all(digit == pin[0] for digit in pin[1:])
    ascending = all(
        pin[index] == (pin[index - 1] + 1) % 10
        for index in range(1, len(pin))
    )
    descending = all(
        pin[index] == (pin[index - 1] + 9) % 10
        for index in range(1, len(pin))
    )
    return repeated or ascending or descending


def ephemeral_pin(excluded: bytearray | None = None) -> bytearray:
    while True:
        candidate = bytearray(secrets.randbelow(10) for _ in range(6))
        if not pin_weak(candidate) and candidate != excluded:
            return candidate


def wipe_pin(pin: bytearray) -> None:
    for index in range(len(pin)):
        pin[index] = 0


def state_failures(record: dict[str, Any], label: str, *, status: str,
                   failure: str, failed_attempts: int, generation: int,
                   protected: bool) -> list[str]:
    failures = expect(record, {
        "status": status,
        "failure": failure,
        "failed_attempts": failed_attempts,
        "credential_generation": generation,
        "protected_access": protected,
        "worker_active": False,
        "radio_touched": False,
    }, label)
    if status == "retry_delay":
        remaining = record.get("retry_remaining_ms")
        if (not isinstance(remaining, int) or isinstance(remaining, bool) or
                remaining <= 0):
            failures.append(
                f"{label}.retry_remaining_ms: expected positive integer")
    return failures


def full_retry_failures(record: dict[str, Any], label: str,
                        expected_ms: int) -> list[str]:
    remaining = record.get("retry_remaining_ms")
    if (not isinstance(remaining, int) or isinstance(remaining, bool) or
            remaining < expected_ms - 750 or remaining > expected_ms):
        return [
            f"{label}.retry_remaining_ms={remaining!r} outside "
            f"{expected_ms - 750}..{expected_ms}"
        ]
    return []


def wait_lock_state(device: PassiveSerial,
                    predicate: Callable[[dict[str, Any]], bool],
                    description: str, timeout: float = 25.0,
                    ) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        if latest.get("worker_active") is False and predicate(latest):
            return latest
        time.sleep(0.05)
    raise TimeoutError(f"{description}: terminal state not reached")


def enter_pin(device: PassiveSerial, pin: bytearray) -> None:
    """Enter one six-digit editor pass without retaining PIN-shaped replies."""
    if len(pin) != 6 or any(digit > 9 for digit in pin):
        raise ValueError("PIN must contain exactly six decimal digits")
    for digit in pin:
        direction = "down" if digit <= 5 else "up"
        presses = digit if digit <= 5 else 10 - digit
        for _ in range(presses):
            action(device, direction)
        action(device, "right")


def begin_hil(device: PassiveSerial, run_id: str,
              app_identity: str) -> dict[str, Any]:
    return query(
        device, f"hil.begin {run_id} {app_identity}".encode("ascii"),
        "leshy.hil.session.v1", "begun")


def end_hil(device: PassiveSerial, run_id: str) -> dict[str, Any]:
    return query(
        device, f"hil.end {run_id}".encode("ascii"),
        "leshy.hil.session.v1", "ended")


def public_artifact_manifest(output: Path) -> None:
    lines: list[str] = []
    for path in sorted(output.rglob("*")):
        if (not path.is_file() or path.name == "artifacts.sha256" or
                "private" in path.parts):
            continue
        lines.append(f"{sha256_file(path)}  {path.relative_to(output)}")
    (output / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    private = args.output / "private"
    private.mkdir()
    backup = private / "nvs-before.bin"
    backup_second = private / "nvs-before-second.bin"
    restore_readback = private / "nvs-restore-readback.bin"
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    correct_pin = ephemeral_pin()
    wrong_pin = ephemeral_pin(correct_pin)
    failures: list[str] = []
    reports: dict[str, Any] = {}
    screens: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {"attempted": False}
    device: PassiveSerial | None = None
    backup_ready = False
    backup_sha = ""
    backup_attempts = 0
    backup_second_attempts = 0
    restore_attempted = False
    restore_attempts = 0
    restore_sha = ""
    restore_verified = False
    private_backup_deleted = False
    final_boot: dict[str, Any] = {}
    final_recovery: dict[str, Any] = {}
    final_reset: dict[str, Any] = {}

    try:
        backup_sha, backup_attempts = read_flash_with_retry(
            args.port, args.flash_baud, NVS_OFFSET, NVS_SIZE, backup)
        backup_second_sha, backup_second_attempts = read_flash_with_retry(
            args.port, args.flash_baud, NVS_OFFSET, NVS_SIZE, backup_second)
        backup_ready = backup_sha == backup_second_sha
        if not backup_ready:
            raise RuntimeError("two independent NVS backup reads differ")
        backup_second.unlink(missing_ok=True)

        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        time.sleep(0.6)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics = read_only_query(
            device, b"metrics", "leshy.boot.v1", "ready")
        recovery = read_only_query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        reports["metrics_before"] = metrics
        reports["recovery_before"] = recovery
        failures.extend(boot_failures(
            metrics, recovery, args.expected_version,
            app_identity, args.expected_cid))
        if failures:
            raise RuntimeError("candidate boot contract failed")
        cleanup_before = best_effort_cleanup(device)
        reports["cleanup_before"] = cleanup_before
        if not cleanup_before.get("complete"):
            raise RuntimeError("initial Home/zero-lease cleanup failed")
        sessions.append(begin_hil(device, run_id, app_identity))

        baseline = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["baseline"] = baseline
        failures.extend(state_failures(
            baseline, "baseline", status="unconfigured", failure="none",
            failed_attempts=0, generation=0, protected=False))
        if failures:
            raise RuntimeError("Device Lock baseline is not virgin")
        home_device(device)
        device_lock_page(device)
        screens["unconfigured"] = capture(
            device, frames, "device-lock-unconfigured")

        opened = action(device, "right")
        failures.extend(expect(opened, {
            "page": "device_lock",
            "runtime_event": "device_lock_editor_opened",
        }, "configure_editor"))
        enter_pin(device, correct_pin)
        enter_pin(device, correct_pin)
        configured = wait_lock_state(
            device, lambda state: state.get("status") == "unlocked",
            "credential enrollment")
        reports["configured"] = configured
        failures.extend(state_failures(
            configured, "configured", status="unlocked", failure="none",
            failed_attempts=0, generation=1, protected=True))
        screens["configured"] = capture(
            device, frames, "device-lock-configured")

        action(device, "right")
        locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["locked_before_reset"] = locked
        failures.extend(state_failures(
            locked, "locked_before_reset", status="locked", failure="none",
            failed_attempts=0, generation=1, protected=False))
        sessions.append(end_hil(device, run_id))
        device.close()
        device = None

        boot_locked, recovery_locked, reset_locked = reset_capture(
            args.port, args.output, "device-lock-cold-locked", 25.0, 2)
        reports["cold_locked_boot"] = boot_locked
        reports["cold_locked_recovery"] = recovery_locked
        reports["cold_locked_reset"] = reset_locked
        failures.extend(boot_failures(
            boot_locked, recovery_locked, args.expected_version,
            app_identity, args.expected_cid))
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        sessions.append(begin_hil(device, run_id, app_identity))
        restored_locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["restored_locked"] = restored_locked
        failures.extend(state_failures(
            restored_locked, "restored_locked", status="locked",
            failure="none", failed_attempts=0, generation=1,
            protected=False))
        home_device(device)
        device_lock_page(device)

        action(device, "right")
        enter_pin(device, wrong_pin)
        retry_one = wait_lock_state(
            device, lambda state: state.get("status") == "retry_delay",
            "first wrong PIN")
        reports["retry_one"] = retry_one
        failures.extend(state_failures(
            retry_one, "retry_one", status="retry_delay",
            failure="wrong_pin", failed_attempts=1, generation=2,
            protected=False))
        failures.extend(full_retry_failures(retry_one, "retry_one", 5000))
        wait_lock_state(
            device, lambda state: state.get("status") == "locked",
            "first retry completion", 8.0)

        action(device, "right")
        enter_pin(device, wrong_pin)
        retry_two = wait_lock_state(
            device, lambda state: state.get("status") == "retry_delay",
            "second wrong PIN")
        reports["retry_two"] = retry_two
        failures.extend(state_failures(
            retry_two, "retry_two", status="retry_delay",
            failure="wrong_pin", failed_attempts=2, generation=3,
            protected=False))
        failures.extend(full_retry_failures(retry_two, "retry_two", 15000))
        screens["retry"] = capture(device, frames, "device-lock-retry")
        device.close()
        device = None

        boot_retry, recovery_retry, reset_retry = reset_capture(
            args.port, args.output, "device-lock-cold-retry", 25.0, 2)
        reports["cold_retry_boot"] = boot_retry
        reports["cold_retry_recovery"] = recovery_retry
        reports["cold_retry_reset"] = reset_retry
        failures.extend(boot_failures(
            boot_retry, recovery_retry, args.expected_version,
            app_identity, args.expected_cid))
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        sessions.append(begin_hil(device, run_id, app_identity))
        restored_retry = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["restored_retry"] = restored_retry
        failures.extend(state_failures(
            restored_retry, "restored_retry", status="retry_delay",
            failure="retry_delay", failed_attempts=2, generation=3,
            protected=False))
        home_device(device)
        device_lock_page(device)
        wait_lock_state(
            device, lambda state: state.get("status") == "locked",
            "restored retry completion", 18.0)

        action(device, "right")
        enter_pin(device, correct_pin)
        unlocked = wait_lock_state(
            device, lambda state: state.get("status") == "unlocked",
            "correct PIN after cold retry")
        reports["unlocked_after_retry"] = unlocked
        failures.extend(state_failures(
            unlocked, "unlocked_after_retry", status="unlocked",
            failure="none", failed_attempts=0, generation=4,
            protected=True))
        screens["unlocked"] = capture(
            device, frames, "device-lock-unlocked")
        action(device, "right")
        terminal_locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["terminal_locked"] = terminal_locked
        failures.extend(state_failures(
            terminal_locked, "terminal_locked", status="locked",
            failure="none", failed_attempts=0, generation=4,
            protected=False))
        sessions.append(end_hil(device, run_id))
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            failures.append("cleanup: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"workflow: {type(error).__name__}: {error}")
        if device is not None:
            try:
                cleanup = best_effort_cleanup(device)
            except Exception as cleanup_error:
                failures.append(
                    "cleanup: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}")
    finally:
        if device is not None:
            device.close()
            device = None
        wipe_pin(correct_pin)
        wipe_pin(wrong_pin)
        if backup_ready and backup.is_file():
            restore_attempted = True
            try:
                expected, observed, restore_attempts = restore_flash(
                    args.port, args.flash_baud, NVS_OFFSET,
                    backup, restore_readback)
                restore_sha = observed
                restore_verified = expected == backup_sha == observed
            except Exception as restore_error:
                failures.append(
                    "NVS restore: "
                    f"{type(restore_error).__name__}: {restore_error}")
            if restore_verified:
                backup.unlink(missing_ok=True)
                restore_readback.unlink(missing_ok=True)
                private_backup_deleted = True
                try:
                    final_boot, final_recovery, final_reset = reset_capture(
                        args.port, args.output,
                        "device-lock-restored-baseline", 25.0, 2)
                    failures.extend(boot_failures(
                        final_boot, final_recovery, args.expected_version,
                        app_identity, args.expected_cid))
                    device = PassiveSerial(
                        args.port, 115200, timeout=0.25)
                    synchronize_console(device, 20.0)
                    final_lock = read_only_query(
                        device, b"device-lock.state", LOCK_SCHEMA, "state")
                    reports["restored_baseline"] = final_lock
                    baseline = reports.get("baseline", {})
                    for field in (
                            "status", "failure", "failed_attempts",
                            "credential_generation", "protected_access"):
                        if final_lock.get(field) != baseline.get(field):
                            failures.append(
                                f"restored_baseline.{field}: "
                                f"{final_lock.get(field)!r} != "
                                f"{baseline.get(field)!r}")
                    final_input = read_only_query(
                        device, b"input.state",
                        "leshy.input.frontend.v1", "state")
                    reports["final_input"] = final_input
                    failures.extend(expect(final_input, {
                        "status": "ready", "read_errors": 0,
                        "queue_drops": 0,
                    }, "final_input"))
                    device.close()
                    device = None
                except Exception as final_error:
                    failures.append(
                        "restored baseline verification: "
                        f"{type(final_error).__name__}: {final_error}")
        elif not backup_ready:
            backup.unlink(missing_ok=True)
            backup_second.unlink(missing_ok=True)

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": not failures and restore_verified and private_backup_deleted,
        "gate_eligible": not failures and restore_verified and
            private_backup_deleted,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "app_elf_sha256": app_identity,
            "flashed": True,
            "flash_mode": "fresh",
        },
        "expected_cid": args.expected_cid,
        "reports": reports,
        "screens": screens,
        "sessions": sessions,
        "cleanup": cleanup,
        "nvs_transaction": {
            "offset": NVS_OFFSET,
            "size": NVS_SIZE,
            "backup_sha256": backup_sha,
            "backup_attempts": backup_attempts,
            "backup_second_attempts": backup_second_attempts,
            "two_reads_matched": backup_ready,
            "restore_attempted": restore_attempted,
            "restore_attempts": restore_attempts,
            "restore_sha256": restore_sha,
            "restore_verified": restore_verified,
            "private_backup_deleted_after_verified_restore":
                private_backup_deleted,
        },
        "final_boot": final_boot,
        "final_recovery": final_recovery,
        "final_reset": final_reset,
        "privacy": {
            "ephemeral_pin_length": 6,
            "pin_or_digest_retained": False,
            "pin_editor_replies_retained": False,
            "private_nvs_in_public_manifest": False,
        },
        "scope": {
            "credential_enrollment": True,
            "credential_persistence": True,
            "wrong_pin_backoff": True,
            "radio": False,
            "product_storage_write": False,
            "mac_wifi": False,
            "clone": False,
            "cardputer": False,
        },
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
    }
    write_json(args.output / "run.json", result)
    public_artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "output": str(args.output),
        "nvs_restored": restore_verified,
    }, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
