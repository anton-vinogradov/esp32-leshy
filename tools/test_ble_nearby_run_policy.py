#!/usr/bin/env python3
"""Adversarial unit tests for Bluetooth Nearby evidence claims."""

import unittest

from ble_nearby_run_policy import (
    boot_recovery_continuity,
    bounded_pipeline_accounting_valid,
    display_signal_signature,
    storage_measurement_scope_valid,
)


class BleNearbyRunPolicyTest(unittest.TestCase):
    def test_bounded_pipeline_requires_exact_explicit_accounting(self) -> None:
        valid = {
            "survey_received": 146,
            "survey_forwarded": 64,
            "survey_dropped": 82,
            "survey_queue_depth": 0,
        }
        self.assertTrue(bounded_pipeline_accounting_valid(valid))
        self.assertFalse(bounded_pipeline_accounting_valid({
            **valid, "survey_dropped": 81,
        }))
        self.assertFalse(bounded_pipeline_accounting_valid({
            **valid, "survey_queue_depth": 1,
        }))
        self.assertFalse(bounded_pipeline_accounting_valid({
            **valid, "survey_received": True,
        }))

    def test_display_signal_signature_uses_rendered_trend_buckets(self) -> None:
        baseline = {
            "rssi_dbm": -73,
            "minimum_rssi_dbm": -74,
            "maximum_rssi_dbm": -73,
            "rssi_trend_db": 1,
        }
        same_pixels = {**baseline, "rssi_trend_db": 0}
        approaching = {**baseline, "rssi_trend_db": 4}
        receding = {**baseline, "rssi_trend_db": -4}
        changed_rssi = {**baseline, "rssi_dbm": -72}
        self.assertEqual(
            display_signal_signature(baseline),
            display_signal_signature(same_pixels),
        )
        self.assertNotEqual(
            display_signal_signature(baseline),
            display_signal_signature(approaching),
        )
        self.assertNotEqual(
            display_signal_signature(baseline),
            display_signal_signature(receding),
        )
        self.assertNotEqual(
            display_signal_signature(baseline),
            display_signal_signature(changed_rssi),
        )

    def test_continuity_does_not_overclaim_global_physical_writes(self) -> None:
        before = {
            "generation": 7,
            "observations": 19,
            "physical_write_calls": 0,
        }
        after = {
            "generation": 7,
            "observations": 19,
            "physical_write_calls": 23,
        }
        self.assertTrue(boot_recovery_continuity(before, after))

    def test_continuity_rejects_observed_boot_recovery_change(self) -> None:
        self.assertFalse(boot_recovery_continuity(
            {"generation": 7, "observations": 19},
            {"generation": 8, "observations": 19},
        ))
        self.assertFalse(boot_recovery_continuity(
            {"generation": 7, "observations": 19},
            {"generation": 7, "observations": 20},
        ))
        self.assertFalse(boot_recovery_continuity({}, {}))
        self.assertFalse(boot_recovery_continuity(
            {"generation": True, "observations": 19},
            {"generation": True, "observations": 19},
        ))

    def test_scope_discloses_unmeasured_product_storage_writes(self) -> None:
        self.assertTrue(storage_measurement_scope_valid({
            "boot_recovery_continuity": True,
            "product_storage_writes_measured": False,
        }))
        self.assertFalse(storage_measurement_scope_valid({
            "boot_recovery_continuity": True,
            "product_storage_writes_measured": False,
            "storage_write_authorized": False,
        }))
        self.assertFalse(storage_measurement_scope_valid({
            "boot_recovery_continuity": True,
            "product_storage_writes_measured": True,
        }))


if __name__ == "__main__":
    unittest.main()
