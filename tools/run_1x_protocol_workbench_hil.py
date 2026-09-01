#!/usr/bin/env python3
"""Review the receive-only IR Protocol Workbench on exact board-01 TFT pixels."""

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
    valid_cid,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "leshy.protocol_workbench_hil.run.v1"
FIXTURE_SCHEMA = "leshy.protocol_workbench.hil_fixture.v1"
UI_SCHEMA = "leshy.ui.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
RECOVERY_SCHEMA = "leshy.storage.product_boot_recovery.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_CLONE_PORT = "/dev/cu.usbmodem1101"
FRAME_BYTES = 240 * 320 * 2


def read_only(device: PassiveSerial, command: bytes, schema: str,
              kind: str, timeout: float = 12.0) -> dict[str, Any]:
    return query(device, command, schema, kind, timeout=timeout)


def action(device: PassiveSerial, name: str,
           timeout: float = 20.0) -> dict[str, Any]:
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


def capture_frame(device: PassiveSerial, output: Path,
                  name: str) -> tuple[dict[str, Any], bytes]:
    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    frame = read_exact(device, int(begin.get("bytes", 0)), timeout=30.0)
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    if ((begin.get("width"), begin.get("height"), begin.get("format"),
         len(frame)) != (240, 320, "rgb565be", FRAME_BYTES)):
        raise RuntimeError(f"invalid TFT frame {name}: {begin!r}")
    rgb = output / f"{name}.rgb565"
    png = output / f"{name}.png"
    rgb.write_bytes(frame)
    png.write_bytes(rgb565be_to_png(frame, 240, 320))
    record = {
        "frame_begin": begin,
        "frame_end": end,
        "bytes": len(frame),
        "sha256": hashlib.sha256(frame).hexdigest(),
    }
    write_json(output / f"{name}.json", record)
    return record, frame


def cursor_delta(before: bytes, after: bytes) -> dict[str, Any]:
    if len(before) != FRAME_BYTES or len(after) != FRAME_BYTES:
        raise RuntimeError("frame size changed")
    changed: list[tuple[int, int]] = []
    outside: list[tuple[int, int]] = []
    for pixel in range(240 * 320):
        offset = pixel * 2
        if before[offset:offset + 2] == after[offset:offset + 2]:
            continue
        x = pixel % 240
        y = pixel // 240
        changed.append((x, y))
        allowed = 8 <= x < 232 and (
            184 <= y < 196 or 202 <= y < 221)
        if not allowed:
            outside.append((x, y))
    bbox = None if not changed else {
        "left": min(point[0] for point in changed),
        "top": min(point[1] for point in changed),
        "right": max(point[0] for point in changed),
        "bottom": max(point[1] for point in changed),
    }
    return {
        "changed_pixels": len(changed),
        "outside_allowed_regions": len(outside),
        "bbox": bbox,
        "allowed_regions": [
            {"x": 8, "y": 184, "width": 224, "height": 12},
            {"x": 8, "y": 202, "width": 224, "height": 19},
        ],
    }


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
    frames = output / "frames"
    frames.mkdir(parents=True)
    candidate = output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    for name in ("firmware.elf", "firmware.map"):
        shutil.copyfile(args.firmware.parent / name, output / name)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    checker = ROOT / "tools/check_protocol_workbench_hil_run.py"
    shutil.copyfile(checker, output / checker.name)
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

        records["home_before"] = normalize_home(device)
        sessions.append(read_only(
            device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
            HIL_SCHEMA, "begun"))
        opened = read_only(
            device, b"protocol.workbench.hil-fixture open-nec",
            FIXTURE_SCHEMA, "state")
        records["opened"] = opened
        require(opened, {
            "status": "opened", "hil_active": True,
            "fixture_active": True, "page": "protocol_workbench",
            "analysis_status": "valid", "protocol": "nec",
            "pulses": 67, "selected_pulse": 0,
            "read_only": True, "radio_touched": False,
            "application_tx_calls": 0, "storage_mounted": False,
            "storage_written": False, "runtime_owner": "none",
            "lease_mask": 0,
        }, "open fixture")
        if int(opened.get("base_unit_us", 0)) <= 0 or \
                int(opened.get("timing_bands", 0)) < 2:
            raise RuntimeError("fixture analysis is not useful")
        records["frame_0"], frame_0 = capture_frame(
            device, frames, "pulse-00")

        ui_1 = action(device, "down")
        records["ui_1"] = ui_1
        state_1 = read_only(
            device, b"protocol.workbench.hil-fixture state",
            FIXTURE_SCHEMA, "state")
        records["state_1"] = state_1
        require(state_1, {"status": "active", "selected_pulse": 1,
                          "pulses": 67}, "pulse 1")
        records["frame_1"], frame_1 = capture_frame(
            device, frames, "pulse-01")
        records["delta_0_1"] = cursor_delta(frame_0, frame_1)

        ui_2 = action(device, "down")
        records["ui_2"] = ui_2
        state_2 = read_only(
            device, b"protocol.workbench.hil-fixture state",
            FIXTURE_SCHEMA, "state")
        records["state_2"] = state_2
        require(state_2, {"status": "active", "selected_pulse": 2,
                          "pulses": 67}, "pulse 2")
        records["frame_2"], frame_2 = capture_frame(
            device, frames, "pulse-02")
        records["delta_1_2"] = cursor_delta(frame_1, frame_2)

        for key in ("delta_0_1", "delta_1_2"):
            delta = records[key]
            if delta["changed_pixels"] <= 0 or \
                    delta["outside_allowed_regions"] != 0:
                raise RuntimeError(f"dirty-region violation: {key} {delta!r}")
        if ui_1.get("ui_full_repaints") != ui_2.get("ui_full_repaints"):
            raise RuntimeError("pulse navigation triggered a full repaint")
        if int(ui_2.get("ui_delta_repaints", 0)) <= \
                int(ui_1.get("ui_delta_repaints", 0)):
            raise RuntimeError("second pulse navigation was not a delta repaint")

        records["clear"] = read_only(
            device, b"protocol.workbench.hil-fixture clear",
            FIXTURE_SCHEMA, "state")
        require(records["clear"], {
            "status": "cleared", "fixture_active": False,
            "ui_home": True, "page": "home", "pulses": 0,
            "storage_written": False, "runtime_owner": "none",
            "lease_mask": 0, "cleanup_complete": True,
        }, "clear fixture")
        sessions.append(read_only(
            device, f"hil.end {run_id}".encode("ascii"),
            HIL_SCHEMA, "ended"))
        records["recovery_after"] = read_only(
            device, b"storage.product.boot-recovery", RECOVERY_SCHEMA, "state")
        for key in ("generation", "observations", "expected_fingerprint",
                    "observed_fingerprint"):
            if records["recovery_after"].get(key) != \
                    records["recovery_before"].get(key):
                raise RuntimeError(f"storage continuity changed: {key}")
        require(records["recovery_after"], {
            "physical_write_calls": 0, "cleanup_complete": True,
            "mounted_read_only": True, "read_only_guaranteed": True,
        }, "recovery_after")
        records["safe_outputs"] = read_only(
            device, b"hardware.safe-outputs",
            "leshy.hardware.safe-outputs.v1", "state")
        require(records["safe_outputs"], {
            "buzzer_inactive": True, "nrf_ce_inactive": True,
        }, "safe outputs")
        records["final_ui"] = normalize_home(device)
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        if device is not None:
            try:
                if sessions and len(sessions) == 1:
                    try:
                        read_only(
                            device,
                            b"protocol.workbench.hil-fixture clear",
                            FIXTURE_SCHEMA, "state")
                    except Exception:
                        pass
                    try:
                        sessions.append(read_only(
                            device, f"hil.end {run_id}".encode("ascii"),
                            HIL_SCHEMA, "ended"))
                    except Exception:
                        pass
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
            "fixture_source": "retained_physical_nec_0.129",
            "fixture_storage": "bounded_ram",
            "product_storage_writes": 0,
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
