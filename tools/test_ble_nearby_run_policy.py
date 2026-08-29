#!/usr/bin/env python3
"""Adversarial unit tests for Bluetooth Nearby evidence claims."""

import unittest

from ble_nearby_run_policy import (
    boot_recovery_continuity,
    storage_measurement_scope_valid,
)


class BleNearbyRunPolicyTest(unittest.TestCase):
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
