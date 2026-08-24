#!/usr/bin/env python3
"""Prove real Product Survey worker deadline supervision on one board."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_boot_watchdog_hil import capture_until_ready, parse_ready
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
    reset_capture,
    resolve_expected_cid,
)


RUN_SCHEMA = "leshy.worker_deadline_hil.run.v1"
SOFTWARE_RESET_REASON = 3


def wait_state(
    device: PassiveSerial,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    message: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"safety.state", "leshy.safety.v1", "state")
        if predicate(last):
            return last
        time.sleep(0.15)
    raise RuntimeError(f"{message}: {last}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    source_root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if args.source_commit != head:
        parser.error(
            f"--source-commit {args.source_commit} does not match HEAD {head}"
        )
    for diff_args in (["git", "diff", "--quiet"],
                      ["git", "diff", "--cached", "--quiet"]):
        if subprocess.run(diff_args, cwd=source_root, check=False).returncode != 0:
            parser.error("tracked source changes must be committed before exact HIL")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    runner_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected_cid = args.expected_cid or ""
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    restart_raw = b""
    clear_raw = b""

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)

        before_ready, before_recovery, before_timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        records["boot_before"] = {
            "ready": before_ready,
            "recovery": before_recovery,
            "timing": before_timing,
        }
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            before_recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            records["boot_before"]["recovery"] = before_recovery
            expected_cid = resolve_expected_cid(args.expected_cid, before_recovery)
            failures.extend(boot_failures(
                before_ready, before_recovery, args.expected_version,
                app_identity, expected_cid,
            ))
            records["safety_before"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            failures.extend(expect(records["safety_before"], {
                "state": "armed", "reason": "none", "armed": True,
                "latched": False, "runtime_owner": "none", "lease_mask": 0,
                "worker_supervision": True, "worker_active": "none",
                "worker_armed": False, "worker_expired": False,
                "worker_trip_count": 0,
            }, "safety_before"))
            records["ui_before"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            failures.extend(expect(records["ui_before"], {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
                "safety_latched": False,
            }, "ui_before"))
            if failures:
                raise RuntimeError("preflight contract failed")

            device.write(b"safety.worker-deadline-test confirm\n")
            device.flush()
            records["injection"] = read_json(
                device, "leshy.safety.worker_deadline_test.v1", "armed", 5.0
            )
            failures.extend(expect(records["injection"], {
                "worker": "product_survey", "deadline_ms": 6000,
                "injection_ms": 8000, "requires_public_survey_start": True,
                "outputs_inactive": True, "physical_write_calls": 0,
            }, "injection"))

            trace.append(action(device, "down"))
            setup = action(device, "select")
            trace.append(setup)
            failures.extend(expect(setup, {
                "page": "survey", "survey_workflow_state": "setup",
                "survey_setup_view": "plan", "survey_setup_selection": 0,
                "survey_source_selected_mask": 1,
                "survey_source_can_start": True,
            }, "survey_setup"))
            start_row = action(device, "down")
            trace.append(start_row)
            failures.extend(expect(start_row, {
                "survey_setup_selection": 1,
            }, "survey_start_row"))
            start_ack = action(device, "select")
            trace.append(start_ack)
            failures.extend(expect(start_ack, {
                "survey_product_status": "preparing",
                "survey_workflow_state": "setup",
            }, "survey_start_ack"))
            if failures:
                raise RuntimeError("public Survey start contract failed")

            records["safety_tripped"] = wait_state(
                device,
                lambda state: (
                    state.get("latched") is True and
                    state.get("reason") == "worker_deadline"
                ),
                15.0,
                "worker deadline did not latch Safe Mode",
            )
            failures.extend(expect(records["safety_tripped"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "armed": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_supervision": True,
                "worker_last_expired": "product_survey",
                "worker_armed": True, "worker_expired": True,
                "worker_deadline_ms": 6000, "worker_trip_count": 1,
                "automatic_clear": False,
            }, "safety_tripped"))
            if int(records["safety_tripped"].get("worker_age_ms", 0)) < 6000:
                failures.append("worker trip age is below its deadline")

            records["safety_cleanup"] = wait_state(
                device,
                lambda state: (
                    state.get("latched") is True and
                    state.get("worker_armed") is False and
                    state.get("worker_active") == "none"
                ),
                6.0,
                "cancelled worker did not reach terminal cleanup",
            )
            failures.extend(expect(records["safety_cleanup"], {
                "reason": "worker_deadline", "latched": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": True,
                "worker_last_expired": "product_survey",
                "worker_deadline_ms": 6000, "worker_trip_count": 1,
            }, "safety_cleanup"))
            records["outputs_latched"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state",
            )
            records["ui_latched"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            failures.extend(expect(records["outputs_latched"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
            }, "outputs_latched"))
            failures.extend(expect(records["ui_latched"], {
                "page": "safe_mode", "safety_latched": True,
                "runtime_owner": "none", "lease_mask": 0,
            }, "ui_latched"))
            records["frame_latched"] = capture(
                device, frames, "worker-deadline-latched"
            )
            device.write(b"safety.restart-test confirm\n")
            device.flush()
            records["restart_request"] = read_json(
                device, "leshy.safety.restart_test.v1", "restart", 5.0
            )
            restart_raw, restart_ready_ms = capture_until_ready(
                device, args.boot_seconds
            )
            records["restart_ready_marker_ms"] = restart_ready_ms

        (args.output / "latched-restart.ndjson").write_bytes(restart_raw)
        restart_ready = parse_ready(restart_raw)
        records["restart_ready"] = restart_ready
        failures.extend(expect(restart_ready, {
            "version": args.expected_version,
            "app_elf_sha256": app_identity,
            "reset_reason_code": SOFTWARE_RESET_REASON,
        }, "restart_ready"))

        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["safety_after_restart"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["recovery_after_restart"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            failures.extend(expect(records["safety_after_restart"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "clear_pending": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_supervision": True, "worker_active": "none",
                "worker_armed": False, "worker_expired": False,
                "automatic_clear": False,
            }, "safety_after_restart"))
            failures.extend(expect(records["recovery_after_restart"], {
                "status": "safety_latched", "cleanup_complete": True,
                "physical_write_calls": 0, "owned_after": 0,
            }, "recovery_after_restart"))
            records["ui_clear_pending"] = action(device, "right")
            failures.extend(expect(records["ui_clear_pending"], {
                "page": "safe_mode", "safety_state": "clear_pending",
                "safety_latched": True, "safety_clear_pending": True,
            }, "ui_clear_pending"))
            records["frame_clear_pending"] = capture(
                device, frames, "worker-deadline-clear-pending"
            )
            device.write(b"ui.key right\n")
            device.flush()
            clear_raw, clear_ready_ms = capture_until_ready(
                device, args.boot_seconds
            )
            records["clear_ready_marker_ms"] = clear_ready_ms

        (args.output / "clear-restart.ndjson").write_bytes(clear_raw)
        clear_ready = parse_ready(clear_raw)
        records["clear_ready"] = clear_ready
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["recovery_final"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            records["safety_final"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["ui_final"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["frame_final"] = capture(device, frames, "home-final")
        failures.extend(boot_failures(
            clear_ready, records["recovery_final"], args.expected_version,
            app_identity, expected_cid,
        ))
        failures.extend(expect(records["safety_final"], {
            "state": "armed", "reason": "none", "armed": True,
            "latched": False, "trip_count": 0,
            "emergency_quiesce_count": 0,
            "runtime_owner": "none", "lease_mask": 0,
            "worker_supervision": True, "worker_active": "none",
            "worker_armed": False, "worker_expired": False,
            "worker_trip_count": 0,
        }, "safety_final"))
        failures.extend(expect(records["ui_final"], {
            "page": "home", "safety_latched": False,
            "runtime_owner": "none", "lease_mask": 0,
        }, "ui_final"))
        if (records["recovery_final"].get("generation") !=
                before_recovery.get("generation") or
                records["recovery_final"].get("observations") !=
                before_recovery.get("observations")):
            failures.append("worker deadline injection changed product catalog")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "runner_sha256": runner_sha,
            "flashed": args.flash,
        },
        "expected_cid": expected_cid,
        "restart_raw": {
            "bytes": len(restart_raw),
            "sha256": hashlib.sha256(restart_raw).hexdigest(),
        },
        "clear_raw": {
            "bytes": len(clear_raw),
            "sha256": hashlib.sha256(clear_raw).hexdigest(),
        },
        "records": records,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
