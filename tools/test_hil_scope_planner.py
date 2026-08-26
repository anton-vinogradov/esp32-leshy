#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
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

    def test_only_explicit_pass_status_counts_as_accepted(self) -> None:
        with tempfile.TemporaryDirectory(dir=MODULE.ROOT) as directory:
            root = Path(directory)
            passing = root / "passing.json"
            partial = root / "partial.json"
            failed = root / "failed.json"
            malformed = root / "malformed.json"
            passing.write_text('{"status":"pass"}', encoding="utf-8")
            partial.write_text(
                '{"status":"pass_delta_positive_source_open"}',
                encoding="utf-8",
            )
            failed.write_text('{"status":"failed"}', encoding="utf-8")
            malformed.write_text('{', encoding="utf-8")
            self.assertTrue(MODULE.is_accepted_evidence(passing))
            self.assertTrue(MODULE.is_accepted_evidence(partial))
            self.assertFalse(MODULE.is_accepted_evidence(failed))
            self.assertFalse(MODULE.is_accepted_evidence(malformed))

    def test_cross_cutting_change_selects_full(self) -> None:
        result = MODULE.plan(
            POLICY, ["firmware/leshy1/src/storage/SessionStore.cpp"],
            stage_end=False, release_candidate=False,
        )
        self.assertEqual(result["scope"], "full")
        self.assertIn("cross_cutting_runtime_change", result["reasons"])

    def test_exact_reviewed_additive_cross_cutting_change_selects_delta(self) -> None:
        review = {
            "id": "additive-codec",
            "rationale": "Adds a backward-compatible value.",
            "reviewed_cross_cutting_sha256": {
                "firmware/leshy1/src/storage/SessionStore.cpp": "unused",
            },
            "required_host_checks": ["codec regression"],
            "required_hil_scenarios": ["adjacent save/reopen"],
        }
        result = MODULE.plan(
            POLICY, ["firmware/leshy1/src/storage/SessionStore.cpp"],
            stage_end=False, release_candidate=False, delta_review=review,
        )
        self.assertEqual(result["scope"], "delta")
        self.assertIn("reviewed_additive_cross_cutting_delta", result["reasons"])

    def test_partial_review_cannot_hide_another_cross_cutting_change(self) -> None:
        review = {
            "id": "partial",
            "rationale": "Only one path was reviewed.",
            "reviewed_cross_cutting_sha256": {
                "firmware/leshy1/src/storage/A.cpp": "unused",
            },
            "required_host_checks": ["one"],
            "required_hil_scenarios": ["one"],
        }
        result = MODULE.plan(
            POLICY,
            ["firmware/leshy1/src/storage/A.cpp",
             "firmware/leshy1/src/storage/B.cpp"],
            stage_end=False, release_candidate=False, delta_review=review,
        )
        self.assertEqual(result["scope"], "full")

    def test_delta_review_hash_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=MODULE.ROOT) as directory:
            relative = str(Path(directory).relative_to(MODULE.ROOT) / "input.cpp")
            (MODULE.ROOT / relative).write_text("current", encoding="utf-8")
            review_path = Path(directory) / "review.json"
            review_path.write_text(
                '{"schema":"leshy.hil_delta_review.v1","id":"stale",'
                '"rationale":"test","reviewed_cross_cutting_sha256":{'
                f'"{relative}":"stale"}},"required_host_checks":["x"],'
                '"required_hil_scenarios":["y"]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "is stale"):
                MODULE.load_delta_review(review_path)

    def test_phase_end_overrides_docs_only(self) -> None:
        result = MODULE.plan(POLICY, ["docs/v1/STATUS.md"], stage_end=True,
                             release_candidate=False, delta_review={
                                 "id": "ignored", "rationale": "ignored",
                                 "reviewed_cross_cutting_sha256": {},
                                 "required_host_checks": ["x"],
                                 "required_hil_scenarios": ["y"],
                             })
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
