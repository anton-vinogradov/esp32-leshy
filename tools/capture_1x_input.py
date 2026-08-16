#!/usr/bin/env python3
"""Capture interactive-target input events without intentionally resetting the board."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import serial


class PassiveSerial(serial.Serial):
    """Serial port that never toggles ESP32-S3 reset/boot control lines."""

    def _update_dtr_state(self) -> None:
        pass

    def _update_rts_state(self) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--command", default="metrics")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    raw = bytearray()
    input_records: list[dict[str, object]] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    interrupted = False
    try:
        device = PassiveSerial()
        device.port = args.port
        device.baudrate = 115200
        device.timeout = 0.1
        device.open()
        with device, args.output.open("wb") as evidence:
            device.write((args.command + "\n").encode("ascii"))
            device.flush()
            deadline = time.monotonic() + args.seconds
            buffered = bytearray()
            while time.monotonic() < deadline:
                chunk = device.read(device.in_waiting or 1)
                if not chunk:
                    continue
                raw.extend(chunk)
                evidence.write(chunk)
                evidence.flush()
                buffered.extend(chunk)
                while b"\n" in buffered:
                    line, _, remainder = buffered.partition(b"\n")
                    buffered = bytearray(remainder)
                    try:
                        value = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(value, dict) and value.get("schema") == "leshy.boot.v1":
                        print(json.dumps(value, sort_keys=True), flush=True)
                        if value.get("kind") == "input":
                            input_records.append(value)
    except KeyboardInterrupt:
        interrupted = True
    print(
        json.dumps(
            {
                "output": str(args.output),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "input_records": input_records,
                "interrupted": interrupted,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if input_records or args.allow_empty else (130 if interrupted else 2)


if __name__ == "__main__":
    raise SystemExit(main())
