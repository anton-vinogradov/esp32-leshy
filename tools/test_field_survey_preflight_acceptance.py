#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import unittest

import check_field_survey_preflight_acceptance as checker


class FieldSurveyPreflightAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(checker.EVIDENCE.read_text(encoding="utf-8"))

    def test_current_evidence_passes(self) -> None:
        self.assertEqual(checker.failures(copy.deepcopy(self.record)), [])

    def test_ble_timeout_cannot_pass(self) -> None:
        mutated = copy.deepcopy(self.record)
        mutated["positive"]["ble_begin_stage"] = "host_sync"
        mutated["positive"]["ble_begin_error"] = 263
        self.assertTrue(checker.failures(mutated))

    def test_drop_write_or_leak_cannot_pass(self) -> None:
        for field, value in (
            ("pipeline_dropped", 1),
            ("writes_committed", 1),
            ("final_lease_mask", 15),
            ("hil_active_after", True),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.record)
                mutated["positive"][field] = value
                self.assertTrue(checker.failures(mutated))

    def test_preflight_cannot_claim_capability_gate(self) -> None:
        mutated = copy.deepcopy(self.record)
        mutated["scope"]["capability_gate_eligible"] = True
        self.assertTrue(checker.failures(mutated))


if __name__ == "__main__":
    unittest.main()
