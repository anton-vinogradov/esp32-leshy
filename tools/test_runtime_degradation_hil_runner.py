#!/usr/bin/env python3
"""Host tests for the runtime-degradation HIL assertions."""

from __future__ import annotations

import sys
import types
import unittest

sys.modules.setdefault("capture_1x_ui", types.SimpleNamespace())

from run_1x_runtime_degradation_hil import (  # noqa: E402
    BLE_MASK,
    DUAL_MASK,
    WIFI_MASK,
    committed_failures,
    degraded_failures,
    export_failures,
    injection_failures,
)


class RuntimeDegradationAssertionsTest(unittest.TestCase):
    def degraded(self) -> dict[str, object]:
        return {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_workflow_state": "running",
            "survey_product_status": "running_degraded",
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": False,
            "survey_product_source_active": True,
            "survey_product_selected_source_mask": DUAL_MASK,
            "survey_product_active_source_mask": WIFI_MASK,
            "survey_product_unavailable_source_mask": BLE_MASK,
            "survey_product_source_failure_injected": False,
            "survey_product_runtime_source_failure_injected": True,
            "survey_product_runtime_source_failure_injected_mask": BLE_MASK,
            "survey_product_runtime_source_injection_armed_mask": 0,
            "survey_scan_status": "valid", "survey_scan_reported": 7,
            "survey_scan_read": 7, "survey_scan_accepted": 7,
            "survey_scan_rejected": 0, "survey_scan_dropped": 0,
            "survey_ble_scan_status": "not_started",
            "survey_ble_scan_reported": 0, "survey_ble_scan_read": 0,
            "survey_ble_scan_accepted": 0, "survey_ble_scan_rejected": 0,
            "survey_ble_scan_dropped": 0,
            "survey_product_scan_cycles": 2,
            "survey_product_wifi_scan_cycles": 2,
            "survey_product_ble_scan_cycles": 0,
            "survey_observations": 7, "survey_forwarded": 7,
            "survey_dropped": 0, "survey_queue_depth": 0,
            "survey_timeline_state": "running",
            "survey_timeline_healthy": True,
            "survey_timeline_failure_status": "none",
            "survey_timeline_selected_mask": DUAL_MASK,
            "survey_timeline_queue_depth": 0,
            "survey_timeline_queue_high_water": 1,
            "survey_timeline_overflow": 0,
            "survey_timeline_archived_windows": 6,
            "survey_timeline_wifi_accepted": 7,
            "survey_timeline_wifi_dropped": 0,
            "survey_timeline_ble_state": "unavailable",
            "survey_timeline_ble_accepted": 0,
            "survey_timeline_ble_dropped": 0,
        }

    def committed(self) -> dict[str, object]:
        return {
            **self.degraded(),
            "survey_workflow_state": "result",
            "survey_product_status": "committed",
            "survey_generation": 78,
            "survey_product_backend_open": False,
            "survey_product_cleanup_complete": True,
            "survey_product_source_active": False,
            "survey_timeline_state": "stopped",
            "survey_timeline_archive_status": "finalized",
            "survey_timeline_persisted": True,
            "survey_timeline_archived_windows": 8,
            "survey_timeline_persisted_windows": 8,
            "survey_timeline_retained_windows": 8,
            "survey_timeline_evicted_windows": 0,
        }

    def exported(self) -> dict[str, object]:
        return {
            "status": "valid", "generation": 78, "integrity": "valid",
            "persistent": True, "simulated": False,
            "storage_backend": "persistent_media", "radio_touched": False,
            "session": {
                "schema": "leshy.session.summary.v2",
                "id": "product-passive-live", "observations": 7,
                "dropped": 0, "sources": {"wifi": 7, "ble": 0},
                "timeline": {
                    "selected_mask": DUAL_MASK, "started_us": 100,
                    "stopped_us": 300, "windows": 8, "retained": 8,
                    "evicted": 0, "overflow": 0,
                    "wifi": {
                        "scheduled_us": 80, "active_us": 120,
                        "unavailable_us": 0, "fault_us": 0,
                        "accepted": 7, "dropped": 0, "duty_permille": 600,
                    },
                    "ble": {
                        "scheduled_us": 20, "active_us": 1,
                        "unavailable_us": 179, "fault_us": 0,
                        "accepted": 0, "dropped": 0, "duty_permille": 5,
                    },
                },
            },
            "timeline_windows": [
                {"source": "wifi", "state": "scheduled", "reason": "duty_cycle"},
                {"source": "wifi", "state": "active", "reason": "none"},
                {"source": "ble", "state": "scheduled", "reason": "duty_cycle"},
                {"source": "ble", "state": "active", "reason": "none"},
                {"source": "ble", "state": "unavailable",
                 "reason": "driver_unavailable"},
                {"source": "wifi", "state": "scheduled", "reason": "duty_cycle"},
                {"source": "wifi", "state": "active", "reason": "none"},
                {"source": "wifi", "state": "scheduled", "reason": "duty_cycle"},
            ],
        }

    def test_accepts_exact_degraded_contract(self) -> None:
        injection = {
            "status": "armed", "one_shot": True, "armed_mask": BLE_MASK,
            "worker_idle": True, "ui_home": True,
            "runtime_owner": "none", "lease_mask": 0,
            "hardware_touched": False, "storage_mounted": False,
            "storage_written": False,
        }
        self.assertEqual(injection_failures(injection), [])
        self.assertEqual(degraded_failures(self.degraded()), [])
        self.assertEqual(committed_failures(self.committed(), 78), [])
        self.assertEqual(export_failures(self.exported(), 78, 7), [])

    def test_rejects_hidden_abort_or_fake_ble_data(self) -> None:
        state = self.degraded()
        state["survey_product_status"] = "running"
        state["survey_product_active_source_mask"] = DUAL_MASK
        state["survey_ble_scan_accepted"] = 1
        self.assertTrue(degraded_failures(state))

    def test_rejects_physical_storage_overlap_while_degraded(self) -> None:
        for field in (
                "survey_product_backend_open",
                "survey_product_storage_mounted"):
            with self.subTest(field=field):
                state = self.degraded()
                state[field] = True
                self.assertTrue(degraded_failures(state))

    def test_rejects_physical_storage_overlap_after_commit(self) -> None:
        state = self.committed()
        self.assertEqual([], committed_failures(state, 78))
        state["survey_product_storage_mounted"] = True
        self.assertTrue(committed_failures(state, 78))

    def test_rejects_export_without_retained_unavailability(self) -> None:
        artifact = self.exported()
        artifact["timeline_windows"] = [
            {"source": "wifi", "state": "active", "reason": "none"}
        ] * 8
        self.assertTrue(export_failures(artifact, 78, 7))


if __name__ == "__main__":
    unittest.main()
