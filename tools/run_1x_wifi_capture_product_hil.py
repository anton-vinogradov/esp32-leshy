#!/usr/bin/env python3
"""Flash once and verify the user-facing passive Wi-Fi packet recorder."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

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
from run_1x_wifi_frame_capture_hil import parse_pcap, read_pcap


RUN_SCHEMA = "leshy.wifi_capture_product_hil.run.v1"
CAPTURE_SCHEMA = "leshy.capture.wifi_frame.v1"
WIDTH = 240
HEIGHT = 320


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def robust_cleanup(device: PassiveSerial) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for _ in range(3):
        result = best_effort_cleanup(device, timeout=8.0)
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


def wait_capture(device: PassiveSerial, predicate: Any, timeout: float,
                 description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"capture.state", CAPTURE_SCHEMA, "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def home_wifi(device: PassiveSerial) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    if state.get("page") != "home":
        raise RuntimeError(f"Home expected: {state!r}")
    while int(state.get("selection", -1)) > 0:
        state = action(device, "up")
    require_exact(state, {
        "page": "home", "selection": 0, "selected_id": "wifi",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "home_wifi")
    return state


def open_product_capture(device: PassiveSerial) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    home_wifi(device)
    menu = action(device, "right")
    trace.append(menu)
    require_exact(menu, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "wifi_product_view": "menu", "wifi_product_selection": 0,
    }, "wifi_menu")
    for selected_index in (1, 2, 3):
        selected = action(device, "down")
        trace.append(selected)
        require_exact(selected, {
            "wifi_product_view": "menu",
            "wifi_product_selection": selected_index,
        }, f"wifi_menu_selection_{selected_index}")
    opened = action(device, "right")
    trace.append(opened)
    require_exact(opened, {
        "wifi_product_view": "capture", "runtime_owner": "wifi",
        "lease_mask": 15, "runtime_event": "wifi_capture_setup",
    }, "wifi_capture_opened")
    setup = query(device, b"capture.state", CAPTURE_SCHEMA, "state")
    require_exact(setup, {
        "state": "idle", "passive_only": True, "rx_only": True,
        "volatile_ram": True, "storage_written": False,
        "persist_state": "result", "pcap_available": False,
        "frames_accepted": 0, "payload_bytes": 0, "lease_mask": 15,
    }, "wifi_capture_setup")
    return trace


def is_live_pixel(x: int, y: int) -> bool:
    del x
    return 46 <= y < 102 or 130 <= y < 158


def changed_pixels(frames: Path, before_name: str,
                   after_name: str) -> dict[str, int]:
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
            if is_live_pixel(x, y):
                live += 1
            else:
                static += 1
    return {"live_changed_pixels": live, "static_changed_pixels": static}


def run_lifecycle(device: PassiveSerial, trace: list[dict[str, Any]],
                  capture_screens: bool, frames: Path,
                  screens: dict[str, Any]) -> dict[str, Any]:
    trace.extend(open_product_capture(device))
    if capture_screens:
        screens["setup"] = capture(device, frames, "wifi-capture-setup")

    started = action(device, "right")
    trace.append(started)
    require_exact(started, {
        "wifi_product_view": "capture", "runtime_owner": "wifi",
        "lease_mask": 15, "runtime_event": "capture_running",
    }, "capture_started")
    running = wait_capture(
        device,
        lambda value: value.get("state") == "running" and
        int(value.get("frames_accepted", 0)) >= 1,
        5.0, "passive Wi-Fi capture received no frame")
    require_exact(running, {
        "state": "running", "passive_only": True, "rx_only": True,
        "application_connect_calls": 0, "application_raw_tx_calls": 0,
        "physical_no_tx_verified": False, "storage_written": False,
        "volatile_ram": True, "channel_plan": 0, "duration_ms": 10000,
        "channel_dwell_ms": 120, "snap_length": 256,
        "maximum_frames": 16, "driver_error": 0,
        "pcap_available": False, "lease_mask": 15,
    }, "capture_running")

    pixel_changes: dict[str, int] = {}
    if capture_screens:
        time.sleep(0.65)
        first = wait_capture(
            device, lambda value: value.get("state") == "running", 2.0,
            "capture left running state before first TFT sample")
        screens["running_first"] = capture(
            device, frames, "wifi-capture-running-first")
        time.sleep(0.65)
        second = wait_capture(
            device,
            lambda value: value.get("state") == "running" and (
                value.get("current_channel") != first.get("current_channel") or
                value.get("frames_dropped_capacity") !=
                first.get("frames_dropped_capacity")),
            2.0, "live Wi-Fi metrics did not advance")
        time.sleep(0.55)
        screens["running_second"] = capture(
            device, frames, "wifi-capture-running-second")
        pixel_changes = changed_pixels(
            frames, "wifi-capture-running-first",
            "wifi-capture-running-second")
        if pixel_changes["live_changed_pixels"] <= 0:
            raise RuntimeError(f"live TFT metrics did not change: {pixel_changes}")
        if pixel_changes["static_changed_pixels"] != 0:
            raise RuntimeError(
                f"live redraw escaped metric rows: {pixel_changes}")
        running = second

    stopped = action(device, "right")
    trace.append(stopped)
    complete = wait_capture(
        device, lambda value: value.get("state") == "complete", 5.0,
        "manual Stop did not complete capture")
    require_exact(complete, {
        "state": "complete", "driver_error": 0, "pcap_available": True,
        "cleanup_complete": True, "storage_written": False,
        "persist_state": "result", "lease_mask": 15,
    }, "capture_complete")
    reported = int(complete.get("frames_reported", -1))
    accepted = int(complete.get("frames_accepted", -1))
    dropped_capacity = int(complete.get("frames_dropped_capacity", -1))
    dropped_invalid = int(complete.get("frames_dropped_invalid", -1))
    payload_bytes = int(complete.get("payload_bytes", -1))
    if not 1 <= accepted <= 16:
        raise RuntimeError(f"accepted frame bound invalid: {accepted}")
    if reported != accepted + dropped_capacity + dropped_invalid:
        raise RuntimeError("reported frame accounting is inconsistent")
    if not accepted <= payload_bytes <= accepted * 256:
        raise RuntimeError("captured payload byte bound is invalid")
    if capture_screens:
        screens["result"] = capture(device, frames, "wifi-capture-result")

    pcap_begin, pcap_payload, pcap_end = read_pcap(device)
    pcap_summary, pcap_failures = parse_pcap(pcap_payload)
    if pcap_failures:
        raise RuntimeError("; ".join(pcap_failures))
    require_exact(pcap_begin, {
        "bytes": len(pcap_payload), "frames": accepted,
        "linktype": 127, "timebase": "monotonic_us", "streaming": True,
        "storage_written": False,
    }, "pcap_begin")
    require_exact(pcap_end, {
        "status": "valid", "bytes": len(pcap_payload), "frames": accepted,
        "storage_written": False,
    }, "pcap_end")
    if pcap_summary.get("records") != accepted:
        raise RuntimeError("PCAP record count differs from accepted frames")
    if pcap_summary.get("captured_frame_bytes") != payload_bytes:
        raise RuntimeError("PCAP byte count differs from capture accounting")

    return {
        "running": running,
        "complete": complete,
        "pcap": {"begin": pcap_begin, "end": pcap_end,
                 "summary": pcap_summary},
        "pixel_changes": pixel_changes,
    }


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
    first: dict[str, Any] = {}
    second: dict[str, Any] = {}
    confirm: dict[str, Any] = {}
    cancelled: dict[str, Any] = {}
    scrubbed: dict[str, Any] = {}
    metrics_after_first: dict[str, Any] = {}
    metrics_after_second: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
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

                first = run_lifecycle(
                    device, trace, True, frames, screens)
                confirm_ui = action(device, "right")
                trace.append(confirm_ui)
                confirm = query(device, b"capture.state", CAPTURE_SCHEMA, "state")
                require_exact(confirm, {
                    "state": "complete", "persist_state": "confirm",
                    "persist_status": "awaiting_confirmation",
                    "storage_written": False, "lease_mask": 15,
                }, "privacy_confirm")
                screens["confirm"] = capture(
                    device, frames, "wifi-capture-confirm")
                cancelled_ui = action(device, "left")
                trace.append(cancelled_ui)
                cancelled = query(
                    device, b"capture.state", CAPTURE_SCHEMA, "state")
                require_exact(cancelled, {
                    "state": "complete", "persist_state": "result",
                    "persist_status": "volatile", "storage_written": False,
                    "lease_mask": 15,
                }, "privacy_cancelled")
                to_menu = action(device, "left")
                trace.append(to_menu)
                require_exact(to_menu, {
                    "wifi_product_view": "menu", "wifi_product_selection": 3,
                    "runtime_owner": "wifi", "lease_mask": 15,
                }, "wifi_menu_after_first")
                scrubbed = query(
                    device, b"capture.state", CAPTURE_SCHEMA, "state")
                require_exact(scrubbed, {
                    "state": "idle", "frames_reported": 0,
                    "frames_accepted": 0, "payload_bytes": 0,
                    "pcap_available": False, "lease_mask": 15,
                }, "capture_scrubbed")
                screens["wifi_menu_after"] = capture(
                    device, frames, "wifi-menu-after-capture")
                home = action(device, "left")
                trace.append(home)
                require_exact(home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "home_after_first")
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                second = run_lifecycle(
                    device, trace, False, frames, screens)
                trace.append(action(device, "left"))
                second_menu = query(device, b"ui.state", "leshy.ui.v1", "state")
                require_exact(second_menu, {
                    "wifi_product_view": "menu", "runtime_owner": "wifi",
                    "lease_mask": 15,
                }, "wifi_menu_after_second")
                trace.append(action(device, "left"))
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                require_exact(final, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                    "safety_latched": False,
                }, "final_home")
                screens["home"] = capture(device, frames, "home-final")

                metrics_after_second = query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
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
                if (metrics_after_second.get("heap_total") !=
                        metrics_after_first.get("heap_total") or
                        metrics_after_second.get("heap_free") !=
                        metrics_after_first.get("heap_free")):
                    failures.append("heap changed between post-warm lifecycles")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = robust_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

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
        "first": first,
        "privacy_confirm": confirm,
        "privacy_cancelled": cancelled,
        "scrubbed": scrubbed,
        "metrics_after_first": metrics_after_first,
        "second": second,
        "metrics_after_second": metrics_after_second,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "final": final,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_receive_only": True,
            "bounded_ram_capture": True,
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "privacy_confirmation_tested_without_storage_write": True,
            "static_pixels_unchanged_during_live_refresh": True,
            "two_complete_wifi_lifecycles": True,
            "storage_write_authorized": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
        "pixel_changes": first.get("pixel_changes", {}),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
