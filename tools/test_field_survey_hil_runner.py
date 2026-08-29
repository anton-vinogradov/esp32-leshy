#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_field_survey_hil.py")
    spec = importlib.util.spec_from_file_location("field_survey_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


def result(status: str = "first_visit") -> dict[str, Any]:
    record = {
        "active": True,
        "previous_available": status == "compared",
        "compare_previous": status == "compared",
        "status": status,
        "build_status": "complete",
        "complete": True,
        "current_unique": 5,
        "baseline_unique": 0,
        "seen_again": 0,
        "new_this_visit": 5,
        "missing_this_visit": 0,
        "wifi_access_points": 2,
        "wifi_stations": 1,
        "ble_devices": 2,
        "session_id_exact": True,
        "session_stopped": True,
        "radio_touched": False,
        "storage_touched": False,
    }
    if status == "compared":
        record.update({
            "baseline_unique": 4,
            "seen_again": 3,
            "new_this_visit": 2,
            "missing_this_visit": 1,
        })
    return record


class FieldSurveyHilRunnerTests(unittest.TestCase):
    def test_first_visit_result_requires_exact_count_accounting(self) -> None:
        record = result()
        self.assertEqual(
            [], RUNNER.field_result_failures(record, "first_visit"))
        record["ble_devices"] = 1
        self.assertTrue(
            RUNNER.field_result_failures(record, "first_visit"))

    def test_revisit_result_requires_set_arithmetic_and_exact_baseline(self) -> None:
        record = result("compared")
        self.assertEqual(
            [], RUNNER.field_result_failures(record, "compared", 4))
        record["missing_this_visit"] = 2
        self.assertTrue(
            RUNNER.field_result_failures(record, "compared", 4))

    def test_navigation_timeout_is_not_replayed(self) -> None:
        recovered = {"page": "survey"}
        with patch.object(RUNNER, "raw_action", side_effect=TimeoutError("lost")), \
             patch.object(RUNNER, "read_only_query", return_value=recovered):
            state = RUNNER.action(object(), "down")
        self.assertEqual(1, state["host_navigation_action_writes"])
        self.assertEqual(0, state["host_navigation_action_replays"])
        self.assertFalse(state["host_navigation_ack_received"])

    def test_hil_begin_timeout_recovers_read_only_without_replay(self) -> None:
        recovered = {
            "session_id": "1" * 32,
            "active": True,
            "app_elf_sha256": "a" * 64,
            "firmware_version": "test",
        }
        with patch.object(RUNNER, "query", side_effect=TimeoutError("lost")), \
             patch.object(RUNNER, "read_only_query", return_value=recovered):
            state = RUNNER.begin_hil(
                object(), "1" * 32, "a" * 64, "test")
        self.assertEqual(1, state["host_begin_action_writes"])
        self.assertEqual(0, state["host_begin_action_replays"])
        self.assertFalse(state["host_begin_ack_received"])

    def test_runner_is_single_flash_and_contains_physical_negative(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        self.assertEqual(1, source.count("flash_candidate(args.port"))
        self.assertIn("survey.field-visit.test-incomplete once", source)
        self.assertIn('"survey_product_wifi_scan_cycles"', source)
        self.assertIn('"survey_product_ble_scan_cycles"', source)
        self.assertIn('"page": "home", "runtime_owner": "none", "lease_mask": 0',
                      source)


if __name__ == "__main__":
    unittest.main()
