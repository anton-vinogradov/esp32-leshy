#!/usr/bin/env python3
"""Exercise the first 1.x passive infrared receive/capture user slice."""

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
from run_1x_subghz_raw_hil import select_home_app


RUN_SCHEMA = "leshy.infrared_capture_hil.run.v1"
STATE_SCHEMA = "leshy.capture.infrared_raw.v1"


def wait_no_signal_terminal(device: Any, timeout: float = 11.5) -> dict[str, Any]:
    # A host query, screenshot, or key event must never interrupt a physical
    # pulse train. Stay completely silent for longer than the bounded wait.
    time.sleep(timeout)
    return query(device, b"capture.ir.state", STATE_SCHEMA, "state")


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
    captures: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.5) as device:
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

                home = select_home_app(device, "capture", trace)
                failures.extend(expect(home, {
                    "page": "home", "selected_id": "capture",
                    "selected_enabled": True, "runtime_owner": "none",
                    "lease_mask": 0,
                }, "home_capture"))
                captures["home"] = capture(device, frames, "home")

                source_menu = action(device, "right")
                trace.append(source_menu)
                failures.extend(expect(source_menu, {
                    "page": "capture", "runtime_owner": "capture",
                    "lease_mask": 11,
                }, "source_menu"))
                captures["source_menu"] = capture(
                    device, frames, "source-menu")

                trace.append(action(device, "down"))
                captures["source_ir"] = capture(device, frames, "source-ir")
                trace.append(action(device, "right"))
                setup = query(device, b"capture.ir.state", STATE_SCHEMA,
                              "state")
                reports["setup"] = setup
                failures.extend(expect(setup, {
                    "state": "idle", "passive_only": True, "rx_only": True,
                    "gpio_rx": 21, "gpio_tx": 14, "tx_level": "low",
                    "application_tx_calls": 0, "storage_written": False,
                    "persist_state": "volatile", "cleanup_complete": True,
                    "lease_mask": 11,
                }, "setup"))
                captures["setup"] = capture(device, frames, "setup")

                trace.append(action(device, "right"))
                waiting = query(device, b"capture.ir.state", STATE_SCHEMA,
                                "state")
                reports["waiting"] = waiting
                failures.extend(expect(waiting, {
                    "state": "waiting", "passive_only": True,
                    "rx_only": True, "gpio_rx": 21, "gpio_tx": 14,
                    "tx_level": "low", "application_tx_calls": 0,
                    "wait_timeout_ms": 10000, "maximum_capture_ms": 1000,
                    "minimum_pulse_us": 80, "end_gap_us": 20000,
                    "maximum_sample_gap_us": 250, "maximum_pulses": 512,
                    "cleanup_complete": False, "storage_written": False,
                    "persist_state": "volatile", "lease_mask": 11,
                }, "waiting"))
                if not isinstance(waiting.get("samples"), int):
                    failures.append("waiting: sample counter missing")
                captures["waiting"] = capture(device, frames, "waiting")

                terminal = wait_no_signal_terminal(device)
                reports["terminal"] = terminal
                failures.extend(expect(terminal, {
                    "state": "timed_out", "passive_only": True,
                    "rx_only": True, "gpio_rx": 21, "gpio_tx": 14,
                    "tx_level": "low", "application_tx_calls": 0,
                    "signal_started_us": 0, "transitions": 0,
                    "pulses": 0, "protocol": "unknown",
                    "decode_integrity_valid": False,
                    "csv_available": False, "cleanup_complete": True,
                    "storage_written": False, "persist_state": "volatile",
                    "persist_generation": 0, "driver_error": 0,
                    "lease_mask": 11,
                }, "terminal"))
                if not isinstance(terminal.get("samples"), int) or \
                        terminal.get("samples", 0) < 100_000:
                    failures.append("terminal: no bounded physical GPIO sampling")
                elapsed = terminal.get("ended_us", 0) - \
                    terminal.get("started_us", 0)
                if not 10_000_000 <= elapsed <= 10_100_000:
                    failures.append(
                        f"terminal: wait elapsed {elapsed!r} us is out of bounds")
                captures["terminal"] = capture(device, frames, "terminal")

                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                failures.extend(expect(final, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final_home"))
                reports["final"] = final
                captures["final_home"] = capture(
                    device, frames, "final-home")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                metrics_after = query(device, b"metrics", "leshy.boot.v1",
                                      "ready")
                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                if recovery_after.get("generation") != \
                        recovery_before.get("generation") or \
                        recovery_after.get("observations") != \
                        recovery_before.get("observations") or \
                        recovery_after.get("physical_write_calls") != 0:
                    failures.append(
                        "no-signal workflow changed product storage continuity")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap_free changed across infrared workflow")
                if input_state.get("queue_drops") != 0 or \
                        input_state.get("read_errors") != 0:
                    failures.append("input path reported errors or drops")
                if safe_outputs.get("buzzer_inactive") is not True or \
                        safe_outputs.get("nrf_ce_inactive") is not True:
                    failures.append("safe-output invariant failed")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup = best_effort_cleanup(device)
                if not cleanup.get("complete"):
                    failures.append("cleanup: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": False,
        "checkpoint": "physical_receive_no_signal",
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "exact_flash_reused": args.reuse_exact_flash,
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "metrics_after": metrics_after,
        "reports": reports,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "cleanup": cleanup,
        "captures": captures,
        "trace": trace,
        "limits": {
            "physical_known_transmitter_used": False,
            "successful_physical_signal_required": False,
            "physical_persistence_exercised": False,
            "host_nec_codec_store_csv_tests": True,
            "raw_ir_payload_retained": False,
            "ir_tx_or_replay_in_product_scope": False,
            "second_board_fixture_connected": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "terminal_state": reports.get("terminal", {}).get("state"),
        "failures": failures, "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
