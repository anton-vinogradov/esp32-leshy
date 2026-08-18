#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_source_timeline_hil.py")
    spec = importlib.util.spec_from_file_location("source_timeline_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


def running_state() -> dict[str, Any]:
    return {
        "survey_timeline_state": "running",
        "survey_timeline_status": "observation_recorded",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": 1,
        "survey_timeline_overflow": 0,
        "survey_timeline_ble_state": "unselected",
        "survey_timeline_ble_duty_permille": 0,
        "survey_timeline_ble_accepted": 0,
        "survey_timeline_ble_dropped": 0,
        "survey_timeline_wifi_state": "scheduled",
        "survey_timeline_wifi_duty_permille": 640,
        "survey_timeline_wifi_accepted": 12,
        "survey_timeline_wifi_dropped": 0,
        "survey_forwarded": 12,
        "survey_timeline_queue_depth": 4,
        "survey_timeline_queue_high_water": 4,
    }


class SourceTimelineHilRunnerTests(unittest.TestCase):
    def test_running_timeline_accepts_both_observable_transition_statuses(self) -> None:
        state = running_state()
        self.assertEqual([], RUNNER.timeline_failures(state, False))
        state["survey_timeline_status"] = "transitioned"
        self.assertEqual([], RUNNER.timeline_failures(state, False))

    def test_running_timeline_rejects_drop_mismatch_and_overflow(self) -> None:
        state = running_state()
        state["survey_timeline_wifi_dropped"] = 1
        state["survey_timeline_overflow"] = 1
        state["survey_timeline_wifi_accepted"] = 11
        self.assertEqual(3, len(RUNNER.timeline_failures(state, False)))

    def test_terminal_timeline_requires_stopped_state_and_closed_window(self) -> None:
        state = running_state()
        state.update({
            "survey_timeline_state": "stopped",
            "survey_timeline_status": "stopped",
            "survey_timeline_wifi_state": "stopped",
            "survey_timeline_queue_depth": 5,
            "survey_timeline_queue_high_water": 5,
        })
        self.assertEqual([], RUNNER.timeline_failures(state, True))
        state["survey_timeline_wifi_state"] = "active"
        self.assertTrue(RUNNER.timeline_failures(state, True))


if __name__ == "__main__":
    unittest.main()
