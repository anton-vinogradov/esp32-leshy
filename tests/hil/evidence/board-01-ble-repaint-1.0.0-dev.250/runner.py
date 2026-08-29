#!/usr/bin/env python3
"""Flash once and verify Bluetooth Nearby on the physical board."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from ble_nearby_entry_gate import (
    BLE_ENTRY_STABILITY_SECONDS,
    ble_entry_failure,
)
from ble_nearby_run_policy import (
    boot_recovery_continuity,
    bounded_pipeline_accounting_valid,
    display_signal_signature,
)
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


RUN_SCHEMA = "leshy.ble_nearby_hil.run.v2"
CONTENT_X0 = 12
CONTENT_X1 = 228
CONTENT_Y0 = 32
CONTENT_Y1 = 293
ENTRY_STABILITY_SECONDS = BLE_ENTRY_STABILITY_SECONDS
ENTRY_STABILITY_POLL_SECONDS = 0.25


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def home_ble(device: PassiveSerial) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    if state.get("page") != "home":
        raise RuntimeError(f"Home expected: {state!r}")
    while int(state.get("selection", -1)) > 1:
        state = action(device, "up")
    while int(state.get("selection", -1)) < 1:
        state = action(device, "down")
    require_exact(state, {
        "page": "home", "selection": 1, "selected_id": "ble",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "home_ble")
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


def detail_changed_pixels(frames: Path, before_name: str,
                          after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != 240 * 320 * 2 or len(after) != 240 * 320 * 2:
        raise RuntimeError("BLE detail comparison requires complete TFT frames")
    changes = {"radar_changed_pixels": 0, "static_changed_pixels": 0,
               "chrome_changed_pixels": 0}
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if CONTENT_X0 <= x < CONTENT_X1 and 170 <= y < CONTENT_Y1:
                changes["radar_changed_pixels"] += 1
            elif CONTENT_Y0 <= y < CONTENT_Y1:
                changes["static_changed_pixels"] += 1
            else:
                changes["chrome_changed_pixels"] += 1
    return changes


def ble_detail(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"ble.device.detail",
                 "leshy.ble.device_detail.v1", "state")


def fact_signature(state: dict[str, Any]) -> tuple[Any, ...]:
    fields = (
        "identity_hash", "label_known", "vendor_known", "vendor",
        "company_known", "company_id", "device_kind", "subtype", "tracker",
        "address_type", "advertisement_type", "legacy", "scannable",
        "connectable", "tx_power_known", "tx_power_dbm",
        "appearance_known", "appearance", "service", "known_service_mask",
        "service_uuid_hash",
        "service_uuid_count", "service_data_count",
        "manufacturer_data_length", "payload_length",
    )
    return tuple(state.get(field) for field in fields)


def wait_live(device: PassiveSerial, minimum_cycle: int = 1,
              minimum_revision: int = 0) -> dict[str, Any]:
    return wait_ui_state(
        device,
        lambda state: (
            state.get("ble_product_view") == "devices" and
            state.get("survey_workflow_state") == "running" and
            state.get("ble_devices_strongest_first") is True and
            int(state.get("ble_devices_unique", 0)) >= 1 and
            int(state.get("survey_product_ble_scan_cycles", 0)) >=
                minimum_cycle and
            int(state.get("ble_device_catalog_revision", 0)) >
                minimum_revision
        ), 60.0, "nearby Bluetooth devices did not appear")


def wait_stable_ble_entry(
        device: PassiveSerial,
        duration_seconds: float = ENTRY_STABILITY_SECONDS) -> dict[str, Any]:
    """Observe past NimBLE's bounded sync window and fail on any route bounce."""
    started = time.monotonic()
    samples = 0
    final_state: dict[str, Any] = {}
    while True:
        final_state = query(device, b"ui.state", "leshy.ui.v1", "state")
        samples += 1
        failure = ble_entry_failure(final_state)
        if failure is not None:
            raise RuntimeError(f"BLE entry stability failed: {failure}")
        elapsed = time.monotonic() - started
        if elapsed >= duration_seconds:
            return {
                "duration_ms": int(elapsed * 1000.0),
                "samples": samples,
                "final_state": final_state,
            }
        time.sleep(ENTRY_STABILITY_POLL_SECONDS)


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
    list_render_first: dict[str, Any] = {}
    list_render_second: dict[str, Any] = {}
    detail_first: dict[str, Any] = {}
    detail_second: dict[str, Any] = {}
    detail_oracle_first: dict[str, Any] = {}
    detail_oracle_second: dict[str, Any] = {}
    entry_stability: dict[str, Any] = {}

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

                home_ble(device)
                preparing = action(device, "right")
                trace.append(preparing)
                require_exact(preparing, {
                    "page": "survey", "selected_id": "ble",
                    "runtime_owner": "ble", "lease_mask": 15,
                    "ble_product_view": "devices",
                    "survey_product_selected_source_mask": 2,
                }, "ble_nearby_preparing")
                entry_stability = wait_stable_ble_entry(device)
                trace.append(entry_stability["final_state"])
                live_first = wait_live(device)
                trace.append(live_first)
                require_exact(live_first, {
                    "runtime_owner": "ble", "lease_mask": 15,
                    "survey_product_status": "running",
                    "survey_product_active_source_mask": 2,
                    "survey_ble_scan_status": "valid",
                    "survey_ble_scan_dropped": 0,
                    "survey_product_store_open_attempted": True,
                }, "ble_nearby_live")
                if not bounded_pipeline_accounting_valid(live_first):
                    raise RuntimeError(
                        "first bounded BLE pipeline accounting mismatch")
                first_attempts = int(live_first.get(
                    "survey_ble_scan_attempts", 0))
                first_retries = int(live_first.get(
                    "survey_ble_scan_transient_retries", -1))
                first_cycles = int(live_first[
                    "survey_product_ble_scan_cycles"])
                if not first_cycles <= first_attempts <= first_cycles * 2 or \
                        first_retries != first_attempts - first_cycles:
                    raise RuntimeError(
                        "BLE bounded scan-retry accounting mismatch")
                screens["ble_devices_first"] = capture(
                    device, frames, "ble-devices-first")
                list_render_first = ble_detail(device)
                first_cycle = int(live_first["survey_product_ble_scan_cycles"])
                first_revision = int(live_first["ble_device_catalog_revision"])
                live_second = wait_live(
                    device, first_cycle + 1, first_revision)
                trace.append(live_second)
                second_attempts = int(live_second.get(
                    "survey_ble_scan_attempts", 0))
                second_retries = int(live_second.get(
                    "survey_ble_scan_transient_retries", -1))
                second_cycles = int(live_second[
                    "survey_product_ble_scan_cycles"])
                if not second_cycles <= second_attempts <= second_cycles * 2 \
                        or second_retries != second_attempts - second_cycles:
                    raise RuntimeError(
                        "BLE cumulative scan-retry accounting mismatch")
                if not bounded_pipeline_accounting_valid(live_second):
                    raise RuntimeError(
                        "second bounded BLE pipeline accounting mismatch")
                screens["ble_devices_second"] = capture(
                    device, frames, "ble-devices-second")
                list_render_second = ble_detail(device)
                list_pixel_changes = changed_pixels(
                    frames, "ble-devices-first", "ble-devices-second")
                row_repaint_delta = int(list_render_second.get(
                    "list_row_repaints", -1)) - int(list_render_first.get(
                        "list_row_repaints", -1))
                content_changed = list_pixel_changes[
                    "content_changed_pixels"]
                bounded_rows = (content_changed == 0 and
                                row_repaint_delta == 0) or \
                    (content_changed > 0 and
                     1 <= row_repaint_delta <= 4)
                if list_pixel_changes["chrome_changed_pixels"] != 0 or \
                        not bounded_rows or \
                        list_render_second.get("list_content_clears") != \
                        list_render_first.get("list_content_clears"):
                    raise RuntimeError(
                        "BLE live list used an unbounded repaint: "
                        f"rows={row_repaint_delta}, "
                        f"first={list_render_first!r}, "
                        f"second={list_render_second!r}")

                detail_first = action(device, "right")
                trace.append(detail_first)
                require_exact(detail_first, {
                    "ble_product_view": "device_detail",
                    "runtime_owner": "ble", "lease_mask": 15,
                    "survey_workflow_state": "running",
                }, "ble_device_detail")
                screens["ble_detail_first"] = capture(
                    device, frames, "ble-detail-first")
                detail_oracle_first = ble_detail(device)
                require_exact(detail_oracle_first, {
                    "active": True, "passive": True,
                    "active_probe_allowed": False, "facts_known": True,
                    "company_database_available": True,
                    "company_database_records": 4012,
                }, "ble_device_detail_oracle")
                if int(detail_oracle_first.get("signal_samples", 0)) < 1 or \
                        int(detail_oracle_first.get("payload_length", 0)) < 1:
                    raise RuntimeError(
                        f"BLE advertisement facts/signal missing: "
                        f"{detail_oracle_first!r}")
                deadline = time.monotonic() + 90.0
                baseline_facts = fact_signature(detail_oracle_first)
                baseline_signal = display_signal_signature(detail_oracle_first)
                while time.monotonic() < deadline:
                    current = ble_detail(device)
                    if current.get("identity_hash") != \
                            detail_oracle_first.get("identity_hash"):
                        raise RuntimeError("BLE detail identity moved")
                    current_facts = fact_signature(current)
                    if current_facts != baseline_facts:
                        # Enrichment is useful static data, not flicker. Make it
                        # the new baseline and prove the next update is radar-only.
                        baseline_facts = current_facts
                        detail_oracle_first = current
                        time.sleep(0.2)
                        screens["ble_detail_first"] = capture(
                            device, frames, "ble-detail-first")
                        baseline_signal = display_signal_signature(current)
                    elif display_signal_signature(current) != baseline_signal:
                        detail_oracle_second = current
                        break
                    time.sleep(0.25)
                if not detail_oracle_second:
                    raise RuntimeError(
                        "selected BLE device produced no live RSSI update")
                detail_second = query(
                    device, b"ui.state", "leshy.ui.v1", "state")
                trace.append(detail_second)
                screens["ble_detail_second"] = capture(
                    device, frames, "ble-detail-second")
                detail_pixel_changes = detail_changed_pixels(
                    frames, "ble-detail-first", "ble-detail-second")
                if detail_pixel_changes["radar_changed_pixels"] <= 0 or \
                        detail_pixel_changes["static_changed_pixels"] != 0 or \
                        detail_pixel_changes["chrome_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"BLE live redraw escaped radar: {detail_pixel_changes}")
                if detail_oracle_second.get("detail_content_clears") != \
                        detail_oracle_first.get("detail_content_clears") or \
                        detail_oracle_second.get("radar_full_repaints") != \
                        detail_oracle_first.get("radar_full_repaints") or \
                        int(detail_oracle_second.get(
                            "radar_delta_repaints", -1)) <= int(
                                detail_oracle_first.get(
                                    "radar_delta_repaints", -1)):
                    raise RuntimeError(
                        "BLE detail signal update used a full repaint: "
                        f"first={detail_oracle_first!r}, "
                        f"second={detail_oracle_second!r}")

                back_to_list = action(device, "left")
                trace.append(back_to_list)
                require_exact(back_to_list, {
                    "ble_product_view": "devices",
                    "runtime_owner": "ble", "lease_mask": 15,
                }, "ble_detail_back")
                trace.append(action(device, "left"))
                home_after = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("page") == "home" and
                        state.get("runtime_owner") == "none" and
                        state.get("lease_mask") == 0 and
                        state.get("survey_product_cleanup_complete") is True
                    ), 30.0, "BLE scan did not cancel to Home")
                trace.append(home_after)
                screens["home_after"] = capture(
                    device, frames, "ble-home-after")
                metrics_after_first = query(
                    device, b"metrics", "leshy.boot.v1", "ready")

                home_ble(device)
                trace.append(action(device, "right"))
                warm_live = wait_live(device)
                trace.append(warm_live)
                trace.append(action(device, "left"))
                warm_home = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("page") == "home" and
                        state.get("runtime_owner") == "none" and
                        state.get("lease_mask") == 0 and
                        state.get("survey_product_cleanup_complete") is True
                    ), 30.0, "second BLE lifecycle did not clean up")
                trace.append(warm_home)

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
                if not boot_recovery_continuity(
                        recovery_before, recovery_after):
                    failures.append("boot-recovery continuity changed")
                if metrics_after.get("heap_total") != \
                        metrics_after_first.get("heap_total") or \
                        metrics_after.get("heap_free") != \
                        metrics_after_first.get("heap_free"):
                    failures.append("heap changed after second BLE lifecycle")
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
        "list_render_first": list_render_first,
        "list_render_second": list_render_second,
        "detail_first": detail_first,
        "detail_second": detail_second,
        "detail_oracle_first": detail_oracle_first,
        "detail_oracle_second": detail_oracle_second,
        "entry_stability": entry_stability,
        "list_pixel_changes": list_pixel_changes,
        "detail_pixel_changes": detail_pixel_changes,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "delayed_entry_stability_gate": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_ble_only": True,
            "active_scan": False,
            "strongest_first_unique_rows": True,
            "live_redraw_data_rows_only": True,
            "detail_live_radar_only": True,
            "intermediate_clear_counters_checked": True,
            "advertisement_facts_visible": True,
            "offline_company_database": True,
            "two_complete_ble_lifecycles": True,
            "zero_heap_drift_after_warmup": (
                metrics_after.get("heap_free") ==
                metrics_after_first.get("heap_free")
            ),
            "boot_recovery_continuity": boot_recovery_continuity(
                recovery_before, recovery_after),
            # This focused gate retains the store-write telemetry reported by
            # each live UI state, but it does not observe all product storage
            # paths and therefore makes no global no-write claim.
            "product_storage_writes_measured": False,
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
