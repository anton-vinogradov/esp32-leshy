#!/usr/bin/env python3
"""Prove the runtime Task-WDT, retained Safe Mode, and explicit clear on one board."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from capture_1x_boot import capture_reconnecting_until_ready
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_boot_watchdog_hil import parse_ready
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


RUN_SCHEMA = "leshy.safety_watchdog_hil.run.v2"
WATCHDOG_RESET_REASONS = {4, 5, 6, 7}
SOFTWARE_RESET_REASON = 3


def journal_latched_failures(
        state: dict[str, Any], expected_version: str,
        app_identity: str, expected_sequence: int,
        first_boot: bool) -> list[str]:
    failures = expect(state, {
        "watchdog_trace_valid": True,
        "watchdog_incident_sequence": expected_sequence,
        "watchdog_trip_stage": "console",
        "watchdog_trip_wifi_view": "none",
        "watchdog_journal_present": True,
        "watchdog_journal_load_status": "valid",
        "watchdog_journal_persist_status": (
            "written_verified" if first_boot else "already_persisted"
        ),
        "watchdog_journal_nvs_write_attempted": first_boot,
        "watchdog_journal_nvs_verified": True,
        "watchdog_journal_sequence": expected_sequence,
        "watchdog_journal_version": expected_version,
        "watchdog_journal_app_elf_sha256": app_identity,
        "watchdog_journal_reset_reason_code": 6,
        "watchdog_journal_stage": "console",
        "watchdog_journal_wifi_view": "none",
        "watchdog_journal_sd_status": "deferred_safe_mode",
        "watchdog_journal_sd_write_attempted": False,
    }, "watchdog_journal_latched")
    if state.get("watchdog_journal_triggered_cpu_mask", 0) == 0:
        failures.append(
            "watchdog_journal_latched.triggered_cpu_mask: expected nonzero"
        )
    if (state.get("watchdog_trip_page") !=
            state.get("watchdog_journal_page")):
        failures.append("watchdog journal changed the retained page")
    if state.get("watchdog_journal_sd_mirrored_sequence") == expected_sequence:
        failures.append("Safe Mode unexpectedly marked the incident on SD")
    return failures


def journal_final_failures(
        state: dict[str, Any], expected_version: str,
        app_identity: str, expected_sequence: int) -> list[str]:
    return expect(state, {
        "watchdog_trace_valid": False,
        "watchdog_incident_sequence": 0,
        "watchdog_journal_present": True,
        "watchdog_journal_load_status": "valid",
        "watchdog_journal_persist_status": "retained_verified",
        "watchdog_journal_nvs_write_attempted": False,
        "watchdog_journal_nvs_verified": True,
        "watchdog_journal_sequence": expected_sequence,
        "watchdog_journal_version": expected_version,
        "watchdog_journal_app_elf_sha256": app_identity,
        "watchdog_journal_reset_reason_code": 6,
        "watchdog_journal_stage": "console",
        "watchdog_journal_wifi_view": "none",
        "watchdog_journal_sd_status": "written_verified",
        "watchdog_journal_sd_write_attempted": True,
        "watchdog_journal_sd_write_status": "written",
        "watchdog_journal_sd_mirrored_sequence": expected_sequence,
    }, "watchdog_journal_final")


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
    parser.add_argument("--watchdog-seconds", type=float, default=20.0)
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
        stdout=subprocess.PIPE, text=True
    ).stdout.strip()
    if args.source_commit != head:
        parser.error(
            f"--source-commit {args.source_commit} does not match HEAD {head}"
        )
    source_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if source_status:
        parser.error("source tree must be clean before exact HIL")

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
    watchdog_raw = b""
    restart_raw = b""
    clear_raw = b""
    flash_completed = False

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flash_completed = True
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
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            records["boot_before"]["recovery"] = before_recovery
            expected_cid = resolve_expected_cid(
                args.expected_cid, before_recovery
            )
            failures.extend(boot_failures(
                before_ready, before_recovery, args.expected_version,
                app_identity, expected_cid
            ))
            records["safety_before"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            prior_sequence = int(
                records["safety_before"].get(
                    "watchdog_journal_sequence", 0
                )
            )
            expected_sequence = prior_sequence + 1
            if prior_sequence >= 0xFFFFFFFF:
                failures.append("watchdog journal sequence exhausted")
            records["ui_before"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["outputs_before"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state"
            )
            failures.extend(expect(records["safety_before"], {
                "state": "armed", "reason": "none", "armed": True,
                "latched": False, "clear_pending": False,
                "trip_count": 0, "emergency_quiesce_count": 0,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "software_only": True,
                "physical_rail_kill_available": False,
                "thermal_sensor_available": False,
                "cc1101_hard_kill_available": False,
                "automatic_clear": False,
            }, "safety_before"))
            if records["safety_before"].get(
                    "watchdog_journal_present", False):
                failures.extend(expect(records["safety_before"], {
                    "watchdog_journal_load_status": "valid",
                    "watchdog_journal_nvs_verified": True,
                }, "journal_before"))
            failures.extend(expect(records["ui_before"], {
                "page": "home", "safety_latched": False,
                "runtime_owner": "none", "lease_mask": 0,
            }, "ui_before"))
            if not failures:
                device.write(b"safety.watchdog-test confirm\n")
                device.flush()
                records["injection"] = read_json(
                    device, "leshy.safety.watchdog_test.v1", "armed", 5.0
                )
        if "injection" in records:
            (watchdog_raw, ready_ms, watchdog_disconnects,
             watchdog_open_attempts) = capture_reconnecting_until_ready(
                args.port, args.watchdog_seconds
            )
            records["watchdog_ready_marker_ms"] = ready_ms
            records["watchdog_usb_disconnects"] = watchdog_disconnects
            records["watchdog_usb_open_attempts"] = watchdog_open_attempts
            if ready_ms is None:
                failures.append("watchdog_boot.ready_marker: missing")
        (args.output / "watchdog-reset.ndjson").write_bytes(watchdog_raw)
        watchdog_ready = parse_ready(watchdog_raw)
        records["watchdog_ready"] = watchdog_ready
        if watchdog_ready.get("reset_reason_code") not in WATCHDOG_RESET_REASONS:
            failures.append("watchdog reset reason was not panic/watchdog")
        failures.extend(expect(records.get("injection", {}), {
            "status": "ready", "outputs_inactive": True,
            "filesystem_write_attempted": False, "physical_write_calls": 0,
        }, "injection"))

        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["safety_latched"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["ui_latched"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["outputs_latched"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state"
            )
            records["recovery_latched"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            records["frame_latched"] = capture(
                device, frames, "safety-latched"
            )
            failures.extend(expect(records["safety_latched"], {
                "state": "latched", "reason": "runtime_watchdog",
                "armed": True, "latched": True, "clear_pending": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "automatic_clear": False,
            }, "safety_latched"))
            failures.extend(journal_latched_failures(
                records["safety_latched"], args.expected_version,
                app_identity, expected_sequence, True,
            ))
            failures.extend(expect(records["ui_latched"], {
                "page": "safe_mode", "safety_latched": True,
                "runtime_owner": "none", "lease_mask": 0,
            }, "ui_latched"))
            failures.extend(expect(records["outputs_latched"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
                "physical_rail_kill_available": False,
                "cc1101_hard_kill_available": False,
            }, "outputs_latched"))
            failures.extend(expect(records["recovery_latched"], {
                "status": "safety_latched", "cleanup_complete": True,
                "physical_write_calls": 0, "owned_after": 0,
            }, "recovery_latched"))
            # A later reset must not silently turn an accepted watchdog latch
            # back into normal operation. Use the firmware's explicit,
            # output-quiesced software restart so native USB control-line
            # behavior cannot become part of the safety claim.
            device.write(b"safety.restart-test confirm\n")
            device.flush()
            records["latched_restart_request"] = read_json(
                device, "leshy.safety.restart_test.v1", "restart", 5.0
            )
        (restart_raw, restart_ready_ms, restart_disconnects,
         restart_open_attempts) = capture_reconnecting_until_ready(
            args.port, args.boot_seconds
        )
        records["latched_restart_ready_marker_ms"] = restart_ready_ms
        records["latched_restart_usb_disconnects"] = restart_disconnects
        records["latched_restart_usb_open_attempts"] = restart_open_attempts
        if restart_ready_ms is None:
            failures.append("latched_restart_boot.ready_marker: missing")
        (args.output / "latched-restart.ndjson").write_bytes(restart_raw)
        latched_restart_ready = parse_ready(restart_raw)
        records["latched_restart_ready"] = latched_restart_ready
        failures.extend(expect(records["latched_restart_request"], {
            "latch_preserved": True, "outputs_inactive": True,
            "filesystem_write_attempted": False, "physical_write_calls": 0,
        }, "latched_restart_request"))
        failures.extend(expect(latched_restart_ready, {
            "version": args.expected_version,
            "app_elf_sha256": app_identity,
            "reset_reason_code": SOFTWARE_RESET_REASON,
        }, "latched_restart_ready"))

        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["safety_after_latched_restart"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["recovery_after_latched_restart"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            failures.extend(expect(records["safety_after_latched_restart"], {
                "state": "latched", "reason": "runtime_watchdog",
                "armed": True, "latched": True, "clear_pending": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "automatic_clear": False,
            }, "safety_after_latched_restart"))
            failures.extend(journal_latched_failures(
                records["safety_after_latched_restart"],
                args.expected_version, app_identity, expected_sequence, False,
            ))
            failures.extend(expect(
                records["recovery_after_latched_restart"], {
                    "status": "safety_latched", "cleanup_complete": True,
                    "physical_write_calls": 0, "owned_after": 0,
                }, "recovery_after_latched_restart"
            ))
            records["ui_clear_pending"] = action(device, "right")
            failures.extend(expect(records["ui_clear_pending"], {
                "page": "safe_mode", "safety_state": "clear_pending",
                "safety_latched": True, "safety_clear_pending": True,
            }, "ui_clear_pending"))
            records["frame_clear_pending"] = capture(
                device, frames, "safety-clear-pending"
            )
            device.write(b"ui.key right\n")
            device.flush()
        (clear_raw, clear_ready_ms, clear_disconnects,
         clear_open_attempts) = capture_reconnecting_until_ready(
            args.port, args.boot_seconds
        )
        records["clear_ready_marker_ms"] = clear_ready_ms
        records["clear_usb_disconnects"] = clear_disconnects
        records["clear_usb_open_attempts"] = clear_open_attempts
        if clear_ready_ms is None:
            failures.append("clear_boot.ready_marker: missing")
        (args.output / "clear-restart.ndjson").write_bytes(clear_raw)
        clear_ready = parse_ready(clear_raw)
        records["clear_ready"] = clear_ready

        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["recovery_final"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            records["safety_final"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["ui_final"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["outputs_final"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state"
            )
            records["frame_final"] = capture(device, frames, "home-final")
        failures.extend(boot_failures(
            clear_ready, records["recovery_final"], args.expected_version,
            app_identity, expected_cid
        ))
        failures.extend(expect(records["safety_final"], {
            "state": "armed", "reason": "none", "armed": True,
            "latched": False, "clear_pending": False,
            "trip_count": 0, "emergency_quiesce_count": 0,
            "runtime_owner": "none", "lease_mask": 0,
        }, "safety_final"))
        failures.extend(journal_final_failures(
            records["safety_final"], args.expected_version,
            app_identity, expected_sequence,
        ))
        failures.extend(expect(records["ui_final"], {
            "page": "home", "safety_latched": False,
            "runtime_owner": "none", "lease_mask": 0,
        }, "ui_final"))
        if (records["recovery_final"].get("generation") !=
                before_recovery.get("generation") or
                records["recovery_final"].get("observations") !=
                before_recovery.get("observations")):
            failures.append("safety injection changed product catalog")
    except Exception as error:  # retain terminal fail-closed evidence
        failures.append(f"{type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": flash_completed and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "runner_sha256": runner_sha,
            "flash_requested": args.flash,
            "flashed": flash_completed,
        },
        "expected_cid": expected_cid,
        "watchdog_raw": {
            "bytes": len(watchdog_raw),
            "sha256": hashlib.sha256(watchdog_raw).hexdigest(),
        },
        "restart_raw": {
            "bytes": len(restart_raw),
            "sha256": hashlib.sha256(restart_raw).hexdigest(),
        },
        "clear_raw": {
            "bytes": len(clear_raw),
            "sha256": hashlib.sha256(clear_raw).hexdigest(),
        },
        "records": records,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
