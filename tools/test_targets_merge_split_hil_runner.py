#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
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
