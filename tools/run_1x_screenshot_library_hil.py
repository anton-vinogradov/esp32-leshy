#!/usr/bin/env python3
"""Capture, protect, export, and cold-recover one exact TFT screenshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import (
    PassiveSerial,
    read_exact,
    read_json,
    rgb565be_to_png,
    synchronize_console,
)
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    artifact_manifest,
    best_effort_cleanup,
    boot_ready_failures,
    expect,
    query,
    reset_capture,
    valid_cid,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "leshy.screenshot_library_hil.run.v1"
UI_SCHEMA = "leshy.ui.v1"
LOCK_SCHEMA = "leshy.device_lock.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
RECOVERY_SCHEMA = "leshy.storage.product_boot_recovery.v1"
EXPORT_SCHEMA = "leshy.screenshot.export.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_CLONE_PORT = "/dev/cu.usbmodem1101"
FRAME_BYTES = 240 * 320 * 2


def crc32c(payload: bytes) -> int:
    value = 0xFFFFFFFF
    for byte in payload:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
    return value ^ 0xFFFFFFFF


def read_only(device: PassiveSerial, command: bytes, schema: str,
              kind: str, timeout: float = 8.0) -> dict[str, Any]:
    return query(device, command, schema, kind, timeout=timeout)


def action(device: PassiveSerial, name: str,
           timeout: float = 60.0) -> dict[str, Any]:
    device.write(f"ui.key {name}\n".encode("ascii"))
    device.flush()
    return read_json(device, UI_SCHEMA, "state", timeout=timeout)


def require(record: dict[str, Any], expected: dict[str, Any],
            label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def normalize_home(device: PassiveSerial) -> dict[str, Any]:
    current = read_only(device, b"ui.state", UI_SCHEMA, "state")
    for _ in range(16):
        if (current.get("page") == "home" and
                current.get("runtime_owner") == "none" and
                current.get("lease_mask") == 0):
            return current
        current = action(device, "left")
    raise RuntimeError(f"cannot reach clean Home: {current!r}")


def focus_home(device: PassiveSerial, item_id: str,
               index: int) -> dict[str, Any]:
    current = normalize_home(device)
    for _ in range(12):
        if current.get("selection") == index:
            break
        direction = "down" if int(current.get("selection", -1)) < index else "up"
        current = action(device, direction)
    require(current, {
        "page": "home", "selection": index, "selected_id": item_id,
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, f"focus {item_id}")
    return current


def capture_reference(device: PassiveSerial, output: Path) -> dict[str, Any]:
    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    frame = read_exact(device, int(begin.get("bytes", 0)), timeout=30.0)
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    if ((begin.get("width"), begin.get("height"), begin.get("format"),
         len(frame)) != (240, 320, "rgb565be", FRAME_BYTES)):
        raise RuntimeError(f"invalid reference frame: {begin!r}")
    (output / "capture-reference.rgb565").write_bytes(frame)
    (output / "capture-reference.png").write_bytes(
        rgb565be_to_png(frame, 240, 320))
    return {
        "frame_begin": begin,
        "frame_end": end,
        "bytes": len(frame),
        "crc32c": f"{crc32c(frame):08x}",
        "sha256": hashlib.sha256(frame).hexdigest(),
    }


def export_screenshot(device: PassiveSerial, output: Path) -> dict[str, Any]:
    device.write(b"library.export.screenshot\n")
    device.flush()
    begin = read_json(device, EXPORT_SCHEMA, "frame_begin", timeout=20.0)
    byte_count = int(begin.get("bytes", 0))
    if byte_count != FRAME_BYTES:
        raise RuntimeError(f"invalid export byte count: {byte_count}")
    frame = read_exact(device, byte_count, timeout=60.0)
    end = read_json(device, EXPORT_SCHEMA, "frame_end", timeout=20.0)
    metadata = begin.get("metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("export metadata is missing")
    require(end, {"bytes": FRAME_BYTES, "status": "valid"}, "frame end")
    observed_crc = f"{crc32c(frame):08x}"
    if metadata.get("pixel_crc32c") != observed_crc:
        raise RuntimeError(
            f"export CRC mismatch: {metadata.get('pixel_crc32c')} != {observed_crc}")
    (output / "exported.rgb565").write_bytes(frame)
    (output / "exported.png").write_bytes(rgb565be_to_png(frame, 240, 320))
    return {
        "frame_begin": begin,
        "frame_end": end,
        "bytes": len(frame),
        "crc32c": observed_crc,
        "sha256": hashlib.sha256(frame).hexdigest(),
    }


def open_screenshot_export(device: PassiveSerial) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    focus_home(device, "library", 6)
    current = action(device, "right")
    trace.append(current)
    require(current, {"page": "library", "library_view": "list"},
            "open Library")
    for _ in range(5):
        if current.get("library_selected_kind") == "screenshot":
            break
        current = action(device, "down")
        trace.append(current)
    require(current, {
        "page": "library", "library_view": "list",
        "library_selected_kind": "screenshot", "library_persistent": True,
        "screenshot_available": True,
    }, "select Screenshot")
    current = action(device, "right")
    trace.append(current)
    require(current, {
        "page": "library", "library_view": "detail",
        "library_selected_kind": "screenshot",
    }, "Screenshot detail")
    current = action(device, "right")
    trace.append(current)
    require(current, {
        "page": "library", "library_view": "actions",
        "library_selected_kind": "screenshot",
    }, "Screenshot actions")
    current = action(device, "right")
    trace.append(current)
    require(current, {
        "page": "library", "library_view": "export_ready",
        "library_selected_kind": "screenshot",
    }, "Screenshot export ready")
    return trace


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
    output.mkdir(parents=True)
    candidate = output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    for name in ("firmware.elf", "firmware.map"):
        shutil.copyfile(args.firmware.parent / name, output / name)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    app_sha = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    records: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    device: PassiveSerial | None = None

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.8)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        records["metrics_before"] = read_only(
            device, b"metrics", "leshy.boot.v1", "ready")
        failures.extend(boot_ready_failures(
            records["metrics_before"], args.expected_version, app_sha))
        records["lock_before"] = read_only(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        failures.extend(expect(records["lock_before"], {
            "status": "unlocked", "protected_access": True,
            "worker_active": False,
        }, "lock_before"))
        records["recovery_before"] = read_only(
            device, b"storage.product.boot-recovery", RECOVERY_SCHEMA, "state")
        failures.extend(expect(records["recovery_before"], {
            "expected_fingerprint": args.expected_cid,
            "observed_fingerprint": args.expected_cid,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "cleanup_complete": True,
            "physical_write_calls": 0,
        }, "recovery_before"))
        if failures:
            raise RuntimeError("preflight failed")

        normalize_home(device)
        sessions.append(read_only(
            device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
            HIL_SCHEMA, "begun"))
        focus_home(device, "capture", 4)
        current = action(device, "right")
        require(current, {
            "page": "capture", "capture_source_selection": 0,
            "screenshot_armed": False,
        }, "open Capture")
        current = action(device, "down")
        current = action(device, "down")
        require(current, {
            "page": "capture", "capture_source_selection": 2,
            "screenshot_armed": False,
        }, "focus Screenshot")
        current = action(device, "right")
        require(current, {
            "page": "home", "selected_id": "capture",
            "runtime_owner": "none", "lease_mask": 0,
            "screenshot_armed": True, "screenshot_status": "armed",
        }, "arm Screenshot")
        records["reference"] = capture_reference(device, output)
        current = action(device, "select", timeout=90.0)
        records["saved_state"] = current
        require(current, {
            "page": "home", "runtime_event": "screenshot_saved",
            "screenshot_armed": True, "screenshot_status": "saved",
            "screenshot_available": True,
        }, "save Screenshot")
        if int(current.get("screenshot_generation", 0)) <= 0:
            raise RuntimeError("saved Screenshot has no generation")
        records["library_trace"] = open_screenshot_export(device)
        records["export"] = export_screenshot(device, output)
        if records["export"]["sha256"] != records["reference"]["sha256"]:
            raise RuntimeError("exported pixels differ from exact TFT reference")
        generation = int(current["screenshot_generation"])
        records["generation"] = generation
        records["cleanup_before_reboot"] = best_effort_cleanup(device)
        if not records["cleanup_before_reboot"].get("complete"):
            raise RuntimeError("pre-reboot Home/zero-lease cleanup failed")
        sessions.append(read_only(
            device, f"hil.end {run_id}".encode("ascii"), HIL_SCHEMA, "ended"))
        device.close()
        device = None

        ready, recovery, reset = reset_capture(
            args.port, output, "cold-recovery", 30.0, maximum_attempts=2)
        records["cold_reset"] = reset
        records["cold_ready"] = ready
        records["cold_recovery"] = recovery
        failures.extend(boot_ready_failures(ready, args.expected_version, app_sha))
        failures.extend(expect(recovery, {
            "expected_fingerprint": args.expected_cid,
            "observed_fingerprint": args.expected_cid,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "cleanup_complete": True,
            "screenshot_admitted": True,
            "screenshot_generation": generation,
        }, "cold_recovery"))
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        records["final_ui"] = normalize_home(device)
        require(records["final_ui"], {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "screenshot_available": True,
            "screenshot_generation": generation,
        }, "cold Home")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        if device is not None:
            try:
                records["final_cleanup"] = best_effort_cleanup(device)
            except Exception as error:
                failures.append(f"cleanup {type(error).__name__}: {error}")
            device.close()

    result = {
        "schema": RUN_SCHEMA,
        "status": "pass" if not failures else "failed",
        "passed": not failures,
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
        "policy": {
            "mac_wifi_controlled": False,
            "clone_port_touched": False,
            "radio_tx_commands": 0,
            "temporary_device_lock_fixture": False,
            "exact_tft_bytes_required": True,
        },
        "hil_sessions": sessions,
        "records": records,
    }
    write_json(output / "run.json", result)
    artifact_manifest(output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "failures": failures, "run": str(output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
