#!/usr/bin/env python3
"""Run correlation delta with board 02 as a beacon, then restore it."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import serial

from capture_1x_ui import PassiveSerial, read_json
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import artifact_manifest


SCHEMA = "leshy.targets_correlation_fixture_orchestration.v1"
FIXTURE_SCHEMA = "leshy.hil.correlation_fixture.v1"
FIXTURE_LABEL = "LESHY-HIL-CORR"


def flash_with_openocd(executable: Path, scripts: Path, serial: str,
                       image: Path) -> None:
    command = [
        str(executable.resolve()), "-s", str(scripts.resolve()),
        "-f", "board/esp32s3-builtin.cfg",
        "-c", f"adapter serial {serial}",
        "-c", "init",
        "-c", f"program_esp {image.resolve()} 0x10000 verify reset exit",
    ]
    subprocess.run(command, check=True)


def wait_fixture_ready(port: str, timeout: float = 30.0) -> dict[str, Any]:
    """Require two stable fixture replies after native-USB re-enumeration."""
    started = time.monotonic()
    deadline = started + timeout
    attempts = 0
    last_error = "fixture endpoint did not appear"
    while time.monotonic() < deadline:
        attempts += 1
        device: PassiveSerial | None = None
        try:
            device = PassiveSerial()
            device.port = port
            device.baudrate = 115200
            device.timeout = 0.25
            device.open()
            states = []
            for _ in range(2):
                device.reset_input_buffer()
                device.write(b"state\n")
                device.flush()
                state = read_json(
                    device, FIXTURE_SCHEMA, "state", timeout=2.0)
                if state.get("label") != FIXTURE_LABEL:
                    raise RuntimeError(f"unexpected fixture state: {state}")
                states.append(state)
                time.sleep(0.5)
            return {
                "fixture_ready_attempts": attempts,
                "fixture_ready_elapsed_ms": round(
                    (time.monotonic() - started) * 1000.0, 3),
                "fixture_ready_state": states[-1],
                "fixture_ready_stable_replies": len(states),
            }
        except (OSError, serial.SerialException, TimeoutError,
                RuntimeError) as error:
            last_error = f"{type(error).__name__}: {error}"
            time.sleep(0.25)
        finally:
            if device is not None and device.is_open:
                device.close()
    raise TimeoutError(
        f"fixture USB did not stabilize on {port} after {attempts} attempts: "
        f"{last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dut-port", required=True)
    parser.add_argument("--fixture-port", required=True)
    parser.add_argument("--dut-firmware", required=True, type=Path)
    parser.add_argument("--dut-elf", required=True, type=Path)
    parser.add_argument("--dut-map", required=True, type=Path)
    parser.add_argument("--fixture-firmware", required=True, type=Path)
    parser.add_argument("--fixture-restore", required=True, type=Path)
    parser.add_argument("--fixture-restore-sha256", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-exact-dut-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--fixture-openocd", type=Path)
    parser.add_argument("--fixture-openocd-scripts", type=Path)
    parser.add_argument("--fixture-openocd-serial")
    args = parser.parse_args()
    if args.dut_port == args.fixture_port:
        parser.error("DUT and fixture ports must differ")
    for path in (args.dut_firmware, args.dut_elf, args.dut_map,
                 args.fixture_firmware, args.fixture_restore):
        if not path.is_file():
            parser.error(f"artifact missing: {path}")
    actual_restore_hash = sha256_file(args.fixture_restore)
    if actual_restore_hash != args.fixture_restore_sha256:
        parser.error(
            f"fixture restore hash mismatch: {actual_restore_hash}")
    openocd_values = (
        args.fixture_openocd,
        args.fixture_openocd_scripts,
        args.fixture_openocd_serial,
    )
    if any(value is not None for value in openocd_values) and not all(
            value is not None for value in openocd_values):
        parser.error("all fixture OpenOCD arguments must be supplied together")
    use_openocd = args.fixture_openocd is not None
    if use_openocd and (
            not args.fixture_openocd.is_file() or
            not args.fixture_openocd_scripts.is_dir()):
        parser.error("fixture OpenOCD executable/scripts are unavailable")

    record = {
        "schema": SCHEMA,
        "status": "in_progress",
        "dut_port": args.dut_port,
        "fixture_port": args.fixture_port,
        "fixture_firmware_sha256": sha256_file(args.fixture_firmware),
        "fixture_restore_sha256": actual_restore_hash,
        "fixture_flash_offset": 0x10000,
        "fixture_flash_method": "usb_jtag" if use_openocd else "rom_serial",
        "fixture_openocd_serial": args.fixture_openocd_serial,
        "fixture_restore_attempted": False,
        "fixture_restore_complete": False,
        "fixture_ready_attempts": 0,
        "fixture_ready_elapsed_ms": None,
        "fixture_ready_state": None,
        "fixture_ready_stable_replies": 0,
    }
    failure: BaseException | None = None
    try:
        if use_openocd:
            flash_with_openocd(
                args.fixture_openocd, args.fixture_openocd_scripts,
                args.fixture_openocd_serial, args.fixture_firmware)
        else:
            flash_candidate(args.fixture_port, args.fixture_firmware, 0x10000,
                            args.flash_baud)
        record.update(wait_fixture_ready(args.fixture_port))
        command = [
            sys.executable, "tools/run_1x_targets_correlation_hil.py",
            "--port", args.dut_port,
            "--fixture-port", args.fixture_port,
            "--firmware", str(args.dut_firmware),
            "--elf", str(args.dut_elf),
            "--map", str(args.dut_map),
            "--expected-version", args.expected_version,
            "--source-commit", args.source_commit,
            "--output", str(args.output),
            "--flash-baud", str(args.flash_baud),
        ]
        if args.reuse_exact_dut_flash:
            command.append("--reuse-exact-flash")
        subprocess.run(command, check=True)
        record["status"] = "pass"
    except BaseException as error:
        failure = error
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
    finally:
        record["fixture_restore_attempted"] = True
        try:
            if use_openocd:
                flash_with_openocd(
                    args.fixture_openocd, args.fixture_openocd_scripts,
                    args.fixture_openocd_serial, args.fixture_restore)
            else:
                flash_candidate(
                    args.fixture_port, args.fixture_restore, 0x10000,
                    args.flash_baud)
            record["fixture_restore_complete"] = True
        except BaseException as restore_error:
            record["status"] = "failed"
            record["fixture_restore_error"] = (
                f"{type(restore_error).__name__}: {restore_error}")
            if failure is None:
                failure = restore_error

    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "fixture-orchestration.json", record)
    artifact_manifest(args.output)
    print(json.dumps(record, sort_keys=True))
    if failure is not None:
        raise failure
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
