#!/usr/bin/env python3
"""Retain a read-only USB/chip/flash profile before assigning board-02."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "leshy.hil.board_profile.v1"
READ_ONLY_COMMANDS = ("chip-id", "read-mac", "flash-id", "get-security-info")
MAC = re.compile(r"MAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.I)
FLASH_SIZE = re.compile(r"Detected flash size:\s*([^\r\n]+)", re.I)


def esptool_python() -> Path:
    candidate = Path.home() / ".platformio/penv/bin/python"
    if not candidate.is_file():
        raise ValueError("PlatformIO Python with esptool is unavailable")
    return candidate


def serial_metadata(port: str) -> dict[str, Any]:
    from serial.tools import list_ports

    match = next((value for value in list_ports.comports()
                  if value.device == port), None)
    if match is None:
        raise ValueError(f"serial port is not present: {port}")
    return {
        "device": match.device,
        "name": match.name,
        "description": match.description,
        "hwid": match.hwid,
        "vid": match.vid,
        "pid": match.pid,
        "serial_number": match.serial_number,
        "manufacturer": match.manufacturer,
        "product": match.product,
        "location": match.location,
    }


def run_read_only(port: str, command: str) -> dict[str, Any]:
    if command not in READ_ONLY_COMMANDS:
        raise ValueError(f"command is outside read-only allowlist: {command}")
    invocation = [
        str(esptool_python()), "-m", "esptool", "--chip", "esp32s3",
        "--port", port, "--connect-attempts", "3", "--no-stub",
        "--after", "hard-reset", command,
    ]
    result = subprocess.run(
        invocation, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False, timeout=30)
    output = result.stdout.decode("utf-8", errors="replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "output": output,
        "output_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "read_only": True,
    }


def interpret_outputs(commands: list[dict[str, Any]]) -> dict[str, Any]:
    combined = "\n".join(str(value.get("output", ""))
                         for value in commands)
    mac_match = MAC.search(combined)
    flash_match = FLASH_SIZE.search(combined)
    mac = mac_match.group(1).upper() if mac_match else None
    return {
        "mac": mac,
        "fixture_id": "0000" + mac.replace(":", "") if mac else None,
        "chip_is_esp32s3": "ESP32-S3" in combined,
        "flash_size": flash_match.group(1).strip() if flash_match else None,
        "commands_passed": all(value.get("returncode") == 0
                               for value in commands),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-read-only-profile", action="store_true")
    parser.add_argument(
        "--declare-standard-v2-no-extensions", action="store_true")
    parser.add_argument("--declare-antennas-attached", action="store_true")
    args = parser.parse_args()
    if not args.execute_read_only_profile:
        parser.error("--execute-read-only-profile is required")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    try:
        usb = serial_metadata(args.port)
        commands = [run_read_only(args.port, value)
                    for value in READ_ONLY_COMMANDS]
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        parser.error(str(error))
    interpreted = interpret_outputs(commands)
    mac = interpreted["mac"]
    fixture_id = interpreted["fixture_id"]
    chip_is_esp32s3 = interpreted["chip_is_esp32s3"]
    flash_size = interpreted["flash_size"]
    commands_passed = interpreted["commands_passed"]
    accepted = (
        commands_passed and chip_is_esp32s3 and flash_size == "16MB" and
        fixture_id is not None and
        args.declare_standard_v2_no_extensions and
        args.declare_antennas_attached
    )
    profile = {
        "schema": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "role": "fixture_candidate",
        "status": "accepted" if accepted else "incomplete",
        "accepted_for_fixture_flash": accepted,
        "port_at_profile": args.port,
        "usb": usb,
        "chip": {
            "family": "esp32-s3" if chip_is_esp32s3 else "unknown",
            "base_mac": mac,
            "fixture_id": fixture_id,
            "flash_size": flash_size,
        },
        "assembly": {
            "profile": "esp32-div-v2-n16"
                if args.declare_standard_v2_no_extensions else "unconfirmed",
            "extension_modules": "none"
                if args.declare_standard_v2_no_extensions else "unconfirmed",
            "antennas_attached": args.declare_antennas_attached,
            "shield_inventory": "declared_standard_v2_pending_functional_hil"
                if args.declare_standard_v2_no_extensions else "unconfirmed",
        },
        "operations": commands,
        "writes_performed": False,
        "flash_erases_performed": 0,
        "flash_bytes_written": 0,
        "ram_stub_uploaded": False,
        "limits": {
            "functional_receivers_verified": False,
            "ir_tx_verified": False,
            "rf_tx_authorized": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": profile["status"],
        "fixture_id": fixture_id,
        "flash_size": flash_size,
        "output": str(args.output),
    }, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
