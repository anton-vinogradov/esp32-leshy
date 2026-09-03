#!/usr/bin/env python3
"""Flash once and verify passive Wi-Fi client discovery on board-01."""

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
from temporary_device_lock_hil import TemporaryDeviceLockHil


RUN_SCHEMA = "leshy.wifi_devices_hil.run.v4"
DETAIL_SCHEMA = "leshy.wifi.device_detail.v1"
CONTENT_X0 = 12
CONTENT_X1 = 228
CONTENT_Y0 = 32
CONTENT_Y1 = 293


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


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


def query_device_detail(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"wifi.device.detail", DETAIL_SCHEMA, "state")


def wait_device_detail(device: PassiveSerial, predicate: Any,
                       timeout: float, description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query_device_detail(device)
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def changed_pixels(frames: Path, before_name: str,
                   after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != 240 * 320 * 2 or len(after) != len(before):
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    content = 0
    chrome = 0
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if CONTENT_X0 <= x < CONTENT_X1 and CONTENT_Y0 <= y < CONTENT_Y1:
                content += 1
            else:
                chrome += 1
    return {"content_changed_pixels": content, "chrome_changed_pixels": chrome}


def changed_live_detail_pixels(frames: Path, before_name: str,
                               after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != 240 * 320 * 2 or len(after) != len(before):
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    identity = 0
    live = 0
    chrome = 0
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if CONTENT_X0 <= x < CONTENT_X1 and 101 <= y < CONTENT_Y1:
                live += 1
            elif CONTENT_X0 <= x < CONTENT_X1 and CONTENT_Y0 <= y < 101:
                identity += 1
            else:
                chrome += 1
    return {
        "identity_changed_pixels": identity,
        "live_changed_pixels": live,
        "chrome_changed_pixels": chrome,
    }


def open_devices(device: PassiveSerial, frames: Path | None = None,
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
    selected = action(device, "down")
    trace.append(selected)
    require_exact(selected, {
        "wifi_product_view": "menu", "wifi_product_selection": 1,
    }, "wifi_devices_selected")
    started = action(device, "right")
    trace.append(started)
    require_exact(started, {
        "wifi_product_view": "devices", "runtime_owner": "wifi",
        "lease_mask": 15, "wifi_device_monitor_active": True,
        "wifi_device_nvs_disabled": True,
        "wifi_device_volatile_storage_only": True,
    }, "wifi_devices_started")
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
    parser.add_argument("--endurance-seconds", type=int, default=0)
    parser.add_argument("--endurance-minimum-hops", type=int, default=0)
    parser.add_argument("--endurance-max-hop-gap-seconds", type=float,
                        default=10.0)
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
    if args.endurance_seconds < 0 or args.endurance_minimum_hops < 0:
        parser.error("endurance duration and hop floor must be non-negative")
    if args.endurance_max_hop_gap_seconds <= 0:
        parser.error("--endurance-max-hop-gap-seconds must be positive")

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
    detail_first: dict[str, Any] = {}
    detail_second: dict[str, Any] = {}
    detail_after_first_capture: dict[str, Any] = {}
    detail_after_second_capture: dict[str, Any] = {}
    detail_oracle_first: dict[str, Any] = {}
    detail_oracle_second: dict[str, Any] = {}
    monitor_after_first: dict[str, Any] = {}
    monitor_after_second: dict[str, Any] = {}
    metrics_after_first: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    device_lock_fixture: dict[str, Any] = {}
    temporary_lock: TemporaryDeviceLockHil | None = None
    list_pixel_changes: dict[str, int] = {}
    detail_pixel_changes: dict[str, int] = {}
    detail_visual_input_changed = False
    detail_attempts: list[dict[str, Any]] = []
    endurance: dict[str, Any] = {
        "requested_seconds": args.endurance_seconds,
        "minimum_hops": args.endurance_minimum_hops,
        "max_hop_gap_seconds": args.endurance_max_hop_gap_seconds,
        "completed": args.endurance_seconds == 0,
        "checkpoints": [],
    }

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
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                # Protected product pages must not depend on whichever Device
                # Lock state happens to be present on the user's board.  Use
                # the isolated HIL namespace, configure an ephemeral key only
                # there, and restore the untouched product namespace below.
                temporary_lock = TemporaryDeviceLockHil(device, app_identity)
                temporary_lock.start()
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                trace.extend(open_devices(device, frames, screens))
                live_first = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "devices" and
                        state.get("wifi_device_monitor_active") is True and
                        state.get("wifi_devices_strongest_first") is True and
                        int(state.get("wifi_devices_unique", 0)) >= 1 and
                        int(state.get("wifi_device_clients_accepted", 0)) >= 1 and
                        int(state.get("wifi_device_channel_hops", 0)) >= 13
                    ), 90.0, "passive Wi-Fi clients did not appear")
                trace.append(live_first)
                require_exact(live_first, {
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "wifi_device_monitor_active": True,
                    "wifi_device_nvs_disabled": True,
                    "wifi_device_volatile_storage_only": True,
                }, "wifi_devices_live")
                screens["wifi_devices_first"] = capture(
                    device, frames, "wifi-devices-first")
                first_revision = int(live_first["wifi_device_catalog_revision"])
                first_accepted = int(live_first["wifi_device_clients_accepted"])
                live_second = wait_ui_state(
                    device,
                    lambda state: (
                        int(state.get("wifi_device_catalog_revision", 0)) >
                            first_revision and
                        int(state.get("wifi_device_clients_accepted", 0)) >
                            first_accepted
                    ), 60.0, "Wi-Fi client catalog did not advance")
                trace.append(live_second)
                screens["wifi_devices_second"] = capture(
                    device, frames, "wifi-devices-second")
                list_pixel_changes = changed_pixels(
                    frames, "wifi-devices-first", "wifi-devices-second")
                if list_pixel_changes["chrome_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"live device redraw escaped data rows: {list_pixel_changes}")

                if args.endurance_seconds:
                    endurance_start = time.monotonic()
                    endurance_deadline = (
                        endurance_start + args.endurance_seconds)
                    endurance_start_hops = int(live_second.get(
                        "wifi_device_channel_hops", 0))
                    endurance_last_hops = endurance_start_hops
                    endurance_last_progress = endurance_start
                    endurance_next_checkpoint = endurance_start
                    endurance_heap_total: int | None = None
                    endurance_final_state = live_second
                    while time.monotonic() < endurance_deadline:
                        endurance_final_state = query(
                            device, b"ui.state", "leshy.ui.v1", "state")
                        require_exact(endurance_final_state, {
                            "wifi_product_view": "devices",
                            "runtime_owner": "wifi", "lease_mask": 15,
                            "wifi_device_monitor_active": True,
                            "wifi_device_channel_locked": False,
                            "wifi_device_clients_dropped": 0,
                            "wifi_device_nvs_disabled": True,
                            "wifi_device_volatile_storage_only": True,
                            "safety_latched": False,
                            "safety_reason": "none",
                        }, "wifi_devices_endurance")
                        now = time.monotonic()
                        hops = int(endurance_final_state.get(
                            "wifi_device_channel_hops", 0))
                        if hops > endurance_last_hops:
                            endurance_last_hops = hops
                            endurance_last_progress = now
                        elif now - endurance_last_progress > \
                                args.endurance_max_hop_gap_seconds:
                            raise RuntimeError(
                                "Wi-Fi passive monitor stalled for "
                                f"{now - endurance_last_progress:.1f}s at "
                                f"hop {hops}")
                        if now >= endurance_next_checkpoint:
                            safety = query(
                                device, b"safety.state",
                                "leshy.safety.v1", "state")
                            require_exact(safety, {
                                "state": "armed", "reason": "none",
                                "armed": True, "latched": False,
                                "clear_pending": False,
                                "watchdog_trace_valid": False,
                                "watchdog_triggered_cpu_mask": 0,
                                "watchdog_trip_stage": "unknown",
                                "watchdog_trip_page": 0,
                                "watchdog_trip_wifi_view": "none",
                                "watchdog_first_trip_preserved": True,
                            }, "wifi_devices_endurance_safety")
                            metrics = query(
                                device, b"metrics", "leshy.boot.v1", "ready")
                            if metrics.get("version") != args.expected_version:
                                raise RuntimeError(
                                    "candidate version changed during endurance")
                            if metrics.get("app_elf_sha256") != app_identity:
                                raise RuntimeError(
                                    "candidate app identity changed during endurance")
                            heap_total = int(metrics.get("heap_total", -1))
                            if endurance_heap_total is None:
                                endurance_heap_total = heap_total
                            elif heap_total != endurance_heap_total:
                                raise RuntimeError(
                                    "heap total changed during endurance")
                            checkpoint = {
                                "elapsed_seconds": round(now - endurance_start, 3),
                                "channel_hops": hops,
                                "channel": int(endurance_final_state.get(
                                    "wifi_device_current_channel", 0)),
                                "catalog_revision": int(endurance_final_state.get(
                                    "wifi_device_catalog_revision", 0)),
                                "devices": int(endurance_final_state.get(
                                    "wifi_devices_unique", 0)),
                                "frames_reported": int(endurance_final_state.get(
                                    "wifi_device_frames_reported", 0)),
                                "clients_accepted": int(endurance_final_state.get(
                                    "wifi_device_clients_accepted", 0)),
                                "clients_dropped": int(endurance_final_state.get(
                                    "wifi_device_clients_dropped", -1)),
                                "heap_total": heap_total,
                                "heap_free": int(metrics.get("heap_free", -1)),
                                "heap_min_free": int(metrics.get(
                                    "heap_min_free", -1)),
                                "safety_latched": endurance_final_state.get(
                                    "safety_latched"),
                                "watchdog_trace_valid": safety.get(
                                    "watchdog_trace_valid"),
                            }
                            endurance["checkpoints"].append(checkpoint)
                            print(json.dumps({
                                "status": "in_progress",
                                "endurance": checkpoint,
                            }, sort_keys=True), flush=True)
                            endurance_next_checkpoint = now + 15.0
                        time.sleep(0.25)
                    endurance_end = time.monotonic()
                    endurance_hops = endurance_last_hops - endurance_start_hops
                    endurance.update({
                        "completed": True,
                        "elapsed_seconds": round(
                            endurance_end - endurance_start, 3),
                        "start_hops": endurance_start_hops,
                        "end_hops": endurance_last_hops,
                        "hops_completed": endurance_hops,
                        "final_state": endurance_final_state,
                    })
                    if endurance_hops < args.endurance_minimum_hops:
                        raise RuntimeError(
                            "Wi-Fi device endurance hop floor missed: "
                            f"{endurance_hops} < {args.endurance_minimum_hops}")

                    # A bounded catalog intentionally retains identities after
                    # they leave the air.  After a long hold, restart the
                    # passive monitor before testing Detail so the candidate
                    # matrix contains recently observed clients rather than a
                    # stale strongest-ever row.
                    endurance_cleanup = action(device, "left")
                    trace.append(endurance_cleanup)
                    require_exact(endurance_cleanup, {
                        "wifi_product_view": "menu",
                        "wifi_product_selection": 1,
                        "wifi_device_monitor_active": False,
                        "wifi_device_monitor_cleanup_complete": True,
                    }, "wifi_devices_endurance_cleanup")
                    endurance_restart = action(device, "right")
                    trace.append(endurance_restart)
                    require_exact(endurance_restart, {
                        "wifi_product_view": "devices",
                        "wifi_device_monitor_active": True,
                        "wifi_device_channel_locked": False,
                        "wifi_device_clients_dropped": 0,
                    }, "wifi_devices_endurance_restart")
                    detail_list_state = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("wifi_product_view") == "devices" and
                            state.get("wifi_device_monitor_active") is True and
                            int(state.get("wifi_device_visible_size", 0)) >= 1 and
                            int(state.get("wifi_device_clients_accepted", 0)) >= 1
                        ), 90.0,
                        "fresh passive clients did not appear after endurance")
                    trace.append(detail_list_state)
                    endurance["cleanup"] = endurance_cleanup
                    endurance["restart"] = endurance_restart
                    endurance["fresh_detail_list"] = detail_list_state
                else:
                    detail_list_state = live_second

                # Passive client identities can legitimately disappear after
                # one frame.  Do not spend the whole gate waiting on whichever
                # ephemeral identity happened to sort first: try up to three
                # already-visible rows within the same 90-second total budget.
                visible_candidates = max(
                    1, int(detail_list_state.get(
                        "wifi_device_visible_size", 0)))
                candidate_attempts = min(3, visible_candidates)
                for candidate_index in range(candidate_attempts):
                    if candidate_index > 0:
                        selected = action(device, "down")
                        trace.append(selected)
                        require_exact(selected, {
                            "wifi_product_view": "devices",
                            "wifi_device_monitor_active": True,
                            "wifi_device_channel_locked": False,
                        }, f"wifi_device_candidate_{candidate_index}")
                    detail_first = action(device, "right")
                    trace.append(detail_first)
                    if detail_first.get("wifi_product_view") != "device_detail":
                        detail_attempts.append({
                            "candidate_index": candidate_index,
                            "identity_hash": 0,
                            "outcome": "identity_expired_before_detail",
                            "timeout_seconds": 0,
                        })
                        detail_second = {}
                        continue
                    require_exact(detail_first, {
                        "wifi_product_view": "device_detail",
                        "runtime_owner": "wifi", "lease_mask": 15,
                        "wifi_device_monitor_active": True,
                        "wifi_device_channel_locked": True,
                        "wifi_device_oui_database_available": True,
                        "wifi_device_oui_records": 39984,
                        # Keep the strongest-first catalog live.  Detail
                        # identity is pinned by MAC/identity_hash instead of
                        # freezing the list order after the first input.
                        "wifi_device_navigation_locked": False,
                    }, "wifi_device_live_detail")
                    screens["wifi_device_detail_first"] = capture(
                        device, frames, "wifi-device-live-detail-first")
                    # A full 240x320 diagnostic readback is deliberately
                    # synchronous.  On a busy locked channel the passive RX
                    # callback can fill its bounded queue while serial bytes
                    # are being exported.  Snapshot that instrumentation
                    # backpressure separately and require monotonic counters;
                    # zero-drop radio acceptance belongs to nonvisual gates.
                    detail_after_first_capture = query(
                        device, b"ui.state", "leshy.ui.v1", "state")
                    trace.append(detail_after_first_capture)
                    require_exact(detail_after_first_capture, {
                        "wifi_product_view": "device_detail",
                        "wifi_device_monitor_active": True,
                        "wifi_device_channel_locked": True,
                    }, "wifi_device_detail_after_first_capture")
                    detail_oracle_first = query_device_detail(device)
                    require_exact(detail_oracle_first, {
                        "active": True,
                        "passive": True,
                        "active_probe_allowed": False,
                        "channel_locked": True,
                        "detail_content_clears": 1,
                        "radar_full_repaints": 1,
                        "atomic_text_row_allocation_failures": 0,
                        "direct_text_row_fallbacks": 0,
                    }, "wifi_device_detail_oracle_first")
                    detail_accepted = int(
                        detail_first.get("wifi_device_clients_accepted", 0))
                    detail_revision = int(
                        detail_first.get("wifi_device_catalog_revision", 0))
                    detail_last_seen = int(
                        detail_first.get("wifi_device_detail_last_seen_us", 0))
                    detail_hops = int(
                        detail_first.get("wifi_device_channel_hops", 0))
                    try:
                        detail_second = wait_ui_state(
                            device,
                            lambda state: (
                                state.get("wifi_product_view") ==
                                    "device_detail" and
                                state.get("wifi_device_channel_locked") is True and
                                int(state.get(
                                    "wifi_device_clients_accepted", 0)) >
                                    detail_accepted and
                                int(state.get(
                                    "wifi_device_catalog_revision", 0)) >
                                    detail_revision and
                                int(state.get(
                                    "wifi_device_detail_last_seen_us", 0)) >
                                    detail_last_seen
                            ), 30.0,
                            "selected passive client produced no repeat frame")
                    except TimeoutError:
                        detail_attempts.append({
                            "candidate_index": candidate_index,
                            "identity_hash": detail_oracle_first.get(
                                "identity_hash"),
                            "outcome": "no_repeat_frame",
                            "timeout_seconds": 30,
                        })
                        back = action(device, "left")
                        trace.append(back)
                        require_exact(back, {
                            "wifi_product_view": "devices",
                            "wifi_device_channel_locked": False,
                            "wifi_device_monitor_active": True,
                        }, "wifi_device_candidate_back")
                        detail_second = {}
                        continue
                    trace.append(detail_second)
                    detail_oracle_second = wait_device_detail(
                        device,
                        lambda state: (
                            state.get("active") is True and
                            state.get("identity_hash") ==
                                detail_oracle_first.get("identity_hash") and
                            int(state.get("signal_samples", 0)) >
                                int(detail_oracle_first.get(
                                    "signal_samples", 0)) and
                            int(state.get("radar_delta_repaints", 0)) >
                                int(detail_oracle_first.get(
                                    "radar_delta_repaints", 0))
                        ), 5.0,
                        "integrated device radar produced no bounded delta")
                    detail_attempts.append({
                        "candidate_index": candidate_index,
                        "identity_hash": detail_oracle_first.get(
                            "identity_hash"),
                        "outcome": "live_delta",
                        "timeout_seconds": 30,
                    })
                    break
                if not detail_second:
                    raise TimeoutError(
                        "no visible passive Wi-Fi client repeated within the "
                        f"bounded candidate matrix: {detail_attempts!r}")
                if (detail_oracle_second.get("detail_content_clears") !=
                        detail_oracle_first.get("detail_content_clears") or
                        detail_oracle_second.get("radar_full_repaints") !=
                        detail_oracle_first.get("radar_full_repaints") or
                        detail_oracle_second.get(
                            "atomic_text_row_allocation_failures") != 0 or
                        detail_oracle_second.get(
                            "direct_text_row_fallbacks") != 0):
                    raise RuntimeError(
                        "integrated device radar used a full/unsafe repaint: "
                        f"{detail_oracle_second!r}")
                if int(detail_second.get("wifi_device_channel_hops", -1)) != \
                        detail_hops:
                    raise RuntimeError(
                        "integrated device radar hopped away from its channel")
                screens["wifi_device_detail_second"] = capture(
                    device, frames, "wifi-device-live-detail-second")
                detail_after_second_capture = query(
                    device, b"ui.state", "leshy.ui.v1", "state")
                trace.append(detail_after_second_capture)
                require_exact(detail_after_second_capture, {
                    "wifi_product_view": "device_detail",
                    "wifi_device_monitor_active": True,
                    "wifi_device_channel_locked": True,
                }, "wifi_device_detail_after_second_capture")
                detail_pixel_changes = changed_live_detail_pixels(
                    frames, "wifi-device-live-detail-first",
                    "wifi-device-live-detail-second")
                detail_visual_input_changed = (
                    detail_second.get("wifi_device_detail_rssi_dbm") !=
                    detail_first.get("wifi_device_detail_rssi_dbm"))
                if (detail_pixel_changes["identity_changed_pixels"] != 0 or
                        detail_pixel_changes["chrome_changed_pixels"] != 0 or
                        (detail_visual_input_changed and
                         detail_pixel_changes["live_changed_pixels"] == 0)):
                    raise RuntimeError(
                        "integrated live-detail redraw mismatch: "
                        f"{detail_pixel_changes}")

                list_after_detail = action(device, "left")
                trace.append(list_after_detail)
                require_exact(list_after_detail, {
                    "wifi_product_view": "devices",
                    "wifi_device_channel_locked": False,
                    "wifi_device_monitor_active": True,
                }, "wifi_device_live_detail_back")
                monitor_after_first = action(device, "left")
                trace.append(monitor_after_first)
                require_exact(monitor_after_first, {
                    "wifi_product_view": "menu",
                    "wifi_product_selection": 1,
                    "wifi_device_monitor_active": False,
                    "wifi_device_monitor_cleanup_complete": True,
                }, "wifi_devices_first_cleanup")
                if int(monitor_after_first.get(
                        "wifi_device_clients_dropped", -1)) < int(
                        detail_after_second_capture.get(
                            "wifi_device_clients_dropped", 0)):
                    raise RuntimeError(
                        "device drop counter regressed during cleanup")
                screens["wifi_menu_after"] = capture(
                    device, frames, "wifi-menu-after")
                home = action(device, "left")
                trace.append(home)
                require_exact(home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "wifi_home")
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                trace.extend(open_devices(device))
                warm_live = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "devices" and
                        state.get("wifi_devices_strongest_first") is True and
                        int(state.get("wifi_devices_unique", 0)) >= 1 and
                        int(state.get("wifi_device_clients_accepted", 0)) >= 1
                    ), 90.0, "second Wi-Fi device lifecycle found no clients")
                trace.append(warm_live)
                monitor_after_second = action(device, "left")
                trace.append(monitor_after_second)
                require_exact(monitor_after_second, {
                    "wifi_product_view": "menu",
                    "wifi_device_monitor_active": False,
                    "wifi_device_monitor_cleanup_complete": True,
                }, "wifi_devices_second_cleanup")
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
                if metrics_after.get("heap_total") != \
                        metrics_after_first.get("heap_total") or \
                        metrics_after.get("heap_free") != \
                        metrics_after_first.get("heap_free"):
                    failures.append(
                        "heap changed between complete post-warm device lifecycles")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
                if temporary_lock is not None:
                    try:
                        temporary_lock.close()
                    except Exception as error:
                        failures.append(
                            "device_lock_fixture_cleanup: "
                            f"{type(error).__name__}: {error}")
                    device_lock_fixture = temporary_lock.evidence()
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
        "detail_first": detail_first,
        "detail_second": detail_second,
        "detail_after_first_capture": detail_after_first_capture,
        "detail_after_second_capture": detail_after_second_capture,
        "detail_oracle_first": detail_oracle_first,
        "detail_oracle_second": detail_oracle_second,
        "monitor_after_first": monitor_after_first,
        "monitor_after_second": monitor_after_second,
        "metrics_after_first": metrics_after_first,
        "metrics_after": metrics_after,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "list_pixel_changes": list_pixel_changes,
        "detail_pixel_changes": detail_pixel_changes,
        "detail_visual_input_changed": detail_visual_input_changed,
        "detail_attempts": detail_attempts,
        "endurance": endurance,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "device_lock_fixture": device_lock_fixture,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_client_inference_only": True,
            "access_point_beacons_excluded": True,
            "channels_listened": list(range(1, 14)),
            "live_redraw_data_rows_only": True,
            "integrated_live_device_detail": True,
            "live_list_order_not_frozen": True,
            "detail_identity_pinned_by_hash": True,
            "diagnostic_capture_backpressure_accounted": True,
            "serial_observation_backpressure_accounted": True,
            "zero_radio_drop_claim_delegated_to_nonvisual_gate": True,
            "device_identity_region_stable": True,
            "embedded_ieee_oui_records": 39984,
            "passive_probe_association_wps_fingerprint": True,
            "identity_stable_device_navigation": True,
            "channel_locked_live_radar": True,
            "live_detail_redraw_live_region_only": True,
            "live_detail_atomic_rows": True,
            "live_detail_no_full_repaint_after_entry": True,
            "two_complete_wifi_lifecycles": True,
            "continuous_wifi_device_endurance": (
                args.endurance_seconds > 0 and endurance.get("completed") is True
                and int(endurance.get("hops_completed", 0)) >=
                    args.endurance_minimum_hops
            ),
            "zero_heap_drift_after_warmup": (
                metrics_after.get("heap_free") ==
                metrics_after_first.get("heap_free")
            ),
            "storage_write_authorized": False,
            "product_device_lock_namespace_mutated": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
