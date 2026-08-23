#!/usr/bin/env python3
"""Flash once and verify the product Sub-GHz frequency-finder workflow."""

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


RUN_SCHEMA = "leshy.cc1101_signal_finder_hil.run.v1"
FINDER_SCHEMA = "leshy.cc1101.signal-finder.v1"
HEADER_Y1 = 26
INFO_Y1 = 84
GRAPH_Y0 = 99
GRAPH_Y1 = 278
AXIS_Y1 = 293


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def finder_report(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"hardware.cc1101.finder", FINDER_SCHEMA, "state")


def home_subghz(device: PassiveSerial) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    if state.get("page") != "home":
        raise RuntimeError(f"Home expected: {state!r}")
    while int(state.get("selection", -1)) > 3:
        state = action(device, "up")
    while int(state.get("selection", -1)) < 3:
        state = action(device, "down")
    require_exact(state, {
        "page": "home", "selection": 3, "selected_id": "subghz",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "home_subghz")
    return state


def wait_for_calibration(device: PassiveSerial,
                         timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report = finder_report(device)
        if report.get("calibrated") is True and \
                int(report.get("sweeps", 0)) >= 3:
            return report
        time.sleep(0.12)
    raise RuntimeError(f"frequency finder did not calibrate: {report!r}")


def wait_for_next_sweep(device: PassiveSerial, previous: int,
                        timeout: float = 40.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report = finder_report(device)
        if int(report.get("sweeps", 0)) > previous:
            return report
        time.sleep(0.12)
    raise RuntimeError(f"frequency finder did not advance: {report!r}")


def changed_regions(frames: Path, before_name: str,
                    after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != 240 * 320 * 2 or len(after) != 240 * 320 * 2:
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    changes = {key: 0 for key in (
        "header_changed_pixels", "result_changed_pixels",
        "legend_changed_pixels", "graph_changed_pixels",
        "axis_changed_pixels", "footer_changed_pixels")}
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if y < HEADER_Y1:
                key = "header_changed_pixels"
            elif y < INFO_Y1:
                key = "result_changed_pixels"
            elif y < GRAPH_Y0:
                key = "legend_changed_pixels"
            elif y < GRAPH_Y1:
                key = "graph_changed_pixels"
            elif y < AXIS_Y1:
                key = "axis_changed_pixels"
            else:
                key = "footer_changed_pixels"
            changes[key] += 1
    return changes


def tunable(frequency_khz: object) -> bool:
    return isinstance(frequency_khz, int) and any(
        first <= frequency_khz <= last for first, last in (
            (300000, 348000), (387000, 464000), (779000, 928000)))


def report_failures(report: dict[str, Any], *, active: bool,
                    state: str) -> list[str]:
    failures = expect(report, {
        "view": "cc1101_finder" if active else "subghz_menu",
        "state": state,
        "bins": 1099,
        "step_khz": 250,
        "rx_only": True,
        "adapter_active": active,
        "volatile": True,
        "baseline_semantics": "median_of_three_ambient_sweeps",
        "response_semantics": "local_rssi_rise_after_common_drift",
        "current_owner": "subghz",
        "current_lease_mask": 9,
    }, f"finder_{state}")
    if report.get("tuning_windows_khz") != [
            [300000, 348000], [387000, 464000], [779000, 928000]]:
        failures.append("finder tuning windows differ from the CC1101 envelope")
    side_effects = report.get("side_effects", {})
    if side_effects != {
            "rejected_strobes": 0, "tx_strobes": 0,
            "pa_table_writes": 0, "fifo_writes": 0,
            "storage_writes": 0}:
        failures.append(f"unexpected side effects: {side_effects!r}")
    if active:
        if report.get("calibrated") is not True:
            failures.append("finder is not calibrated")
        found = report.get("found")
        frequency = report.get("frequency_khz")
        response = report.get("response_db")
        threshold = report.get("response_threshold_db")
        if found is True:
            if not tunable(frequency):
                failures.append(f"found frequency outside plan: {frequency!r}")
            if not isinstance(response, int) or not isinstance(threshold, int) \
                    or response < threshold:
                failures.append("found result is below threshold")
        elif found is False:
            if frequency != 0:
                failures.append("not-found result exposes a false frequency")
            if not isinstance(response, int) or not isinstance(threshold, int) \
                    or response >= threshold:
                failures.append("not-found result reaches detection threshold")
        else:
            failures.append(f"invalid found state: {found!r}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
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
    boot_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    calibrated: dict[str, Any] = {}
    advanced: dict[str, Any] = {}
    restarted: dict[str, Any] = {}
    stopped: dict[str, Any] = {}
    changes: dict[str, int] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_samples = stabilized_boot_metrics(device)
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

                home_subghz(device)
                modes = action(device, "right")
                trace.append(modes)
                require_exact(modes, {
                    "page": "survey", "selected_id": "subghz",
                    "runtime_event": "subghz_modes",
                    "runtime_owner": "subghz", "lease_mask": 9,
                }, "subghz_modes")
                screens["modes"] = capture(device, frames, "modes")
                focused = action(device, "down")
                trace.append(focused)
                require_exact(focused, {
                    "runtime_event": "subghz_modes", "changed": True,
                    "render_mode": "incremental",
                }, "finder_focus")
                screens["finder_focus"] = capture(
                    device, frames, "finder-focus")
                started = action(device, "right")
                trace.append(started)
                require_exact(started, {
                    "runtime_event": "cc1101_finder_calibrating",
                    "runtime_owner": "subghz", "lease_mask": 9,
                }, "finder_start")
                screens["calibrating"] = capture(
                    device, frames, "calibrating")

                calibrated = wait_for_calibration(device)
                failures.extend(report_failures(
                    calibrated, active=True, state="searching"))
                screens["searching_first"] = capture(
                    device, frames, "searching-first")
                advanced = wait_for_next_sweep(
                    device, int(calibrated.get("sweeps", 0)))
                failures.extend(report_failures(
                    advanced, active=True, state="searching"))
                screens["searching_second"] = capture(
                    device, frames, "searching-second")
                changes = changed_regions(
                    frames, "searching-first", "searching-second")
                for static in (
                        "header_changed_pixels", "legend_changed_pixels",
                        "axis_changed_pixels", "footer_changed_pixels"):
                    if changes.get(static) != 0:
                        failures.append(
                            f"live redraw escaped dynamic content: {changes}")
                        break

                again = action(device, "right")
                trace.append(again)
                require_exact(again, {
                    "runtime_event": "cc1101_finder_calibrating",
                    "changed": True,
                }, "finder_again")
                restarted = finder_report(device)
                require_exact(restarted, {
                    "view": "cc1101_finder", "state": "calibrating",
                    "calibrated": False, "found": False,
                    "sweeps": 0, "calibration_passes": 0,
                    "bins": 1099, "step_khz": 250,
                    "rx_only": True, "adapter_active": True,
                    "current_owner": "subghz", "current_lease_mask": 9,
                }, "finder_restarted")
                screens["restarted"] = capture(device, frames, "restarted")

                trace.append(action(device, "left"))
                stopped = finder_report(device)
                failures.extend(report_failures(
                    stopped, active=False, state="idle"))
                screens["stopped_menu"] = capture(
                    device, frames, "stopped-menu")
                final_home = action(device, "left")
                trace.append(final_home)
                require_exact(final_home, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final_home")
                screens["home_after"] = capture(
                    device, frames, "home-after")
                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                metrics_after = query(device, b"metrics", "leshy.boot.v1", "ready")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
                for field in ("generation", "observations"):
                    if recovery_after.get(field) != recovery_before.get(field):
                        failures.append(f"product {field} changed")
                if recovery_after.get("physical_write_calls") != 0:
                    failures.append("frequency finder wrote persistent storage")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap free did not return to boot baseline")
            except Exception as error:
                failures.append(
                    f"frequency_finder_phase: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: terminal zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "flash_mode": "fresh" if args.flash else "none",
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "boot_metrics_samples": boot_samples,
        "recovery_before": recovery_before,
        "calibrated": calibrated,
        "advanced": advanced,
        "restarted": restarted,
        "stopped": stopped,
        "pixel_changes": changes,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "recovery_after": recovery_after,
        "metrics_after": metrics_after,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "physical_ambient_receive_path_verified": True,
            "known_signal_source_present": False,
            "found_branch_host_injected": True,
            "physical_rf_silence_measured": False,
            "rf_instrument_available": False,
            "software_rx_only_counters_verified": True,
            "raw_identifiers_retained": False,
            "storage_write_authorized": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
