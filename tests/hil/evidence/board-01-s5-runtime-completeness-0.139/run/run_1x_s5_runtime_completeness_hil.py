#!/usr/bin/env python3
"""Prove the S5.5 power/profile/Sub-GHz Store runtime slice on one board."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_hil_scenario import select_home_app


RUN_SCHEMA = "leshy.s5_runtime_completeness_hil.run.v1"
POWER_SCHEMA = "leshy.power.runtime.v1"
LOW_SCHEMA = "leshy.power.low_voltage_test.v1"
SLEEP_SCHEMA = "leshy.power.sleep_test.v1"
SUBGHZ_SCHEMA = "leshy.capture.subghz_raw.v1"
FIXTURE_SCHEMA = "leshy.capture.subghz_store_fixture.v1"


def wait_record(device: PassiveSerial, command: bytes, schema: str,
                predicate: Callable[[dict[str, Any]], bool], timeout_s: float,
                message: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, command, schema, "state")
        if predicate(last):
            return last
        time.sleep(0.1)
    raise TimeoutError(f"{message}: {last!r}")


def reconnect_after_light_sleep(device: PassiveSerial,
                                timeout_s: float = 12.0) -> None:
    """Replace the macOS native-USB handle invalidated by S3 light sleep."""
    time.sleep(0.05)
    device.close()
    time.sleep(1.0)
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            device.open()
            synchronize_console(device, 2.0)
            return
        except Exception as error:
            last_error = error
            if device.is_open:
                device.close()
            time.sleep(0.25)
    raise TimeoutError(
        f"native USB did not recover after light sleep: {last_error}")


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

    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one flash mode")
    if not args.firmware.is_file():
        parser.error(f"firmware missing: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
        check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    retained_firmware = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    retained_runner = args.output / Path(__file__).name
    shutil.copyfile(args.firmware, retained_firmware)
    build = args.firmware.parent
    shutil.copyfile(build / "firmware.elf", retained_elf)
    shutil.copyfile(build / "firmware.map", retained_map)
    shutil.copyfile(Path(__file__), retained_runner)
    # The ESP app descriptor carrying the ELF digest lives in the flash image;
    # the helper intentionally parses firmware.bin rather than the ELF file.
    app_sha = app_elf_sha256(retained_firmware)
    firmware_sha = sha256_file(retained_firmware)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    expected_generation = 0
    saved_generation = 0

    try:
        if args.flash:
            flash_candidate(args.port, retained_firmware, 0x10000,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 45.0)
            ready = query(device, b"metrics", "leshy.boot.v1", "ready")
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            records["ready"] = ready
            records["recovery_before"] = recovery
            failures.extend(boot_failures(
                ready, recovery, args.expected_version, app_sha,
                args.expected_cid))
            expected_generation = int(recovery.get("generation", 0))
            records["hil_begin"] = query(
                device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
                "leshy.hil.session.v1", "begun")
            failures.extend(expect(records["hil_begin"], {
                "status": "begun", "session_id": run_id, "active": True,
                "app_elf_sha256": app_sha,
                "firmware_version": args.expected_version,
            }, "hil_begin"))

            records["power_before"] = query(
                device, b"power.state", POWER_SCHEMA, "state")
            failures.extend(expect(records["power_before"], {
                "assembly_profile": "stock-rf-no-gps-no-pn532",
                "manager_address": 117, "manager_address_ack": True,
                "manager_identified": False, "voltage_available": False,
                "battery_percent_available": False,
                "voltage_source": "gpio2_forbidden_buzzer_shared",
                "telemetry_state": "unavailable",
                "write_disposition": "atomic_only",
                "atomic_store_enabled": True,
                "confirmed_low_voltage_gate": True,
                "low_threshold_mv": 3350, "recovery_threshold_mv": 3550,
                "confirm_samples": 3, "sleep_supported": True,
                "gps": "not_applicable", "pn532": "not_applicable",
                "buzzer_inactive": True,
            }, "power_before"))
            sleep_count_before = int(
                records["power_before"].get("sleep_count", 0))

            records["low_voltage"] = query(
                device, b"power.low-voltage-test confirm", LOW_SCHEMA,
                "result")
            failures.extend(expect(records["low_voltage"], {
                "status": "pass", "injected_state": "low_voltage",
                "write_disposition": "prohibited_low_voltage",
                "store_permit": "power_unsafe", "samples": 3,
                "trip_delta": 1, "physical_storage_opened": False,
                "physical_write_calls": 0, "filesystem_mounted": False,
                "restored_state": "unavailable", "buzzer_inactive": True,
                "owned_before": 0, "owned_after": 0,
            }, "low_voltage"))
            if (records["low_voltage"].get("generation_before") !=
                    expected_generation or
                    records["low_voltage"].get("generation_after") !=
                    expected_generation):
                failures.append("low-voltage test changed catalog generation")

            # Native USB is suspended by real ESP32-S3 light sleep. Do not make
            # the gate depend on the first packet emitted during USB resume:
            # trigger once, resynchronize, then read the retained result.
            device.write(b"power.sleep-test confirm\n")
            device.flush()
            reconnect_after_light_sleep(device)
            records["sleep"] = query(
                device, b"power.sleep-test state", SLEEP_SCHEMA, "result",
                8.0)
            failures.extend(expect(records["sleep"], {
                "status": "pass", "sleep_kind": "esp32_light_sleep",
                "requested_us": 300000, "wakeup": "timer",
                "backlight_restored": True, "input_task_retained": True,
                "filesystem_mounted": False, "physical_write_calls": 0,
                "lease_mask": 0, "buzzer_inactive": True,
                "radio_tx_commands": 0,
            }, "sleep"))
            if not 280000 <= int(records["sleep"].get("elapsed_us", 0)) <= 800000:
                failures.append("light-sleep elapsed time is out of bounds")
            if (records["sleep"].get("generation_before") !=
                    records["sleep"].get("generation_after")):
                failures.append("light sleep changed catalog generation")

            trace.append(select_home_app(device, "device", trace))
            trace.append(action(device, "right"))
            trace.append(action(device, "right"))
            records["power_frame"] = capture(device, frames, "power-runtime")
            device.write(b"ui.key right\n")
            device.flush()
            reconnect_after_light_sleep(device)
            trace.append(query(device, b"ui.state", "leshy.ui.v1", "state"))
            records["power_after_public_sleep"] = query(
                device, b"power.state", POWER_SCHEMA, "state")
            if int(records["power_after_public_sleep"].get(
                    "sleep_count", 0)) != sleep_count_before + 2:
                failures.append("public Power sleep action did not execute")
            trace.append(action(device, "left"))
            trace.append(action(device, "left"))

            trace.append(select_home_app(device, "subghz", trace))
            trace.append(action(device, "right"))
            trace.append(action(device, "down"))
            trace.append(action(device, "down"))
            trace.append(action(device, "right"))
            trace.append(action(device, "right"))
            records["subghz_fixture"] = query(
                device, b"capture.subghz.test-fixture fixed-rx-only",
                FIXTURE_SCHEMA, "result")
            failures.extend(expect(records["subghz_fixture"], {
                "status": "ready", "software_fixture": True,
                "physical_signal": False, "rx_only_semantics": True,
                "frequency_khz": 433920, "pulses": 3,
                "capture_state": "complete",
                "receiver_cleanup_complete": True,
                "application_tx_calls": 0, "radio_tx_commands": 0,
                "persist_state": "volatile", "lease_mask": 9,
            }, "subghz_fixture"))
            records["subghz_complete"] = query(
                device, b"capture.subghz.state", SUBGHZ_SCHEMA, "state")
            failures.extend(expect(records["subghz_complete"], {
                "state": "complete", "passive_only": True,
                "rx_only": True, "frequency_khz": 433920, "pulses": 3,
                "application_tx_calls": 0, "tx_strobes": 0,
                "pa_table_writes": 0, "fifo_writes": 0,
                "physical_no_tx_verified": True,
                "cleanup_complete": True, "storage_written": False,
                "persist_state": "volatile", "lease_mask": 9,
            }, "subghz_complete"))
            trace.append(action(device, "right"))
            records["subghz_saved"] = wait_record(
                device, b"capture.subghz.state", SUBGHZ_SCHEMA,
                lambda value: value.get("persist_state") in
                ("saved", "failed"), 35.0,
                "Sub-GHz Store did not terminate")
            failures.extend(expect(records["subghz_saved"], {
                "persist_state": "saved", "persist_status": "saved",
                "storage_written": True, "filesystem_mount_error": 0,
                "application_tx_calls": 0, "tx_strobes": 0,
                "pa_table_writes": 0, "fifo_writes": 0,
                "physical_no_tx_verified": True, "cleanup_complete": True,
                "lease_mask": 9,
            }, "subghz_saved"))
            saved_generation = int(
                records["subghz_saved"].get("persist_generation", 0))
            if saved_generation != expected_generation + 1:
                failures.append("Sub-GHz Store generation discontinuity")
            if (int(records["subghz_saved"].get(
                    "heap_free_before_mount", 0)) <= 0 or
                    int(records["subghz_saved"].get(
                        "heap_largest_before_mount", 0)) <= 0):
                failures.append("Sub-GHz Store heap telemetry is missing")
            records["subghz_frame"] = capture(
                device, frames, "subghz-software-fixture-saved")
            records["safety_after_store"] = query(
                device, b"safety.state", "leshy.safety.v1", "state")
            failures.extend(expect(records["safety_after_store"], {
                "state": "armed", "reason": "none", "latched": False,
                "runtime_owner": "subghz", "lease_mask": 9,
                "worker_active": "none", "worker_armed": False,
                "worker_trip_count": 0,
            }, "safety_after_store"))
            trace.append(action(device, "left"))
            trace.append(action(device, "left"))
            records["ui_final"] = query(
                device, b"ui.state", "leshy.ui.v1", "state")
            failures.extend(expect(records["ui_final"], {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
                "safety_latched": False,
            }, "ui_final"))
            records["outputs_final"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            failures.extend(expect(records["outputs_final"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
                "physical_rail_kill_available": False,
                "cc1101_hard_kill_available": False,
            }, "outputs_final"))
            records["home_frame"] = capture(device, frames, "home-final")
            records["hil_end"] = query(
                device, f"hil.end {run_id}".encode("ascii"),
                "leshy.hil.session.v1", "ended")
            failures.extend(expect(records["hil_end"], {
                "status": "ended", "session_id": run_id, "active": False,
                "app_elf_sha256": app_sha,
            }, "hil_end"))
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
        try:
            with PassiveSerial(args.port, 115200, timeout=0.05) as device:
                synchronize_console(device, 10.0)
                for _ in range(4):
                    state = query(device, b"ui.state", "leshy.ui.v1", "state")
                    if (state.get("page") == "home" and
                            state.get("lease_mask") == 0):
                        break
                    action(device, "left")
                records["failure_cleanup"] = query(
                    device, b"ui.state", "leshy.ui.v1", "state")
                if records.get("hil_begin", {}).get("active") is True:
                    records["failure_hil_end"] = query(
                        device, f"hil.end {run_id}".encode("ascii"),
                        "leshy.hil.session.v1", "ended")
        except Exception as cleanup_error:
            failures.append(
                f"cleanup {type(cleanup_error).__name__}: {cleanup_error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": args.flash and not failures,
        "failures": failures,
        "board": "board-01",
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_sha,
            "map_sha256": sha256_file(retained_map),
            "runner_sha256": sha256_file(retained_runner),
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "generation_before": expected_generation,
        "generation_after_store": saved_generation,
        "records": records,
        "trace": trace,
        "scope": {
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "actual_light_sleep": True,
            "low_voltage_injection": True,
            "low_voltage_physical_write_calls": 0,
            "subghz_software_fixture": True,
            "subghz_physical_signal": False,
            "subghz_application_tx_calls": 0,
            "subghz_normal_store_authorized": True,
            "physical_subghz_positive_gate_closed": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures, "output": str(args.output),
        "generation": [expected_generation, saved_generation],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
