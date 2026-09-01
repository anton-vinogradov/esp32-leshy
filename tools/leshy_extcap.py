#!/usr/bin/env python3
"""Read an already-running Leshy Wi-Fi recording into Wireshark.

The adapter is deliberately read-only: it never starts/stops a radio, changes
the host network, sends a UI action, or asks the firmware for a TX capability.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any, BinaryIO, Callable, Protocol


INTERFACE = "leshy-wifi"
REQUEST_SCHEMA = "leshy.companion.request.v1"
RESPONSE_SCHEMA = "leshy.companion.response.v1"
LIVE_SCOPE = "capture.live.read"
LIVE_CAPABILITY = "capture.live.wifi"
MAX_FRAME_BYTES = 512
MAX_CHUNK_BYTES = 80
_HEX = re.compile(r"(?:[0-9A-F]{2})*")


class Transport(Protocol):
    def exchange(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


class PassiveSerialTransport:
    """Native-USB serial transport that does not toggle ESP reset lines."""

    def __init__(self, port: str, timeout: float = 3.0) -> None:
        import serial

        class PassiveSerial(serial.Serial):
            def _update_dtr_state(self) -> None:
                pass

            def _update_rts_state(self) -> None:
                pass

            def flush(self) -> None:
                return None

        self._serial = PassiveSerial()
        self._serial.port = port
        self._serial.baudrate = 115200
        self._serial.timeout = 0.15
        self._serial.write_timeout = 1.0
        self._timeout = timeout
        self._serial.open()

    def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = (json.dumps(request, separators=(",", ":"),
                              ensure_ascii=True) + "\n").encode("ascii")
        if len(payload) - 1 > MAX_FRAME_BYTES:
            raise ValueError("companion request exceeds firmware frame bound")
        self._serial.write(payload)
        deadline = time.monotonic() + self._timeout
        request_id = request["request_id"]
        while time.monotonic() < deadline:
            line = self._serial.readline()
            if not line:
                continue
            try:
                response = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if (isinstance(response, dict) and
                    response.get("schema") == RESPONSE_SCHEMA and
                    response.get("request_id") == request_id):
                return response
        raise TimeoutError(f"Leshy did not answer request {request_id}")

    def close(self) -> None:
        self._serial.close()


@dataclass(frozen=True)
class LiveChunk:
    offset: int
    next_offset: int | None
    available_bytes: int
    frames: int
    dropped: int
    terminal: bool
    cleanup_complete: bool
    data: bytes


class LivePcapClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._sequence = 0
        self._connected = False

    def _request_id(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}-{self._sequence}"

    def connect(self) -> None:
        request_id = self._request_id("extcap-connect")
        response = self._transport.exchange({
            "schema": REQUEST_SCHEMA,
            "kind": "connect",
            "request_id": request_id,
            "protocol": 1,
            "scopes": [LIVE_SCOPE],
        })
        expected = {
            "schema", "kind", "request_id", "status", "reason",
            "protocol", "transport", "scopes", "capabilities",
            "max_frame_bytes",
        }
        if set(response) != expected:
            raise RuntimeError("unexpected companion connect response fields")
        if (response["schema"] != RESPONSE_SCHEMA or
                response["request_id"] != request_id or
                response["kind"] != "connect" or response["status"] != "ready" or
                response["reason"] != "none" or response["protocol"] != 1 or
                response["transport"] != "usb_serial_ndjson" or
                response["scopes"] != [LIVE_SCOPE] or
                response["capabilities"] != [LIVE_CAPABILITY] or
                response["max_frame_bytes"] != MAX_FRAME_BYTES):
            raise RuntimeError(
                "start 'Record → Wi-Fi' on Leshy, then start Wireshark capture")
        self._connected = True

    def read(self, offset: int) -> LiveChunk:
        if not self._connected:
            raise RuntimeError("companion is not connected")
        request_id = self._request_id("extcap-read")
        response = self._transport.exchange({
            "schema": REQUEST_SCHEMA,
            "kind": "capture.live.read",
            "request_id": request_id,
            "offset": offset,
        })
        expected = {
            "schema", "kind", "request_id", "status", "reason", "source",
            "link_type", "offset", "next_offset", "available_bytes",
            "frames", "dropped", "terminal", "cleanup_complete", "encoding",
            "data_hex",
        }
        if set(response) != expected:
            raise RuntimeError("unexpected live-capture response fields")
        if (response["schema"] != RESPONSE_SCHEMA or
                response["request_id"] != request_id):
            raise RuntimeError("live-capture response identity changed")
        if response["status"] != "ok" or response["reason"] != "none":
            raise RuntimeError(f"Leshy rejected live read: {response['reason']}")
        if (response["kind"] != "capture.live.read" or
                response["source"] != "wifi" or
                response["link_type"] != 127 or
                response["encoding"] != "hex" or
                response["offset"] != offset):
            raise RuntimeError("live-capture coordinates changed")
        numeric = ("offset", "available_bytes", "frames", "dropped")
        if any(type(response[name]) is not int or response[name] < 0
               for name in numeric):
            raise RuntimeError("live-capture counters are invalid")
        if (type(response["terminal"]) is not bool or
                type(response["cleanup_complete"]) is not bool):
            raise RuntimeError("live-capture lifecycle flags are invalid")
        encoded = response["data_hex"]
        if not isinstance(encoded, str) or _HEX.fullmatch(encoded) is None:
            raise RuntimeError("live-capture payload is not canonical hex")
        data = bytes.fromhex(encoded)
        if len(data) > MAX_CHUNK_BYTES:
            raise RuntimeError("live-capture chunk exceeds negotiated bound")
        available = response["available_bytes"]
        next_offset = response["next_offset"]
        if offset > available or offset + len(data) > available:
            raise RuntimeError("live-capture availability regressed")
        if next_offset is None:
            if (not response["terminal"] or not response["cleanup_complete"] or
                    offset + len(data) != available):
                raise RuntimeError("live-capture ended before safe cleanup")
        elif (type(next_offset) is not int or next_offset < 0 or
              next_offset != offset + len(data)):
            raise RuntimeError("live-capture offset continuity failed")
        if response["terminal"] and not response["cleanup_complete"]:
            raise RuntimeError("Leshy stopped capture without complete cleanup")
        return LiveChunk(
            offset=offset,
            next_offset=next_offset,
            available_bytes=available,
            frames=response["frames"],
            dropped=response["dropped"],
            terminal=response["terminal"],
            cleanup_complete=response["cleanup_complete"],
            data=data,
        )

    def close(self) -> None:
        self._transport.close()


def validate_pcap_header(data: bytes) -> None:
    if len(data) < 24:
        raise RuntimeError("Leshy PCAP header is incomplete")
    magic, major, minor = struct.unpack_from("<IHH", data)
    snaplen, link_type = struct.unpack_from("<II", data, 16)
    if (magic != 0xA1B2C3D4 or major != 2 or minor != 4 or
            not 15 < snaplen <= 65535 or link_type != 127):
        raise RuntimeError("Leshy returned an incompatible PCAP stream")


def stream_live_pcap(client: LivePcapClient, output: BinaryIO,
                     poll_seconds: float = 0.05,
                     sleep: Callable[[float], None] = time.sleep) -> dict[str, int]:
    client.connect()
    offset = 0
    previous_available = 0
    previous_frames = 0
    previous_dropped = 0
    pending_header = bytearray()
    header_validated = False
    while True:
        chunk = client.read(offset)
        if (chunk.available_bytes < previous_available or
                chunk.frames < previous_frames or
                chunk.dropped < previous_dropped):
            raise RuntimeError("live-capture counters moved backwards")
        previous_available = chunk.available_bytes
        previous_frames = chunk.frames
        previous_dropped = chunk.dropped
        if chunk.data:
            if not header_validated:
                pending_header.extend(chunk.data)
                if len(pending_header) >= 24:
                    validate_pcap_header(bytes(pending_header[:24]))
                    output.write(pending_header)
                    pending_header.clear()
                    header_validated = True
            else:
                output.write(chunk.data)
            if header_validated and hasattr(output, "flush"):
                output.flush()
            offset += len(chunk.data)
        if chunk.next_offset is None:
            if offset != chunk.available_bytes:
                raise RuntimeError("terminal PCAP stream is incomplete")
            if not header_validated:
                raise RuntimeError("terminal PCAP stream has no complete header")
            return {
                "bytes": offset,
                "frames": chunk.frames,
                "dropped": chunk.dropped,
            }
        if chunk.next_offset != offset:
            raise RuntimeError("PCAP stream contains an offset gap")
        if not chunk.data:
            sleep(poll_seconds)


def print_interfaces() -> None:
    print("extcap {version=1.0.0}{display=Leshy Live Companion}")
    print("interface {value=leshy-wifi}{display=Леший: эфир Wi-Fi по USB}")


def print_dlts() -> None:
    print("dlt {number=127}{name=IEEE802_11_RADIO}{display=Wi-Fi с метаданными}")


def print_config() -> None:
    print("arg {number=0}{call=--port}{display=USB-порт Лешего}"
          "{type=string}{required=true}"
          "{tooltip=Порт показан в Система → Об устройстве}")


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--extcap-interfaces", action="store_true")
    parser.add_argument("--extcap-dlts", action="store_true")
    parser.add_argument("--extcap-config", action="store_true")
    parser.add_argument("--extcap-interface")
    parser.add_argument("--extcap-version")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--fifo")
    parser.add_argument("--port")
    parser.add_argument("--extcap-capture-filter")
    parser.add_argument("--extcap-control-in")
    parser.add_argument("--extcap-control-out")
    parser.add_argument("--help", action="help")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = argument_parser().parse_args(argv)
    if args.extcap_interfaces:
        print_interfaces()
        return 0
    if args.extcap_dlts:
        print_dlts()
        return 0
    if args.extcap_config:
        print_config()
        return 0
    if not args.capture or args.extcap_interface != INTERFACE:
        raise SystemExit("select --extcap-interface=leshy-wifi and --capture")
    if not args.port or not args.fifo:
        raise SystemExit("--port and --fifo are required for capture")

    transport = PassiveSerialTransport(args.port)
    client = LivePcapClient(transport)
    try:
        with open(args.fifo, "wb", buffering=0) as output:
            stream_live_pcap(client, output)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    except Exception as error:
        print(f"Leshy extcap: {error}", file=sys.stderr)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
