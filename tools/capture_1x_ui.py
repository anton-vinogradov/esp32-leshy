#!/usr/bin/env python3
"""Drive the 1.x diagnostic UI and capture the actual TFT GRAM as a PNG."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import struct
import time
import zlib
from pathlib import Path
from typing import Any

import serial


class PassiveSerial(serial.Serial):
    """Serial port that never toggles ESP32-S3 reset/boot control lines."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # A disconnected/stalled native-USB endpoint must fail closed instead
        # of parking an unattended HIL runner forever inside write(2).
        kwargs.setdefault("write_timeout", 1.0)
        super().__init__(*args, **kwargs)

    def _update_dtr_state(self) -> None:
        pass

    def _update_rts_state(self) -> None:
        pass

    def flush(self) -> None:
        """Do not call pyserial's unbounded POSIX tcdrain() for native USB.

        Diagnostic commands are short, and Serial.write() has already queued
        their bytes in order before the response read begins.  macOS can keep
        tcdrain() blocked forever when the ESP32-S3 USB endpoint stalls, which
        bypasses every workflow timeout and prevents fail-closed evidence.
        """
        return None


def read_json(device: serial.Serial, schema: str, kind: str, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = device.readline()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == schema:
            if value.get("kind") == "error":
                if kind == "error":
                    return value
                raise RuntimeError(f"device rejected command: {value}")
            if value.get("kind") == kind:
                return value
    raise TimeoutError(f"timed out waiting for {schema}/{kind}")


def synchronize_console(device: serial.Serial, timeout: float = 5.0) -> None:
    """Wait until the firmware command loop survives any native-USB reopen reset."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device.reset_input_buffer()
        device.write(b"ping\n")
        device.flush()
        try:
            read_json(device, "leshy.boot.v1", "pong", timeout=0.5)
            device.reset_input_buffer()
            return
        except TimeoutError:
            continue
    raise TimeoutError("timed out synchronizing the firmware console")


def read_exact(device: serial.Serial, size: int, timeout: float = 30.0) -> bytes:
    result = bytearray()
    deadline = time.monotonic() + timeout
    while len(result) < size and time.monotonic() < deadline:
        chunk = device.read(size - len(result))
        if chunk:
            result.extend(chunk)
    if len(result) != size:
        raise TimeoutError(f"frame ended at {len(result)} of {size} bytes")
    return bytes(result)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def rgb565be_to_png(frame: bytes, width: int, height: int) -> bytes:
    expected = width * height * 2
    if len(frame) != expected:
        raise ValueError(f"RGB565 frame is {len(frame)} bytes, expected {expected}")
    rows = bytearray()
    offset = 0
    for _ in range(height):
        rows.append(0)  # PNG filter: None
        for _ in range(width):
            value = (frame[offset] << 8) | frame[offset + 1]
            offset += 2
            red = (value >> 11) & 0x1F
            green = (value >> 5) & 0x3F
            blue = value & 0x1F
            rows.extend(((red << 3) | (red >> 2),
                         (green << 2) | (green >> 4),
                         (blue << 3) | (blue >> 2)))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) +
            png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9)) + png_chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keys", default="", help="comma-separated up/down/left/right/select/back actions")
    parser.add_argument("--settle-ms", type=int, default=120)
    args = parser.parse_args()

    actions = [value.strip() for value in args.keys.split(",") if value.strip()]
    allowed = {"up", "down", "left", "right", "select", "back"}
    invalid = [value for value in actions if value not in allowed]
    if invalid:
        parser.error(f"unsupported actions: {', '.join(invalid)}")

    trace: list[dict[str, Any]] = []
    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    # Configure line state before open. Native USB reset must be an explicit HIL
    # action, never a side effect of taking a screenshot.
    device.open()
    with device:
        synchronize_console(device)
        for action in actions:
            sent_at = time.monotonic()
            device.write(f"ui.key {action}\n".encode("ascii"))
            device.flush()
            state = read_json(device, "leshy.ui.v1", "state")
            state["host_ack_ms"] = round((time.monotonic() - sent_at) * 1000.0, 3)
            trace.append(state)
            time.sleep(args.settle_ms / 1000.0)

        device.write(b"ui.capture\n")
        device.flush()
        begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
        if begin.get("format") != "rgb565be":
            raise RuntimeError(f"unsupported device format: {begin.get('format')}")
        frame = read_exact(device, int(begin["bytes"]))
        end = read_json(device, "leshy.ui.capture.v1", "frame_end")
        device.write(b"ui.state\n")
        device.flush()
        post_capture_state = read_json(device, "leshy.ui.v1", "state")

    width = int(begin["width"])
    height = int(begin["height"])
    png = rgb565be_to_png(frame, width, height)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(png)
    trace_path = args.output.with_suffix(args.output.suffix + ".json")
    evidence = {
        "schema": "leshy.ui.hil.v1",
        "port": args.port,
        "actions": actions,
        "states": trace,
        "frame_begin": begin,
        "frame_end": end,
        "post_capture_state": post_capture_state,
        "rgb565_sha256": hashlib.sha256(frame).hexdigest(),
        "png": str(args.output),
        "png_bytes": len(png),
        "png_sha256": hashlib.sha256(png).hexdigest(),
    }
    trace_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
