#!/usr/bin/env python3
"""Capture one NDJSON diagnostic record without toggling ESP32 reset lines."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from capture_1x_ui import PassiveSerial, read_json, synchronize_console


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    device.open()
    with device:
        synchronize_console(device)
        device.write((args.command + "\n").encode("ascii"))
        device.flush()
        record = read_json(device, args.schema, args.kind, timeout=args.timeout)

    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"record": record, "output": str(args.output),
                      "sha256": hashlib.sha256(payload.encode()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
