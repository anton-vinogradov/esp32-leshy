#!/usr/bin/env python3
"""Host contracts for the declarative HIL scenario boundary."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_hil_scenario as hil  # noqa: E402


class HilScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = json.loads((
            ROOT / "tests/hil/scenarios/infrared-passive-no-signal.json"
        ).read_text(encoding="utf-8"))
        self.ports = {"candidate": "/dev/candidate"}

    def test_repository_scenario_is_valid_for_one_board(self) -> None:
        hil.validate_scenario(self.scenario, self.ports)

    def test_required_fixture_is_fail_closed_until_bound(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario["devices"]["fixture"]["required"] = True
        with self.assertRaisesRegex(ValueError, "fixture"):
            hil.validate_scenario(scenario, self.ports)
        hil.validate_scenario(
            scenario, {**self.ports, "fixture": "/dev/fixture"})

    def test_duplicate_and_missing_candidate_ports_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            hil.parse_ports(["candidate=/dev/a", "candidate=/dev/b"])
        with self.assertRaisesRegex(ValueError, "candidate"):
            hil.parse_ports(["fixture=/dev/b"])

    def test_command_injection_and_path_escape_are_rejected(self) -> None:
        for replacement in (
            {"id": "bad-action", "op": "action", "name": "right\nmetrics"},
            {"id": "bad-query", "op": "query", "command": "metrics\nui.key right",
             "response_schema": "leshy.boot.v1"},
            {"id": "bad-capture", "op": "capture", "name": "../outside"},
        ):
            scenario = copy.deepcopy(self.scenario)
            scenario["steps"][0] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):
                    hil.validate_scenario(scenario, self.ports)

    def test_sleep_and_step_count_are_bounded(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario["steps"][0] = {
            "id": "too-long", "op": "sleep", "seconds": 60.001,
        }
        with self.assertRaisesRegex(ValueError, "0..60"):
            hil.validate_scenario(scenario, self.ports)
        scenario["steps"] = [
            {"id": f"step-{index}", "op": "sleep", "seconds": 0}
            for index in range(257)
        ]
        with self.assertRaisesRegex(ValueError, "1..256"):
            hil.validate_scenario(scenario, self.ports)

    def test_numeric_checks_are_deterministic(self) -> None:
        record = {"samples": 345272, "nested": {"state": "timed_out"}}
        self.assertEqual([], hil.evaluate_checks(record, [
            {"path": "samples", "op": "gte", "value": 100000},
            {"path": "nested.state", "op": "eq", "value": "timed_out"},
        ], "terminal"))
        failures = hil.evaluate_checks(record, [
            {"path": "samples", "op": "lt", "value": 1},
        ], "terminal")
        self.assertEqual(1, len(failures))


if __name__ == "__main__":
    unittest.main()
