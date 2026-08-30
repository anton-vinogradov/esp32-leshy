#!/usr/bin/env python3
"""Verify the stock-board Serial Console boundary without touching muxed pins."""

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
    valid_cid,
)


RUN_SCHEMA = "leshy.serial_console_delta_hil.run.v1"
ACTION_SCHEMA = "leshy.actions.serial_console.v1"
ACTION_ID = "serial.console.start"
ACTION_CONFIG = (
    "profile=mux56-3v3 target=owned-fixture baud=115200 "
    "framing=8N1 mode=monitor duration_ms=60000"
)


def read_only_query(device: PassiveSerial, command: bytes, schema: str,
                    kind: str, timeout: float = 5.0) -> dict[str, Any]:
    """Retry observations only; commands that can mutate state are not replayed."""
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            result = query(device, command, schema, kind, timeout=timeout)
            result["host_transport_attempts"] = attempt
            result["host_transport_transient_retries"] = attempt - 1
            result["host_transport_transient_errors"] = errors
            return result
        except TimeoutError as error:
            if attempt == 2:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable query retry")


def stock_rejection_failures(record: dict[str, Any], kind: str,
                             label: str) -> list[str]:
    failures = expect(record, {
        "kind": kind,
        "parse": "parsed",
        "preflight": "mux_conflict",
        "action_status": "capability_unavailable",
        "active": False,
        "action": "none",
        "profile": "mux56-3v3",
        "mode": "monitor",
        "baud": 115200,
        "framing": "8N1",
        "duration_ms": 60000,
        "rx_bytes": 0,
        "tx_bytes": 0,
        "dropped_bytes": 0,
        "buffered_bytes": 0,
        "buffer_high_water": 0,
        "resources": 0,
        "cleanup_complete": True,
        "pins_touched": False,
    }, label)
    return failures


def inactive_failures(record: dict[str, Any], kind: str,
                      label: str) -> list[str]:
    return expect(record, {
        "kind": kind,
        "parse": "parsed",
        "action_status": "ready",
        "active": False,
        "action": "none",
        "rx_bytes": 0,
        "tx_bytes": 0,
        "dropped_bytes": 0,
        "buffered_bytes": 0,
        "buffer_high_water": 0,
        "resources": 0,
        "cleanup_complete": True,
        "pins_touched": False,
    }, label)


def normalize_device(device: PassiveSerial,
                     trace: list[dict[str, Any]]) -> dict[str, Any]:
    current = read_only_query(
        device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(16):
        if current.get("page") == "home":
            break
        current = action(device, "left")
        trace.append(current)
    if current.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {current}")
    for _ in range(16):
        if current.get("selected_id") == "device":
            break
        current = action(device, "down")
        trace.append(current)
    if current.get("selected_id") != "device":
        raise RuntimeError(f"Device row not reachable: {current}")
    current = action(device, "right")
    trace.append(current)
    if current.get("page") != "device":
        raise RuntimeError(f"Device menu did not open: {current}")
    return current


def open_serial_console(device: PassiveSerial,
                        trace: list[dict[str, Any]]) -> dict[str, Any]:
    current = normalize_device(device, trace)
    while int(current.get("device_selection", -1)) > 3:
        current = action(device, "up")
        trace.append(current)
    while int(current.get("device_selection", -1)) < 3:
        current = action(device, "down")
        trace.append(current)
    if int(current.get("device_selection", -1)) != 3:
        raise RuntimeError(f"Serial Console row not reachable: {current}")
    current = action(device, "right")
    trace.append(current)
    if current.get("page") != "serial_console":
        raise RuntimeError(f"Serial Console page did not open: {current}")
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing application image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    retained_runner = args.output / Path(__file__).name
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.firmware.parent / "firmware.elf", retained_elf)
    shutil.copyfile(args.firmware.parent / "firmware.map", retained_map)
    shutil.copyfile(Path(__file__), retained_runner)

    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    reports: dict[str, Any] = {}
    screens: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    hil_begun = False
    hil_ended: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.6)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            try:
                synchronize_console(device, 45.0)
                metrics_before = read_only_query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                recovery_before = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                reports["metrics_before"] = metrics_before
                reports["recovery_before"] = recovery_before
                failures.extend(boot_failures(
                    metrics_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("candidate boot contract failed")

                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                reports["hil_begun"] = query(
                    device,
                    f"hil.begin {run_id} {app_identity}".encode("ascii"),
                    "leshy.hil.session.v1", "begun")
                hil_begun = True

                reports["safe_before"] = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                failures.extend(expect(reports["safe_before"], {
                    "buzzer_inactive": True,
                    "buzzer_level": "low",
                }, "safe_before"))

                preview_command = (
                    f"action.preview {ACTION_ID} {ACTION_CONFIG}")
                reports["preview"] = query(
                    device, preview_command.encode("ascii"), ACTION_SCHEMA,
                    "preview")
                failures.extend(stock_rejection_failures(
                    reports["preview"], "preview", "preview"))

                run_command = (
                    f"action.run {ACTION_ID} {ACTION_CONFIG} confirm=yes")
                reports["run"] = query(
                    device, run_command.encode("ascii"), ACTION_SCHEMA,
                    "run")
                failures.extend(stock_rejection_failures(
                    reports["run"], "run", "run"))

                reports["status_after_run"] = read_only_query(
                    device, f"action.status {ACTION_ID}".encode("ascii"),
                    ACTION_SCHEMA, "status")
                failures.extend(inactive_failures(
                    reports["status_after_run"], "status",
                    "status_after_run"))

                reports["invalid_raw_gpio"] = query(
                    device,
                    (f"action.run {ACTION_ID} {ACTION_CONFIG} "
                     "rx_pin=5 confirm=yes").encode("ascii"),
                    ACTION_SCHEMA, "error")
                failures.extend(expect(reports["invalid_raw_gpio"], {
                    "kind": "error",
                    "parse": "unknown_field",
                    "preflight": "not_evaluated",
                    "action_status": "invalid_descriptor",
                    "active": False,
                    "resources": 0,
                    "cleanup_complete": True,
                    "pins_touched": False,
                }, "invalid_raw_gpio"))

                page = open_serial_console(device, trace)
                failures.extend(expect(page, {
                    "page": "serial_console",
                    "runtime_owner": "none",
                    "lease_mask": 0,
                    "render_mode": "full",
                }, "serial_console_page"))
                screens["stock_conflict"] = capture(
                    device, frames, "stock-conflict")

                unchanged = action(device, "right")
                trace.append(unchanged)
                failures.extend(expect(unchanged, {
                    "page": "serial_console",
                    "changed": False,
                    "runtime_owner": "none",
                    "lease_mask": 0,
                }, "stock_ui_rejected"))

                reports["cancel"] = query(
                    device, f"action.cancel {ACTION_ID}".encode("ascii"),
                    ACTION_SCHEMA, "cancel")
                failures.extend(inactive_failures(
                    reports["cancel"], "cancel", "cancel"))

                reports["safe_after"] = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                failures.extend(expect(reports["safe_after"], {
                    "buzzer_inactive": True,
                    "buzzer_level": "low",
                }, "safe_after"))
                for field in ("buzzer_inactive", "buzzer_level"):
                    if (reports["safe_before"].get(field) !=
                            reports["safe_after"].get(field)):
                        failures.append(f"safe output {field} changed")

                reports["metrics_after"] = read_only_query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                if (reports["metrics_after"].get("heap_free") !=
                        metrics_before.get("heap_free")):
                    failures.append(
                        "heap_free changed across rejected Serial Console path: "
                        f"{metrics_before.get('heap_free')!r}->"
                        f"{reports['metrics_after'].get('heap_free')!r}")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
                if hil_begun:
                    try:
                        hil_ended = query(
                            device, f"hil.end {run_id}".encode("ascii"),
                            "leshy.hil.session.v1", "ended")
                    except Exception as error:
                        failures.append(
                            f"hil_end: {type(error).__name__}: {error}")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": bool(args.flash or args.reuse_exact_flash) and
            not failures,
        "failures": failures,
        "board": "board-01",
        "expected_cid": args.expected_cid,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "app_elf_sha256": app_identity,
            "elf_sha256": sha256_file(retained_elf),
            "map_sha256": sha256_file(retained_map),
            "runner_sha256": sha256_file(retained_runner),
            "flashed": bool(args.flash or args.reuse_exact_flash),
            "flash_mode": "fresh" if args.flash else "exact_reuse",
        },
        "reports": reports,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "hil_ended": hil_ended,
        "scope": {
            "stock_profile_negative_only": True,
            "external_uart_fixture": False,
            "uart_configure_calls_expected": 0,
            "uart_start_calls_expected": 0,
            "manual_button_presses": 0,
            "screenshots": len(screens),
            "radio_connect_calls": 0,
            "application_raw_tx_calls": 0,
            "host_wifi_control_calls": 0,
            "clone_touched": False,
            "cardputer_touched": False,
            "terminal_zero_lease": cleanup_after.get("complete") is True,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
    }, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
