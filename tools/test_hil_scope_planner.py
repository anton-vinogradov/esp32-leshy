#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("plan_hil_scope.py")
SPEC = importlib.util.spec_from_file_location("plan_hil_scope", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


POLICY = {
    "anchor_evidence": "tests/hil/evidence/anchor.json",
    "full_after_accepted_deltas": 15,
    "firmware_prefixes": ["firmware/", "src/", "tests/native/"],
    "hil_prefixes": ["diagnostics/hil_probe/", "tests/hil/", "tools/run_1x_"],
    "host_only_prefixes": [
        "docs/", "README.md", "README.ru.md", "tools/check_",
        "tools/plan_hil_scope.py", "tools/test_", "tests/hil/evidence/",
        "tests/hil/hil-cadence.v1.json",
    ],
    "cross_cutting_prefixes": [
        "firmware/leshy1/src/kernel/safety/",
        "firmware/leshy1/src/storage/",
    ],
    "execution_rules": {"none": "host", "delta": "target", "full": "matrix"},
}


class HilScopePlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = MODULE.accepted_evidence_since
        MODULE.accepted_evidence_since = lambda _anchor: []

    def tearDown(self) -> None:
        MODULE.accepted_evidence_since = self.original

    def test_docs_only_never_touches_board(self) -> None:
        result = MODULE.plan(POLICY, ["docs/v1/STATUS.md"], stage_end=False,
                             release_candidate=False)
        self.assertEqual(result["scope"], "none")
        self.assertEqual(result["flash_policy"], "no_flash")

    def test_local_firmware_change_selects_delta(self) -> None:
        result = MODULE.plan(
            POLICY, ["firmware/leshy1/src/ui/UiController.cpp"],
            stage_end=False, release_candidate=False,
        )
        self.assertEqual(result["scope"], "delta")
        self.assertEqual(result["flash_policy"],
                         "flash_once_only_if_candidate_image_changed")

    def test_policy_and_retained_evidence_are_host_only(self) -> None:
        result = MODULE.plan(
            POLICY,
            ["tests/hil/hil-cadence.v1.json",
             "tests/hil/evidence/checkpoint.json"],
            stage_end=False, release_candidate=False,
        )
        self.assertEqual(result["scope"], "none")

    def test_cross_cutting_change_selects_full(self) -> None:
        result = MODULE.plan(
            POLICY, ["firmware/leshy1/src/storage/SessionStore.cpp"],
            stage_end=False, release_candidate=False,
        )
        self.assertEqual(result["scope"], "full")
        self.assertIn("cross_cutting_runtime_change", result["reasons"])

    def test_phase_end_overrides_docs_only(self) -> None:
        result = MODULE.plan(POLICY, ["docs/v1/STATUS.md"], stage_end=True,
                             release_candidate=False)
        self.assertEqual(result["scope"], "full")

    def test_fifteenth_accepted_delta_selects_full(self) -> None:
        MODULE.accepted_evidence_since = lambda _anchor: [
            f"tests/hil/evidence/checkpoint-{index}.json" for index in range(15)
        ]
        result = MODULE.plan(POLICY, [], stage_end=False,
                             release_candidate=False)
        self.assertEqual(result["scope"], "full")
        self.assertIn("accepted_delta_interval", result["reasons"])


if __name__ == "__main__":
    unittest.main()
