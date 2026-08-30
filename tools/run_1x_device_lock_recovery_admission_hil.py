#!/usr/bin/env python3
"""Prove CAP-052 admission and destructive recovery on board-01."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_device_lock_hil import LOCK_SCHEMA, device_lock_page, home_device, read_only_query
from run_1x_device_lock_persistence_hil import (
    begin_hil,
    end_hil,
    enter_pin,
    ephemeral_pin,
    fixture_failures,
    state_failures,
    wait_lock_state,
    wipe_pin,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    boot_ready_failures,
    expect,
    query,
    reset_capture,
    valid_cid,
)


RUN_SCHEMA = "leshy.device_lock_recovery_admission_hil.run.v1"
ADMISSION_SCHEMA = "leshy.device_lock.admission.v1"
FIXTURE_SCHEMA = "leshy.device_lock.fixture.v1"

PROTECTED_OPERATIONS = (
    "protected_ui",
    "protected_evidence",
    "secret_read",
    "export",
    "backup",
    "companion",
    "sensitive_settings",
)
SAFE_OPERATIONS = (
    "status",
    "lock",
    "safe_stop",
    "panic",
    "cleanup",
    "update_recovery",
    "factory_reset",
)


def admission_failures(record: dict[str, Any], label: str, *, state: str,
                       protected_access: str, unlock_access: str,
                       configure_access: str,
                       protected_allowed: bool) -> list[str]:
    failures = expect(record, {
        "state": state,
        "protected_all_allowed": protected_allowed,
        "safe_all_allowed": True,
        "protected_content_returned": False,
        "radio_touched": False,
    }, label)
    access = record.get("access")
    if not isinstance(access, dict):
        return failures + [f"{label}.access: expected object"]
    expected: dict[str, str] = {
        operation: protected_access for operation in PROTECTED_OPERATIONS
    }
    expected.update({operation: "allowed" for operation in SAFE_OPERATIONS})
    expected["unlock"] = unlock_access
    expected["configure"] = configure_access
    for operation, value in expected.items():
        if access.get(operation) != value:
            failures.append(
                f"{label}.access.{operation}: "
                f"{access.get(operation)!r} != {value!r}")
    if set(access) != set(expected):
        failures.append(
            f"{label}.access operations: {sorted(access)!r} != "
            f"{sorted(expected)!r}")
    return failures


def fixture_command(device: PassiveSerial, operation: str) -> dict[str, Any]:
    allowed = {
        "begin",
        "resume",
        "cleanup",
        "factory-reset-preview",
        "factory-reset-confirm",
    }
    if operation not in allowed:
        raise ValueError("invalid fixture operation")
    return query(
        device,
        f"device-lock.persistence-fixture {operation}".encode("ascii"),
        FIXTURE_SCHEMA,
        "persistence_fixture",
    )


def admission(device: PassiveSerial) -> dict[str, Any]:
    return read_only_query(
        device, b"device-lock.admission", ADMISSION_SCHEMA, "matrix")


def wait_retry_completion(device: PassiveSerial, attempt: int) -> dict[str, Any]:
    timeout = {1: 10.0, 2: 20.0, 3: 70.0, 4: 310.0}[attempt]
    return wait_lock_state(
        device,
        lambda state: state.get("status") == "locked",
        f"retry {attempt} completion",
        timeout,
    )


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
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
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
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    correct_pin = ephemeral_pin()
    wrong_pin = ephemeral_pin(correct_pin)
    failures: list[str] = []
    reports: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {"attempted": False}
    fixture_ever_started = False
    fixture_active = False
    fixture_cleanup_proven = False
    fixture_cleanup: dict[str, Any] = {}
    device: PassiveSerial | None = None
    candidate_flashed = False
    final_boot: dict[str, Any] = {}
    final_recovery: dict[str, Any] = {}
    final_reset: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            candidate_flashed = True
            time.sleep(0.6)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics = read_only_query(device, b"metrics", "leshy.boot.v1", "ready")
        recovery = read_only_query(
            device,
            b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1",
            "state",
        )
        reports["metrics_before"] = metrics
        reports["recovery_before"] = recovery
        failures.extend(boot_failures(
            metrics, recovery, args.expected_version, app_identity,
            args.expected_cid))
        if failures:
            raise RuntimeError("candidate boot contract failed")
        cleanup_before = best_effort_cleanup(device)
        reports["cleanup_before"] = cleanup_before
        if not cleanup_before.get("complete"):
            raise RuntimeError("initial Home/zero-lease cleanup failed")
        sessions.append(begin_hil(device, run_id, app_identity))

        product_baseline = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["product_baseline"] = product_baseline
        failures.extend(state_failures(
            product_baseline, "product_baseline", status="unconfigured",
            failure="none", failed_attempts=0, generation=0,
            protected=False, fixture_active=False))
        product_admission = admission(device)
        reports["admission_unconfigured"] = product_admission
        failures.extend(admission_failures(
            product_admission, "admission_unconfigured",
            state="unconfigured", protected_access="setup_required",
            unlock_access="setup_required", configure_access="allowed",
            protected_allowed=False))

        home_device(device)
        protected_selection = action(device, "up")
        if protected_selection.get("selected_id") == "device":
            protected_selection = action(device, "up")
        reports["protected_launch_selection"] = protected_selection
        blocked_launch = action(device, "right")
        reports["blocked_launch"] = blocked_launch
        failures.extend(expect(blocked_launch, {
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "runtime_event": "setup_required",
        }, "blocked_launch"))
        blocked_export = query(
            device, b"library.export", ADMISSION_SCHEMA, "blocked")
        reports["blocked_export"] = blocked_export
        failures.extend(expect(blocked_export, {
            "operation": "export",
            "access": "setup_required",
            "protected_content_returned": False,
        }, "blocked_export"))

        fixture_begin = fixture_command(device, "begin")
        fixture_ever_started = True
        fixture_active = True
        reports["fixture_begin"] = fixture_begin
        failures.extend(fixture_failures(
            fixture_begin, "fixture_begin", status="begun",
            operation="begin", active=True, selected=True,
            cleaned=True, product_restored=False))
        home_device(device)
        device_lock_page(device)
        action(device, "right")
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
        unlocked_admission = admission(device)
        reports["admission_unlocked"] = unlocked_admission
        failures.extend(admission_failures(
            unlocked_admission, "admission_unlocked", state="unlocked",
            protected_access="allowed", unlock_access="allowed",
            configure_access="locked", protected_allowed=True))

        action(device, "right")
        locked = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["locked"] = locked
        failures.extend(state_failures(
            locked, "locked", status="locked", failure="none",
            failed_attempts=0, generation=1, protected=False,
            fixture_active=True))
        locked_admission = admission(device)
        reports["admission_locked"] = locked_admission
        failures.extend(admission_failures(
            locked_admission, "admission_locked", state="locked",
            protected_access="locked", unlock_access="allowed",
            configure_access="locked", protected_allowed=False))

        delays_ms = {1: 5000, 2: 15000, 3: 60000, 4: 300000}
        for attempt in range(1, 6):
            action(device, "right")
            enter_pin(device, wrong_pin)
            terminal = wait_lock_state(
                device,
                lambda state, final=attempt == 5:
                    state.get("status") ==
                    ("recovery_only" if final else "retry_delay"),
                f"wrong PIN attempt {attempt}",
                25.0,
            )
            reports[f"wrong_pin_{attempt}"] = terminal
            expected_status = "recovery_only" if attempt == 5 else "retry_delay"
            expected_failure = "recovery_required" if attempt == 5 else "wrong_pin"
            failures.extend(state_failures(
                terminal, f"wrong_pin_{attempt}", status=expected_status,
                failure=expected_failure, failed_attempts=attempt,
                generation=attempt + 1, protected=False,
                fixture_active=True))
            if attempt < 5:
                remaining = terminal.get("retry_remaining_ms")
                expected_ms = delays_ms[attempt]
                if (not isinstance(remaining, int) or isinstance(remaining, bool)
                        or remaining < expected_ms - 1000
                        or remaining > expected_ms):
                    failures.append(
                        f"wrong_pin_{attempt}.retry_remaining_ms={remaining!r} "
                        f"outside {expected_ms - 1000}..{expected_ms}")
                reports[f"retry_complete_{attempt}"] = wait_retry_completion(
                    device, attempt)

        recovery_admission = admission(device)
        reports["admission_recovery"] = recovery_admission
        failures.extend(admission_failures(
            recovery_admission, "admission_recovery",
            state="recovery_only", protected_access="recovery_required",
            unlock_access="recovery_required", configure_access="locked",
            protected_allowed=False))
        device.close()
        device = None

        cold_boot, cold_recovery, cold_reset = reset_capture(
            args.port, args.output, "device-lock-recovery-only", 25.0, 2)
        reports["cold_recovery_boot"] = cold_boot
        reports["cold_recovery_storage"] = cold_recovery
        reports["cold_recovery_reset"] = cold_reset
        failures.extend(boot_ready_failures(
            cold_boot, args.expected_version, app_identity))
        device, session = reopen_after_reset(args.port, run_id, app_identity)
        sessions.append(session)
        product_after_reset = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["product_after_recovery_reset"] = product_after_reset
        failures.extend(state_failures(
            product_after_reset, "product_after_recovery_reset",
            status="unconfigured", failure="none", failed_attempts=0,
            generation=0, protected=False, fixture_active=False,
            fixture_cleanup_required=True))
        fixture_resume = fixture_command(device, "resume")
        reports["fixture_resume_recovery"] = fixture_resume
        failures.extend(fixture_failures(
            fixture_resume, "fixture_resume_recovery", status="resumed",
            operation="resume", active=True, selected=True,
            cleaned=True, product_restored=False))
        restored_recovery = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["restored_recovery"] = restored_recovery
        failures.extend(state_failures(
            restored_recovery, "restored_recovery",
            status="recovery_only", failure="recovery_required",
            failed_attempts=5, generation=6, protected=False,
            fixture_active=True))
        restored_admission = admission(device)
        reports["admission_recovery_after_cold"] = restored_admission
        failures.extend(admission_failures(
            restored_admission, "admission_recovery_after_cold",
            state="recovery_only", protected_access="recovery_required",
            unlock_access="recovery_required", configure_access="locked",
            protected_allowed=False))

        preview = fixture_command(device, "factory-reset-preview")
        reports["factory_reset_preview"] = preview
        failures.extend(expect(preview, {
            "operation": "factory_reset_preview",
            "status": "confirmation_required",
            "active": True,
            "cleanup_required": True,
            "fixture_namespace_selected": True,
            "lock_status": "recovery_only",
            "failure": "confirmation_required",
            "failed_attempts": 5,
            "credential_generation": 6,
            "factory_reset_result": False,
            "protected_erase_calls": 0,
            "credential_present_during_erase": False,
            "fixture_protected_data_erased": False,
            "destructive_order_proven": False,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False,
            "radio_touched": False,
        }, "factory_reset_preview"))
        confirmed = fixture_command(device, "factory-reset-confirm")
        reports["factory_reset_confirm"] = confirmed
        failures.extend(expect(confirmed, {
            "operation": "factory_reset_confirm",
            "status": "recovered",
            "active": True,
            "cleanup_required": True,
            "fixture_namespace_selected": True,
            "lock_status": "unconfigured",
            "failure": "none",
            "failed_attempts": 0,
            "credential_generation": 0,
            "factory_reset_result": True,
            "protected_erase_calls": 1,
            "credential_present_during_erase": True,
            "fixture_protected_data_erased": True,
            "destructive_order_proven": True,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False,
            "radio_touched": False,
        }, "factory_reset_confirm"))

        fixture_cleanup = fixture_command(device, "cleanup")
        reports["fixture_cleanup"] = fixture_cleanup
        cleanup_failures = fixture_failures(
            fixture_cleanup, "fixture_cleanup", status="cleaned",
            operation="cleanup", active=False, selected=False,
            cleaned=True, product_restored=True)
        failures.extend(cleanup_failures)
        fixture_cleanup_proven = not cleanup_failures
        fixture_active = False
        sessions.append(end_hil(device, run_id))
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            failures.append("cleanup: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"workflow: {type(error).__name__}: {error}")
    finally:
        wipe_pin(correct_pin)
        wipe_pin(wrong_pin)
        if fixture_ever_started and not fixture_cleanup_proven:
            try:
                if device is None:
                    device = PassiveSerial(args.port, 115200, timeout=0.25)
                    synchronize_console(device, 20.0)
                hil_state = read_only_query(
                    device, b"hil.state", "leshy.hil.session.v1", "state")
                if hil_state.get("active") is not True:
                    sessions.append(begin_hil(device, run_id, app_identity))
                fixture_cleanup = fixture_command(device, "cleanup")
                cleanup_failures = fixture_failures(
                    fixture_cleanup, "fixture_cleanup_finally",
                    status="cleaned", operation="cleanup", active=False,
                    selected=False, cleaned=True, product_restored=True)
                failures.extend(cleanup_failures)
                fixture_cleanup_proven = not cleanup_failures
                fixture_active = False
                if fixture_cleanup_proven:
                    try:
                        sessions.append(end_hil(device, run_id))
                    except Exception:
                        pass
            except Exception as cleanup_error:
                failures.append(
                    "fixture cleanup: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}")
        if device is not None:
            device.close()
            device = None

    if fixture_ever_started and fixture_cleanup_proven:
        try:
            final_boot, final_recovery, final_reset = reset_capture(
                args.port, args.output, "device-lock-product-final", 25.0, 2)
            failures.extend(boot_ready_failures(
                final_boot, args.expected_version, app_identity))
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            synchronize_console(device, 20.0)
            final_lock = read_only_query(
                device, b"device-lock.state", LOCK_SCHEMA, "state")
            reports["product_final"] = final_lock
            failures.extend(state_failures(
                final_lock, "product_final", status="unconfigured",
                failure="none", failed_attempts=0, generation=0,
                protected=False, fixture_active=False))
            final_input = read_only_query(
                device, b"input.state", "leshy.input.frontend.v1", "state")
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
            "flash_mode": "fresh" if candidate_flashed else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "reports": reports,
        "sessions": sessions,
        "cleanup": cleanup,
        "fixture": {
            "ever_started": fixture_ever_started,
            "active_at_end": fixture_active,
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
            "protected_ui_block": True,
            "protected_export_block": True,
            "admission_matrix": True,
            "recovery_only": True,
            "destructive_reset_order": True,
            "radio": False,
            "product_storage_write": False,
            "mac_wifi": False,
            "clone": False,
            "cardputer": False,
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
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
