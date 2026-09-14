#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import types
import unittest

# These parser tests never open a port or need a physical serial backend.
try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("serial")
    stub.Serial = object
    sys.modules["serial"] = stub

from capture_1x_ui import read_json


class FakeSerial:
    def __init__(self, *records: dict[str, object]) -> None:
        self.lines = [
            (json.dumps(record) + "\n").encode("utf-8")
            for record in records
        ]

    def readline(self) -> bytes:
        return self.lines.pop(0) if self.lines else b""


class ReadJsonTest(unittest.TestCase):
    def test_fragments_and_transport_timeouts_preserve_utf8(self) -> None:
        record = {"schema": "fixture.v1", "kind": "loaded", "name": "Леший"}
        raw = (json.dumps(record, ensure_ascii=False) + "\n").encode()
        device = FakeSerial()
        device.lines = [part for byte in raw for part in (bytes([byte]), b"")]
        self.assertEqual(record, read_json(device, "fixture.v1", "loaded", .1))

    def test_invalid_complete_line_does_not_poison_next_record(self) -> None:
        record = {"schema": "fixture.v1", "kind": "loaded"}
        device = FakeSerial(record)
        device.lines.insert(0, b"boot log\n")
        self.assertEqual(record, read_json(device, "fixture.v1", "loaded", .01))

    def test_partial_timeout_is_diagnostic_not_a_success(self) -> None:
        device = FakeSerial()
        device.lines = [b'{"schema":']
        with self.assertRaisesRegex(TimeoutError, "fragments=1.*pending_bytes=10"):
            read_json(device, "fixture.v1", "loaded", .01)

    def test_oversize_line_fails_bounded(self) -> None:
        device = FakeSerial()
        device.lines = [b"x" * 262145]
        with self.assertRaisesRegex(RuntimeError, "exceeds 256 KiB"):
            read_json(device, "fixture.v1", "loaded", .01)

    def test_does_not_consume_binary_after_frame_header(self) -> None:
        record = {"schema": "fixture.v1", "kind": "frame_begin"}
        device = FakeSerial(record)
        device.lines.append(b"\x00\xff\x00\x01")
        self.assertEqual(record, read_json(device, "fixture.v1", "frame_begin", .01))
        self.assertEqual(device.lines, [b"\x00\xff\x00\x01"])

    def test_explicitly_expected_error_is_returned(self) -> None:
        record = {
            "schema": "fixture.v1",
            "kind": "error",
            "status": "replay_rejected",
        }
        self.assertEqual(
            record,
            read_json(FakeSerial(record), "fixture.v1", "error", 0.01),
        )

    def test_unexpected_error_remains_fail_closed(self) -> None:
        record = {
            "schema": "fixture.v1",
            "kind": "error",
            "status": "unsafe_state",
        }
        with self.assertRaisesRegex(RuntimeError, "device rejected command"):
            read_json(FakeSerial(record), "fixture.v1", "loaded", 0.01)

    def test_expected_non_error_record_is_unchanged(self) -> None:
        record = {"schema": "fixture.v1", "kind": "loaded"}
        self.assertEqual(
            record,
            read_json(FakeSerial(record), "fixture.v1", "loaded", 0.01),
        )


if __name__ == "__main__":
    unittest.main()
