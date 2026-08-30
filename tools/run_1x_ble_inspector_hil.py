#!/usr/bin/env python3
"""Focused physical delta gate for the passive BLE Inspector product path."""

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
from run_1x_ble_nearby_hil import home_ble, wait_live
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


RUN_SCHEMA = "leshy.ble_inspector_hil.run.v1"
EXPORT_SCHEMA = "leshy.ble.inspector.capture.v1"


def selected_identity_hash(address: str) -> int:
    raw = bytes.fromhex(address.replace(":", ""))
    if len(raw) != 6:
        raise ValueError("export target is not a six-byte BLE address")
    value = 2166136261
    for byte in raw:
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def preflight_exact_board(port: str, expected_cid: str) -> dict[str, Any]:
    """Identify existing Leshy state before any flash or reset operation."""
    with PassiveSerial(port, 115200, timeout=0.25) as device:
        synchronize_console(device, 15.0)
        recovery = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
    if recovery.get("cid") != expected_cid:
        raise RuntimeError(
            f"pre-flash CID mismatch: {recovery.get('cid')!r} != "
            f"{expected_cid!r}")
    return {
        "performed_before_application_flash": True,
        "cid": recovery.get("cid"),
        "generation": recovery.get("generation"),
        "port": port,
    }


def wait_inspector(device: PassiveSerial, minimum_records: int,
                   timeout: float = 75.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = query(
            device, b"ble.inspector.state",
            "leshy.ble.inspector.state.v1", "state")
        if (latest.get("view") == "inspector_raw" and
                latest.get("capture_state") in ("running", "frozen") and
                int(latest.get("records", 0)) >= minimum_records):
            return latest
        time.sleep(0.1)
    raise TimeoutError(
        f"selected BLE device produced fewer than {minimum_records} raw "
        f"records: {latest!r}")


def read_export(device: PassiveSerial) -> tuple[dict[str, Any],
                                                 list[dict[str, Any]],
                                                 dict[str, Any], str]:
    device.reset_input_buffer()
    device.write(b"ble.inspector.export.raw\n")
    device.flush()
    header = read_json(device, EXPORT_SCHEMA, "header", timeout=5.0)
    count = int(header.get("records", -1))
    if not 0 <= count <= 32:
        raise RuntimeError(f"invalid export record count: {count}")
    records = [
        read_json(device, EXPORT_SCHEMA, "record", timeout=5.0)
        for _ in range(count)
    ]
    end = read_json(device, EXPORT_SCHEMA, "end", timeout=5.0)
    canonical = "\n".join(
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        for value in [header, *records, end]
    ) + "\n"
    return header, records, end, hashlib.sha256(
        canonical.encode("utf-8")).hexdigest()


def validate_export(header: dict[str, Any], records: list[dict[str, Any]],
                    end: dict[str, Any], expected_hash: int) -> list[str]:
    failures: list[str] = []
    count = len(records)
    if header.get("complete") is not False or header.get("version") != 1:
        failures.append("export header does not declare incomplete version 1")
    if int(header.get("records", -1)) != count or \
            int(end.get("records", -1)) != count or \
            end.get("complete") is not True:
        failures.append("export header/record/end accounting mismatch")
    try:
        if selected_identity_hash(str(header.get("target", ""))) != \
                expected_hash:
            failures.append("export target differs from selected detail")
    except ValueError as error:
        failures.append(str(error))
    previous_us = int(header.get("selected_monotonic_us", 0))
    nonempty = 0
    for index, record in enumerate(records):
        payload = str(record.get("payload_hex", ""))
        payload_length = int(record.get("payload_length", -1))
        monotonic_us = int(record.get("monotonic_us", 0))
        if record.get("index") != index:
            failures.append(f"record {index} has wrong index")
        if payload_length < 0 or payload_length > 31 or \
                len(payload) != payload_length * 2:
            failures.append(f"record {index} payload bounds mismatch")
        try:
            bytes.fromhex(payload)
        except ValueError:
            failures.append(f"record {index} payload is not hexadecimal")
        if monotonic_us < previous_us:
            failures.append(f"record {index} timestamp moved backwards")
        previous_us = monotonic_us
        nonempty += payload_length > 0
    if count == 0 or nonempty == 0:
        failures.append("export contains no non-empty selected packet")
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
    if not args.flash:
        parser.error("focused gate requires --flash")

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
    preflight: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    running_first: dict[str, Any] = {}
    running_second: dict[str, Any] = {}
    frozen: dict[str, Any] = {}
    export_summary: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}

    try:
        preflight = preflight_exact_board(args.port, args.expected_cid)
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, _ = stabilized_boot_metrics(device)
                recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")
                home_ble(device)
                trace.append(action(device, "right"))
                live = wait_live(device)
                trace.append(live)
                detail_ui = action(device, "right")
                trace.append(detail_ui)
                detail = query(
                    device, b"ble.device.detail",
                    "leshy.ble.device_detail.v1", "state")
                failures.extend(expect(detail, {
                    "active": True, "passive": True,
                    "active_probe_allowed": False,
                }, "selected_detail"))
                inspector_ui = action(device, "right")
                trace.append(inspector_ui)
                if inspector_ui.get("ble_product_view") != "inspector_raw":
                    raise RuntimeError(
                        f"Inspector view did not open: {inspector_ui!r}")
                running_first = wait_inspector(device, 1)
                screens["running_first"] = capture(
                    device, frames, "ble-inspector-running-first")
                first_records = int(running_first["records"])
                if (running_first.get("capture_state") == "running" and
                        first_records < 32):
                    running_second = wait_inspector(
                        device, first_records + 1)
                else:
                    running_second = running_first
                screens["running_second"] = capture(
                    device, frames, "ble-inspector-running-second")
                if running_second.get("selected_identity_hash") != \
                        detail.get("identity_hash"):
                    raise RuntimeError("raw capture target moved from detail")
                if int(running_second.get("records", 0)) > first_records:
                    rows_advanced = (
                        int(running_second.get("atomic_row_pushes", 0)) >
                        int(running_first.get("atomic_row_pushes", -1)))
                else:
                    rows_advanced = int(
                        running_second.get("atomic_row_pushes", 0)) > 0
                if int(running_second.get("content_clears", -1)) != 1 or \
                        not rows_advanced:
                    raise RuntimeError(
                        "live raw capture did not use incremental row updates")
                if running_second.get("capture_state") == "running":
                    trace.append(action(device, "right"))
                frozen = query(
                    device, b"ble.inspector.state",
                    "leshy.ble.inspector.state.v1", "state")
                failures.extend(expect(frozen, {
                    "view": "inspector_raw", "capture_state": "frozen",
                    "passive": True, "receive_only": True,
                    "export_ready": True, "gatt_started": False,
                    "invalid": 0, "dropped": 0, "content_clears": 1,
                    "atomic_row_allocation_failures": 0,
                    "direct_row_fallbacks": 0,
                }, "frozen_capture"))
                screens["frozen"] = capture(
                    device, frames, "ble-inspector-frozen")
                header, records, end, export_sha = read_export(device)
                failures.extend(validate_export(
                    header, records, end,
                    int(detail.get("identity_hash", -1))))
                export_summary = {
                    "schema": header.get("schema"),
                    "records": len(records),
                    "payload_bytes": sum(int(record.get(
                        "payload_length", 0)) for record in records),
                    "stream_sha256": export_sha,
                    "raw_identifiers_retained_by_runner": False,
                    "raw_payload_retained_by_runner": False,
                }
                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                home = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("page") == "home" and
                        state.get("runtime_owner") == "none" and
                        state.get("lease_mask") == 0 and
                        state.get("survey_product_cleanup_complete") is True
                    ), 30.0, "BLE Inspector did not clean up to Home")
                trace.append(home)
                screens["home_after"] = capture(
                    device, frames, "ble-inspector-home-after")
                input_state = query(
                    device, b"input.state",
                    "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup = best_effort_cleanup(device)
                if not cleanup.get("complete"):
                    failures.append("cleanup: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": not failures,
        "gate_eligible": not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flash_mode": "fresh",
        },
        "expected_cid": args.expected_cid,
        "preflight": preflight,
        "boot": boot,
        "recovery": recovery,
        "detail": detail,
        "running_first": running_first,
        "running_second": running_second,
        "frozen": frozen,
        "export": export_summary,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "trace": trace,
        "screens": screens,
        "cleanup": cleanup,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "passive_ble_only": True,
            "selected_target_only": True,
            "incremental_rows_only": True,
            "raw_export_checked_in_memory": True,
            "raw_private_evidence_retained": False,
            "mac_wifi_touched": False,
            "clone_touched": False,
            "cardputer_touched": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "records": export_summary.get("records", 0),
        "screens": sorted(screens),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
