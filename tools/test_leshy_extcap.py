#!/usr/bin/env python3

from __future__ import annotations

import io
import unittest
from typing import Any

import leshy_extcap as extcap


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        response = dict(self.responses.pop(0))
        response["request_id"] = request["request_id"]
        return response

    def close(self) -> None:
        self.closed = True


def connect_response() -> dict[str, Any]:
    return {
        "schema": extcap.RESPONSE_SCHEMA,
        "kind": "connect",
        "request_id": "filled-by-fake",
        "status": "ready",
        "reason": "none",
        "protocol": 1,
        "transport": "usb_serial_ndjson",
        "scopes": [extcap.LIVE_SCOPE],
        "capabilities": [extcap.LIVE_CAPABILITY],
        "max_frame_bytes": 512,
    }


def chunk(offset: int, data: bytes, available: int, frames: int,
          terminal: bool = False, dropped: int = 0) -> dict[str, Any]:
    return {
        "schema": extcap.RESPONSE_SCHEMA,
        "kind": "capture.live.read",
        "request_id": "filled-by-fake",
        "status": "ok",
        "reason": "none",
        "source": "wifi",
        "link_type": 127,
        "offset": offset,
        "next_offset": None if terminal else offset + len(data),
        "available_bytes": available,
        "frames": frames,
        "dropped": dropped,
        "terminal": terminal,
        "cleanup_complete": terminal,
        "encoding": "hex",
        "data_hex": data.hex().upper(),
    }


class LeshyExtcapTests(unittest.TestCase):
    def test_streams_exact_pcap_without_radio_or_network_commands(self) -> None:
        header = (b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00" + b"\x00" * 8 +
                  b"\x0f\x01\x00\x00\x7f\x00\x00\x00")
        record = b"record-bytes"
        transport = FakeTransport([
            connect_response(),
            chunk(0, header, len(header), 0),
            chunk(len(header), b"", len(header), 0),
            chunk(len(header), record, len(header) + len(record), 1,
                  terminal=True),
        ])
        client = extcap.LivePcapClient(transport)
        output = io.BytesIO()
        sleeps: list[float] = []
        result = extcap.stream_live_pcap(
            client, output, sleep=sleeps.append)
        self.assertEqual(header + record, output.getvalue())
        self.assertEqual({"bytes": 36, "frames": 1, "dropped": 0}, result)
        self.assertEqual([0.05], sleeps)
        kinds = [request["kind"] for request in transport.requests]
        self.assertEqual(
            ["connect", "capture.live.read", "capture.live.read",
             "capture.live.read"], kinds)
        self.assertNotIn("action", str(transport.requests))
        self.assertNotIn("wifi", str(transport.requests).lower().replace(
            "capture.live.read", "").replace("leshy.companion.request.v1", ""))

    def test_rejects_gap_counter_regression_and_unsafe_cleanup(self) -> None:
        header = (b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00" + b"\x00" * 8 +
                  b"\x0f\x01\x00\x00\x7f\x00\x00\x00")
        bad = chunk(0, header, len(header), 0)
        bad["next_offset"] = 25
        client = extcap.LivePcapClient(FakeTransport([
            connect_response(), bad,
        ]))
        with self.assertRaisesRegex(RuntimeError, "continuity"):
            extcap.stream_live_pcap(client, io.BytesIO())

        unsafe = chunk(0, header, len(header), 0, terminal=True)
        unsafe["cleanup_complete"] = False
        client = extcap.LivePcapClient(FakeTransport([
            connect_response(), unsafe,
        ]))
        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            extcap.stream_live_pcap(client, io.BytesIO())

    def test_discovery_output_is_valid_extcap_shape(self) -> None:
        self.assertEqual(0, extcap.main(["--extcap-interfaces"]))
        self.assertEqual(0, extcap.main([
            "--extcap-interface=leshy-wifi", "--extcap-dlts",
        ]))
        self.assertEqual(0, extcap.main([
            "--extcap-interface=leshy-wifi", "--extcap-config",
        ]))


if __name__ == "__main__":
    unittest.main()
