#!/usr/bin/env python3
"""Reset the clean 1.x target and retain raw boot/resource evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import serial


def reset_and_capture(
    device: serial.Serial, seconds: float
) -> tuple[bytes, float | None, float | None]:
    device.dtr = False
    device.rts = True
    time.sleep(0.1)
    device.dtr = True
    device.rts = False
    released = time.monotonic()
    time.sleep(0.1)
    device.dtr = False

    deadline = released + seconds
    first_byte_ms: float | None = None
    ready_marker_ms: float | None = None
    raw = bytearray()
    while time.monotonic() < deadline:
        chunk = device.read(device.in_waiting or 1)
        if chunk and first_byte_ms is None:
            first_byte_ms = (time.monotonic() - released) * 1000.0
        raw.extend(chunk)
        if ready_marker_ms is None and b'"kind":"ready"' in raw:
            ready_marker_ms = (time.monotonic() - released) * 1000.0
    return bytes(raw), first_byte_ms, ready_marker_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()

    with serial.Serial(args.port, 115200, timeout=0.05) as device:
        raw, first_byte_ms, ready_marker_ms = reset_and_capture(device, args.seconds)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)

    records: list[dict[str, object]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == "leshy.boot.v1":
            records.append(value)

    ready = next((record for record in records if record.get("kind") == "ready"), None)
    summary = {
        "output": str(args.output),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "json_records": len(records),
        "first_serial_byte_ms_after_reset_release": first_byte_ms,
        "ready_marker_ms_after_reset_release": ready_marker_ms,
        "ready": ready,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if ready is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
