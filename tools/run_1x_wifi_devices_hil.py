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


RUN_SCHEMA = "leshy.wifi_devices_hil.run.v1"
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
        "wifi_device_clients_dropped": 0,
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
    detail_first: dict[str, Any] = {}
    detail_second: dict[str, Any] = {}
    monitor_after_first: dict[str, Any] = {}
    monitor_after_second: dict[str, Any] = {}
    metrics_after_first: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    list_pixel_changes: dict[str, int] = {}
    detail_pixel_changes: dict[str, int] = {}

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

                trace.extend(open_devices(device, frames, screens))
                live_first = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "devices" and
                        state.get("wifi_device_monitor_active") is True and
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
                    "wifi_device_clients_dropped": 0,
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

                detail_first = action(device, "right")
                trace.append(detail_first)
                require_exact(detail_first, {
                    "wifi_product_view": "device_detail",
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "wifi_device_monitor_active": True,
                }, "wifi_device_detail")
                screens["wifi_device_detail_first"] = capture(
                    device, frames, "wifi-device-detail-first")
                detail_accepted = int(
                    detail_first.get("wifi_device_clients_accepted", 0))
                detail_hops = int(
                    detail_first.get("wifi_device_channel_hops", 0))
                detail_second = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "device_detail" and
                        int(state.get("wifi_device_clients_accepted", 0)) >
                            detail_accepted and
                        int(state.get("wifi_device_channel_hops", 0)) >
                            detail_hops
                    ), 60.0, "background client monitor did not progress")
                screens["wifi_device_detail_second"] = capture(
                    device, frames, "wifi-device-detail-second")
                detail_pixel_changes = changed_pixels(
                    frames, "wifi-device-detail-first",
                    "wifi-device-detail-second")
                if detail_pixel_changes != {
                        "content_changed_pixels": 0,
                        "chrome_changed_pixels": 0}:
                    raise RuntimeError(
                        f"stable device detail changed: {detail_pixel_changes}")

                trace.append(action(device, "left"))
                monitor_after_first = action(device, "left")
                trace.append(monitor_after_first)
                require_exact(monitor_after_first, {
                    "wifi_product_view": "menu",
                    "wifi_product_selection": 1,
                    "wifi_device_monitor_active": False,
                    "wifi_device_monitor_cleanup_complete": True,
                    "wifi_device_clients_dropped": 0,
                }, "wifi_devices_first_cleanup")
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
                    "wifi_device_clients_dropped": 0,
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
        "monitor_after_first": monitor_after_first,
        "monitor_after_second": monitor_after_second,
        "metrics_after_first": metrics_after_first,
        "metrics_after": metrics_after,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "list_pixel_changes": list_pixel_changes,
        "detail_pixel_changes": detail_pixel_changes,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_client_inference_only": True,
            "access_point_beacons_excluded": True,
            "channels_listened": list(range(1, 14)),
            "live_redraw_data_rows_only": True,
            "detail_screen_stable_during_background_monitor": True,
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
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
