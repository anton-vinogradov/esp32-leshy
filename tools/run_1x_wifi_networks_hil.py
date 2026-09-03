#!/usr/bin/env python3
"""Flash once and verify the product Wi-Fi nearby-networks flow on board-01."""

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


RUN_SCHEMA = "leshy.wifi_networks_hil.run.v1"
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


def changed_pixels(frames: Path, before_name: str,
                   after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    expected = 240 * 320 * 2
    if len(before) != expected or len(after) != expected:
        raise RuntimeError("TFT comparison requires two complete 240x320 frames")
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


def changed_outside_region(frames: Path, before_name: str, after_name: str,
                           x0: int, y0: int, x1: int, y1: int) -> int:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    outside = 0
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if not (x0 <= x < x1 and y0 <= y < y1):
                outside += 1
    return outside


def selected_row_focus_frame(frames: Path, name: str) -> dict[str, Any]:
    """Verify the complete selected-row outline without assuming a theme."""
    frame = (frames / f"{name}.rgb565").read_bytes()
    expected = 240 * 320 * 2
    if len(frame) != expected:
        raise RuntimeError("focus-frame check requires a complete TFT frame")

    def pixel(x: int, y: int) -> bytes:
        offset = (y * 240 + x) * 2
        return frame[offset:offset + 2]

    # Nearby Networks starts at Components::homeRow(0): x=12, y=32,
    # width=216, height=60, radius=4.  Straight segments must retain the
    # exact same focus color after every dynamic RSSI update.
    reference = pixel(120, 32)
    probes = {
        "top_left": pixel(30, 32),
        "top_middle": reference,
        "top_right": pixel(210, 32),
        "right_upper": pixel(227, 45),
        "right_middle": pixel(227, 65),
        "right_lower": pixel(227, 80),
        "bottom_left": pixel(30, 91),
        "bottom_middle": pixel(120, 91),
        "bottom_right": pixel(210, 91),
    }
    mismatches = [key for key, value in probes.items()
                  if value != reference]
    background_distinct = pixel(120, 33) != reference
    return {
        "continuous": not mismatches and background_distinct,
        "reference_rgb565_bytes": reference.hex(),
        "background_distinct": background_distinct,
        "mismatches": mismatches,
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
    parser.add_argument("--network-intelligence", action="store_true")
    parser.add_argument("--network-live-radar", action="store_true")
    parser.add_argument("--security-advisor", action="store_true")
    parser.add_argument("--endurance-seconds", type=int, default=0)
    parser.add_argument("--endurance-minimum-cycles", type=int, default=0)
    parser.add_argument("--endurance-max-cycle-gap-seconds", type=float,
                        default=15.0)
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
    if args.network_live_radar and not args.network_intelligence:
        parser.error("--network-live-radar requires --network-intelligence")
    if args.endurance_seconds < 0 or args.endurance_minimum_cycles < 0:
        parser.error("endurance duration and cycle floor must be non-negative")
    if args.endurance_max_cycle_gap_seconds <= 0:
        parser.error("--endurance-max-cycle-gap-seconds must be positive")

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
    metrics_after_first: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    list_pixel_changes: dict[str, int] = {}
    list_focus_frames: dict[str, Any] = {}
    detail_pixel_changes: dict[str, int] = {}
    live_first: dict[str, Any] = {}
    live_second: dict[str, Any] = {}
    navigation_first: dict[str, Any] = {}
    navigation_second: dict[str, Any] = {}
    navigation_press_count = 0
    detail_first: dict[str, Any] = {}
    detail_second: dict[str, Any] = {}
    detail_facts_first: dict[str, Any] = {}
    detail_facts_second: dict[str, Any] = {}
    detail_outside_signal_pixels = 0
    detail_outside_radar_pixels = 0
    security_pixel_changes: dict[str, int] = {}
    endurance: dict[str, Any] = {
        "requested_seconds": args.endurance_seconds,
        "minimum_cycles": args.endurance_minimum_cycles,
        "max_cycle_gap_seconds": args.endurance_max_cycle_gap_seconds,
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
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                home_wifi(device)
                menu = action(device, "right")
                trace.append(menu)
                require_exact(menu, {
                    "page": "survey", "selected_id": "wifi",
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "wifi_product_view": "menu", "wifi_product_selection": 0,
                }, "wifi_menu")
                screens["wifi_menu"] = capture(device, frames, "wifi-menu")

                preparing = action(device, "right")
                trace.append(preparing)
                require_exact(preparing, {
                    "action": "right", "changed": True,
                    "page": "survey", "runtime_owner": "wifi",
                    "lease_mask": 15, "wifi_product_view": "networks",
                    "survey_product_selected_source_mask": 1,
                }, "wifi_networks_single_press_entry")
                live_first = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "networks" and
                        state.get("survey_workflow_state") == "running" and
                        state.get("wifi_networks_strongest_first") is True and
                        int(state.get("wifi_networks_unique", 0)) >= 2 and
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >= 1
                    ), 45.0, "nearby Wi-Fi networks did not appear")
                trace.append(live_first)
                live_expected = {
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "survey_product_status": "running",
                    "survey_product_active_source_mask": 1,
                    "survey_scan_status": "valid",
                    "survey_scan_dropped": 0,
                    # Nearby Networks is live/read-only.  The supervised
                    # storage worker opens only for an explicit terminal
                    # commit; merely viewing the list must not touch it.
                    "survey_product_store_open_attempted": False,
                    "survey_product_store_bytes_written": 0,
                }
                require_exact(live_first, live_expected, "wifi_networks_live")
                screens["wifi_networks_first"] = capture(
                    device, frames, "wifi-networks-first")
                list_focus_frames["first"] = selected_row_focus_frame(
                    frames, "wifi-networks-first")
                if not list_focus_frames["first"]["continuous"]:
                    raise RuntimeError(
                        "selected Wi-Fi row focus frame is incomplete: "
                        f"{list_focus_frames['first']}")
                first_revision = int(live_first["wifi_network_catalog_revision"])
                first_cycle = int(live_first["survey_product_wifi_scan_cycles"])
                live_second = wait_ui_state(
                    device,
                    lambda state: (
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >
                            first_cycle and
                        int(state.get("wifi_network_catalog_revision", 0)) >
                            first_revision
                    ), 45.0, "live Wi-Fi catalog did not advance")
                screens["wifi_networks_second"] = capture(
                    device, frames, "wifi-networks-second")
                list_focus_frames["second"] = selected_row_focus_frame(
                    frames, "wifi-networks-second")
                if not list_focus_frames["second"]["continuous"]:
                    raise RuntimeError(
                        "selected Wi-Fi row focus frame was damaged by a "
                        "dynamic update: "
                        f"{list_focus_frames['second']}")
                list_pixel_changes = changed_pixels(
                    frames, "wifi-networks-first", "wifi-networks-second")
                if list_pixel_changes["content_changed_pixels"] <= 0 or \
                        list_pixel_changes["chrome_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"live list redraw escaped data rows: {list_pixel_changes}")

                if args.endurance_seconds:
                    endurance_start = time.monotonic()
                    endurance_deadline = (
                        endurance_start + args.endurance_seconds)
                    endurance_start_cycle = int(live_second.get(
                        "survey_product_wifi_scan_cycles", 0))
                    endurance_last_cycle = endurance_start_cycle
                    endurance_last_progress = endurance_start
                    endurance_next_checkpoint = endurance_start
                    endurance_heap_total: int | None = None
                    endurance_final_state = live_second
                    while time.monotonic() < endurance_deadline:
                        endurance_final_state = query(
                            device, b"ui.state", "leshy.ui.v1", "state")
                        require_exact(endurance_final_state, {
                            "wifi_product_view": "networks",
                            "survey_workflow_state": "running",
                            "runtime_owner": "wifi", "lease_mask": 15,
                            "survey_product_active_source_mask": 1,
                            "survey_scan_status": "valid",
                            "survey_scan_dropped": 0,
                            "safety_latched": False,
                            "safety_reason": "none",
                        }, "wifi_networks_endurance")
                        now = time.monotonic()
                        cycle = int(endurance_final_state.get(
                            "survey_product_wifi_scan_cycles", 0))
                        if cycle > endurance_last_cycle:
                            endurance_last_cycle = cycle
                            endurance_last_progress = now
                        elif now - endurance_last_progress > \
                                args.endurance_max_cycle_gap_seconds:
                            raise RuntimeError(
                                "Wi-Fi scan cycle stalled for "
                                f"{now - endurance_last_progress:.1f}s at "
                                f"cycle {cycle}")
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
                            }, "wifi_networks_endurance_safety")
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
                                "scan_cycle": cycle,
                                "catalog_revision": int(endurance_final_state.get(
                                    "wifi_network_catalog_revision", 0)),
                                "networks": int(endurance_final_state.get(
                                    "wifi_networks_unique", 0)),
                                "heap_total": heap_total,
                                "heap_free": int(metrics.get("heap_free", -1)),
                                "heap_min_free": int(metrics.get(
                                    "heap_min_free", -1)),
                                "safety_latched": endurance_final_state.get(
                                    "safety_latched"),
                                "watchdog_trace_valid": safety.get(
                                    "watchdog_trace_valid"),
                                "scan_dropped": int(endurance_final_state.get(
                                    "survey_scan_dropped", -1)),
                            }
                            endurance["checkpoints"].append(checkpoint)
                            print(json.dumps({
                                "status": "in_progress",
                                "endurance": checkpoint,
                            }, sort_keys=True), flush=True)
                            endurance_next_checkpoint = now + 15.0
                        time.sleep(0.25)
                    endurance_end = time.monotonic()
                    endurance_cycles = (
                        endurance_last_cycle - endurance_start_cycle)
                    endurance.update({
                        "completed": True,
                        "elapsed_seconds": round(
                            endurance_end - endurance_start, 3),
                        "start_cycle": endurance_start_cycle,
                        "end_cycle": endurance_last_cycle,
                        "cycles_completed": endurance_cycles,
                        "final_state": endurance_final_state,
                    })
                    if endurance_cycles < args.endurance_minimum_cycles:
                        raise RuntimeError(
                            "Wi-Fi endurance cycle floor missed: "
                            f"{endurance_cycles} < "
                            f"{args.endurance_minimum_cycles}")

                # Exercise real navigation before opening detail. The list must
                # keep sorting by current signal, but once the user has acted
                # the cursor must stay at its chosen row index instead of being
                # pulled back to the first item on every scan.
                navigation_first = query(
                    device, b"ui.state", "leshy.ui.v1", "state")
                for _ in range(8):
                    selection = int(
                        navigation_first.get("wifi_network_selection", 0))
                    visible = int(
                        navigation_first.get("wifi_network_visible_size", 0))
                    direction = "down" if selection + 1 < visible else "up"
                    navigation_first = action(device, direction)
                    navigation_press_count += 1
                trace.append(navigation_first)
                require_exact(navigation_first, {
                    "wifi_product_view": "networks",
                    "wifi_network_focus_user_owned": True,
                    "wifi_network_navigation_locked": False,
                    "wifi_networks_strongest_first": True,
                    "runtime_owner": "wifi", "lease_mask": 15,
                }, "wifi_network_navigation_owned")
                if int(navigation_first.get("wifi_network_selection", 0)) <= 0:
                    raise RuntimeError(
                        "Wi-Fi cursor did not leave the automatic first row")
                locked_cycle = int(
                    navigation_first["survey_product_wifi_scan_cycles"])
                locked_revision = int(
                    navigation_first["wifi_network_catalog_revision"])
                navigation_second = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "networks" and
                        state.get("wifi_network_focus_user_owned") is True and
                        state.get("wifi_network_navigation_locked") is False and
                        state.get("wifi_networks_strongest_first") is True and
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >=
                            locked_cycle + 2 and
                        int(state.get("wifi_network_catalog_revision", 0)) >
                            locked_revision
                    ), 60.0, "user-owned Wi-Fi cursor did not survive live scans")
                trace.append(navigation_second)
                if int(navigation_first.get(
                        "wifi_network_selected_identity_hash", 0)) == 0:
                    raise RuntimeError("selected Wi-Fi identity hash is empty")
                if navigation_second.get(
                        "wifi_network_selected_identity_hash") != \
                        navigation_first.get(
                            "wifi_network_selected_identity_hash"):
                    raise RuntimeError(
                        "Wi-Fi live sort replaced the selected network: "
                        f"{navigation_first.get('wifi_network_selected_identity_hash')!r} -> "
                        f"{navigation_second.get('wifi_network_selected_identity_hash')!r}")
                if int(navigation_second.get("wifi_network_visible_size", 0)) <= \
                        int(navigation_second.get("wifi_network_selection", 0)):
                    raise RuntimeError("Wi-Fi cursor escaped the live list")
                if int(navigation_second.get("wifi_network_selection", 0)) <= 0:
                    raise RuntimeError("Wi-Fi cursor was reset to the first row")

                if args.network_intelligence:
                    # Start at the strongest locked BSSID and, if necessary,
                    # walk the identity-stable list until the physical air
                    # supplies one named AP with a globally assigned OUI.
                    detail_list_state = navigation_second
                    while int(detail_list_state.get(
                            "wifi_network_selection", 0)) > 0:
                        detail_list_state = action(device, "up")
                        navigation_press_count += 1

                detail_first = action(device, "right")
                trace.append(detail_first)
                require_exact(detail_first, {
                    "wifi_product_view": "network_detail",
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "survey_workflow_state": "running",
                }, "wifi_network_detail")
                if args.network_intelligence:
                    visible = int(detail_first.get(
                        "wifi_network_visible_size", 0))
                    for candidate_index in range(max(1, visible)):
                        detail_facts_first = query(
                            device, b"wifi.network.detail",
                            "leshy.wifi.network_detail.v1", "state")
                        if (detail_facts_first.get("ssid_known") is True and
                                detail_facts_first.get("vendor_known") is True and
                                detail_facts_first.get("facts_known") is True):
                            break
                        if candidate_index + 1 >= visible:
                            raise RuntimeError(
                                "no named globally assigned BSSID exposed a "
                                "vendor/facts passport")
                        trace.append(action(device, "left"))
                        moved = action(device, "down")
                        navigation_press_count += 1
                        trace.append(moved)
                        detail_first = action(device, "right")
                        trace.append(detail_first)
                    require_exact(detail_facts_first, {
                        "active": True, "passive": True,
                        "active_probe_allowed": False,
                        "ssid_known": True, "vendor_known": True,
                        "facts_known": True,
                    }, "wifi_network_detail_facts")
                    if (not detail_facts_first.get("vendor") or
                            detail_facts_first.get("authentication") ==
                                "UNKNOWN" or
                            detail_facts_first.get("channel_width") ==
                                "WIDTH ?" or
                            int(detail_facts_first.get("phy_mask", 0)) == 0 or
                            int(detail_facts_first.get("identity_hash", 0)) == 0):
                        raise RuntimeError(
                            f"incomplete physical network passport: "
                            f"{detail_facts_first!r}")
                screens["wifi_network_detail_first"] = capture(
                    device, frames, "wifi-network-detail-first")
                detail_cycle = int(
                    detail_first.get("survey_product_wifi_scan_cycles", 0))
                if args.network_live_radar:
                    radar_deadline = time.monotonic() + 120.0
                    current_cycle = detail_cycle
                    first_samples = int(
                        detail_facts_first.get("signal_samples", 0))
                    visible_signal_fields = (
                        "rssi_dbm", "minimum_rssi_dbm",
                        "maximum_rssi_dbm")
                    first_trend = int(
                        detail_facts_first.get("rssi_trend_db", 0))
                    first_trend_class = (
                        1 if first_trend >= 4 else
                        (-1 if first_trend <= -4 else 0))
                    while time.monotonic() < radar_deadline:
                        detail_second = wait_ui_state(
                            device,
                            lambda state, cycle=current_cycle: (
                                state.get("wifi_product_view") ==
                                    "network_detail" and
                                int(state.get(
                                    "survey_product_wifi_scan_cycles", 0)) >
                                    cycle
                            ), min(35.0, radar_deadline - time.monotonic()),
                            "background scan did not progress on radar")
                        trace.append(detail_second)
                        current_cycle = int(detail_second.get(
                            "survey_product_wifi_scan_cycles", current_cycle))
                        detail_facts_second = query(
                            device, b"wifi.network.detail",
                            "leshy.wifi.network_detail.v1", "state")
                        for field in (
                                "identity_hash", "vendor", "authentication",
                                "pairwise_cipher", "group_cipher",
                                "channel_width", "phy_mask", "channel",
                                "frequency_khz"):
                            if detail_facts_second.get(field) != \
                                    detail_facts_first.get(field):
                                raise RuntimeError(
                                    "network radar moved identity/fact: "
                                    f"{field}")
                        if (int(detail_facts_second.get(
                                "signal_samples", 0)) > first_samples and
                                (any(detail_facts_second.get(field) !=
                                    detail_facts_first.get(field)
                                    for field in visible_signal_fields) or
                                 (1 if int(detail_facts_second.get(
                                    "rssi_trend_db", 0)) >= 4 else
                                  (-1 if int(detail_facts_second.get(
                                    "rssi_trend_db", 0)) <= -4 else 0)) !=
                                    first_trend_class)):
                            break
                    else:
                        raise RuntimeError(
                            "live network radar did not expose a changed "
                            "physical RSSI/range/trend sample")
                else:
                    detail_second = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("wifi_product_view") ==
                                "network_detail" and
                            int(state.get(
                                "survey_product_wifi_scan_cycles", 0)) >
                                detail_cycle
                        ), 45.0,
                        "background scan did not progress on detail")
                    trace.append(detail_second)
                    if args.network_intelligence:
                        detail_facts_second = query(
                            device, b"wifi.network.detail",
                            "leshy.wifi.network_detail.v1", "state")
                screens["wifi_network_detail_second"] = capture(
                    device, frames, "wifi-network-detail-second")
                if args.network_intelligence:
                    for field in (
                            "identity_hash", "vendor", "authentication",
                            "pairwise_cipher", "group_cipher",
                            "channel_width", "phy_mask", "channel",
                            "frequency_khz"):
                        if detail_facts_second.get(field) != \
                                detail_facts_first.get(field):
                            raise RuntimeError(
                                f"network detail identity/fact moved: {field}")
                detail_pixel_changes = changed_pixels(
                    frames, "wifi-network-detail-first",
                    "wifi-network-detail-second")
                detail_outside_signal_pixels = changed_outside_region(
                    frames, "wifi-network-detail-first",
                    "wifi-network-detail-second", CONTENT_X0, 222,
                    CONTENT_X1, 290)
                detail_outside_radar_pixels = changed_outside_region(
                    frames, "wifi-network-detail-first",
                    "wifi-network-detail-second", CONTENT_X0, 222,
                    CONTENT_X1, 290)
                if args.network_live_radar and (
                        detail_pixel_changes["content_changed_pixels"] <= 0 or
                        detail_pixel_changes["chrome_changed_pixels"] != 0 or
                        detail_outside_radar_pixels != 0):
                    raise RuntimeError(
                        "live network radar redrew outside its card: "
                        f"{detail_pixel_changes}, outside="
                        f"{detail_outside_radar_pixels}")
                if (args.network_intelligence and
                        not args.network_live_radar and (
                        detail_pixel_changes["chrome_changed_pixels"] != 0 or
                        detail_outside_signal_pixels != 0)):
                    raise RuntimeError(
                        "live network passport redrew outside the RSSI line: "
                        f"{detail_pixel_changes}, outside="
                        f"{detail_outside_signal_pixels}")
                if not args.network_intelligence and (
                        detail_pixel_changes["chrome_changed_pixels"] != 0 or
                        detail_outside_signal_pixels != 0):
                    raise RuntimeError(
                        "live network detail redrew outside its signal card: "
                        f"{detail_pixel_changes}, outside="
                        f"{detail_outside_signal_pixels}")

                if args.security_advisor:
                    security_first = action(device, "right")
                    trace.append(security_first)
                    require_exact(security_first, {
                        "wifi_product_view": "password_check_intro",
                        "runtime_owner": "wifi", "lease_mask": 15,
                        "survey_workflow_state": "running",
                    }, "wifi_security_advisor")
                    screens["wifi_security_advisor_first"] = capture(
                        device, frames, "wifi-security-advisor-first")
                    time.sleep(1.0)
                    security_second = query(
                        device, b"ui.state", "leshy.ui.v1", "state")
                    trace.append(security_second)
                    require_exact(security_second, {
                        "wifi_product_view": "password_check_intro",
                        "runtime_owner": "wifi", "lease_mask": 15,
                        "survey_workflow_state": "running",
                    }, "wifi_security_advisor_stable")
                    screens["wifi_security_advisor_second"] = capture(
                        device, frames, "wifi-security-advisor-second")
                    security_pixel_changes = changed_pixels(
                        frames, "wifi-security-advisor-first",
                        "wifi-security-advisor-second")
                    if security_pixel_changes != {
                            "content_changed_pixels": 0,
                            "chrome_changed_pixels": 0}:
                        raise RuntimeError(
                            "security advisor changed while idle: "
                            f"{security_pixel_changes}")
                    detail_again = action(device, "left")
                    trace.append(detail_again)
                    require_exact(detail_again, {
                        "wifi_product_view": "network_detail",
                        "runtime_owner": "wifi", "lease_mask": 15,
                    }, "wifi_security_advisor_back")

                back_to_list = action(device, "left")
                trace.append(back_to_list)
                require_exact(back_to_list, {
                    "wifi_product_view": "networks",
                    "runtime_owner": "wifi", "lease_mask": 15,
                }, "wifi_network_detail_back")
                cancelling = action(device, "left")
                trace.append(cancelling)
                menu_after = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "menu" and
                        state.get("survey_product_source_active") is False and
                        state.get("survey_product_cleanup_complete") is True
                    ), 30.0, "Wi-Fi scan did not cancel back to its menu")
                trace.append(menu_after)
                screens["wifi_menu_after"] = capture(
                    device, frames, "wifi-menu-after")
                home = action(device, "left")
                trace.append(home)
                require_exact(home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "wifi_home")

                # ESP-IDF may retain a bounded one-time Wi-Fi initialization
                # allocation. A second complete open/scan/close cycle in the
                # same boot must prove that this plateau does not grow.
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                home_wifi(device)
                warm_menu = action(device, "right")
                trace.append(warm_menu)
                warm_preparing = action(device, "right")
                trace.append(warm_preparing)
                warm_live = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "networks" and
                        state.get("survey_workflow_state") == "running" and
                        state.get("wifi_networks_strongest_first") is True and
                        int(state.get("wifi_networks_unique", 0)) >= 1 and
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >= 1
                    ), 45.0, "warm Wi-Fi cycle did not produce networks")
                trace.append(warm_live)
                trace.append(action(device, "left"))
                warm_menu_after = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "menu" and
                        state.get("survey_product_source_active") is False and
                        state.get("survey_product_cleanup_complete") is True
                    ), 30.0, "warm Wi-Fi cycle did not clean up")
                trace.append(warm_menu_after)
                warm_home = action(device, "left")
                trace.append(warm_home)
                require_exact(warm_home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "wifi_warm_home")

                input_state = query(
                    device, b"input.state",
                    "leshy.input.frontend.v1", "state")
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
                boot_free = boot.get("heap_free")
                first_free = metrics_after_first.get("heap_free")
                final_free = metrics_after.get("heap_free")
                if not all(isinstance(value, int)
                           for value in (boot_free, first_free, final_free)):
                    failures.append("heap measurements are incomplete")
                else:
                    warmup_bytes = boot_free - first_free
                    if warmup_bytes < 0 or warmup_bytes > 2048:
                        failures.append(
                            f"Wi-Fi one-time heap warm-up is unbounded: "
                            f"{warmup_bytes} bytes")
                    if final_free != first_free:
                        failures.append(
                            "heap changed after the second complete Wi-Fi cycle")
                if metrics_after.get("heap_total") != \
                        metrics_after_first.get("heap_total"):
                    failures.append("heap total changed between Wi-Fi cycles")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": bool(args.flash or args.reuse_exact_flash) and
            not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": bool(args.flash or args.reuse_exact_flash),
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "metrics_after_first": metrics_after_first,
        "metrics_after": metrics_after,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "live_first": live_first,
        "live_second": live_second,
        "navigation_first": navigation_first,
        "navigation_second": navigation_second,
        "detail_first": detail_first,
        "detail_second": detail_second,
        "detail_facts_first": detail_facts_first,
        "detail_facts_second": detail_facts_second,
        "list_pixel_changes": list_pixel_changes,
        "list_focus_frames": list_focus_frames,
        "detail_pixel_changes": detail_pixel_changes,
        "detail_outside_signal_pixels": detail_outside_signal_pixels,
        "detail_outside_radar_pixels": detail_outside_radar_pixels,
        "security_pixel_changes": (
            security_pixel_changes if args.security_advisor else {}),
        "endurance": endurance,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_wifi_only": True,
            "unique_bssid_rows": True,
            "live_redraw_data_rows_only": True,
            "storage_untouched_during_live_list": (
                live_first.get("survey_product_store_open_attempted") is False
                and live_first.get("survey_product_store_bytes_written") == 0
            ),
            "selected_focus_frame_continuous": (
                list_focus_frames.get("first", {}).get("continuous") is True
                and list_focus_frames.get("second", {}).get("continuous")
                    is True
            ),
            "detail_screen_stable_during_background_scan": False,
            "network_intelligence": args.network_intelligence,
            "network_vendor_lookup": args.network_intelligence,
            "network_driver_facts": args.network_intelligence,
            "network_live_radar": args.network_live_radar,
            "security_advisor": args.security_advisor,
            "security_advisor_stable": (
                args.security_advisor and security_pixel_changes == {
                    "content_changed_pixels": 0,
                    "chrome_changed_pixels": 0,
                }),
            "detail_live_signal_card_only": not args.network_live_radar,
            "detail_live_radar_only": args.network_live_radar,
            "two_complete_wifi_lifecycles": True,
            "continuous_wifi_cycle_endurance": (
                args.endurance_seconds > 0 and endurance.get("completed") is True
                and int(endurance.get("cycles_completed", 0)) >=
                    args.endurance_minimum_cycles
            ),
            "navigation_press_count": navigation_press_count,
            "live_order_remains_strongest_first": True,
            "cursor_not_reset_after_user_navigation": (
                int(navigation_second.get("wifi_network_selection", 0)) > 0
            ),
            "selected_identity_preserved_during_live_sort": (
                int(navigation_first.get(
                    "wifi_network_selected_identity_hash", 0)) != 0 and
                navigation_second.get(
                    "wifi_network_selected_identity_hash") ==
                navigation_first.get("wifi_network_selected_identity_hash")
            ),
            "bounded_one_time_heap_warmup_bytes": (
                boot.get("heap_free", 0) -
                metrics_after_first.get("heap_free", 0)
            ),
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
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
