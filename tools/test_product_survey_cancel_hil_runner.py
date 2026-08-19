#!/usr/bin/env python3
"""Host tests for active-scan Product Survey cancellation assertions."""

from __future__ import annotations

import copy
import unittest

from run_1x_product_survey_cancel_hil import (
    active_scan_failures,
    cancel_ack_failures,
    cancelled_failures,
    unchanged_recovery_failures,
)


CID = "FE343253440000002000000055019CB7"


class ProductSurveyCancelHilTests(unittest.TestCase):
    def active(self) -> dict[str, object]:
        return {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_workflow_state": "running",
            "survey_product_status": "running",
            "survey_product_worker_ready": True,
            "survey_product_source_active": True,
            "survey_product_scan_active": True,
            "survey_product_cancel_requested_during_scan": False,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_expected_cid": CID,
            "survey_product_observed_cid": CID,
            "survey_product_identity_status": "valid",
            "survey_product_identity_attempts": 1,
            "survey_product_identity_transient_retries": 0,
            "survey_product_start_action_us": 15,
        }

    def cancel_ack(self) -> dict[str, object]:
        return {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_workflow_state": "running",
            "survey_product_status": "cancelling",
            "survey_product_source_active": True,
            "survey_product_cancel_requested_during_scan": True,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_stop_action_us": 12,
        }

    def cancelled(self) -> dict[str, object]:
        return {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "survey_product_status": "cancelled",
            "survey_product_source_active": False,
            "survey_product_scan_active": False,
            "survey_product_cancel_requested_during_scan": True,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": True,
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
        self.assertEqual(active_scan_failures(self.active(), CID), [])
        self.assertEqual(cancel_ack_failures(self.cancel_ack(), 100.0), [])
        self.assertEqual(cancelled_failures(self.cancelled()), [])
        recovery = self.recovery()
        self.assertEqual(unchanged_recovery_failures(recovery, recovery, CID), [])

    def test_rejects_cancel_outside_active_scan(self) -> None:
        state = self.cancel_ack()
        state["survey_product_cancel_requested_during_scan"] = False
        self.assertTrue(cancel_ack_failures(state, 100.0))

    def test_rejects_live_resource_or_scan_after_terminal(self) -> None:
        state = self.cancelled()
        state["survey_product_scan_active"] = True
        state["lease_mask"] = 15
        self.assertTrue(cancelled_failures(state))

    def test_rejects_generation_change(self) -> None:
        before = self.recovery()
        after = copy.deepcopy(before)
        after["generation"] = 69
        self.assertTrue(unchanged_recovery_failures(before, after, CID))

    def test_rejects_latency_overflow(self) -> None:
        self.assertTrue(cancel_ack_failures(self.cancel_ack(), 151.0))


if __name__ == "__main__":
    unittest.main()
