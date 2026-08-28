#!/usr/bin/env python3
"""Flash once and verify the passive Airspace Guard lifecycle on board-01."""

from __future__ import annotations

import argparse
import json
import secrets
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.airspace_guard_hil.run.v1"
STATE_SCHEMA = "leshy.airspace_guard.v1"
WIDTH = 240
HEIGHT = 320
WIFI_LIVE_TOP = 67
WIFI_LIVE_BOTTOM = 279
BLE_LIVE_TOP = 88
BLE_LIVE_BOTTOM = 132
ALLOWED_FINDING_MASK = 0x1F
ELEVATED_NOISE_FINDING_MASK = 1 << 3
MACOS_BLE_FIXTURE_SCHEMA = "leshy.hil.macos_ble_name_fixture.v1"


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def robust_cleanup(device: PassiveSerial) -> dict[str, Any]:
    """Return Home despite one bounded native-USB transport interruption."""
    attempts: list[dict[str, Any]] = []
    for _ in range(3):
        result = best_effort_cleanup(device, timeout=12.0)
        attempts.append(result)
        if result.get("complete"):
            result["transport_attempts"] = len(attempts)
            result["transport_history"] = attempts[:-1]
            return result
        synchronize_console(device, 5.0)
    return {
        "attempted": True,
        "complete": False,
        "transport_attempts": len(attempts),
        "transport_history": attempts,
    }


def guard_state(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"airspace.guard.state", STATE_SCHEMA, "state")


def wait_guard_state(device: PassiveSerial,
                     predicate: Callable[[dict[str, Any]], bool],
                     timeout: float, description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = guard_state(device)
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def home_wifi(device: PassiveSerial,
              trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(10):
        if state.get("page") == "home":
            break
        state = action(device, "back")
        trace.append(state)
    if state.get("page") != "home":
        raise RuntimeError(f"Home expected: {state!r}")
    for _ in range(10):
        if int(state.get("selection", -1)) == 0:
            break
        state = action(device, "up")
        trace.append(state)
    require_exact(state, {
        "page": "home", "selection": 0, "selected_id": "wifi",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "home_wifi")
    return state


def open_guard(device: PassiveSerial,
               trace: list[dict[str, Any]]) -> dict[str, Any]:
    home_wifi(device, trace)
    state = action(device, "right")
    trace.append(state)
    require_exact(state, {
        "page": "survey", "wifi_product_view": "menu",
        "runtime_owner": "wifi", "lease_mask": 15,
    }, "wifi_menu")
    for _ in range(8):
        selection = int(state.get("wifi_product_selection", -1))
        if selection == 4:
            break
        state = action(device, "down" if selection < 4 else "up")
        trace.append(state)
    if int(state.get("wifi_product_selection", -1)) != 4:
        raise RuntimeError(f"cannot focus Airspace Guard: {state!r}")
    state = action(device, "right")
    trace.append(state)
    require_exact(state, {
        "wifi_product_view": "airspace_guard", "runtime_owner": "wifi",
        "lease_mask": 15,
    }, "guard_open")
    return guard_state(device)


def pixel_changes(frames: Path, before_name: str, after_name: str,
                  live_top: int, live_bottom: int) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != WIDTH * HEIGHT * 2 or len(after) != len(before):
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    live = 0
    static = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            offset = (y * WIDTH + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if live_top <= y < live_bottom:
                live += 1
            else:
                static += 1
    return {"live_changed_pixels": live, "static_changed_pixels": static}


def running_failures(state: dict[str, Any], stage: str) -> list[str]:
    failures = expect(state, {
        "capture_state": stage,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
        "ble_worker_ready": True,
        "survey_queues_released": True,
    }, stage)
    if stage == "wifi_running":
        failures.extend(expect(state, {
            "wifi_capture_state": "running",
            "wifi_monitor_active": True,
            "wifi_cleanup_complete": False,
            "ble_worker_control": 0,
            "wifi_driver_error": 0,
        }, stage))
    else:
        failures.extend(expect(state, {
            "wifi_capture_state": "complete",
            "wifi_monitor_active": False,
            "wifi_cleanup_complete": True,
            "wifi_driver_error": 0,
            "wifi_disconnects_dropped": 0,
            "wifi_identity_dropped": 0,
            "wifi_noise_dropped": 0,
            "wifi_invalid_frames": 0,
            "wifi_identity_retention_complete": True,
            "wifi_noise_retention_complete": True,
            "ble_worker_control": 2,
        }, stage))
    before = int(state.get("heap_free_before_queue_release", 0))
    after = int(state.get("heap_free_after_queue_release", 0))
    largest_before = int(
        state.get("heap_largest_before_queue_release", 0))
    largest_after = int(
        state.get("heap_largest_after_queue_release", 0))
    if after <= before:
        failures.append(f"{stage}.queue_release_heap: {before} -> {after}")
    if largest_after < largest_before:
        failures.append(
            f"{stage}.queue_release_largest: "
            f"{largest_before} -> {largest_after}")
    return failures


def stopped_failures(state: dict[str, Any], label: str) -> list[str]:
    return expect(state, {
        "capture_state": "idle",
        "wifi_capture_state": "idle",
        "wifi_monitor_active": False,
        "wifi_cleanup_complete": True,
        "ble_worker_control": 0,
        "survey_queues_released": False,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
    }, label)


def result_failures(state: dict[str, Any], label: str) -> list[str]:
    failures = expect(state, {
        "capture_state": "result",
        "load_status": "ready",
        "evidence_incomplete": False,
        "elevated_noise_low_confidence": True,
        "noise_samples_dropped": 0,
        "noise_samples_malformed": 0,
        "malformed_frames": 0,
        "source_read_failures": 0,
        "source_frames_dropped": 0,
        "findings_dropped": 0,
        "inspection_truncated": False,
        "wifi_capture_state": "complete",
        "wifi_driver_error": 0,
        "wifi_cleanup_complete": True,
        "wifi_monitor_active": False,
        "wifi_disconnects_dropped": 0,
        "wifi_identity_dropped": 0,
        "wifi_identity_malformed_envelope": 0,
        "wifi_identity_malformed_addressing": 0,
        "wifi_identity_malformed_elements": 0,
        "wifi_noise_dropped": 0,
        "wifi_invalid_frames": 0,
        "wifi_receive_invalid_frames": 0,
        "wifi_identity_retention_complete": True,
        "wifi_noise_retention_complete": True,
        "ble_worker_control": 0,
        "ble_worker_ready": True,
        "survey_queues_released": True,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
    }, label)
    if state.get("outcome") not in ("clear", "finding"):
        failures.append(f"{label}.outcome: expected clear or finding")
    for key in ("source_frames_observed", "frames_available",
                "frames_inspected"):
        if not isinstance(state.get(key), int) or state[key] < 1:
            failures.append(f"{label}.{key}: expected >= 1")
    if not isinstance(state.get("ble_records"), int) or state["ble_records"] < 1:
        failures.append(f"{label}.ble_records: expected >= 1")
    available = int(state.get("frames_available", -1))
    inspected = int(state.get("frames_inspected", -1))
    observed = int(state.get("source_frames_observed", -1))
    if inspected > available or observed < available:
        failures.append(f"{label}.frame_accounting: invalid")
    retained = int(state.get("wifi_identity_retained", -1))
    projected = int(state.get("wifi_identity_projected", -1))
    if retained < 0 or projected != retained:
        failures.append(
            f"{label}.identity_projection: {projected} != {retained}")
    malformed_total = sum(int(state.get(key, -1)) for key in (
        "wifi_identity_malformed_envelope",
        "wifi_identity_malformed_addressing",
        "wifi_identity_malformed_elements",
        "wifi_receive_invalid_frames",
    ))
    if malformed_total != int(state.get("wifi_invalid_frames", -1)):
        failures.append(
            f"{label}.invalid_frame_accounting: {malformed_total}")
    noise_observed = int(state.get("noise_samples_observed", -1))
    noise_available = int(state.get("noise_samples_available", -1))
    noise_inspected = int(state.get("noise_samples_inspected", -1))
    if noise_observed < noise_available or noise_inspected != noise_available:
        failures.append(f"{label}.noise_accounting: invalid")
    mask = int(state.get("finding_mask", -1))
    count = int(state.get("finding_count", -1))
    if mask < 0 or mask & ~ALLOWED_FINDING_MASK:
        failures.append(f"{label}.finding_mask: unsupported bits {mask:#x}")
    if (count == 0) != (state.get("outcome") == "clear"):
        failures.append(f"{label}.finding_count/outcome: inconsistent")
    if mask & ELEVATED_NOISE_FINDING_MASK:
        if state.get("outcome") != "finding" or noise_inspected < 4:
            failures.append(f"{label}.elevated_noise: invalid evidence")
    return failures


def cancel_to_menu(device: PassiveSerial,
                   trace: list[dict[str, Any]], label: str) -> dict[str, Any]:
    menu = action(device, "left")
    trace.append(menu)
    require_exact(menu, {
        "wifi_product_view": "menu", "wifi_product_selection": 4,
        "runtime_owner": "wifi", "lease_mask": 15,
    }, f"{label}_menu")
    stopped = wait_guard_state(
        device,
        lambda value: value.get("capture_state") == "idle" and
        value.get("ble_worker_control") == 0 and
        value.get("survey_queues_released") is False,
        8.0, f"{label} cleanup did not become idle")
    failures = stopped_failures(stopped, label)
    if failures:
        raise RuntimeError("; ".join(failures))
    return stopped


def finish_to_home(device: PassiveSerial,
                   trace: list[dict[str, Any]], label: str) -> dict[str, Any]:
    stopped = cancel_to_menu(device, trace, label)
    home = action(device, "left")
    trace.append(home)
    require_exact(home, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, f"{label}_home")
    return stopped


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
    parser.add_argument(
        "--external-ble-label",
        help="BLE local name advertised by --external-ble-executable",
    )
    parser.add_argument(
        "--external-ble-executable", type=Path,
        help="bounded macOS CoreBluetooth fixture executable",
    )
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
    if ((args.external_ble_label is None) !=
            (args.external_ble_executable is None)):
        parser.error(
            "--external-ble-label and --external-ble-executable are a pair")
    if (args.external_ble_executable is not None and
            not args.external_ble_executable.is_file()):
        parser.error("external BLE fixture executable is missing")
    if (args.external_ble_label is not None and
            not 1 <= len(args.external_ble_label.encode("utf-8")) <= 29):
        parser.error("external BLE label must occupy 1..29 UTF-8 bytes")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    wifi_running: dict[str, Any] = {}
    wifi_cancelled: dict[str, Any] = {}
    ble_running: dict[str, Any] = {}
    ble_cancelled: dict[str, Any] = {}
    result_first: dict[str, Any] = {}
    result_second: dict[str, Any] = {}
    result_navigation: list[dict[str, Any]] = []
    metrics_after_first: dict[str, Any] = {}
    metrics_after_second: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    pixel_proof: dict[str, Any] = {}
    fixture_process: subprocess.Popen[str] | None = None
    fixture_states: list[dict[str, Any]] = []
    external_ble_fixture: dict[str, Any] = {
        "kind": ("macos_corebluetooth"
                 if args.external_ble_executable is not None else "none"),
        "label": args.external_ble_label,
        "states": fixture_states,
        "host_wifi_control_calls": 0,
        "terminated": args.external_ble_executable is None,
    }
    if args.external_ble_executable is not None:
        external_ble_fixture["executable_sha256"] = sha256_file(
            args.external_ble_executable)

    try:
        if args.external_ble_executable is not None:
            fixture_process = subprocess.Popen(
                [str(args.external_ble_executable.resolve()),
                 str(args.external_ble_label)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if fixture_process.stdout is None:
                raise RuntimeError("external BLE fixture has no stdout")
            readable, _, _ = select.select(
                [fixture_process.stdout], [], [], 10.0)
            if not readable:
                raise RuntimeError("external BLE fixture did not become ready")
            fixture_state = json.loads(fixture_process.stdout.readline())
            fixture_states.append(fixture_state)
            if (fixture_state.get("schema") != MACOS_BLE_FIXTURE_SCHEMA or
                    fixture_state.get("state") != "advertising" or
                    fixture_state.get("label") != args.external_ble_label):
                raise RuntimeError(
                    f"external BLE fixture start failed: {fixture_state}")
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                cleanup_before = robust_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                wifi_running = open_guard(device, trace)
                failures.extend(running_failures(
                    wifi_running, "wifi_running"))
                screens["wifi_first"] = capture(
                    device, frames, "guard-wifi-first")
                time.sleep(0.65)
                screens["wifi_second"] = capture(
                    device, frames, "guard-wifi-second")
                pixel_proof["wifi"] = pixel_changes(
                    frames, "guard-wifi-first", "guard-wifi-second",
                    WIFI_LIVE_TOP, WIFI_LIVE_BOTTOM)
                if (pixel_proof["wifi"]["live_changed_pixels"] <= 0 or
                        pixel_proof["wifi"]["static_changed_pixels"] != 0):
                    raise RuntimeError(
                        f"Wi-Fi live redraw escaped bounded region: "
                        f"{pixel_proof['wifi']}")
                wifi_cancelled = cancel_to_menu(
                    device, trace, "wifi_cancelled")
                home = action(device, "left")
                trace.append(home)

                open_guard(device, trace)
                ble_running = wait_guard_state(
                    device,
                    lambda value: value.get("capture_state") == "failed" or (
                        value.get("capture_state") == "ble_running" and
                        value.get("ble_worker_control") == 2),
                    18.0, "BLE stage did not start")
                if ble_running.get("capture_state") != "ble_running":
                    raise RuntimeError(
                        f"Wi-Fi evidence did not admit BLE stage: {ble_running!r}")
                failures.extend(running_failures(
                    ble_running, "ble_running"))
                screens["ble_first"] = capture(
                    device, frames, "guard-ble-first")
                time.sleep(0.65)
                screens["ble_second"] = capture(
                    device, frames, "guard-ble-second")
                pixel_proof["ble"] = pixel_changes(
                    frames, "guard-ble-first", "guard-ble-second",
                    BLE_LIVE_TOP, BLE_LIVE_BOTTOM)
                if (pixel_proof["ble"]["live_changed_pixels"] <= 0 or
                        pixel_proof["ble"]["static_changed_pixels"] != 0):
                    raise RuntimeError(
                        f"BLE live redraw escaped bounded region: "
                        f"{pixel_proof['ble']}")
                ble_cancelled = cancel_to_menu(
                    device, trace, "ble_cancelled")
                home = action(device, "left")
                trace.append(home)

                open_guard(device, trace)
                result_first = wait_guard_state(
                    device,
                    lambda value: value.get("capture_state") in
                    ("result", "failed"),
                    35.0, "first complete Guard lifecycle did not finish")
                failures.extend(result_failures(result_first, "result_first"))
                screens["result"] = capture(device, frames, "guard-result")
                if result_first.get("view") == "finding":
                    finding = action(device, "right")
                    trace.append(finding)
                    evidence_list = guard_state(device)
                    result_navigation.append(evidence_list)
                    require_exact(evidence_list, {"view": "evidence_list"},
                                  "evidence_list")
                    screens["evidence_list"] = capture(
                        device, frames, "guard-evidence-list")
                    detail = action(device, "right")
                    trace.append(detail)
                    evidence_detail = guard_state(device)
                    result_navigation.append(evidence_detail)
                    require_exact(evidence_detail, {"view": "evidence_detail"},
                                  "evidence_detail")
                    screens["evidence_detail"] = capture(
                        device, frames, "guard-evidence-detail")
                    trace.append(action(device, "left"))
                    trace.append(action(device, "left"))
                finish_to_home(device, trace, "result_first")
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                open_guard(device, trace)
                result_second = wait_guard_state(
                    device,
                    lambda value: value.get("capture_state") in
                    ("result", "failed"),
                    35.0, "second complete Guard lifecycle did not finish")
                failures.extend(result_failures(result_second, "result_second"))
                finish_to_home(device, trace, "result_second")
                metrics_after_second = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                input_state = query(
                    device, b"input.state",
                    "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
                for key in ("generation", "observations"):
                    if recovery_after.get(key) != recovery_before.get(key):
                        failures.append(f"persistent {key} changed")
                if recovery_after.get("physical_write_calls") != 0:
                    failures.append("physical SD write observed")
                for key in ("heap_total", "heap_free"):
                    if metrics_after_second.get(key) != metrics_after_first.get(key):
                        failures.append(
                            f"{key} changed between complete post-warm lifecycles")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = robust_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")
    finally:
        if fixture_process is not None:
            fixture_process.terminate()
            try:
                fixture_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                fixture_process.kill()
                fixture_process.wait(timeout=5.0)
            external_ble_fixture["terminated"] = True
            external_ble_fixture["returncode"] = fixture_process.returncode
            if fixture_process.stderr is not None:
                fixture_stderr = fixture_process.stderr.read().strip()
                if fixture_stderr:
                    external_ble_fixture["stderr"] = fixture_stderr

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": bool(args.flash or args.reuse_exact_flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": True,
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "wifi_running": wifi_running,
        "wifi_cancelled": wifi_cancelled,
        "ble_running": ble_running,
        "ble_cancelled": ble_cancelled,
        "result_first": result_first,
        "result_second": result_second,
        "result_navigation": result_navigation,
        "metrics_after_first": metrics_after_first,
        "metrics_after_second": metrics_after_second,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "pixel_proof": pixel_proof,
        "external_ble_fixture": external_ble_fixture,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_receive_only": True,
            "deterministic_ble_fixture": (
                external_ble_fixture.get("kind") == "macos_corebluetooth" and
                bool(fixture_states) and
                external_ble_fixture.get("terminated") is True
            ),
            "host_wifi_control_calls": 0,
            "application_wifi_connect_calls": 0,
            "application_raw_tx_calls": 0,
            "wifi_cancel_cleanup_proved": bool(wifi_cancelled),
            "ble_cancel_cleanup_proved": bool(ble_cancelled),
            "two_complete_guard_lifecycles": bool(result_first and result_second),
            "static_pixels_unchanged_during_live_refresh": (
                pixel_proof.get("wifi", {}).get("static_changed_pixels") == 0 and
                pixel_proof.get("ble", {}).get("static_changed_pixels") == 0
            ),
            "zero_heap_drift_after_warmup": (
                metrics_after_second.get("heap_total") ==
                    metrics_after_first.get("heap_total") and
                metrics_after_second.get("heap_free") ==
                    metrics_after_first.get("heap_free")
            ),
            "storage_write_authorized": False,
            "elevated_noise_is_low_confidence_indicator": True,
            "absence_of_noise_finding_is_not_absence_of_interference": True,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
        "pixel_proof": pixel_proof,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
