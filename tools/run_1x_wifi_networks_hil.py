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
    metrics_after_first: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    list_pixel_changes: dict[str, int] = {}
    detail_pixel_changes: dict[str, int] = {}
    live_first: dict[str, Any] = {}
    live_second: dict[str, Any] = {}
    detail_first: dict[str, Any] = {}
    detail_second: dict[str, Any] = {}

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
                    "page": "survey", "runtime_owner": "wifi",
                    "lease_mask": 15, "wifi_product_view": "networks",
                    "survey_product_selected_source_mask": 1,
                }, "wifi_networks_preparing")
                live_first = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "networks" and
                        state.get("survey_workflow_state") == "running" and
                        state.get("wifi_networks_strongest_first") is True and
                        int(state.get("wifi_networks_unique", 0)) >= 1 and
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >= 1
                    ), 45.0, "nearby Wi-Fi networks did not appear")
                trace.append(live_first)
                require_exact(live_first, {
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "survey_product_status": "running",
                    "survey_product_active_source_mask": 1,
                    "survey_scan_status": "valid",
                    "survey_scan_dropped": 0,
                    "survey_product_store_open_attempted": True,
                    "survey_product_store_bytes_written": 0,
                }, "wifi_networks_live")
                screens["wifi_networks_first"] = capture(
                    device, frames, "wifi-networks-first")
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
                list_pixel_changes = changed_pixels(
                    frames, "wifi-networks-first", "wifi-networks-second")
                if list_pixel_changes["content_changed_pixels"] <= 0 or \
                        list_pixel_changes["chrome_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"live list redraw escaped data rows: {list_pixel_changes}")

                detail_first = action(device, "right")
                trace.append(detail_first)
                require_exact(detail_first, {
                    "wifi_product_view": "network_detail",
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "survey_workflow_state": "running",
                }, "wifi_network_detail")
                screens["wifi_network_detail_first"] = capture(
                    device, frames, "wifi-network-detail-first")
                detail_cycle = int(
                    detail_first.get("survey_product_wifi_scan_cycles", 0))
                detail_second = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "network_detail" and
                        int(state.get("survey_product_wifi_scan_cycles", 0)) >
                            detail_cycle
                    ), 45.0, "background scan did not progress on detail")
                screens["wifi_network_detail_second"] = capture(
                    device, frames, "wifi-network-detail-second")
                detail_pixel_changes = changed_pixels(
                    frames, "wifi-network-detail-first",
                    "wifi-network-detail-second")
                if detail_pixel_changes != {
                        "content_changed_pixels": 0,
                        "chrome_changed_pixels": 0}:
                    raise RuntimeError(
                        f"stable detail screen changed: {detail_pixel_changes}")

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
        "detail_first": detail_first,
        "detail_second": detail_second,
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
            "passive_wifi_only": True,
            "unique_bssid_rows": True,
            "live_redraw_data_rows_only": True,
            "detail_screen_stable_during_background_scan": True,
            "two_complete_wifi_lifecycles": True,
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
