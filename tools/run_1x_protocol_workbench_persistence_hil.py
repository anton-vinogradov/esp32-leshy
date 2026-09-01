#!/usr/bin/env python3
"""Prove real IR Capture annotation/decode persistence across a cold boot."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_boot import reset_and_capture_reconnecting
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


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "leshy.protocol_workbench_persistence_hil.run.v1"
IR_SCHEMA = "leshy.capture.infrared_raw.v1"
WORKBENCH_SCHEMA = "leshy.protocol_workbench.state.v1"
UI_SCHEMA = "leshy.ui.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
RECOVERY_SCHEMA = "leshy.storage.product_boot_recovery.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_CLONE_PORT = "/dev/cu.usbmodem1101"


def require(record: dict[str, Any], expected: dict[str, Any],
            label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def wait_record(device: PassiveSerial, command: bytes, schema: str,
                predicate: Callable[[dict[str, Any]], bool], timeout: float,
                message: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, command, schema, "state")
        if predicate(last):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"{message}: {last!r}")


def workbench_state(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"protocol.workbench.state", WORKBENCH_SCHEMA,
                 "state")


def normalize_home(device: PassiveSerial) -> dict[str, Any]:
    current = query(device, b"ui.state", UI_SCHEMA, "state")
    for _ in range(20):
        if (current.get("page") == "home" and
                current.get("runtime_owner") == "none" and
                current.get("lease_mask") == 0):
            return current
        current = action(device, "left")
    raise RuntimeError(f"cannot reach clean Home: {current!r}")


def open_library_generation(device: PassiveSerial, generation: int,
                            trace: list[dict[str, Any]]) -> dict[str, Any]:
    select_home_app(device, "library", trace)
    current = action(device, "right")
    trace.append(current)
    require(current, {"page": "library", "library_view": "list"},
            "library list")
    for _ in range(8):
        previous = current
        current = action(device, "up")
        trace.append(current)
        if current.get("selection") == 0 or current == previous:
            break
    for _ in range(max(1, int(current.get("library_entries", 0)))):
        if int(current.get("library_generation", 0)) == generation:
            return current
        current = action(device, "down")
        trace.append(current)
    raise RuntimeError(
        f"Library generation {generation} is not selectable: {current!r}")


def open_workbench(device: PassiveSerial, generation: int,
                   trace: list[dict[str, Any]]) -> dict[str, Any]:
    selected = open_library_generation(device, generation, trace)
    require(selected, {"library_persistent": True,
                       "library_selected_kind": "session"},
            "persistent IR session")
    detail = action(device, "right")
    trace.append(detail)
    require(detail, {"page": "library", "library_view": "detail",
                     "library_generation": generation}, "IR detail")
    actions = action(device, "right")
    trace.append(actions)
    require(actions, {"page": "library", "library_view": "actions",
                      "library_generation": generation}, "IR actions")
    opened = action(device, "right")
    trace.append(opened)
    require(opened, {"page": "protocol_workbench"}, "Analyze action")
    return workbench_state(device)


def annotate_and_decode(device: PassiveSerial,
                        trace: list[dict[str, Any]]) -> tuple[
                            dict[str, Any], dict[str, Any]]:
    def press(name: str) -> dict[str, Any]:
        value = action(device, name)
        trace.append(value)
        return workbench_state(device)

    require(press("right"), {"task_view": "waveform",
                             "selected_pulse": 0}, "view signal")
    press("down")
    require(press("down"), {"task_view": "waveform",
                            "selected_pulse": 2}, "pulse 2")
    require(press("right"), {"task_view": "explain",
                             "task_selection": 0}, "explain tasks")
    require(press("right"), {"task_view": "annotate",
                             "annotation_view": 0}, "mark parts")
    require(press("right"), {"annotation_view": 1,
                             "annotations": 0}, "annotation actions")
    require(press("right"), {"annotation_view": 2,
                             "selected_pulse": 2}, "range start")
    require(press("right"), {"annotation_view": 3,
                             "selected_pulse": 2}, "range end")
    require(press("down"), {"annotation_view": 3,
                            "selected_pulse": 3}, "range end pulse 3")
    require(press("right"), {"annotation_view": 4,
                             "annotation_kind": 0}, "meaning")
    require(press("down"), {"annotation_view": 4,
                            "annotation_kind": 1}, "Address meaning")
    require(press("right"), {"annotation_view": 5, "annotations": 1,
                             "annotation_dirty": True}, "marked result")
    require(press("right"), {"annotation_view": 0, "annotations": 1,
                             "annotation_dirty": True}, "marked waveform")
    require(press("right"), {"annotation_view": 1,
                             "annotation_action": 0}, "save actions")
    press("down")
    require(press("down"), {"annotation_view": 1,
                            "annotation_action": 2}, "Save selection")
    saved = press("right")
    require(saved, {"annotation_view": 5, "annotations": 1,
                    "annotation_dirty": False,
                    "annotation_status": "saved"}, "saved marks")
    if int(saved.get("annotation_store_generation", 0)) <= 0:
        raise RuntimeError("annotation store generation is missing")

    require(press("right"), {"annotation_view": 0}, "saved waveform")
    require(press("left"), {"task_view": "explain",
                            "task_selection": 0}, "decode parent")
    require(press("down"), {"task_view": "explain",
                            "task_selection": 1}, "Read marked parts")
    decoded = press("right")
    require(decoded, {"task_view": "decode", "decode_valid": True,
                      "decode_outcome": "complete", "decode_fields": 1,
                      "decode_status": "saved",
                      "raw_capture_mutated": False}, "saved decode")
    if int(decoded.get("decode_store_generation", 0)) <= 0:
        raise RuntimeError("decode store generation is missing")
    return saved, decoded


def validate_args(parser: argparse.ArgumentParser,
                  args: argparse.Namespace) -> None:
    if args.port == FORBIDDEN_CLONE_PORT or args.port != BOARD_PORT:
        parser.error(f"runner is bound to original board-01 at {BOARD_PORT}")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")
    if args.signal_window < 8.0 or args.signal_window > 30.0:
        parser.error("--signal-window must be between 8 and 30 seconds")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")


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
    parser.add_argument("--signal-window", type=float, default=11.0)
    args = parser.parse_args()
    validate_args(parser, args)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    output = args.output.resolve()
    frames = output / "frames"
    frames.mkdir(parents=True)
    candidate = output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    for name in ("firmware.elf", "firmware.map"):
        shutil.copyfile(args.firmware.parent / name, output / name)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    checker = ROOT / "tools/check_protocol_workbench_persistence_hil_run.py"
    shutil.copyfile(checker, output / checker.name)

    app_sha = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    saved_generation = 0
    source_fingerprint = ""
    annotation_generation = 0
    decode_generation = 0
    cleanup: dict[str, Any] = {"complete": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.8)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 35.0)
            records["metrics_before"] = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            records["recovery_before"] = query(
                device, b"storage.product.boot-recovery", RECOVERY_SCHEMA,
                "state")
            failures.extend(boot_failures(
                records["metrics_before"], records["recovery_before"],
                args.expected_version, app_sha, args.expected_cid))
            cleanup = best_effort_cleanup(device)
            if failures or not cleanup.get("complete"):
                raise RuntimeError("preflight did not reach exact clean Home")
            sessions.append(query(
                device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
                HIL_SCHEMA, "begun"))

            select_home_app(device, "capture", trace)
            trace.append(action(device, "right"))
            trace.append(action(device, "down"))
            trace.append(action(device, "right"))
            records["ir_idle"] = query(
                device, b"capture.ir.state", IR_SCHEMA, "state")
            require(records["ir_idle"], {
                "state": "idle", "passive_only": True, "rx_only": True,
                "application_tx_calls": 0, "storage_written": False,
                "persist_state": "volatile", "cleanup_complete": True,
            }, "IR idle")
            trace.append(action(device, "right"))
            records["ir_waiting"] = query(
                device, b"capture.ir.state", IR_SCHEMA, "state")
            require(records["ir_waiting"], {
                "state": "waiting", "passive_only": True,
                "rx_only": True, "application_tx_calls": 0,
                "storage_written": False,
            }, "IR waiting")
            print("IR_SIGNAL_WINDOW_OPEN press_one_remote_button_now", flush=True)
            time.sleep(args.signal_window)
            records["ir_complete"] = query(
                device, b"capture.ir.state", IR_SCHEMA, "state")
            require(records["ir_complete"], {
                "state": "complete", "passive_only": True,
                "rx_only": True, "application_tx_calls": 0,
                "cleanup_complete": True, "storage_written": False,
            }, "real IR Capture")
            if int(records["ir_complete"].get("pulses", 0)) < 4:
                raise RuntimeError("captured IR signal has too few pulses")
            captures["ir_complete"] = capture(
                device, frames, "ir-capture-complete")
            trace.append(action(device, "right"))
            records["ir_saved"] = wait_record(
                device, b"capture.ir.state", IR_SCHEMA,
                lambda value: value.get("persist_state") in ("saved", "failed"),
                35.0, "IR persistence did not terminate")
            require(records["ir_saved"], {
                "state": "complete", "persist_state": "saved",
                "persist_status": "saved", "storage_written": True,
                "application_tx_calls": 0, "cleanup_complete": True,
            }, "saved IR Capture")
            saved_generation = int(
                records["ir_saved"].get("persist_generation", 0))
            if saved_generation <= int(
                    records["recovery_before"].get("generation", 0)):
                raise RuntimeError("IR generation did not advance")
            captures["ir_saved"] = capture(device, frames, "ir-capture-saved")
            normalize_home(device)

            records["workbench_open"] = open_workbench(
                device, saved_generation, trace)
            require(records["workbench_open"], {
                "status": "active", "active": True,
                "source_kind": "immutable_capture",
                "capture_generation": saved_generation,
                "task_view": "tasks", "task_selection": 0,
                "annotations": 0, "annotation_dirty": False,
                "annotation_status": "empty", "decode_valid": False,
                "decode_status": "no_marks", "read_only_analysis": True,
                "raw_capture_mutated": False, "radio_touched": False,
                "application_tx_calls": 0, "storage_open_now": False,
                "lease_mask": 0, "cleanup_complete": True,
            }, "fresh immutable workbench")
            source_fingerprint = str(
                records["workbench_open"].get("source_fingerprint", ""))
            if len(source_fingerprint) != 16:
                raise RuntimeError("source fingerprint is invalid")
            captures["workbench_open"] = capture(
                device, frames, "workbench-real-capture")
            saved, decoded = annotate_and_decode(device, trace)
            records["annotations_saved"] = saved
            records["decode_saved"] = decoded
            annotation_generation = int(
                saved.get("annotation_store_generation", 0))
            decode_generation = int(decoded.get("decode_store_generation", 0))
            if (saved.get("source_fingerprint") != source_fingerprint or
                    decoded.get("source_fingerprint") != source_fingerprint or
                    int(decoded.get("capture_generation", 0)) != saved_generation):
                raise RuntimeError("raw Capture identity changed during derivation")
            captures["decode_saved"] = capture(
                device, frames, "workbench-decode-saved")
            normalize_home(device)
            sessions.append(query(
                device, f"hil.end {run_id}".encode("ascii"),
                HIL_SCHEMA, "ended"))
            records["cleanup_before_reset"] = best_effort_cleanup(device)
            if not records["cleanup_before_reset"].get("complete"):
                raise RuntimeError("pre-reset cleanup incomplete")

        boot_raw, ready_ms, disconnects, attempts = \
            reset_and_capture_reconnecting(args.port, 35.0)
        (output / "cold-boot.ndjson").write_bytes(boot_raw)
        records["cold_reset"] = {
            "bytes": len(boot_raw),
            "sha256": hashlib.sha256(boot_raw).hexdigest(),
            "ready_marker_ms": ready_ms,
            "usb_disconnects": disconnects,
            "usb_open_attempts": attempts,
        }
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 25.0)
            records["metrics_after"] = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            records["recovery_after"] = query(
                device, b"storage.product.boot-recovery", RECOVERY_SCHEMA,
                "state")
            failures.extend(boot_failures(
                records["metrics_after"], records["recovery_after"],
                args.expected_version, app_sha, args.expected_cid))
            require(records["recovery_after"], {
                "generation": saved_generation, "mounted_read_only": True,
                "read_only_guaranteed": True, "physical_write_calls": 0,
                "cleanup_complete": True,
            }, "cold product recovery")
            records["workbench_reopened"] = open_workbench(
                device, saved_generation, trace)
            require(records["workbench_reopened"], {
                "status": "active", "active": True,
                "source_kind": "immutable_capture",
                "capture_generation": saved_generation,
                "source_fingerprint": source_fingerprint,
                "annotations": 1, "annotation_dirty": False,
                "annotation_store_generation": annotation_generation,
                "annotation_status": "recovered", "decode_valid": True,
                "decode_outcome": "complete", "decode_fields": 1,
                "decode_store_generation": decode_generation,
                "decode_status": "recovered", "read_only_analysis": True,
                "raw_capture_mutated": False, "radio_touched": False,
                "application_tx_calls": 0, "storage_open_now": False,
                "lease_mask": 0, "cleanup_complete": True,
            }, "cold workbench reopen")
            captures["workbench_reopened"] = capture(
                device, frames, "workbench-cold-reopened")
            normalize_home(device)
            records["safe_outputs"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            require(records["safe_outputs"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
            }, "safe outputs")
            records["final_ui"] = query(
                device, b"ui.state", UI_SCHEMA, "state")
            require(records["final_ui"], {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            }, "final Home")
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("final cleanup incomplete")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "status": "pass" if not failures else "failed",
        "passed": bool(args.flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "board": "board-01",
        "exact_port": args.port,
        "expected_cid": args.expected_cid,
        "run_id": run_id,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "app_elf_sha256": app_sha,
            "fresh_flash": args.flash,
            "reuse_exact_flash": args.reuse_exact_flash,
        },
        "proof": {
            "real_physical_ir_capture": records.get("ir_complete", {}).get(
                "state") == "complete",
            "capture_generation": saved_generation,
            "source_fingerprint": source_fingerprint,
            "annotation_store_generation": annotation_generation,
            "decode_store_generation": decode_generation,
            "cold_reopen": records.get("workbench_reopened", {}).get(
                "decode_status") == "recovered",
            "raw_capture_mutated": False,
        },
        "policy": {
            "mac_wifi_controlled": False,
            "clone_port_touched": False,
            "cardputer_touched": False,
            "radio_tx_commands": 0,
            "ir_transmit_commands": 0,
            "manual_action": "one_owned_remote_button_press",
            "protected_writes": ["ir_capture", "annotations", "decode"],
            "cold_recovery_read_only": True,
        },
        "hil_sessions": sessions,
        "records": records,
        "captures": captures,
        "trace": trace,
        "cleanup": cleanup,
    }
    write_json(output / "run.json", result)
    artifact_manifest(output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "failures": failures, "run": str(output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
