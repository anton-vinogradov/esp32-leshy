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
    path = Path(__file__).with_name("run_1x_airspace_guard_hil.py")
    spec = importlib.util.spec_from_file_location(
        "airspace_guard_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class AirspaceGuardHilRunnerTests(unittest.TestCase):
    def test_navigation_action_recovers_lost_ack_without_replay(self) -> None:
        device = object()
        recovered = {"page": "survey", "wifi_product_view": "menu"}
        with patch.object(
                RUNNER, "raw_action",
                side_effect=TimeoutError("lost UI ACK")) as raw_action, \
                patch.object(
                    RUNNER, "read_only_query",
                    return_value=recovered) as read_state:
            state = RUNNER.action(device, "right")
        raw_action.assert_called_once_with(device, "right", timeout=15.0)
        read_state.assert_called_once_with(
            device, b"ui.state", "leshy.ui.v1", "state",
            timeout=5.0, maximum_attempts=3)
        self.assertIs(recovered, state)
        self.assertFalse(state["host_navigation_ack_received"])
        self.assertEqual(1, state["host_navigation_action_writes"])
        self.assertEqual(0, state["host_navigation_action_replays"])

    def test_navigation_action_records_normal_ack(self) -> None:
        device = object()
        acknowledged = {"page": "survey", "wifi_product_view": "menu"}
        with patch.object(
                RUNNER, "raw_action", return_value=acknowledged) as raw_action, \
                patch.object(RUNNER, "read_only_query") as read_state:
            state = RUNNER.action(device, "right", timeout=2.0)
        raw_action.assert_called_once_with(device, "right", timeout=2.0)
        read_state.assert_not_called()
        self.assertIs(acknowledged, state)
        self.assertTrue(state["host_navigation_ack_received"])
        self.assertEqual(0, state["host_navigation_action_replays"])

    def test_read_only_query_retries_one_transport_timeout(self) -> None:
        device = types.SimpleNamespace(reset_input_buffer=lambda: None)
        expected = {"schema": "state.v1", "kind": "state"}
        with patch.object(
                RUNNER, "query",
                side_effect=[TimeoutError("lost response"), expected]), \
                patch.object(RUNNER, "synchronize_console") as synchronize:
            record = RUNNER.read_only_query(
                device, b"state", "state.v1", "state")
        self.assertEqual(2, record["host_transport_attempts"])
        self.assertEqual(1, record["host_transport_transient_retries"])
        self.assertEqual(
            ["lost response"], record["host_transport_transient_errors"])
        synchronize.assert_called_once_with(device, 10.0)


if __name__ == "__main__":
    unittest.main()
