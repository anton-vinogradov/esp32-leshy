#!/usr/bin/env python3
"""Prove the Product Survey missing-source UI and cleanup path on real TFT."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
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
    resolve_expected_cid,
    setup_failures,
    valid_cid,
    wait_ui_state,
)


RUN_SCHEMA = "leshy.product_survey_missing_source_hil.run.v1"
INJECTION_SCHEMA = "leshy.survey.source_unavailable_test.v1"


def arm_failures(state: dict[str, Any]) -> list[str]:
    return expect(state, {
        "status": "armed",
        "one_shot": True,
        "armed": True,
        "worker_idle": True,
        "ui_home": True,
        "runtime_owner": "none",
        "lease_mask": 0,
        "hardware_touched": False,
        "source_started": False,
        "storage_mounted": False,
        "storage_written": False,
    }, "arm")


def source_unavailable_failures(state: dict[str, Any],
                                expected_cid: str) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "none",
        "lease_mask": 0,
        "survey_simulated": False,
        "survey_persistent": True,
        "survey_workflow_state": "setup",
        "survey_running": False,
        "survey_observations": 0,
        "survey_generation": 0,
        "survey_received": 0,
        "survey_forwarded": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_product_selected": True,
        "survey_product_status": "source_unavailable",
        "survey_product_backend_open": False,
        "survey_product_store_status": "permitted",
        "survey_product_admission_status": "source_unavailable",
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_product_identity_status": "valid",
        "survey_scan_status": "not_started",
        "survey_scan_reported": 0,
        "survey_scan_read": 0,
        "survey_scan_accepted": 0,
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_product_cleanup_complete": True,
        "survey_product_worker_ready": True,
        "survey_product_source_active": False,
        "survey_product_source_start_attempted": False,
        "survey_product_source_failure_injected": True,
        "survey_product_source_injection_armed": False,
        "survey_product_store_open_attempted": False,
        "survey_product_store_bytes_written": 0,
        "survey_product_scan_active": False,
        "survey_product_cancel_requested_during_scan": False,
        "survey_product_scan_cycles": 0,
        "library_persistent": True,
    }, "source_unavailable")
    attempts = state.get("survey_product_identity_attempts")
    retries = state.get("survey_product_identity_transient_retries")
    if (not isinstance(attempts, int) or isinstance(attempts, bool) or
            attempts < 1 or attempts > 8):
        failures.append("source_unavailable.identity_attempts: expected 1..8")
    if (not isinstance(retries, int) or isinstance(retries, bool) or
            not isinstance(attempts, int) or retries != attempts - 1):
        failures.append(
            "source_unavailable.identity_retries: expected attempts - 1"
        )
    return failures


def retry_blocked_failures(state: dict[str, Any],
                           expected_cid: str) -> list[str]:
    failures = source_unavailable_failures(state, expected_cid)
    failures.extend(expect(state, {
        "action": "select",
        "changed": False,
        "runtime_event": "source_unavailable_waiting_back",
    }, "retry_blocked"))
    return failures


def home_failures(state: dict[str, Any]) -> list[str]:
    return expect(state, {
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "survey_product_status": "cancelled",
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
        "survey_product_scan_active": False,
        "survey_product_source_injection_armed": False,
    }, "home")


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
            "cleanup_complete": True,
            "blocked_write_attempts": 0,
            "physical_write_calls": 0,
            "owned_after": 0,
        }, f"recovery_{name}"))
    for field in ("generation", "observations"):
        if after.get(field) != before.get(field):
            failures.append(
                f"recovery_after.{field}: {after.get(field)!r} changed from "
                f"{before.get(field)!r} after missing-source failure"
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
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    failures: list[str] = []
    run_id = secrets.token_hex(16)
    runner_source_sha256 = sha256_file(Path(__file__).resolve())
    firmware_sha = ""
    app_identity = ""
    expected_cid = args.expected_cid or ""
    before_ready: dict[str, Any] = {}
    before_recovery: dict[str, Any] = {}
    before_timing: dict[str, Any] = {}
    after_ready: dict[str, Any] = {}
    after_recovery: dict[str, Any] = {}
    after_timing: dict[str, Any] = {}
    arm: dict[str, Any] = {}
    setup: dict[str, Any] = {}
    start_ack: dict[str, Any] = {}
    unavailable: dict[str, Any] = {}
    retry_blocked: dict[str, Any] = {}
    home: dict[str, Any] = {}
    cleanup_before_reboot: dict[str, Any] = {"attempted": False}
    cleanup_final: dict[str, Any] = {"attempted": False}
    captures: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    try:
        shutil.copyfile(args.firmware, candidate)
        firmware_sha = sha256_file(candidate)
        app_identity = app_elf_sha256(candidate)
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(args.post_flash_settle)

        before_ready, before_recovery, before_timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
            try:
                synchronize_console(device)
                before_recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state"
                )
                try:
                    expected_cid = resolve_expected_cid(
                        args.expected_cid, before_recovery
                    )
                except ValueError as error:
                    failures.append(f"product_identity: {error}")
                failures.extend(boot_failures(
                    before_ready, before_recovery, args.expected_version,
                    app_identity, expected_cid
                ))
                if not failures:
                    arm = query(
                        device,
                        b"survey.product.test-source-unavailable once",
                        INJECTION_SCHEMA, "state"
                    )
                    failures.extend(arm_failures(arm))
                if not failures:
                    trace.append(action(device, "down"))
                    setup = action(device, "select")
                    trace.append(setup)
                    failures.extend(setup_failures(setup))
                    failures.extend(expect(setup, {
                        "survey_product_source_injection_armed": True,
                    }, "setup_injection"))
                    captures["setup"] = capture(device, frames, "setup")
                if not failures:
                    start_ack = action(device, "select")
                    trace.append(start_ack)
                    failures.extend(expect(start_ack, {
                        "page": "survey",
                        "runtime_owner": "survey",
                        "lease_mask": 15,
                        "survey_workflow_state": "setup",
                        "survey_product_status": "preparing",
                    }, "start_ack"))
                    unavailable = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("page") == "survey" and
                            state.get("survey_product_status") ==
                                "source_unavailable" and
                            state.get("lease_mask") == 0
                        ),
                        20.0,
                        "missing-source failure never reached visible zero-lease state",
                    )
                    trace.append(unavailable)
                    failures.extend(source_unavailable_failures(
                        unavailable, expected_cid
                    ))
                if not failures:
                    captures["source-unavailable"] = capture(
                        device, frames, "source-unavailable"
                    )
                    retry_blocked = action(device, "select")
                    trace.append(retry_blocked)
                    failures.extend(retry_blocked_failures(
                        retry_blocked, expected_cid
                    ))
                    home = action(device, "back")
                    trace.append(home)
                    failures.extend(home_failures(home))
                    captures["home"] = capture(device, frames, "home")
            except Exception as error:
                failures.append(
                    f"missing_source_workflow: {type(error).__name__}: {error}"
                )
            finally:
                try:
                    query(
                        device,
                        b"survey.product.test-source-unavailable clear",
                        INJECTION_SCHEMA, "state"
                    )
                except Exception:
                    pass
                cleanup_before_reboot = best_effort_cleanup(device)
                if not cleanup_before_reboot.get("complete"):
                    failures.append(
                        "missing_source_cleanup: terminal zero-lease state unproven"
                    )

        if unavailable and not failures:
            after_ready, after_recovery, after_timing = reset_capture(
                args.port, args.output, "boot-after", args.boot_seconds
            )
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
                try:
                    synchronize_console(device)
                    after_recovery = query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"
                    )
                    failures.extend(boot_failures(
                        after_ready, after_recovery, args.expected_version,
                        app_identity, expected_cid
                    ))
                    failures.extend(unchanged_recovery_failures(
                        before_recovery, after_recovery, expected_cid
                    ))
                except Exception as error:
                    failures.append(
                        f"post_failure_boot: {type(error).__name__}: {error}"
                    )
                finally:
                    cleanup_final = best_effort_cleanup(device)
                    if not cleanup_final.get("complete"):
                        failures.append(
                            "post_failure_cleanup: terminal zero-lease state unproven"
                        )
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

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
            "ready": before_ready,
            "recovery": before_recovery,
            "timing": before_timing,
        },
        "injection": arm,
        "setup": setup,
        "start_ack": start_ack,
        "source_unavailable": unavailable,
        "retry_blocked": retry_blocked,
        "home": home,
        "cleanup_before_reboot": cleanup_before_reboot,
        "boot_after": {
            "ready": after_ready,
            "recovery": after_recovery,
            "timing": after_timing,
        },
        "cleanup_final": cleanup_final,
        "captures": captures,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
