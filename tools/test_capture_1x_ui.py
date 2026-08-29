#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest

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
