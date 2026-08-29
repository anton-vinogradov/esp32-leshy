#!/usr/bin/env python3
"""Focused unit tests for the delayed BLE product-entry HIL gate."""

from __future__ import annotations

import unittest

from ble_nearby_entry_gate import (
    BLE_ENTRY_STABILITY_MARGIN_MS,
    BLE_ENTRY_STABILITY_MINIMUM_MS,
    BLE_ENTRY_STABILITY_SECONDS,
    BLE_HOST_SHUTDOWN_TIMEOUT_MS,
    BLE_SCAN_RETRY_BUDGET_MS,
    NIMBLE_SYNC_TIMEOUT_MS,
    ble_entry_failure,
    ble_entry_stability_evidence_failure,
)


class BleEntryGateTests(unittest.TestCase):
    def stable(self) -> dict[str, object]:
        return {
            "page": "survey",
            "ble_product_view": "devices",
            "runtime_owner": "ble",
            "lease_mask": 15,
            "survey_product_status": "running",
            "survey_product_admission_status": "permitted",
            "ble_begin_stage": "ready",
            "ble_begin_error": 0,
        }

    def test_accepts_stable_ble_product_route(self) -> None:
        self.assertIsNone(ble_entry_failure(self.stable()))

    def test_rejects_the_observed_bounce_to_home(self) -> None:
        state = self.stable()
        state["page"] = "home"
        state["runtime_owner"] = "none"
        state["lease_mask"] = 0
        self.assertEqual(ble_entry_failure(state), "page_bounced")

    def test_unavailable_reason_retains_only_bounded_diagnostics(self) -> None:
        state = self.stable()
        state.update({
            "survey_product_status": "source_unavailable",
            "survey_product_admission_status": "source_unavailable",
            "ble_begin_stage": "host_sync",
            "ble_begin_error": 263,
            "ble_begin_heap_free_before": 100000,
            "ble_begin_heap_free_after": 75000,
            "ble_begin_heap_largest_before": 50000,
            "ble_begin_heap_largest_after": 30000,
            "untrusted_identity": "must-not-escape",
        })
        reason = ble_entry_failure(state)
        self.assertIsNotNone(reason)
        self.assertIn("stage=host_sync,error=263", reason)
        self.assertNotIn("must-not-escape", reason)

    def test_stability_budget_covers_complete_bounded_lifecycle(self) -> None:
        bounded_ms = (
            NIMBLE_SYNC_TIMEOUT_MS + BLE_HOST_SHUTDOWN_TIMEOUT_MS +
            BLE_SCAN_RETRY_BUDGET_MS)
        self.assertEqual(13100, bounded_ms)
        self.assertEqual(1900, BLE_ENTRY_STABILITY_MARGIN_MS)
        self.assertEqual(15000, BLE_ENTRY_STABILITY_MINIMUM_MS)
        self.assertEqual(15.0, BLE_ENTRY_STABILITY_SECONDS)

    def test_retained_stability_rejects_old_short_window(self) -> None:
        evidence = {
            "duration_ms": 6500,
            "samples": 2,
            "final_state": self.stable(),
        }
        self.assertEqual(
            "bounded_lifecycle_unproven",
            ble_entry_stability_evidence_failure(evidence))

    def test_retained_stability_accepts_full_window(self) -> None:
        evidence = {
            "duration_ms": BLE_ENTRY_STABILITY_MINIMUM_MS,
            "samples": 2,
            "final_state": self.stable(),
        }
        self.assertIsNone(ble_entry_stability_evidence_failure(evidence))


if __name__ == "__main__":
    unittest.main()
