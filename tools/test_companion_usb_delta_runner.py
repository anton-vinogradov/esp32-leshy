#!/usr/bin/env python3
"""Host checks for the focused companion USB HIL runner."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_1x_companion_usb_delta_hil as runner  # noqa: E402


class FakeSerial:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = [
            (json.dumps(value, separators=(",", ":")) + "\n").encode()
            for value in responses
        ]
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> int:
        self.writes.append(value)
        return len(value)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        return self.responses.pop(0) if self.responses else b""


class CompanionUsbDeltaRunnerTests(unittest.TestCase):
    def test_request_is_compact_and_operation_fields_are_explicit(self) -> None:
        frame = runner.request("session.list", "one", offset=0)
        self.assertEqual(json.loads(frame), {
            "schema": "leshy.companion.request.v1",
            "kind": "session.list",
            "request_id": "one",
            "offset": 0,
        })
        self.assertNotIn(b" ", frame)

    def test_companion_request_returns_denials_without_hiding_them(self) -> None:
        denial = {
            "schema": runner.PROTOCOL_SCHEMA,
            "kind": "connect",
            "status": "denied",
            "reason": "scope_unavailable",
        }
        device = FakeSerial([denial])
        self.assertEqual(
            runner.companion_request(device, b"{}"), denial)
        self.assertEqual(device.writes, [b"{}\n"])

    def test_pagination_uses_only_returned_next_offset(self) -> None:
        responses = [
            {
                "schema": runner.PROTOCOL_SCHEMA,
                "kind": "target.list",
                "status": "ok",
                "reason": "none",
                "offset": 0,
                "next_offset": 1,
                "items": [{"target_id": "01"}],
            },
            {
                "schema": runner.PROTOCOL_SCHEMA,
                "kind": "target.list",
                "status": "ok",
                "reason": "none",
                "offset": 1,
                "next_offset": None,
                "items": [{"target_id": "02"}],
            },
        ]
        device = FakeSerial(responses)
        items, pages = runner.collect_pages(
            device, "target.list", "page", {})
        self.assertEqual([item["target_id"] for item in items], ["01", "02"])
        self.assertEqual(len(pages), 2)
        self.assertEqual(json.loads(device.writes[0]), {
            "schema": "leshy.companion.request.v1",
            "kind": "target.list",
            "request_id": "page-0",
            "offset": 0,
        })
        self.assertEqual(json.loads(device.writes[1])["offset"], 1)

    def test_runner_has_no_serial_discovery_or_implicit_target(self) -> None:
        source = (ROOT / "tools/run_1x_companion_usb_delta_hil.py").read_text()
        self.assertNotIn("serial.tools.list_ports", source)
        self.assertNotIn("/dev/cu.usbmodem", source)
        self.assertIn('parser.add_argument("--port", required=True)', source)
        self.assertIn("flash_candidate(args.port", source)
        self.assertIn("PassiveSerial(args.port", source)
        self.assertIn('"serial_port_discovery_calls": 0', source)
        self.assertIn('"cardputer_ports_opened": 0', source)
        self.assertNotIn("networksetup", source)
        self.assertNotIn("airport", source.lower())
        self.assertNotIn("en0", source)
        self.assertIn('"active_mac_wifi_touched": False', source)
        self.assertIn('"host_network_tools_invoked": False', source)
        self.assertIn("TemporaryProtectedReadAdmissionHil", source)
        self.assertIn('"associated_stations": 0', source)
        self.assertIn('"--exercise-device-web-lifecycle"', source)
        self.assertIn("exercise_device_web_lifecycle(device)", source)
        self.assertIn("build_snapshot", source)
        self.assertIn("write_snapshot", source)
        self.assertIn('"canonical_round_trip": True', source)
        self.assertIn('denied.get("reason") == "scope_denied"', source)


if __name__ == "__main__":
    unittest.main()
