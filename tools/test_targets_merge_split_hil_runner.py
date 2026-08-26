#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import hashlib
import struct
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_targets_merge_split_hil.py")
    spec = importlib.util.spec_from_file_location(
        "targets_merge_split_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class TargetsMergeSplitHilRunnerTests(unittest.TestCase):
    @staticmethod
    def partition_table(entries: list[tuple[int, int, int, int, str]]) -> bytes:
        payload = bytearray(b"\xff" * RUNNER.PARTITION_TABLE_SIZE)
        for index, (kind, subtype, offset, size, label) in enumerate(entries):
            payload[index * 32:(index + 1) * 32] = struct.pack(
                "<HBBLL16sL", RUNNER.PARTITION_MAGIC, kind, subtype,
                offset, size, label.encode("ascii").ljust(16, b"\0"), 0)
        md5_offset = len(entries) * 32
        payload[md5_offset:md5_offset + 32] = (
            struct.pack("<H", RUNNER.PARTITION_MD5_MAGIC) +
            b"\xff" * 14 + hashlib.md5(payload[:md5_offset]).digest())
        return bytes(payload)

    def test_temporary_partition_layout_requires_exact_inactive_ota1(
            self) -> None:
        entries = [
            (1, 0x02, 0x9000, 0x5000, "nvs"),
            (1, 0x00, 0xE000, 0x2000, "otadata"),
            (0, 0x10, 0x10000, 0x400000, "app0"),
            (0, 0x11, 0x410000, 0x400000, "app1"),
            (1, 0x82, 0x810000, 0x7D0000, "spiffs"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partitions.bin"
            path.write_bytes(self.partition_table(entries))
            layout = RUNNER.validated_partition_layout(path, 3_200_000)
        self.assertEqual(RUNNER.OTA1_OFFSET, layout["app1"]["offset"])
        self.assertEqual(RUNNER.OTA1_SIZE, layout["app1"]["size"])

    def test_factory_table_without_ota1_is_rejected(self) -> None:
        entries = [
            (0, 0x10, 0x10000, 0x330000, "app0"),
            (1, 0x82, 0x340000, 0x230000, "font"),
            (1, 0x82, 0x670000, 0x180000, "spiffs"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "factory-partitions.bin"
            path.write_bytes(self.partition_table(entries))
            with self.assertRaisesRegex(ValueError, "app0|app1"):
                RUNNER.validated_partition_layout(path, 3_200_000)

    def test_read_only_query_retries_one_transport_timeout(self) -> None:
        device = types.SimpleNamespace(reset_input_buffer=lambda: None)
        expected = {"schema": "state.v1", "kind": "state"}
        with patch.object(
                RUNNER, "query",
                side_effect=[TimeoutError("lost response"), expected]), \
                patch.object(RUNNER, "synchronize_console") as synchronize:
            record = RUNNER.read_only_query(
                device, b"read-only.state", "state.v1", "state")
        self.assertEqual(2, record["host_transport_attempts"])
        self.assertEqual(1, record["host_transport_transient_retries"])
        self.assertEqual(
            ["lost response"], record["host_transport_transient_errors"])
        synchronize.assert_called_once_with(device, 10.0)

    def test_read_only_query_never_exceeds_bound(self) -> None:
        device = types.SimpleNamespace(reset_input_buffer=lambda: None)
        with patch.object(
                RUNNER, "query", side_effect=TimeoutError("offline")), \
                patch.object(RUNNER, "synchronize_console"):
            with self.assertRaisesRegex(TimeoutError, "offline"):
                RUNNER.read_only_query(
                    device, b"read-only.state", "state.v1", "state")

    def test_normalize_home_uses_bounded_read_only_query(self) -> None:
        device = object()
        home = {"page": "home", "selection": 0}
        with patch.object(
                RUNNER, "read_only_query", return_value=home) as query_state, \
                patch.object(RUNNER, "action") as action:
            self.assertIs(home, RUNNER.normalize_home(device))
        query_state.assert_called_once_with(
            device, b"ui.state", "leshy.ui.v1", "state")
        action.assert_not_called()

    def test_watchdog_reset_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "watchdog/panic reset"):
            RUNNER.require_non_watchdog_boot(
                {"reset_reason_code": 4}, "cold reopen")
        RUNNER.require_non_watchdog_boot(
            {"reset_reason_code": 3}, "cold reopen")

    def test_target_load_requires_sub_watchdog_phases(self) -> None:
        RUNNER.require_bounded_target_load({
            "load_elapsed_us": 8_100_000,
            "load_watchdog_feeds": 11,
            "load_maximum_phase_us": 1_700_000,
        }, "Targets list")
        with self.assertRaisesRegex(RuntimeError, "invalid load watchdog proof"):
            RUNNER.require_bounded_target_load({
                "load_elapsed_us": 8_100_000,
                "load_watchdog_feeds": 1,
                "load_maximum_phase_us": 5_000_000,
            }, "Targets list")


if __name__ == "__main__":
    unittest.main()
