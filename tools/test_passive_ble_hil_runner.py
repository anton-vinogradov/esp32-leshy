#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_passive_ble_hil.py")
    spec = importlib.util.spec_from_file_location("passive_ble_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


def valid_running() -> dict[str, Any]:
    state: dict[str, Any] = {
        "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
        "survey_workflow_state": "running", "survey_product_status": "running",
        "survey_product_backend_open": True,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": True,
        "survey_product_selected_source_mask": 3,
        "survey_product_active_source_mask": 3,
        "survey_product_unavailable_source_mask": 0,
        "survey_scan_status": "valid", "survey_scan_reported": 12,
        "survey_scan_read": 12, "survey_scan_accepted": 12,
        "survey_scan_rejected": 0, "survey_scan_dropped": 0,
        "survey_ble_scan_status": "valid", "survey_ble_scan_reported": 7,
        "survey_ble_scan_read": 7, "survey_ble_scan_accepted": 7,
        "survey_ble_scan_rejected": 0, "survey_ble_scan_dropped": 0,
        "survey_observations": 19, "survey_forwarded": 19,
        "survey_dropped": 0, "survey_queue_depth": 0,
        "survey_product_wifi_scan_cycles": 1,
        "survey_product_ble_scan_cycles": 1,
        "survey_product_scan_cycles": 1,
        "survey_timeline_state": "running",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": 3,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_wifi_dropped": 0,
        "survey_timeline_ble_dropped": 0,
        "survey_timeline_wifi_accepted": 12,
        "survey_timeline_ble_accepted": 7,
        "survey_timeline_wifi_duty_permille": 420,
        "survey_timeline_ble_duty_permille": 380,
        "survey_timeline_archived_windows": 4,
    }
    return state


def valid_export() -> dict[str, Any]:
    source = {
        "scheduled_us": 600, "active_us": 400,
        "unavailable_us": 0, "fault_us": 0,
        "duty_permille": 400, "accepted": 5, "dropped": 0,
    }
    return {
        "status": "valid", "generation": 75, "integrity": "valid",
        "persistent": True, "simulated": False,
        "storage_backend": "persistent_media", "radio_touched": False,
        "session": {
            "schema": "leshy.session.summary.v2",
            "id": "product-passive-live", "observations": 10, "dropped": 0,
            "sources": {"wifi": 5, "ble": 5},
            "timeline": {
                "selected_mask": 3, "overflow": 0,
                "started_us": 100, "stopped_us": 1100,
                "windows": 10, "retained": 10, "evicted": 0,
                "wifi": dict(source), "ble": dict(source),
            },
        },
        "timeline_windows": [
            {"source": "wifi"}, {"source": "ble"},
            *({"source": "wifi"} for _ in range(8)),
        ],
    }


class PassiveBleHilRunnerTests(unittest.TestCase):
    def test_running_requires_one_cycle_from_both_sources_and_exact_accounting(self) -> None:
        state = valid_running()
        self.assertEqual([], RUNNER.running_failures(state))
        state["survey_ble_scan_accepted"] = 0
        self.assertTrue(RUNNER.running_failures(state))

    def test_running_rejects_degradation_drop_and_missing_cycle(self) -> None:
        state = valid_running()
        state["survey_product_active_source_mask"] = 1
        state["survey_product_unavailable_source_mask"] = 2
        state["survey_ble_scan_dropped"] = 1
        state["survey_product_ble_scan_cycles"] = 0
        self.assertGreaterEqual(len(RUNNER.running_failures(state)), 4)

    def test_export_requires_durable_dual_source_timeline(self) -> None:
        artifact = valid_export()
        self.assertEqual([], RUNNER.export_failures(artifact, 75, 10))
        artifact["session"]["timeline"]["selected_mask"] = 1
        self.assertTrue(RUNNER.export_failures(artifact, 75, 10))

    def test_export_rejects_fabricated_or_missing_ble_evidence(self) -> None:
        artifact = valid_export()
        artifact["session"]["timeline"]["ble"]["accepted"] = 0
        artifact["session"]["sources"]["ble"] = 0
        artifact["timeline_windows"] = [{"source": "wifi"}] * 10
        self.assertGreaterEqual(len(RUNNER.export_failures(artifact, 75, 10)), 3)


if __name__ == "__main__":
    unittest.main()
