#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_product_home_hil.py")
    spec = importlib.util.spec_from_file_location("product_home_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class ProductHomeHilRunnerTests(unittest.TestCase):
    def test_current_home_includes_lab_before_device(self) -> None:
        self.assertEqual(
            ("library", "lab", "device"), RUNNER.HOME_ITEMS[-3:])

    def test_fixture_pin_is_wiped_in_place(self) -> None:
        pin = bytearray((7, 0, 4, 2, 8, 1))
        RUNNER.wipe_pin(pin)
        self.assertEqual(bytearray(6), pin)

    def test_read_only_query_retries_one_transport_timeout(self) -> None:
        class Device:
            resets = 0

            def reset_input_buffer(self) -> None:
                self.resets += 1

        device = Device()
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
        self.assertEqual(1, device.resets)
        synchronize.assert_called_once_with(device, 10.0)

    def test_read_only_query_never_exceeds_bound(self) -> None:
        device = types.SimpleNamespace(reset_input_buffer=lambda: None)
        with patch.object(
                RUNNER, "query", side_effect=TimeoutError("offline")), \
                patch.object(RUNNER, "synchronize_console"):
            with self.assertRaisesRegex(TimeoutError, "offline"):
                RUNNER.read_only_query(
                    device, b"read-only.state", "state.v1", "state")


if __name__ == "__main__":
    unittest.main()
