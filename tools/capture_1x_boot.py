#!/usr/bin/env python3
"""Reset the clean 1.x target and retain raw boot/resource evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import serial


def capture_reconnecting_until_ready(
        port: str, seconds: float, *, serial_factory=None,
        settle_seconds: float = 1.0, retry_seconds: float = 0.1,
        ) -> tuple[bytes, float | None, int, int]:
    """Capture native-USB boot output across disconnect/re-enumeration."""
    from capture_1x_ui import PassiveSerial

    if seconds <= 0:
        raise ValueError("capture timeout must be positive")
    if settle_seconds < 0 or retry_seconds < 0:
        raise ValueError("capture timing values must not be negative")

    factory = serial_factory or (
        lambda: PassiveSerial(port, 115200, timeout=0.05)
    )
    deadline = time.monotonic() + seconds
    started = time.monotonic()
    ready_at: float | None = None
    raw = bytearray()
    device = None
    disconnects = 0
    open_attempts = 0

    try:
        while time.monotonic() < deadline:
            if device is None:
                open_attempts += 1
                try:
                    device = factory()
                except (OSError, serial.SerialException):
                    if retry_seconds:
                        time.sleep(retry_seconds)
                    continue
            try:
                chunk = device.read(device.in_waiting or 1)
            except (OSError, serial.SerialException):
                disconnects += 1
                try:
                    device.close()
                except (OSError, serial.SerialException):
                    pass
                device = None
                if retry_seconds:
                    time.sleep(retry_seconds)
                continue
            if chunk:
                raw.extend(chunk)
                if (ready_at is None and
                        b'"schema":"leshy.boot.v1","kind":"ready"' in raw):
                    ready_at = time.monotonic()
            if (ready_at is not None and
                    time.monotonic() - ready_at >= settle_seconds):
                break
    finally:
        if device is not None:
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass

    ready_ms = (
        None if ready_at is None
        else round((ready_at - started) * 1000.0, 3)
    )
    return bytes(raw), ready_ms, disconnects, open_attempts


def trigger_reset(device: serial.Serial) -> None:
    """Pulse the native-USB reset lines and release the target."""
    device.dtr = False
    device.rts = True
    time.sleep(0.1)
    device.dtr = True
    device.rts = False
    time.sleep(0.1)
    device.dtr = False


def reset_and_capture_reconnecting(
        port: str, seconds: float,
        ) -> tuple[bytes, float | None, int, int]:
    """Reset once, then reopen native USB across every bounded boot retry."""
    with serial.Serial(port, 115200, timeout=0.05) as device:
        trigger_reset(device)
    return capture_reconnecting_until_ready(port, seconds)


def reset_and_capture(
    device: serial.Serial, seconds: float
) -> tuple[bytes, float | None, float | None]:
    trigger_reset(device)
    released = time.monotonic()

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
