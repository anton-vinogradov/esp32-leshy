#!/usr/bin/env python3
"""Prove the IR Capture Store deadline with a bounded second ESP32-DIV."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_boot import (
    capture_reconnecting_until_ready,
    reset_and_capture_reconnecting,
)
from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_product_boot_watchdog_hil import parse_ready
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    parse_boot_records,
    query,
    resolve_expected_cid,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_hil_scenario import (
    fixture_admission_failures,
    fixture_inactive_failures,
    select_home_app,
    validate_fixture_profile,
)


RUN_SCHEMA = "leshy.infrared_store_deadline_hil.run.v1"
IR_SCHEMA = "leshy.capture.infrared_raw.v1"
INJECTION_SCHEMA = "leshy.safety.pulse_capture_store_deadline_test.v1"
FIXTURE_SCHEMA = "leshy.hil.fixture.signal.v1"
SOFTWARE_RESET_REASON = 3


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def wait_record(
    device: PassiveSerial,
    command: bytes,
    schema: str,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    message: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, command, schema, "state")
        if predicate(last):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"{message}: {last}")


def wait_ir(
    device: PassiveSerial,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    message: str,
) -> dict[str, Any]:
    return wait_record(
        device, b"capture.ir.state", IR_SCHEMA, predicate, timeout_s,
        message)


def wait_safety(
    device: PassiveSerial,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    message: str,
) -> dict[str, Any]:
    return wait_record(
        device, b"safety.state", "leshy.safety.v1", predicate, timeout_s,
        message)


def begin_fixture_session(
    fixture: PassiveSerial,
    session_id: str,
    fixture_app_sha: str,
    fixture_id: str,
    expected_version: str,
) -> dict[str, Any]:
    command = f"fixture.begin {session_id} {fixture_app_sha} {fixture_id}"
    armed = query(
        fixture, command.encode("ascii"), FIXTURE_SCHEMA, "armed", 5.0)
    failures = fixture_admission_failures(
        armed, expected_version, fixture_id, fixture_app_sha)
    failures.extend(expect(armed, {
        "state": "armed", "session_id": session_id, "armed": True,
    }, "fixture_admission"))
    if failures:
        raise RuntimeError("; ".join(failures))
    return armed


def emit_nec(
    fixture: PassiveSerial,
    session_id: str,
) -> dict[str, Any]:
    command = f"fixture.ir.nec.once {session_id} nec-10-34"
    result = query(
        fixture, command.encode("ascii"), FIXTURE_SCHEMA, "result", 5.0)
    failures = fixture_inactive_failures(result, "fixture_nec")
    failures.extend(expect(result, {
        "state": "complete", "session_id": session_id,
        "signal": "infrared_nec", "vector_id": "nec-10-34",
        "fixed_vector_only": True, "armed": False,
        "maximum_ir_emission_us": 100000,
    }, "fixture_nec"))
    duration = int(result.get("last_duration_us", 0))
    if not 0 < duration <= 100000:
        failures.append(f"fixture_nec duration out of bounds: {duration}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return result


def open_ir_capture(
    product: PassiveSerial,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    trace.append(select_home_app(product, "capture", trace))
    trace.append(action(product, "right"))
    trace.append(action(product, "down"))
    trace.append(action(product, "right"))
    idle = query(product, b"capture.ir.state", IR_SCHEMA, "state")
    failures = expect(idle, {
        "state": "idle", "passive_only": True, "rx_only": True,
        "gpio_rx": 21, "gpio_tx": 14, "tx_level": "low",
        "application_tx_calls": 0, "storage_written": False,
        "persist_state": "volatile", "cleanup_complete": True,
        "lease_mask": 11,
    }, "ir_idle")
    if failures:
        raise RuntimeError("; ".join(failures))
    trace.append(action(product, "right"))
    return wait_ir(
        product, lambda value: value.get("state") == "waiting", 3.0,
        "IR receiver did not enter waiting")


def wait_decoded(product: PassiveSerial) -> dict[str, Any]:
    decoded = wait_ir(
        product, lambda value: value.get("state") == "complete", 3.0,
        "fixed NEC signal was not captured")
    failures = expect(decoded, {
        "state": "complete", "protocol": "nec",
        "raw_code": 3409243920, "address": 16, "command": 52,
        "decode_integrity_valid": True, "pulses": 67,
        "start_level": False, "truncated": False,
        "cleanup_complete": True, "storage_written": False,
        "persist_state": "volatile", "lease_mask": 11,
    }, "ir_decoded")
    if int(decoded.get("transitions", 0)) < 67:
        failures.append("IR transition count is below the NEC vector")
    if failures:
        raise RuntimeError("; ".join(failures))
    return decoded


def close_ir_to_home(
    product: PassiveSerial,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    trace.append(action(product, "left"))
    trace.append(action(product, "left"))
    home = query(product, b"ui.state", "leshy.ui.v1", "state")
    failures = expect(home, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "safety_latched": False,
    }, "home_after_ir")
    if failures:
        raise RuntimeError("; ".join(failures))
    return home


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-port", required=True)
    parser.add_argument("--fixture-port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--fixture-firmware", required=True, type=Path)
    parser.add_argument("--fixture-profile", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-fixture-version", required=True)
    parser.add_argument("--expected-fixture-id", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-fixture", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--reuse-exact-fixture-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=30.0)
    parser.add_argument("--post-flash-ready-seconds", type=float, default=45.0)
    args = parser.parse_args()

    if args.candidate_port == args.fixture_port:
        parser.error("candidate and fixture ports must be distinct")
    for path in (args.firmware, args.fixture_firmware, args.fixture_profile):
        if not path.is_file():
            parser.error(f"required file is missing: {path}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one candidate flash mode")
    if args.flash_fixture == args.reuse_exact_fixture_flash:
        parser.error("choose exactly one fixture flash mode")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    source_root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_root, check=True, stdout=subprocess.PIPE,
        text=True).stdout.strip()
    if args.source_commit != head or status:
        parser.error("exact HIL requires clean committed HEAD")

    profile = load_object(args.fixture_profile)
    try:
        validate_fixture_profile(
            profile, args.expected_fixture_id, args.fixture_port)
    except ValueError as error:
        parser.error(str(error))

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    fixture_image = args.output / "fixture.bin"
    retained_profile = args.output / "fixture-profile.json"
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.fixture_firmware, fixture_image)
    shutil.copyfile(args.fixture_profile, retained_profile)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    fixture_sha = sha256_file(fixture_image)
    fixture_app_identity = app_elf_sha256(fixture_image)
    runner_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected_cid = args.expected_cid or ""
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    restart_raw = b""
    clear_raw = b""
    fixture_session = ""
    saved_generation = 0

    try:
        if args.flash:
            flash_candidate(
                args.candidate_port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        if args.flash_fixture:
            flash_candidate(
                args.fixture_port, fixture_image, 0x10000, args.flash_baud)
            time.sleep(0.5)

        # esptool already hard-resets each target.  Do not issue the
        # independent candidate reset until its boot-time product-SD recovery
        # has reached the command loop: interrupting that bounded transaction
        # tests the harness reset timing rather than the IR Store deadline.
        if args.flash or args.flash_fixture:
            with PassiveSerial(
                    args.candidate_port, 115200, timeout=0.05) as product, \
                 PassiveSerial(
                     args.fixture_port, 115200, timeout=0.05) as fixture:
                synchronize_console(product, args.post_flash_ready_seconds)
                synchronize_console(fixture, args.post_flash_ready_seconds)
                post_flash_ready = query(
                    product, b"metrics", "leshy.boot.v1", "ready")
                post_flash_recovery = query(
                    product, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                post_flash_fixture = query(
                    fixture, b"fixture.identity", FIXTURE_SCHEMA, "ready", 5.0)
                records["post_flash"] = {
                    "ready": post_flash_ready,
                    "recovery": post_flash_recovery,
                    "fixture": post_flash_fixture,
                }
                post_flash_cid = resolve_expected_cid(
                    args.expected_cid, post_flash_recovery)
                failures.extend(boot_failures(
                    post_flash_ready, post_flash_recovery,
                    args.expected_version, app_identity, post_flash_cid))
                failures.extend(fixture_admission_failures(
                    post_flash_fixture, args.expected_fixture_version,
                    args.expected_fixture_id, fixture_app_identity))
            if failures:
                raise RuntimeError("post-flash boot contract failed")

        boot_raw, ready_ms, usb_disconnects, open_attempts = \
            reset_and_capture_reconnecting(
                args.candidate_port, args.boot_seconds)
        (args.output / "boot-before.ndjson").write_bytes(boot_raw)
        before_ready, before_recovery = parse_boot_records(boot_raw)
        before_timing = {
            "bytes": len(boot_raw),
            "sha256": hashlib.sha256(boot_raw).hexdigest(),
            "first_byte_ms": None,
            "ready_marker_ms": ready_ms,
            "usb_disconnects": usb_disconnects,
            "usb_open_attempts": open_attempts,
            "reconnecting_capture": True,
        }
        records["boot_before"] = {
            "ready": before_ready, "recovery": before_recovery,
            "timing": before_timing,
        }
        with PassiveSerial(
                args.candidate_port, 115200, timeout=0.05) as product, \
             PassiveSerial(
                 args.fixture_port, 115200, timeout=0.05) as fixture:
            synchronize_console(product, 15.0)
            synchronize_console(fixture, 15.0)
            before_recovery = query(
                product, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            records["boot_before"]["recovery"] = before_recovery
            expected_cid = resolve_expected_cid(
                args.expected_cid, before_recovery)
            failures.extend(boot_failures(
                before_ready, before_recovery, args.expected_version,
                app_identity, expected_cid))
            records["fixture_identity"] = query(
                fixture, b"fixture.identity", FIXTURE_SCHEMA, "ready", 5.0)
            failures.extend(fixture_admission_failures(
                records["fixture_identity"], args.expected_fixture_version,
                args.expected_fixture_id, fixture_app_identity))
            records["fixture_reset"] = query(
                fixture, b"fixture.panic", FIXTURE_SCHEMA, "state", 5.0)
            failures.extend(fixture_inactive_failures(
                records["fixture_reset"], "fixture_reset"))
            records["safety_before"] = query(
                product, b"safety.state", "leshy.safety.v1", "state")
            failures.extend(expect(records["safety_before"], {
                "state": "armed", "reason": "none", "latched": False,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": False, "worker_trip_count": 0,
            }, "safety_before"))
            if failures:
                raise RuntimeError("preflight contract failed")
            generation_before = int(before_recovery.get("generation", 0))

            records["normal_waiting"] = open_ir_capture(product, trace)
            fixture_session = secrets.token_hex(16)
            records["fixture_normal_armed"] = begin_fixture_session(
                fixture, fixture_session, fixture_app_identity,
                args.expected_fixture_id, args.expected_fixture_version)
            records["fixture_normal_nec"] = emit_nec(
                fixture, fixture_session)
            records["normal_decoded"] = wait_decoded(product)
            trace.append(action(product, "right"))
            records["normal_saved"] = wait_ir(
                product,
                lambda value: value.get("persist_state") in
                ("saved", "failed"),
                35.0, "normal IR store did not terminate")
            failures.extend(expect(records["normal_saved"], {
                "persist_state": "saved", "persist_status": "saved",
                "storage_written": True, "filesystem_mount_error": 0,
            }, "normal_saved"))
            saved_generation = int(
                records["normal_saved"].get("persist_generation", 0))
            if saved_generation != generation_before + 1:
                failures.append("normal IR store generation discontinuity")
            if int(records["normal_saved"].get(
                    "heap_free_before_mount", 0)) <= 0 or int(
                    records["normal_saved"].get(
                        "heap_largest_before_mount", 0)) <= 0:
                failures.append("normal IR store heap telemetry missing")
            records["safety_after_normal"] = query(
                product, b"safety.state", "leshy.safety.v1", "state")
            failures.extend(expect(records["safety_after_normal"], {
                "state": "armed", "latched": False,
                "worker_active": "none", "worker_armed": False,
                "worker_deadline_ms": 8000, "worker_arm_count": 1,
                "worker_trip_count": 0,
            }, "safety_after_normal"))
            if int(records["safety_after_normal"].get(
                    "worker_heartbeat_count", 0)) < 8:
                failures.append("normal IR store heartbeat coverage incomplete")
            records["home_after_normal"] = close_ir_to_home(product, trace)
            if failures:
                raise RuntimeError("normal IR calibration failed")

            product.write(
                b"safety.capture-ir-store-deadline-test confirm\n")
            product.flush()
            records["injection"] = read_json(
                product, INJECTION_SCHEMA, "armed", 5.0)
            failures.extend(expect(records["injection"], {
                "worker": "infrared_capture_store", "source": "infrared",
                "deadline_ms": 8000, "injection_ms": 10000,
                "requires_public_capture_save": True,
                "before_storage_hardware": True,
                "outputs_inactive": True, "physical_write_calls": 0,
            }, "injection"))

            records["injected_waiting"] = open_ir_capture(product, trace)
            fixture_session = secrets.token_hex(16)
            records["fixture_injected_armed"] = begin_fixture_session(
                fixture, fixture_session, fixture_app_identity,
                args.expected_fixture_id, args.expected_fixture_version)
            records["fixture_injected_nec"] = emit_nec(
                fixture, fixture_session)
            records["injected_decoded"] = wait_decoded(product)
            trace.append(action(product, "right"))
            records["saving"] = query(
                product, b"capture.ir.state", IR_SCHEMA, "state")
            failures.extend(expect(records["saving"], {
                "persist_state": "saving", "persist_status": "saving",
                "storage_written": False, "heap_free_before_mount": 0,
                "heap_largest_before_mount": 0,
                "filesystem_mount_error": 0,
            }, "injected_saving"))
            if failures:
                raise RuntimeError("public injected IR save contract failed")

            records["safety_tripped"] = wait_safety(
                product,
                lambda value: value.get("latched") is True and
                value.get("reason") == "worker_deadline",
                15.0, "IR store deadline did not latch Safe Mode")
            failures.extend(expect(records["safety_tripped"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "armed": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_last_expired": "infrared_capture_store",
                "worker_active": "infrared_capture_store",
                "worker_armed": True, "worker_expired": True,
                "worker_deadline_ms": 8000, "worker_arm_count": 2,
                "worker_trip_count": 1, "automatic_clear": False,
            }, "safety_tripped"))
            if int(records["safety_tripped"].get("worker_age_ms", 0)) < 8000:
                failures.append("IR store trip age is below its deadline")
            records["safety_cleanup"] = wait_safety(
                product,
                lambda value: value.get("latched") is True and
                value.get("worker_armed") is False and
                value.get("worker_active") == "none",
                6.0, "cancelled IR store did not clean up")
            records["ui_latched"] = query(
                product, b"ui.state", "leshy.ui.v1", "state")
            records["outputs_latched"] = query(
                product, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            failures.extend(expect(records["safety_cleanup"], {
                "reason": "worker_deadline", "latched": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_last_expired": "infrared_capture_store",
                "worker_trip_count": 1,
            }, "safety_cleanup"))
            failures.extend(expect(records["outputs_latched"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
            }, "outputs_latched"))
            records["frame_latched"] = capture(
                product, frames, "infrared-store-deadline-latched")

            product.write(b"safety.restart-test confirm\n")
            product.flush()
            records["restart_request"] = read_json(
                product, "leshy.safety.restart_test.v1", "restart", 5.0)

        (restart_raw, restart_ready_ms, restart_disconnects,
         restart_open_attempts) = capture_reconnecting_until_ready(
            args.candidate_port, args.boot_seconds)
        records["restart_ready_marker_ms"] = restart_ready_ms
        records["restart_usb_disconnects"] = restart_disconnects
        records["restart_usb_open_attempts"] = restart_open_attempts

        (args.output / "latched-restart.ndjson").write_bytes(restart_raw)
        records["restart_ready"] = parse_ready(restart_raw)
        failures.extend(expect(records["restart_ready"], {
            "version": args.expected_version,
            "app_elf_sha256": app_identity,
            "reset_reason_code": SOFTWARE_RESET_REASON,
        }, "restart_ready"))

        with PassiveSerial(args.candidate_port, 115200, timeout=0.05) as product:
            synchronize_console(product, 15.0)
            records["safety_after_restart"] = query(
                product, b"safety.state", "leshy.safety.v1", "state")
            records["recovery_after_restart"] = query(
                product, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            failures.extend(expect(records["safety_after_restart"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "clear_pending": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "automatic_clear": False,
            }, "safety_after_restart"))
            failures.extend(expect(records["recovery_after_restart"], {
                "status": "safety_latched", "cleanup_complete": True,
                "physical_write_calls": 0, "owned_after": 0,
            }, "recovery_after_restart"))
            records["ui_clear_pending"] = action(product, "right")
            records["frame_clear_pending"] = capture(
                product, frames, "infrared-store-deadline-clear-pending")
            product.write(b"ui.key right\n")
            product.flush()

        (clear_raw, clear_ready_ms, clear_disconnects,
         clear_open_attempts) = capture_reconnecting_until_ready(
            args.candidate_port, args.boot_seconds)
        records["clear_ready_marker_ms"] = clear_ready_ms
        records["clear_usb_disconnects"] = clear_disconnects
        records["clear_usb_open_attempts"] = clear_open_attempts

        (args.output / "clear-restart.ndjson").write_bytes(clear_raw)
        records["clear_ready"] = parse_ready(clear_raw)
        with PassiveSerial(args.candidate_port, 115200, timeout=0.05) as product:
            synchronize_console(product, 15.0)
            records["recovery_final"] = query(
                product, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            records["safety_final"] = query(
                product, b"safety.state", "leshy.safety.v1", "state")
            records["ui_final"] = query(
                product, b"ui.state", "leshy.ui.v1", "state")
            records["frame_final"] = capture(product, frames, "home-final")
        failures.extend(boot_failures(
            records["clear_ready"], records["recovery_final"],
            args.expected_version, app_identity, expected_cid))
        failures.extend(expect(records["safety_final"], {
            "state": "armed", "reason": "none", "armed": True,
            "latched": False, "trip_count": 0,
            "emergency_quiesce_count": 0,
            "runtime_owner": "none", "lease_mask": 0,
            "worker_active": "none", "worker_armed": False,
            "worker_expired": False, "worker_trip_count": 0,
        }, "safety_final"))
        failures.extend(expect(records["ui_final"], {
            "page": "home", "safety_latched": False,
            "runtime_owner": "none", "lease_mask": 0,
        }, "ui_final"))
        if int(records["recovery_final"].get("generation", -1)) != \
                saved_generation:
            failures.append("injected IR store changed product generation")
        if records["recovery_final"].get("physical_write_calls") != 0:
            failures.append("final read-only recovery wrote to storage")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        try:
            with PassiveSerial(
                    args.fixture_port, 115200, timeout=0.05) as fixture:
                synchronize_console(fixture, 10.0)
                records["fixture_cleanup"] = query(
                    fixture, b"fixture.panic", FIXTURE_SCHEMA, "state", 5.0)
                failures.extend(fixture_inactive_failures(
                    records["fixture_cleanup"], "fixture_cleanup"))
        except Exception as cleanup_error:
            failures.append(
                "fixture cleanup: "
                f"{type(cleanup_error).__name__}: {cleanup_error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": bool(args.flash and args.flash_fixture) and
        not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "runner_sha256": runner_sha,
            "flashed": args.flash,
        },
        "fixture": {
            "firmware_sha256": fixture_sha,
            "app_elf_sha256": fixture_app_identity,
            "version": args.expected_fixture_version,
            "fixture_id": args.expected_fixture_id,
            "profile_sha256": sha256_file(retained_profile),
            "flashed": args.flash_fixture,
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
        "scope": {
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "two_bounded_fixture_emissions": True,
            "normal_storage_write_authorized": True,
            "fault_injection_before_storage_hardware": True,
            "fault_injection_physical_write_calls": 0,
            "product_ir_transmit_calls": 0,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "worker": "infrared_capture_store",
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
