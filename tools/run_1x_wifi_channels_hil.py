#!/usr/bin/env python3
"""Flash once and verify passive Wi-Fi channel airtime on board-01."""

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
    wait_ui_state,
)


RUN_SCHEMA = "leshy.wifi_channels_hil.run.v2"
WIDTH = 240
HEIGHT = 320
AVERAGE_GRAY_RGB565 = 0x6B6D


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def robust_cleanup(device: PassiveSerial) -> dict[str, Any]:
    """Tolerate a transient native-USB reply loss, never a dirty final state."""
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


def is_dynamic_pixel(x: int, y: int) -> bool:
    # Only the graph body, selected channel label and recommendation may change.
    return (58 <= y < 252 or 252 <= y < 275 or
            (116 <= x < WIDTH and 32 <= y < 58))


def changed_pixels(frames: Path, before_name: str,
                   after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != WIDTH * HEIGHT * 2 or len(after) != len(before):
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    dynamic = 0
    static = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            offset = (y * WIDTH + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if is_dynamic_pixel(x, y):
                dynamic += 1
            else:
                static += 1
    return {
        "dynamic_changed_pixels": dynamic,
        "static_changed_pixels": static,
    }


def count_graph_tone(frames: Path, name: str, tone: int) -> int:
    frame = (frames / f"{name}.rgb565").read_bytes()
    if len(frame) != WIDTH * HEIGHT * 2:
        raise RuntimeError("TFT tone count requires a complete 240x320 frame")
    target = tone.to_bytes(2, "big")
    count = 0
    for y in range(58, 252):
        row = y * WIDTH * 2
        for x in range(WIDTH):
            offset = row + x * 2
            if frame[offset:offset + 2] == target:
                count += 1
    return count


def open_channels(device: PassiveSerial, frames: Path | None = None,
                  screens: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    home_wifi(device)
    menu = action(device, "right")
    trace.append(menu)
    require_exact(menu, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "wifi_product_view": "menu", "wifi_product_selection": 0,
    }, "wifi_menu")
    if frames is not None and screens is not None and "wifi_menu" not in screens:
        screens["wifi_menu"] = capture(device, frames, "wifi-menu")
    for selected_index in (1, 2):
        selected = action(device, "down")
        trace.append(selected)
        require_exact(selected, {
            "wifi_product_view": "menu",
            "wifi_product_selection": selected_index,
        }, f"wifi_menu_selection_{selected_index}")
    started = action(device, "right")
    trace.append(started)
    require_exact(started, {
        "wifi_product_view": "channels", "runtime_owner": "wifi",
        "lease_mask": 15, "wifi_channel_monitor_active": True,
        "wifi_device_nvs_disabled": True,
        "wifi_device_volatile_storage_only": True,
        "wifi_channel_completed_dwells": 0,
        "wifi_channel_completed_sweeps": 0,
        "wifi_channel_measured_mask": 0,
    }, "wifi_channels_started")
    return trace


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
    live_first: dict[str, Any] = {}
    live_second: dict[str, Any] = {}
    monitor_after_first: dict[str, Any] = {}
    monitor_after_second: dict[str, Any] = {}
    metrics_after_first: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    pixel_changes: dict[str, int] = {}
    average_gray_pixels: dict[str, int] = {}

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

                trace.extend(open_channels(device, frames, screens))
                live_first = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "channels" and
                        state.get("wifi_channel_monitor_active") is True and
                        int(state.get("wifi_channel_measured_mask", 0)) == 8191 and
                        int(state.get("wifi_channel_completed_sweeps", 0)) >= 2 and
                        int(state.get("wifi_channel_frames_reported", 0)) > 0 and
                        int(state.get("wifi_channel_best_primary", 0)) in range(1, 14)
                    ), 60.0, "complete passive Wi-Fi channel sweep did not appear")
                trace.append(live_first)
                require_exact(live_first, {
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "wifi_channel_monitor_active": True,
                    "wifi_device_nvs_disabled": True,
                    "wifi_device_volatile_storage_only": True,
                    "wifi_channel_measured_mask": 8191,
                }, "wifi_channels_live")
                screens["wifi_channels_first"] = capture(
                    device, frames, "wifi-channels-first")
                average_gray_pixels["first"] = count_graph_tone(
                    frames, "wifi-channels-first", AVERAGE_GRAY_RGB565)
                if average_gray_pixels["first"] <= 0:
                    raise RuntimeError(
                        "session-average gray bars are absent from first TFT frame")
                first_revision = int(live_first["wifi_channel_revision"])
                first_sweeps = int(live_first["wifi_channel_completed_sweeps"])
                first_frames = int(live_first["wifi_channel_frames_reported"])
                live_second = wait_ui_state(
                    device,
                    lambda state: (
                        int(state.get("wifi_channel_revision", 0)) > first_revision and
                        int(state.get("wifi_channel_completed_sweeps", 0)) > first_sweeps and
                        int(state.get("wifi_channel_frames_reported", 0)) > first_frames
                    ), 60.0, "Wi-Fi channel measurements did not advance")
                trace.append(live_second)
                screens["wifi_channels_second"] = capture(
                    device, frames, "wifi-channels-second")
                average_gray_pixels["second"] = count_graph_tone(
                    frames, "wifi-channels-second", AVERAGE_GRAY_RGB565)
                if average_gray_pixels["second"] <= 0:
                    raise RuntimeError(
                        "session-average gray bars are absent from second TFT frame")
                pixel_changes = changed_pixels(
                    frames, "wifi-channels-first", "wifi-channels-second")
                if pixel_changes["static_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"channel redraw escaped live data regions: {pixel_changes}")

                monitor_after_first = action(device, "left")
                trace.append(monitor_after_first)
                require_exact(monitor_after_first, {
                    "wifi_product_view": "menu",
                    "wifi_product_selection": 2,
                    "wifi_channel_monitor_active": False,
                    "wifi_channel_monitor_cleanup_complete": True,
                }, "wifi_channels_first_cleanup")
                screens["wifi_menu_after"] = capture(
                    device, frames, "wifi-menu-after")
                home = action(device, "left")
                trace.append(home)
                require_exact(home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "wifi_home")
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                trace.extend(open_channels(device))
                warm_live = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "channels" and
                        int(state.get("wifi_channel_measured_mask", 0)) == 8191 and
                        int(state.get("wifi_channel_completed_sweeps", 0)) >= 1 and
                        int(state.get("wifi_channel_frames_reported", 0)) > 0
                    ), 60.0, "second Wi-Fi channel lifecycle did not complete")
                trace.append(warm_live)
                monitor_after_second = action(device, "left")
                trace.append(monitor_after_second)
                require_exact(monitor_after_second, {
                    "wifi_product_view": "menu",
                    "wifi_channel_monitor_active": False,
                    "wifi_channel_monitor_cleanup_complete": True,
                }, "wifi_channels_second_cleanup")
                warm_home = action(device, "left")
                trace.append(warm_home)
                require_exact(warm_home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "wifi_warm_home")

                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                metrics_after = query(
                    device, b"metrics", "leshy.boot.v1", "ready")
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
                if (metrics_after.get("heap_total") !=
                        metrics_after_first.get("heap_total") or
                        metrics_after.get("heap_free") !=
                        metrics_after_first.get("heap_free")):
                    failures.append(
                        "heap changed between complete post-warm channel lifecycles")
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
        "live_first": live_first,
        "live_second": live_second,
        "monitor_after_first": monitor_after_first,
        "monitor_after_second": monitor_after_second,
        "metrics_after_first": metrics_after_first,
        "metrics_after": metrics_after,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "pixel_changes": pixel_changes,
        "average_gray_pixels": average_gray_pixels,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_receive_only": True,
            "channels_measured": list(range(1, 14)),
            "lower_bound_airtime_estimate": True,
            "recommended_primary_channels": list(range(1, 14)),
            "average_load_rendered_gray": True,
            "recommendation_uses_session_average": True,
            "recommendation_primary_criterion": "visible_session_average",
            "recommendation_tie_break": "adjacent_overlap_pressure",
            "recommended_axis_label_highlighted": True,
            "current_bar_tone_channel_neutral": True,
            "minimum_average_dwells_per_channel": 2,
            "static_pixels_unchanged_during_live_refresh": True,
            "two_complete_wifi_lifecycles": True,
            "zero_heap_drift_after_warmup": (
                metrics_after.get("heap_free") ==
                metrics_after_first.get("heap_free")
            ),
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
        "pixel_changes": pixel_changes,
        "average_gray_pixels": average_gray_pixels,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
