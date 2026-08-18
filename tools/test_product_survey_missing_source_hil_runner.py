#!/usr/bin/env python3
"""Host tests for the Product Survey missing-source HIL assertions."""

from __future__ import annotations

import copy
import unittest

from run_1x_product_survey_missing_source_hil import (
    arm_failures,
    home_failures,
    retry_blocked_failures,
    source_unavailable_failures,
    unchanged_recovery_failures,
)


CID = "FE343253440000002000000055019CB7"


class ProductSurveyMissingSourceHilTests(unittest.TestCase):
    def unavailable(self) -> dict[str, object]:
        return {
            "page": "survey", "runtime_owner": "none", "lease_mask": 0,
            "survey_simulated": False, "survey_persistent": True,
            "survey_workflow_state": "setup", "survey_running": False,
            "survey_observations": 0, "survey_generation": 0,
            "survey_received": 0, "survey_forwarded": 0,
            "survey_dropped": 0, "survey_queue_depth": 0,
            "survey_product_selected": True,
            "survey_product_status": "source_unavailable",
            "survey_product_backend_open": False,
            "survey_product_store_status": "permitted",
            "survey_product_admission_status": "source_unavailable",
            "survey_product_expected_cid": CID,
            "survey_product_observed_cid": CID,
            "survey_product_identity_status": "valid",
            "survey_product_identity_attempts": 1,
            "survey_product_identity_transient_retries": 0,
            "survey_scan_status": "not_started",
            "survey_scan_reported": 0, "survey_scan_read": 0,
            "survey_scan_accepted": 0, "survey_scan_rejected": 0,
            "survey_scan_dropped": 0,
            "survey_product_cleanup_complete": True,
            "survey_product_worker_ready": True,
            "survey_product_source_active": False,
            "survey_product_source_start_attempted": False,
            "survey_product_source_failure_injected": True,
            "survey_product_source_injection_armed": False,
            "survey_product_store_open_attempted": False,
            "survey_product_store_bytes_written": 0,
            "survey_product_scan_active": False,
            "survey_product_cancel_requested_during_scan": False,
            "survey_product_scan_cycles": 0,
            "library_persistent": True,
        }

    def recovery(self) -> dict[str, object]:
        return {
            "status": "admitted", "expected_fingerprint": CID,
            "observed_fingerprint": CID, "fingerprint_matched": True,
            "mounted_read_only": True, "read_only_guaranteed": True,
            "catalog_admitted": True, "cleanup_complete": True,
            "blocked_write_attempts": 0, "physical_write_calls": 0,
            "owned_after": 0, "generation": 68, "observations": 25,
        }

    def test_valid_contract(self) -> None:
        arm = {
            "status": "armed", "one_shot": True, "armed": True,
            "worker_idle": True, "ui_home": True,
            "runtime_owner": "none", "lease_mask": 0,
            "hardware_touched": False, "source_started": False,
            "storage_mounted": False, "storage_written": False,
        }
        self.assertEqual(arm_failures(arm), [])
        unavailable = self.unavailable()
        self.assertEqual(source_unavailable_failures(unavailable, CID), [])
        retry = {**unavailable, "action": "select", "changed": False,
                 "runtime_event": "source_unavailable_waiting_back"}
        self.assertEqual(retry_blocked_failures(retry, CID), [])
        home = {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "survey_product_status": "cancelled",
            "survey_product_backend_open": False,
            "survey_product_cleanup_complete": True,
            "survey_product_source_active": False,
            "survey_product_scan_active": False,
            "survey_product_source_injection_armed": False,
        }
        self.assertEqual(home_failures(home), [])
        recovery = self.recovery()
        self.assertEqual(
            unchanged_recovery_failures(recovery, recovery, CID), []
        )

    def test_rejects_hidden_source_start_or_store_open(self) -> None:
        state = self.unavailable()
        state["survey_product_source_start_attempted"] = True
        state["survey_product_store_open_attempted"] = True
        self.assertTrue(source_unavailable_failures(state, CID))

    def test_rejects_leaked_resources_or_writes(self) -> None:
        state = self.unavailable()
        state["lease_mask"] = 15
        state["survey_product_store_bytes_written"] = 1
        self.assertTrue(source_unavailable_failures(state, CID))

    def test_rejects_hidden_retry(self) -> None:
        state = self.unavailable()
        state.update({"action": "select", "changed": True,
                      "runtime_event": "product_survey_preparing"})
        self.assertTrue(retry_blocked_failures(state, CID))

    def test_rejects_generation_change(self) -> None:
        before = self.recovery()
        after = copy.deepcopy(before)
        after["generation"] = 69
        self.assertTrue(unchanged_recovery_failures(before, after, CID))


if __name__ == "__main__":
    unittest.main()
