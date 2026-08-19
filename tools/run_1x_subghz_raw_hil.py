#!/usr/bin/env python3
"""Exercise the first 1.x Sub-GHz RAW receive-only user slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
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


RUN_SCHEMA = "leshy.subghz_raw_hil.run.v1"
STATE_SCHEMA = "leshy.capture.subghz_raw.v1"
CSV_SCHEMA = "leshy.capture.subghz_raw.csv.v1"
TERMINAL_STATES = {"complete", "timed_out", "signal_too_long", "failed"}


def select_home_app(device: Any, app_id: str,
                    trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(10):
        if state.get("selection") == 0:
            break
        state = action(device, "up")
        trace.append(state)
    for _ in range(10):
        if state.get("selected_id") == app_id:
            return state
        state = action(device, "down")
        trace.append(state)
    raise RuntimeError(f"Home app {app_id!r} is not reachable: {state!r}")


def wait_terminal(device: Any, timeout: float = 18.0) -> dict[str, Any]:
    # Do not poll while pulse timing may be active. The firmware also defers
    # console commands during a burst, but a quiet host is stronger evidence.
    time.sleep(timeout)
    last = query(device, b"capture.subghz.state", STATE_SCHEMA, "state")
    if last.get("state") in TERMINAL_STATES:
        return last
    raise TimeoutError(f"Sub-GHz RAW capture did not terminate: {last!r}")


def read_live_csv(device: Any, pulses: int,
                  timeout: float = 10.0) -> tuple[dict[str, Any], dict[str, Any]]:
    device.reset_input_buffer()
    device.write(b"capture.subghz.export.csv\n")
    device.flush()
    begin = read_json(device, CSV_SCHEMA, "csv_begin", timeout=timeout)
    digest = hashlib.sha256()
    bytes_read = 0
    records = 0
    expected_header = b"pulse_index,level,duration_us\r\n"
    for index in range(pulses + 1):
        line = device.readline()
        if not line:
            raise TimeoutError("Sub-GHz RAW CSV line timed out")
        digest.update(line)
        bytes_read += len(line)
        if index == 0:
            if line != expected_header:
                raise ValueError(f"unexpected RAW CSV header: {line!r}")
            continue
        columns = line.decode("ascii").strip().split(",")
        if len(columns) != 3 or int(columns[0]) != index - 1 or \
                int(columns[1]) not in (0, 1) or not 1 <= int(columns[2]) <= 65535:
            raise ValueError(f"invalid RAW CSV row {index}: {line!r}")
        records += 1
    end = read_json(device, CSV_SCHEMA, "csv_end", timeout=timeout)
    return begin, {
        "end": end,
        "records": records,
        "bytes": bytes_read,
        "sha256": digest.hexdigest(),
        "raw_payload_retained": False,
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
    if args.flash and args.reuse_exact_flash:
        parser.error("--flash and --reuse-exact-flash are mutually exclusive")
    if not args.flash and not args.reuse_exact_flash:
        parser.error("use --flash or explicitly acknowledge --reuse-exact-flash")

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
    csv: dict[str, Any] = {"available": False,
                           "raw_payload_retained": False}

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

                home = select_home_app(device, "subghz", trace)
                failures.extend(expect(home, {
                    "page": "home", "selected_id": "subghz",
                    "selected_enabled": True, "runtime_owner": "none",
                    "lease_mask": 0,
                }, "home_subghz"))
                captures["home"] = capture(device, frames, "home")

                trace.append(action(device, "right"))
                reports["mode_spectrum"] = query(
                    device, b"capture.subghz.state", STATE_SCHEMA, "state")
                captures["modes_spectrum"] = capture(
                    device, frames, "modes-spectrum")
                trace.append(action(device, "down"))
                captures["modes_raw"] = capture(device, frames, "modes-raw")
                trace.append(action(device, "right"))
                captures["bands"] = capture(device, frames, "bands")

                trace.append(action(device, "right"))
                waiting = query(
                    device, b"capture.subghz.state", STATE_SCHEMA, "state")
                reports["waiting"] = waiting
                failures.extend(expect(waiting, {
                    "state": "waiting", "passive_only": True,
                    "rx_only": True, "modulation": "ook_envelope",
                    "frequency_khz": 433920, "threshold_dbm": -72,
                    "wait_timeout_ms": 10000, "maximum_capture_ms": 5000,
                    "debounce_us": 60, "end_gap_us": 20000,
                    "maximum_pulses": 512, "application_tx_calls": 0,
                    "tx_strobes": 0, "pa_table_writes": 0,
                    "fifo_writes": 0, "cleanup_complete": False,
                    "storage_written": False, "persist_state": "volatile",
                }, "waiting"))
                if not isinstance(waiting.get("samples"), int):
                    failures.append("waiting: sample counter missing")
                captures["waiting"] = capture(device, frames, "waiting")

                terminal = wait_terminal(device)
                reports["terminal"] = terminal
                failures.extend(expect(terminal, {
                    "passive_only": True, "rx_only": True,
                    "modulation": "ook_envelope", "frequency_khz": 433920,
                    "application_tx_calls": 0, "tx_strobes": 0,
                    "pa_table_writes": 0, "fifo_writes": 0,
                    "physical_no_tx_verified": True,
                    "cleanup_complete": True, "storage_written": False,
                    "persist_state": "volatile",
                }, "terminal"))
                if terminal.get("state") == "failed":
                    failures.append(
                        f"receiver failed with driver error {terminal.get('driver_error')!r}")
                if not isinstance(terminal.get("samples"), int) or \
                        terminal.get("samples", 0) < 1:
                    failures.append("terminal: no physical RSSI samples")
                if terminal.get("state") == "complete":
                    pulses = terminal.get("pulses")
                    if not isinstance(pulses, int) or not 1 <= pulses <= 512:
                        failures.append(f"terminal: invalid pulse count {pulses!r}")
                    else:
                        begin, summary = read_live_csv(device, pulses)
                        csv = {"available": True, "begin": begin, **summary}
                        failures.extend(expect(begin, {
                            "pulses": pulses, "frequency_khz": 433920,
                            "modulation": "ook_envelope", "streaming": True,
                        }, "csv_begin"))
                        failures.extend(expect(summary.get("end", {}), {
                            "status": "valid", "pulses": pulses,
                            "bytes": summary.get("bytes"),
                        }, "csv_end"))
                elif terminal.get("state") == "timed_out":
                    if terminal.get("signal_started_us") != 0 or \
                            terminal.get("pulses") != 0 or \
                            terminal.get("csv_available") is not False:
                        failures.append("no-signal timeout invented a RAW artifact")
                captures["terminal"] = capture(device, frames, "terminal")

                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                failures.extend(expect(final, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final_home"))
                reports["final"] = final
                captures["final_home"] = capture(device, frames, "final-home")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                metrics_after = query(device, b"metrics", "leshy.boot.v1", "ready")
                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                if recovery_after.get("generation") != recovery_before.get("generation") or \
                        recovery_after.get("observations") != \
                        recovery_before.get("observations") or \
                        recovery_after.get("physical_write_calls") != 0:
                    failures.append("no-save workflow changed product storage continuity")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap_free changed across RAW workflow")
                if input_state.get("queue_drops") != 0 or \
                        input_state.get("read_errors") != 0:
                    failures.append("input path reported errors or drops")
                if safe_outputs.get("buzzer_inactive") is not True:
                    failures.append("buzzer-safe invariant failed")
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
        "checkpoint": "physical_receive_path",
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
        "csv": csv,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "cleanup": cleanup,
        "captures": captures,
        "trace": trace,
        "limits": {
            "physical_known_transmitter_used": False,
            "successful_physical_burst_required": False,
            "persistence_exercised": False,
            "host_codec_store_csv_tests": True,
            "raw_rf_payload_retained": False,
            "tx_or_replay_in_scope": False,
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
