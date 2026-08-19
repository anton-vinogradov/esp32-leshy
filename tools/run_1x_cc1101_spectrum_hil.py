#!/usr/bin/env python3
"""Exercise the 0.92 full-width CC1101 spectrum and waterfall workflow."""

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


RUN_SCHEMA = "leshy.cc1101_spectrum_hil.run.v1"
SPECTRUM_SCHEMA = "leshy.cc1101.spectrum.v1"
BANDS = {
    "315": [300000, 348000],
    "433": [433050, 434790],
    "868": [863000, 870000],
    "915": [902000, 928000],
}
MIN_WATERFALL_ROWS = 16


def spectrum_failures(
    report: dict[str, Any], *, state: str, active: bool, cleanup: bool,
    band: str, display_mode: str,
) -> list[str]:
    failures = expect(report, {
        "view": "live" if active else "cc_band_menu",
        "display_mode": display_mode,
        "state": state,
        "status": "ready",
        "band": band,
        "range_khz": BANDS[band],
        "bins": 64,
        "settle_us": 500,
        "ready_timeout_us": 3000,
        "partnum": 0,
        "version": 0x14,
        "rx_only": True,
        "volatile": True,
        "adapter_active": active,
        "profile_declared": True,
        "nrf_slot3_gated": True,
        "gpio21_stable_high": True,
        "cleanup_complete": cleanup,
        "current_owner": "survey",
        "current_lease_mask": 15,
    }, f"cc1101_{band}_{state}")
    sweeps = report.get("sweeps")
    history_rows = report.get("history_rows")
    if not isinstance(history_rows, int) or history_rows < 1 or history_rows > 224:
        failures.append(f"bounded waterfall history differs: {history_rows!r}")
    samples = report.get("samples")
    adapter_samples = report.get("adapter_samples")
    next_bin = report.get("next_bin")
    if not isinstance(sweeps, int) or sweeps < 1:
        failures.append(f"no complete CC1101 sweep for {band}: {sweeps!r}")
    if not isinstance(samples, int) or samples < 64:
        failures.append(f"too few current-band samples for {band}: {samples!r}")
    elif not isinstance(next_bin, int) or next_bin != samples % 64:
        failures.append(
            f"current-band sample/bin continuity differs: {samples!r}/{next_bin!r}"
        )
    if not isinstance(adapter_samples, int) or adapter_samples < samples:
        failures.append(
            f"adapter sample count is not cumulative: {adapter_samples!r}"
        )

    peak = report.get("peak_khz")
    peak_rssi = report.get("peak_rssi_dbm")
    latest_rssi = report.get("latest_rssi_dbm")
    if not isinstance(peak, int) or not BANDS[band][0] <= peak <= BANDS[band][1]:
        failures.append(f"peak outside selected band {band}: {peak!r}")
    for label, value in (("peak", peak_rssi), ("latest", latest_rssi)):
        if not isinstance(value, int) or not -128 <= value <= 20:
            failures.append(f"{label} RSSI outside CC1101 bounds: {value!r}")

    wire = report.get("wire", {})
    side_effects = report.get("side_effects", {})
    if isinstance(adapter_samples, int):
        ready_timeouts = wire.get("receive_ready_timeouts")
        transient_retries = wire.get("transient_retries")
        if not isinstance(ready_timeouts, int) or \
                not isinstance(transient_retries, int) or \
                transient_retries != ready_timeouts or \
                not 0 <= transient_retries <= adapter_samples:
            failures.append(
                "CC1101 bounded RX-ready retry accounting differs: "
                f"{ready_timeouts!r}/{transient_retries!r}"
            )
            transient_retries = 0
        writes = wire.get("register_writes")
        reads = wire.get("register_reads")
        strobes = wire.get("command_strobes")
        reset_strobes = wire.get("reset_strobes")
        receive_strobes = wire.get("receive_strobes")
        idle_strobes = wire.get("idle_strobes")
        spi_bytes = wire.get("spi_bytes_clocked")
        if writes != 16 + 3 * (adapter_samples + transient_retries):
            failures.append(
                f"CC1101 write bound differs: {writes!r} for {adapter_samples} samples"
            )
        if not isinstance(reads, int) or reads < 2 + 2 * adapter_samples:
            failures.append(
                f"CC1101 read lower bound differs: {reads!r} for {adapter_samples}"
            )
        if reset_strobes != 1 or \
                receive_strobes != adapter_samples + transient_retries:
            failures.append(
                "CC1101 reset/receive strobe accounting differs: "
                f"{reset_strobes!r}/{receive_strobes!r}"
            )
        if not all(isinstance(value, int) for value in (
                strobes, reset_strobes, receive_strobes, idle_strobes)) or \
                strobes != reset_strobes + receive_strobes + idle_strobes:
            failures.append(f"CC1101 strobe sum differs: {wire!r}")
        if all(isinstance(value, int) for value in (
                writes, reads, strobes, spi_bytes)) and \
                spi_bytes != 2 * writes + 2 * reads + strobes:
            failures.append(f"CC1101 SPI byte accounting differs: {wire!r}")
    if side_effects != {
        "rejected_strobes": 0,
        "tx_strobes": 0,
        "pa_table_writes": 0,
        "fifo_writes": 0,
        "storage_writes": 0,
    }:
        failures.append(f"unexpected CC1101 side effects: {side_effects!r}")
    return failures


def wait_for_sweep(
    device: PassiveSerial, band: str, minimum_sweeps: int = 1,
    timeout: float = 24.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report = query(
            device, b"hardware.cc1101.spectrum", SPECTRUM_SCHEMA, "state")
        if report.get("band") == band and \
                int(report.get("sweeps", 0)) >= minimum_sweeps and \
                int(report.get("history_rows", 0)) >= minimum_sweeps:
            return report
        time.sleep(0.25)
    raise RuntimeError(
        f"CC1101 band {band} did not complete {minimum_sweeps} sweeps: {report}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot = query(device, b"metrics", "leshy.boot.v1", "ready")
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
                    raise RuntimeError("initial cleanup did not reach Home/lease 0")

                state = query(device, b"ui.state", "leshy.ui.v1", "state")
                for _ in range(8):
                    if int(state.get("selection", -1)) == 0:
                        break
                    state = action(device, "up")
                    trace.append(state)
                query(device, b"ui.language ru", "leshy.ui.v1", "state")
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "survey", "survey_setup_view": "plan",
                    "survey_setup_selection": 0, "runtime_owner": "survey",
                    "lease_mask": 15,
                }, "survey_plan"))
                captures["plan"] = capture(device, frames, "plan")

                trace.append(action(device, "down"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "opened_spectrum", "page": "survey",
                    "changed": True,
                }, "spectrum_source_menu"))
                state = action(device, "down")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "opened_spectrum", "changed": True,
                    "render_mode": "incremental",
                }, "cc1101_source_focus"))
                captures["source_menu"] = capture(device, frames, "source-menu")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "cc1101_spectrum_band_menu",
                    "page": "survey", "changed": True,
                    "runtime_owner": "survey", "lease_mask": 15,
                }, "cc1101_band_menu"))
                captures["band_menu_433"] = capture(
                    device, frames, "band-menu-433")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "cc1101_spectrum_running",
                    "page": "survey", "changed": True,
                    "runtime_owner": "survey", "lease_mask": 15,
                }, "cc1101_start_433"))
                reports["band_433"] = wait_for_sweep(device, "433")
                failures.extend(spectrum_failures(
                    reports["band_433"], state="running", active=True,
                    cleanup=False, band="433", display_mode="spectrum"))
                captures["spectrum_433"] = capture(
                    device, frames, "spectrum-433")

                state = action(device, "down")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "spectrum_waterfall_view",
                    "changed": True,
                }, "cc1101_waterfall_view"))
                reports["waterfall_433"] = wait_for_sweep(
                    device, "433", MIN_WATERFALL_ROWS)
                failures.extend(spectrum_failures(
                    reports["waterfall_433"], state="running", active=True,
                    cleanup=False, band="433", display_mode="waterfall"))
                captures["waterfall_433"] = capture(
                    device, frames, "waterfall-433")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "cc1101_spectrum_paused",
                    "changed": True,
                }, "cc1101_pause"))
                reports["paused_before"] = query(
                    device, b"hardware.cc1101.spectrum",
                    SPECTRUM_SCHEMA, "state")
                time.sleep(0.4)
                reports["paused_after"] = query(
                    device, b"hardware.cc1101.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["paused_after"], state="paused", active=True,
                    cleanup=False, band="433", display_mode="waterfall"))
                if reports["paused_after"].get("adapter_samples") != \
                        reports["paused_before"].get("adapter_samples"):
                    failures.append("paused CC1101 spectrum continued sampling")
                captures["paused"] = capture(device, frames, "paused")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "cc1101_spectrum_running",
                    "changed": True,
                }, "cc1101_resume"))
                before_resume = int(
                    reports["paused_after"].get("adapter_samples", 0))
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    reports["resumed"] = query(
                        device, b"hardware.cc1101.spectrum",
                        SPECTRUM_SCHEMA, "state")
                    if int(reports["resumed"].get("adapter_samples", 0)) > \
                            before_resume:
                        break
                    time.sleep(0.05)
                failures.extend(spectrum_failures(
                    reports["resumed"], state="running", active=True,
                    cleanup=False, band="433", display_mode="waterfall"))
                if int(reports["resumed"].get("adapter_samples", 0)) <= \
                        before_resume:
                    failures.append("resume did not restart CC1101 sampling")

                state = action(device, "up")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "spectrum_bar_view", "changed": True,
                }, "cc1101_spectrum_view_restored"))

                state = action(device, "left")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "cc1101_spectrum_stopped",
                    "page": "survey", "changed": True,
                }, "cc1101_stop"))
                reports["stopped_433"] = query(
                    device, b"hardware.cc1101.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["stopped_433"], state="idle", active=False,
                    cleanup=True, band="433", display_mode="spectrum"))

                band_index = 1
                for target_index, band in ((2, "868"), (3, "915"), (0, "315")):
                    while band_index < target_index:
                        trace.append(action(device, "down"))
                        band_index += 1
                    while band_index > target_index:
                        trace.append(action(device, "up"))
                        band_index -= 1
                    captures[f"band_menu_{band}"] = capture(
                        device, frames, f"band-menu-{band}")
                    state = action(device, "right")
                    trace.append(state)
                    failures.extend(expect(state, {
                        "runtime_event": "cc1101_spectrum_running",
                        "page": "survey", "changed": True,
                    }, f"cc1101_start_{band}"))
                    reports[f"band_{band}"] = wait_for_sweep(device, band)
                    failures.extend(spectrum_failures(
                        reports[f"band_{band}"], state="running", active=True,
                        cleanup=False, band=band, display_mode="spectrum"))
                    captures[f"spectrum_{band}"] = capture(
                        device, frames, f"spectrum-{band}")
                    state = action(device, "left")
                    trace.append(state)
                    failures.extend(expect(state, {
                        "runtime_event": "cc1101_spectrum_stopped",
                        "page": "survey", "changed": True,
                    }, f"cc1101_stop_{band}"))
                    reports[f"stopped_{band}"] = query(
                        device, b"hardware.cc1101.spectrum",
                        SPECTRUM_SCHEMA, "state")
                    failures.extend(spectrum_failures(
                        reports[f"stopped_{band}"], state="idle", active=False,
                        cleanup=True, band=band, display_mode="spectrum"))

                captures["stopped"] = capture(device, frames, "stopped")

                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                state = action(device, "left")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final_home"))
                captures["home"] = capture(device, frames, "home")
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
                if recovery_after.get("generation") != \
                        recovery_before.get("generation") or \
                        recovery_after.get("observations") != \
                        recovery_before.get("observations") or \
                        recovery_after.get("physical_write_calls") != 0:
                    failures.append("CC1101 spectrum changed persistent product data")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap free did not return to boot baseline")
            except Exception as error:
                failures.append(
                    f"cc1101_spectrum_phase: {type(error).__name__}: {error}"
                )
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
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "recovery_before": recovery_before,
        "reports": reports,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "recovery_after": recovery_after,
        "metrics_after": metrics_after,
        "captures": captures,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
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
