#!/usr/bin/env python3
"""Exercise Device Lock persistence in an isolated disposable NVS namespace."""

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
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    reset_capture,
    valid_cid,
)


RUN_SCHEMA = "leshy.device_lock_persistence_hil.run.v2"
FIXTURE_SCHEMA = "leshy.device_lock.fixture.v1"


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
                   protected: bool, fixture_active: bool,
                   ) -> list[str]:
    failures = expect(record, {
        "status": status,
        "failure": failure,
        "failed_attempts": failed_attempts,
        "credential_generation": generation,
        "protected_access": protected,
        "worker_active": False,
        "persistence_fixture_active": fixture_active,
        "persistence_fixture_cleanup_required": fixture_active,
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


def fixture_failures(record: dict[str, Any], label: str, *, status: str,
                     operation: str, active: bool, selected: bool,
                     cleaned: bool, product_restored: bool,
                     ) -> list[str]:
    return expect(record, {
        "operation": operation,
        "status": status,
        "active": active,
        "cleanup_required": active,
        "fixture_namespace_selected": selected,
        "fixture_cleanup_complete": cleaned,
        "product_restored": product_restored,
        "product_namespace_written_or_erased": False,
        "whole_nvs_read_or_copied": False,
        "radio_touched": False,
    }, label)


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
    """Enter one editor pass without retaining any PIN-shaped UI replies."""
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


def fixture_command(device: PassiveSerial, operation: str) -> dict[str, Any]:
    if operation not in {"begin", "resume", "cleanup"}:
        raise ValueError("invalid fixture operation")
    return query(
        device,
        f"device-lock.persistence-fixture {operation}".encode("ascii"),
        FIXTURE_SCHEMA, "persistence_fixture")


def reopen_after_reset(port: str, run_id: str,
                       app_identity: str) -> tuple[PassiveSerial, dict[str, Any]]:
    device = PassiveSerial(port, 115200, timeout=0.25)
    synchronize_console(device, 20.0)
    return device, begin_hil(device, run_id, app_identity)


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
    candidate_flashed = False
    fixture_started = False
    fixture_ever_started = False
    fixture_cleanup: dict[str, Any] = {}
    fixture_cleanup_proven = False
    final_boot: dict[str, Any] = {}
    final_recovery: dict[str, Any] = {}
    final_reset: dict[str, Any] = {}

    try:
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        candidate_flashed = True
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
        reports["product_baseline"] = baseline
        failures.extend(state_failures(
            baseline, "product_baseline", status="unconfigured",
            failure="none", failed_attempts=0, generation=0,
            protected=False, fixture_active=False))
        if failures:
            raise RuntimeError("product Device Lock baseline is not virgin")

        fixture_begin = fixture_command(device, "begin")
        fixture_started = True
        fixture_ever_started = True
        reports["fixture_begin"] = fixture_begin
        failures.extend(fixture_failures(
            fixture_begin, "fixture_begin", status="begun",
            operation="begin", active=True, selected=True,
            cleaned=True, product_restored=False))
        fixture_baseline = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        failures.extend(state_failures(
            fixture_baseline, "fixture_baseline", status="unconfigured",
            failure="none", failed_attempts=0, generation=0,
            protected=False, fixture_active=True))
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
            failed_attempts=0, generation=1, protected=True,
            fixture_active=True))
        screens["configured"] = capture(
            device, frames, "device-lock-configured")

        action(device, "right")
        locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["locked_before_reset"] = locked
        failures.extend(state_failures(
            locked, "locked_before_reset", status="locked", failure="none",
            failed_attempts=0, generation=1, protected=False,
            fixture_active=True))
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
        device, session = reopen_after_reset(
            args.port, run_id, app_identity)
        sessions.append(session)
        product_after_reset = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        failures.extend(state_failures(
            product_after_reset, "product_after_reset", status="unconfigured",
            failure="none", failed_attempts=0, generation=0,
            protected=False, fixture_active=False))
        fixture_resume = fixture_command(device, "resume")
        reports["fixture_resume_locked"] = fixture_resume
        failures.extend(fixture_failures(
            fixture_resume, "fixture_resume_locked", status="resumed",
            operation="resume", active=True, selected=True,
            cleaned=True, product_restored=False))
        restored_locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["restored_locked"] = restored_locked
        failures.extend(state_failures(
            restored_locked, "restored_locked", status="locked",
            failure="none", failed_attempts=0, generation=1,
            protected=False, fixture_active=True))
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
            protected=False, fixture_active=True))
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
            protected=False, fixture_active=True))
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
        device, session = reopen_after_reset(
            args.port, run_id, app_identity)
        sessions.append(session)
        fixture_resume_retry = fixture_command(device, "resume")
        reports["fixture_resume_retry"] = fixture_resume_retry
        failures.extend(fixture_failures(
            fixture_resume_retry, "fixture_resume_retry", status="resumed",
            operation="resume", active=True, selected=True,
            cleaned=True, product_restored=False))
        restored_retry = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["restored_retry"] = restored_retry
        failures.extend(state_failures(
            restored_retry, "restored_retry", status="retry_delay",
            failure="retry_delay", failed_attempts=2, generation=3,
            protected=False, fixture_active=True))
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
            protected=True, fixture_active=True))
        screens["unlocked"] = capture(
            device, frames, "device-lock-unlocked")
        action(device, "right")
        terminal_locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["terminal_locked"] = terminal_locked
        failures.extend(state_failures(
            terminal_locked, "terminal_locked", status="locked",
            failure="none", failed_attempts=0, generation=4,
            protected=False, fixture_active=True))

        fixture_cleanup = fixture_command(device, "cleanup")
        reports["fixture_cleanup"] = fixture_cleanup
        cleanup_failures = fixture_failures(
            fixture_cleanup, "fixture_cleanup", status="cleaned",
            operation="cleanup", active=False, selected=False,
            cleaned=True, product_restored=True)
        failures.extend(cleanup_failures)
        fixture_cleanup_proven = not cleanup_failures
        fixture_started = False
        sessions.append(end_hil(device, run_id))
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            failures.append("cleanup: Home/zero lease unproven")
        product_after_cleanup = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["product_after_cleanup"] = product_after_cleanup
        failures.extend(state_failures(
            product_after_cleanup, "product_after_cleanup",
            status="unconfigured", failure="none", failed_attempts=0,
            generation=0, protected=False, fixture_active=False))
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
        wipe_pin(correct_pin)
        wipe_pin(wrong_pin)
        if candidate_flashed and not fixture_cleanup_proven:
            try:
                if device is None:
                    device = PassiveSerial(
                        args.port, 115200, timeout=0.25)
                    synchronize_console(device, 20.0)
                hil_state = read_only_query(
                    device, b"hil.state",
                    "leshy.hil.session.v1", "state")
                if hil_state.get("active") is not True:
                    sessions.append(begin_hil(device, run_id, app_identity))
                fixture_cleanup = fixture_command(device, "cleanup")
                cleanup_failures = fixture_failures(
                    fixture_cleanup, "fixture_cleanup_finally",
                    status="cleaned", operation="cleanup", active=False,
                    selected=False, cleaned=True, product_restored=True)
                failures.extend(cleanup_failures)
                fixture_cleanup_proven = not cleanup_failures
                fixture_started = False
                if fixture_cleanup_proven:
                    try:
                        sessions.append(end_hil(device, run_id))
                    except Exception:
                        pass
            except Exception as fixture_error:
                failures.append(
                    "fixture cleanup: "
                    f"{type(fixture_error).__name__}: {fixture_error}")
        if device is not None:
            device.close()
            device = None

    if candidate_flashed and fixture_cleanup_proven:
        try:
            final_boot, final_recovery, final_reset = reset_capture(
                args.port, args.output,
                "device-lock-product-after-cleanup", 25.0, 2)
            failures.extend(boot_failures(
                final_boot, final_recovery, args.expected_version,
                app_identity, args.expected_cid))
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            synchronize_console(device, 20.0)
            final_lock = read_only_query(
                device, b"device-lock.state", LOCK_SCHEMA, "state")
            reports["product_after_cleanup_cold"] = final_lock
            failures.extend(state_failures(
                final_lock, "product_after_cleanup_cold",
                status="unconfigured", failure="none", failed_attempts=0,
                generation=0, protected=False, fixture_active=False))
            final_input = read_only_query(
                device, b"input.state",
                "leshy.input.frontend.v1", "state")
            reports["final_input"] = final_input
            failures.extend(expect(final_input, {
                "status": "ready", "read_errors": 0, "queue_drops": 0,
            }, "final_input"))
            device.close()
            device = None
        except Exception as final_error:
            failures.append(
                "final product verification: "
                f"{type(final_error).__name__}: {final_error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": not failures and fixture_cleanup_proven,
        "gate_eligible": not failures and fixture_cleanup_proven,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "app_elf_sha256": app_identity,
            "flashed": candidate_flashed,
            "flash_mode": "fresh",
        },
        "expected_cid": args.expected_cid,
        "reports": reports,
        "screens": screens,
        "sessions": sessions,
        "cleanup": cleanup,
        "fixture": {
            "ever_started": fixture_ever_started,
            "active_at_end": fixture_started,
            "cleanup": fixture_cleanup,
            "cleanup_proven": fixture_cleanup_proven,
            "isolated_namespace": True,
            "whole_nvs_read_or_copied": False,
            "product_namespace_written_or_erased": False,
        },
        "final_boot": final_boot,
        "final_recovery": final_recovery,
        "final_reset": final_reset,
        "privacy": {
            "ephemeral_pin_length": 6,
            "pin_or_digest_retained": False,
            "pin_editor_replies_retained": False,
            "whole_nvs_or_product_namespace_retained": False,
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
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "output": str(args.output),
        "fixture_cleaned": fixture_cleanup_proven,
    }, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
