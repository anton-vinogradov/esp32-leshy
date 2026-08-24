#!/usr/bin/env python3
"""Run one-flash Sub-GHz FSK delta plus adjacent OOK negative regression."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
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
)
from run_hil_scenario import select_home_app


RUN_SCHEMA = "leshy.subghz_fsk_delta_hil.run.v1"
STATE_SCHEMA = "leshy.capture.subghz_raw.v1"


def capture_named(device: PassiveSerial, frames: Path,
                  captures: dict[str, Any], name: str) -> None:
    captures[name] = capture(device, frames, name)


def navigate_to_capture(device: PassiveSerial, modulation: str,
                        trace: list[dict[str, Any]], frames: Path,
                        captures: dict[str, Any]) -> dict[str, Any]:
    trace.append(select_home_app(device, "subghz", trace))
    modes = action(device, "right")
    trace.append(modes)
    if modes.get("runtime_event") != "subghz_modes":
        raise RuntimeError(f"Sub-GHz menu not entered: {modes!r}")
    trace.append(action(device, "down"))
    trace.append(action(device, "down"))
    mode_menu = action(device, "right")
    trace.append(mode_menu)
    if mode_menu.get("runtime_event") != "subghz_raw_mode_menu":
        raise RuntimeError(f"signal type menu not entered: {mode_menu!r}")
    capture_named(device, frames, captures, f"{modulation}-type-ook")
    if modulation == "fsk_async":
        trace.append(action(device, "down"))
        capture_named(device, frames, captures, "fsk_async-type-selected")
    band_menu = action(device, "right")
    trace.append(band_menu)
    if band_menu.get("runtime_event") != "subghz_raw_band_menu":
        raise RuntimeError(f"band menu not entered: {band_menu!r}")
    capture_named(device, frames, captures, f"{modulation}-band-433")
    trace.append(action(device, "right"))
    waiting = query(device, b"capture.subghz.state", STATE_SCHEMA, "state")
    capture_named(device, frames, captures, f"{modulation}-waiting")
    return waiting


def wait_no_signal(device: PassiveSerial, timeout_s: float = 13.0) -> dict[str, Any]:
    # Stay completely silent while the edge timing path is armed or waiting.
    time.sleep(timeout_s)
    return query(device, b"capture.subghz.state", STATE_SCHEMA, "state")


def validate_receiver_accounting(report: dict[str, Any], label: str,
                                 failures: list[str]) -> None:
    writes = report.get("receiver_register_writes")
    commands = report.get("receiver_command_strobes")
    reset = report.get("receiver_reset_strobes")
    receive = report.get("receiver_receive_strobes")
    idle = report.get("receiver_idle_strobes")
    if not isinstance(writes, int) or writes < 1:
        failures.append(f"{label}: receiver register writes missing")
    if not all(isinstance(value, int) for value in
               (commands, reset, receive, idle)) or commands != reset + receive + idle:
        failures.append(f"{label}: receive-only command accounting mismatch")


def run_no_signal_scenario(device: PassiveSerial, modulation: str,
                           trace: list[dict[str, Any]], frames: Path,
                           captures: dict[str, Any],
                           failures: list[str]) -> dict[str, Any]:
    waiting = navigate_to_capture(
        device, modulation, trace, frames, captures)
    expected_waiting = {
        "state": "waiting", "passive_only": True, "rx_only": True,
        "modulation": modulation, "frequency_khz": 433920,
        "threshold_dbm": -72, "wait_timeout_ms": 10000,
        "maximum_capture_ms": 5000, "debounce_us": 60,
        "minimum_fsk_pulse_us": 4, "maximum_pulses": 512,
        "application_tx_calls": 0, "tx_strobes": 0,
        "pa_table_writes": 0, "fifo_writes": 0,
        "receiver_rejected_strobes": 0, "gdo0_gpio": 6,
        "fsk_transport_active": False, "fsk_transport_arms": 0,
        "fsk_edges_drained": 0, "fsk_transport_overflows": 0,
        "storage_written": False, "persist_state": "volatile",
    }
    failures.extend(expect(waiting, expected_waiting, f"{modulation}_waiting"))
    validate_receiver_accounting(waiting, f"{modulation}_waiting", failures)

    terminal = wait_no_signal(device)
    failures.extend(expect(terminal, {
        **expected_waiting,
        "state": "timed_out", "signal_started_us": 0, "pulses": 0,
        "csv_available": False, "physical_no_tx_verified": True,
        "cleanup_complete": True, "lease_mask": 9,
    }, f"{modulation}_terminal"))
    samples = terminal.get("samples")
    if not isinstance(samples, int) or samples < 1:
        failures.append(f"{modulation}_terminal: no physical RSSI samples")
    validate_receiver_accounting(terminal, f"{modulation}_terminal", failures)
    capture_named(device, frames, captures, f"{modulation}-no-signal")

    for _ in range(4):
        trace.append(action(device, "left"))
    home = query(device, b"ui.state", "leshy.ui.v1", "state")
    failures.extend(expect(home, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, f"{modulation}_home"))
    return {"waiting": waiting, "terminal": terminal, "home": home}


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
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one flash mode")
    if not args.firmware.is_file():
        parser.error(f"firmware missing: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        text=True, stdout=subprocess.PIPE).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    build = args.firmware.parent
    for source, name in (
        (args.firmware, "firmware.bin"),
        (build / "firmware.elf", "firmware.elf"),
        (build / "firmware.map", "firmware.map"),
        (Path(__file__), Path(__file__).name),
    ):
        shutil.copyfile(source, args.output / name)
    retained_firmware = args.output / "firmware.bin"
    app_sha = app_elf_sha256(retained_firmware)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, retained_firmware, 0x10000,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 45.0)
            records["ready"] = query(device, b"metrics", "leshy.boot.v1", "ready")
            records["recovery_before"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            failures.extend(boot_failures(
                records["ready"], records["recovery_before"],
                args.expected_version, app_sha, args.expected_cid))
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("initial cleanup did not reach Home/lease 0")
            records["hil_begin"] = query(
                device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
                "leshy.hil.session.v1", "begun")
            failures.extend(expect(records["hil_begin"], {
                "status": "begun", "session_id": run_id, "active": True,
                "app_elf_sha256": app_sha,
                "firmware_version": args.expected_version,
            }, "hil_begin"))

            records["fsk"] = run_no_signal_scenario(
                device, "fsk_async", trace, frames, captures, failures)
            records["ook"] = run_no_signal_scenario(
                device, "ook_envelope", trace, frames, captures, failures)
            records["recovery_after"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            before = records["recovery_before"]
            after = records["recovery_after"]
            for key in ("generation", "observations", "physical_write_calls"):
                if after.get(key) != before.get(key):
                    failures.append(f"storage continuity changed: {key}")
            records["metrics_after"] = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            if records["metrics_after"].get("heap_free") != \
                    records["ready"].get("heap_free"):
                failures.append("heap_free changed across delta")
            records["input"] = query(
                device, b"input.state", "leshy.input.frontend.v1", "state")
            failures.extend(expect(records["input"], {
                "queue_drops": 0, "read_errors": 0,
            }, "input"))
            records["outputs"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            failures.extend(expect(records["outputs"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
            }, "outputs"))
            capture_named(device, frames, captures, "home-final")
            records["hil_end"] = query(
                device, f"hil.end {run_id}".encode("ascii"),
                "leshy.hil.session.v1", "ended")
            failures.extend(expect(records["hil_end"], {
                "status": "ended", "session_id": run_id, "active": False,
                "app_elf_sha256": app_sha,
            }, "hil_end"))
    except Exception as error:
        failures.append(f"workflow: {type(error).__name__}: {error}")
    finally:
        try:
            with PassiveSerial(args.port, 115200, timeout=0.05) as device:
                synchronize_console(device, 10.0)
                cleanup = best_effort_cleanup(device)
                if records.get("hil_begin", {}).get("active") is True and \
                        records.get("hil_end", {}).get("active") is not False:
                    records["failure_hil_end"] = query(
                        device, f"hil.end {run_id}".encode("ascii"),
                        "leshy.hil.session.v1", "ended")
        except Exception as error:
            failures.append(f"cleanup: {type(error).__name__}: {error}")
    if not cleanup.get("complete"):
        failures.append("cleanup did not retain Home/none/lease 0")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": args.flash and not failures,
        "scope": "delta",
        "full_matrix_run": False,
        "failures": failures,
        "board": "board-01",
        "expected_cid": args.expected_cid,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(retained_firmware),
            "app_elf_sha256": app_sha,
            "flashed": args.flash,
            "exact_flash_reused": args.reuse_exact_flash,
        },
        "records": records,
        "captures": captures,
        "trace": trace,
        "cleanup": cleanup,
        "coverage": {
            "fsk_menu_and_no_signal_cleanup": True,
            "ook_adjacent_no_signal_cleanup": True,
            "physical_fsk_positive_source_used": False,
            "physical_fsk_edge_capture_proven": False,
            "tx_or_replay_in_scope": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "scope": "delta", "flashes": 1 if args.flash else 0,
        "failures": failures, "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
