#!/usr/bin/env python3
"""Host regression for the cold-start Wi-Fi heap plateau oracle."""

from __future__ import annotations

import unittest

from wifi_heap_plateau_policy import (
    MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES,
    wifi_heap_plateau_failures,
)


class WifiHeapPlateauPolicyTest(unittest.TestCase):
    def test_accepts_measured_cold_initialization_then_exact_plateau(self) -> None:
        self.assertEqual([], wifi_heap_plateau_failures(
            66_664, 59_320, 59_320, 142_284, 142_284))

    def test_accepts_already_warm_exact_image_reuse(self) -> None:
        self.assertEqual([], wifi_heap_plateau_failures(
            59_320, 59_320, 59_320, 142_284, 142_284))

    def test_rejects_more_than_bounded_process_lifetime_initialization(self) -> None:
        failures = wifi_heap_plateau_failures(
            70_000,
            70_000 - MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES - 1,
            70_000 - MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES - 1,
            142_284, 142_284)
        self.assertEqual(1, len(failures))
        self.assertIn("unbounded", failures[0])

    def test_rejects_post_warm_leak_and_total_change(self) -> None:
        failures = wifi_heap_plateau_failures(
            66_664, 59_320, 59_316, 142_284, 142_280)
        self.assertIn(
            "heap changed after the second complete Wi-Fi cycle", failures)
        self.assertIn("heap total changed between Wi-Fi cycles", failures)

    def test_rejects_incomplete_or_boolean_measurements(self) -> None:
        self.assertEqual(
            ["heap measurements are incomplete"],
            wifi_heap_plateau_failures(
                66_664, None, 59_320, 142_284, 142_284))
        self.assertEqual(
            ["heap measurements are incomplete"],
            wifi_heap_plateau_failures(
                True, 59_320, 59_320, 142_284, 142_284))


if __name__ == "__main__":
    unittest.main()
