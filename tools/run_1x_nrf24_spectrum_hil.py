#!/usr/bin/env python3
"""Exercise the 0.92 full-width nRF24 spectrum and waterfall workflow."""

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


RUN_SCHEMA = "leshy.nrf24_spectrum_hil.run.v1"
SPECTRUM_SCHEMA = "leshy.nrf24.spectrum.v1"
MIN_WATERFALL_ROWS = 32


def spectrum_failures(
    report: dict[str, Any], *, state: str, active: bool, cleanup: bool,
    display_mode: str,
) -> list[str]:
    failures = expect(report, {
        "view": "live" if active else "source_menu",
        "display_mode": display_mode,
        "state": state,
        "status": "ready",
        "range_mhz": [2402, 2484],
        "channels": 83,
        "dwell_us": 200,
        "modules": 2,
        "rx_only": True,
        "volatile": True,
        "adapter_active": active,
        "profile_declared": True,
        "nrf_slot3_gated": True,
        "gpio21_stable_high": True,
        "cleanup_complete": cleanup,
        "current_owner": "survey",
        "current_lease_mask": 15,
    }, f"spectrum_{state}")
    sweeps = report.get("sweeps")
    history_rows = report.get("history_rows")
    if not isinstance(history_rows, int) or history_rows < 1 or history_rows > 112:
        failures.append(f"bounded waterfall history differs: {history_rows!r}")
    wire = report.get("wire", {})
    side_effects = report.get("side_effects", {})
    if not isinstance(sweeps, int) or sweeps < 1:
        failures.append(f"no completed spectrum sweep: {sweeps!r}")
    else:
        final_writes = 2 if cleanup else 0
        expected = {
            "register_reads": 10 + 83 * sweeps,
            "register_writes": 10 + 83 * sweeps + final_writes,
            "spi_bytes_clocked": 40 + 332 * sweeps + 2 * final_writes,
            "receive_ce_high_events": 83 * sweeps,
        }
        if wire != expected:
            failures.append(f"wire bounds differ: expected={expected}, actual={wire}")
    if side_effects != {
        "tx_mode_entries": 0,
        "tx_payload_commands": 0,
        "cc_command_strobes": 0,
        "storage_writes": 0,
    }:
        failures.append(f"unexpected side effects: {side_effects!r}")
    peak_mhz = report.get("peak_mhz")
    if not isinstance(peak_mhz, int) or not 2402 <= peak_mhz <= 2484:
        failures.append(f"peak is outside plan: {peak_mhz!r}")
    return failures


def wait_for_history(
    device: PassiveSerial, minimum_rows: int, timeout: float = 8.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report = query(
            device, b"hardware.nrf24.spectrum", SPECTRUM_SCHEMA, "state")
        if int(report.get("history_rows", 0)) >= minimum_rows:
            return report
        time.sleep(0.05)
    raise RuntimeError(
        f"nRF24 waterfall did not accumulate {minimum_rows} rows: {report}"
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

                state = action(device, "down")
                trace.append(state)
                failures.extend(expect(state, {
                    "survey_setup_selection": 1,
                    "render_mode": "incremental",
                }, "spectrum_plan_focus"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "opened_spectrum", "page": "survey",
                    "changed": True,
                }, "spectrum_source_menu"))
                captures["source_menu"] = capture(
                    device, frames, "source-menu")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "nrf24_spectrum_running",
                    "page": "survey", "changed": True,
                    "runtime_owner": "survey", "lease_mask": 15,
                }, "spectrum_start"))
                time.sleep(0.6)
                reports["running"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["running"], state="running", active=True,
                    cleanup=False, display_mode="spectrum"))
                captures["spectrum"] = capture(device, frames, "spectrum")

                state = action(device, "down")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "spectrum_waterfall_view",
                    "changed": True,
                }, "waterfall_view"))
                reports["waterfall"] = wait_for_history(
                    device, MIN_WATERFALL_ROWS)
                failures.extend(spectrum_failures(
                    reports["waterfall"], state="running", active=True,
                    cleanup=False, display_mode="waterfall"))
                captures["waterfall"] = capture(device, frames, "waterfall")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "nrf24_spectrum_paused",
                    "changed": True,
                }, "spectrum_pause"))
                reports["paused_before"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                time.sleep(0.4)
                reports["paused_after"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["paused_after"], state="paused", active=True,
                    cleanup=False, display_mode="waterfall"))
                if reports["paused_after"].get("sweeps") != \
                        reports["paused_before"].get("sweeps"):
                    failures.append("paused spectrum continued sweeping")
                captures["paused"] = capture(device, frames, "paused")

                state = action(device, "right")
                trace.append(state)
                time.sleep(0.4)
                reports["resumed"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["resumed"], state="running", active=True,
                    cleanup=False, display_mode="waterfall"))
                if int(reports["resumed"].get("sweeps", 0)) <= int(
                        reports["paused_after"].get("sweeps", 0)):
                    failures.append("resume did not restart sweeping")

                state = action(device, "up")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "spectrum_bar_view", "changed": True,
                }, "spectrum_view_restored"))
                reports["spectrum_restored"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["spectrum_restored"], state="running", active=True,
                    cleanup=False, display_mode="spectrum"))
                captures["spectrum_restored"] = capture(
                    device, frames, "spectrum-restored")

                state = action(device, "left")
                trace.append(state)
                failures.extend(expect(state, {
                    "runtime_event": "nrf24_spectrum_stopped",
                    "page": "survey", "changed": True,
                }, "spectrum_stop"))
                reports["stopped"] = query(
                    device, b"hardware.nrf24.spectrum",
                    SPECTRUM_SCHEMA, "state")
                failures.extend(spectrum_failures(
                    reports["stopped"], state="idle", active=False,
                    cleanup=True, display_mode="spectrum"))
                captures["stopped"] = capture(device, frames, "stopped")

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
                if (recovery_after.get("generation") !=
                        recovery_before.get("generation") or
                        recovery_after.get("observations") !=
                        recovery_before.get("observations") or
                        recovery_after.get("physical_write_calls") != 0):
                    failures.append("spectrum changed persistent product data")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap free did not return to boot baseline")
            except Exception as error:
                failures.append(f"spectrum_phase: {type(error).__name__}: {error}")
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
