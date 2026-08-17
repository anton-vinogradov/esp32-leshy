#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_product_survey_hil.py")
    spec = importlib.util.spec_from_file_location("product_survey_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
CID = "FE343253440000002000000055019CB7"


class ProductSurveyHilRunnerTests(unittest.TestCase):
    def test_running_acceptance_requires_exact_real_bounded_accounting(self) -> None:
        state = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_simulated": False, "survey_persistent": True,
            "survey_workflow_state": "running", "survey_pipeline_status": "drained",
            "survey_product_status": "running", "survey_product_backend_open": True,
            "survey_product_store_status": "permitted",
            "survey_product_admission_status": "permitted",
            "survey_product_expected_cid": CID,
            "survey_product_observed_cid": CID,
            "survey_scan_status": "valid", "survey_scan_rejected": 0,
            "survey_scan_dropped": 0, "survey_dropped": 0,
            "survey_queue_depth": 0, "survey_product_cleanup_complete": False,
            "survey_observations": 17, "survey_scan_accepted": 17,
            "survey_forwarded": 17, "survey_product_cached_free_bytes": 2_000_000,
            "survey_product_capacity_bytes": 4_000_000,
        }
        self.assertEqual([], RUNNER.running_failures(state, CID))
        state["survey_product_observed_cid"] = "0" * 32
        state["survey_scan_dropped"] = 1
        self.assertEqual(2, len(RUNNER.running_failures(state, CID)))

    def test_commit_and_recovery_require_next_exact_generation(self) -> None:
        committed = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_workflow_state": "result", "survey_workflow_status": "committed",
            "survey_pipeline_status": "committed", "survey_product_status": "committed",
            "survey_product_backend_open": False,
            "survey_product_cleanup_complete": True,
            "library_persistent": True, "library_simulated": False,
            "survey_generation": 8, "library_generation": 8,
        }
        self.assertEqual([], RUNNER.committed_failures(committed, 7))
        committed["survey_generation"] = 9
        self.assertTrue(RUNNER.committed_failures(committed, 7))

    def test_boot_parser_ignores_noise_and_keeps_product_record(self) -> None:
        raw = (
            b"noise\n"
            b'{"schema":"leshy.storage.product_boot_recovery.v1",'
            b'"kind":"state","generation":3}\n'
            b'{"schema":"leshy.boot.v1","kind":"ready","version":"x"}\n'
        )
        ready, recovery = RUNNER.parse_boot_records(raw)
        self.assertEqual("x", ready["version"])
        self.assertEqual(3, recovery["generation"])


if __name__ == "__main__":
    unittest.main()
