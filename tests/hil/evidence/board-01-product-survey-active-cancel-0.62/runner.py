#!/usr/bin/env python3
"""Cancel Product Survey during a physically active passive Wi-Fi scan."""

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


RUN_SCHEMA = "leshy.product_survey_cancel_hil.run.v1"


def active_scan_failures(state: dict[str, Any], expected_cid: str) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "running",
        "survey_product_status": "running",
        "survey_product_worker_ready": True,
        "survey_product_source_active": True,
        "survey_product_scan_active": True,
        "survey_product_cancel_requested_during_scan": False,
        "survey_product_backend_open": True,
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_product_identity_status": "valid",
        "survey_product_identity_attempts": 1,
        "survey_product_identity_transient_retries": 0,
    }, "active_scan")
    if state.get("survey_product_start_action_us", 10001) > 10000:
        failures.append("active_scan.start_action exceeded 10000 us")
    return failures


def cancel_ack_failures(state: dict[str, Any], latency_ms: float) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "running",
        "survey_product_status": "cancelling",
        "survey_product_source_active": True,
        "survey_product_cancel_requested_during_scan": True,
        "survey_product_backend_open": True,
    }, "cancel_ack")
    if state.get("survey_product_stop_action_us", 10001) > 10000:
        failures.append("cancel_ack.stop_action exceeded 10000 us")
    if latency_ms <= 0 or latency_ms > 150:
        failures.append(f"cancel_ack.latency_ms: {latency_ms:.3f} outside (0, 150]")
    return failures


def cancelled_failures(state: dict[str, Any]) -> list[str]:
    return expect(state, {
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "survey_product_status": "cancelled",
        "survey_product_source_active": False,
        "survey_product_scan_active": False,
        "survey_product_cancel_requested_during_scan": True,
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
    }, "cancelled")


def unchanged_recovery_failures(before: dict[str, Any], after: dict[str, Any],
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
                f"{before.get(field)!r} after cancel"
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
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    parser.add_argument("--post-flash-settle", type=float, default=1.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.expected_cid is not None and not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be exactly 32 uppercase hexadecimal characters")
    if args.post_flash_settle < 0 or args.post_flash_settle > 10:
        parser.error("--post-flash-settle must be between 0 and 10 seconds")

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
    setup: dict[str, Any] = {}
    start_ack: dict[str, Any] = {}
    active_scan: dict[str, Any] = {}
    cancel_ack: dict[str, Any] = {}
    cancelled: dict[str, Any] = {}
    cancel_ack_ms = 0.0
    cleanup_before_reboot: dict[str, Any] = {"attempted": False}
    cleanup_final: dict[str, Any] = {"attempted": False}
    captures: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    try:
        shutil.copyfile(args.firmware, candidate)
        firmware_sha = sha256_file(candidate)
        app_identity = app_elf_sha256(candidate)
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
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
                    trace.append(action(device, "down"))
                    setup = action(device, "select")
                    trace.append(setup)
                    failures.extend(setup_failures(setup))
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
                        "survey_product_scan_active": False,
                        "survey_product_cancel_requested_during_scan": False,
                    }, "start_ack"))
                    active_scan = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "running" and
                            state.get("survey_product_source_active") is True and
                            state.get("survey_product_scan_active") is True
                        ),
                        20.0,
                        "Product Survey never exposed an active physical scan",
                    )
                    trace.append(active_scan)
                    failures.extend(active_scan_failures(active_scan, expected_cid))
                if not failures:
                    cancel_started = time.monotonic()
                    cancel_ack = action(device, "back")
                    cancel_ack_ms = (time.monotonic() - cancel_started) * 1000.0
                    trace.append(cancel_ack)
                    failures.extend(cancel_ack_failures(cancel_ack, cancel_ack_ms))
                    cancelled = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("page") == "home" and
                            state.get("survey_product_status") == "cancelled" and
                            state.get("lease_mask") == 0
                        ),
                        20.0,
                        "active-scan cancel did not reach terminal Home",
                    )
                    trace.append(cancelled)
                    failures.extend(cancelled_failures(cancelled))
                    captures["cancelled"] = capture(
                        device, frames, "cancelled"
                    )
            except Exception as error:
                failures.append(f"cancel_workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_before_reboot = best_effort_cleanup(device)
                if not cleanup_before_reboot.get("complete"):
                    failures.append("cancel_cleanup: terminal zero-lease state unproven")

        if cancelled and not failures:
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
                    failures.append(f"post_cancel_boot: {type(error).__name__}: {error}")
                finally:
                    cleanup_final = best_effort_cleanup(device)
                    if not cleanup_final.get("complete"):
                        failures.append(
                            "post_cancel_cleanup: terminal zero-lease state unproven"
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
        "setup": setup,
        "start_ack": start_ack,
        "active_scan": active_scan,
        "cancel_ack": cancel_ack,
        "cancel_ack_ms": cancel_ack_ms,
        "cancelled": cancelled,
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
