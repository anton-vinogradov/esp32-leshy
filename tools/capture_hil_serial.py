#!/usr/bin/env python3
"""Reset an ESP32-DIV into the HIL image and retain raw CP2102 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import serial


SAFE_COMMAND_SECONDS = {
    "inventory": 3.0,
    "i2c-read": 5.0,
    "gps-listen": 12.0,
}
RF_CONFIRMATION = "rf-read shield-no-gps-no-pn532"


def read_for(port: serial.Serial, seconds: float) -> bytes:
    deadline = time.monotonic() + seconds
    result = bytearray()
    while time.monotonic() < deadline:
        result.extend(port.read(port.in_waiting or 1))
    return bytes(result)


def normal_reset(port: serial.Serial) -> None:
    port.dtr = False  # GPIO0 high
    port.rts = True   # EN low
    time.sleep(0.1)
    port.dtr = True
    port.rts = False  # EN high
    time.sleep(0.1)
    port.dtr = False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--command", action="append", choices=sorted(SAFE_COMMAND_SECONDS), default=[]
    )
    parser.add_argument(
        "--rf-read-confirmed",
        action="store_true",
        help="operator confirmed GPS/PN532 are physically absent; run guarded RF identity reads",
    )
    args = parser.parse_args()

    raw = bytearray()
    with serial.Serial(args.port, 115200, timeout=0.1) as device:
        normal_reset(device)
        raw.extend(read_for(device, 3.0))
        commands = list(args.command)
        if args.rf_read_confirmed:
            commands.append(RF_CONFIRMATION)
        for command in commands:
            device.write(command.encode("ascii") + b"\n")
            device.flush()
            raw.extend(read_for(device, SAFE_COMMAND_SECONDS.get(command, 8.0)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)

    json_records = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == "leshy.hil.v1":
            json_records += 1

    print(
        json.dumps(
            {
                "output": str(args.output),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "json_records": json_records,
                "commands": commands,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
