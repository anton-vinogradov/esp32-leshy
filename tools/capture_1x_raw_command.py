#!/usr/bin/env python3
"""Capture the first raw serial line after a diagnostic command."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from capture_1x_ui import PassiveSerial, synchronize_console


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--schema")
    parser.add_argument("--kind")
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
        deadline = time.monotonic() + args.timeout
        raw = b""
        while time.monotonic() < deadline and not raw:
            candidate = device.readline()
            if not candidate:
                continue
            if args.schema is None and args.kind is None:
                raw = candidate
                continue
            try:
                value = json.loads(candidate)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if args.schema is not None and value.get("schema") != args.schema:
                continue
            if args.kind is not None and value.get("kind") != args.kind:
                continue
            raw = candidate
    if not raw:
        raise TimeoutError("timed out waiting for a raw serial line")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    try:
        decoded = raw.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        decoded = "<non-utf8>"
    print(json.dumps({"bytes": len(raw), "line": decoded,
                      "output": str(args.output),
                      "sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
