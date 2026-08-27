#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


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
    def test_boot_acceptance_requires_bounded_input_probe_accounting(self) -> None:
        ready = {
            "version": "test", "app_elf_sha256": "a" * 64,
            "buzzer_inactive": True, "input_detected": True,
            "input_probe_attempts": 2,
            "input_probe_transient_retries": 1,
        }
        recovery = {
            "status": "admitted", "enrolled": True,
            "expected_fingerprint": CID, "observed_fingerprint": CID,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "blocked_write_attempts": 0,
            "catalog_admitted": True, "cleanup_complete": True,
            "physical_write_calls": 0, "generation": 1,
            "attempts": 1, "transient_retries": 0,
        }
        self.assertEqual(
            [], RUNNER.boot_failures(ready, recovery, "test", "a" * 64, CID)
        )
        ready["input_probe_transient_retries"] = 0
        self.assertTrue(
            RUNNER.boot_failures(ready, recovery, "test", "a" * 64, CID)
        )

    def test_running_acceptance_requires_exact_real_bounded_accounting(self) -> None:
        state = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_simulated": False, "survey_persistent": True,
            "survey_workflow_state": "running", "survey_pipeline_status": "drained",
            "survey_product_status": "running", "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_store_status": "permitted",
            "survey_product_admission_status": "permitted",
            "survey_product_expected_cid": CID,
            "survey_product_observed_cid": CID,
            "survey_product_identity_status": "valid",
            "survey_product_identity_attempts": 1,
            "survey_product_identity_transient_retries": 0,
            "survey_scan_status": "valid", "survey_scan_rejected": 0,
            "survey_scan_dropped": 0, "survey_dropped": 0,
            "survey_queue_depth": 0, "survey_product_cleanup_complete": False,
            "survey_observations": 17, "survey_scan_accepted": 10,
            "survey_ble_scan_accepted": 7,
            "survey_forwarded": 17, "survey_product_cached_free_bytes": 2_000_000,
            "survey_product_capacity_bytes": 4_000_000,
            "survey_product_worker_ready": True,
            "survey_product_source_active": True,
            "survey_product_scan_cycles": 1,
            "survey_product_start_action_us": 250,
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
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": True,
            "survey_product_source_active": False,
            "survey_product_stop_action_us": 300,
            "library_persistent": True, "library_simulated": False,
            "survey_generation": 8, "library_generation": 8,
        }
        self.assertEqual([], RUNNER.committed_failures(committed, 7))
        committed["survey_generation"] = 9
        self.assertTrue(RUNNER.committed_failures(committed, 7))

    def test_running_detail_back_preserves_session_and_meets_budget(self) -> None:
        detail = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_view": "detail", "survey_workflow_state": "running",
            "survey_running": True, "survey_observations": 17,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": False,
            "survey_product_source_active": True,
            "survey_product_scan_cycles": 2,
        }
        self.assertEqual([], RUNNER.detail_failures(detail, 17, 2))
        detail["survey_running"] = False
        self.assertTrue(RUNNER.detail_failures(detail, 17, 2))

        list_state = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_view": "list", "survey_workflow_state": "running",
            "survey_running": True, "survey_observations": 17,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": False,
            "survey_product_source_active": True,
        }
        self.assertEqual(
            [], RUNNER.list_after_detail_failures(list_state, 17, 99.5)
        )
        self.assertTrue(
            RUNNER.list_after_detail_failures(list_state, 17, 150.1)
        )

    def test_release_pause_is_stable_and_radio_inactive(self) -> None:
        paused = {
            "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
            "survey_view": "list", "survey_filter_focused": True,
            "survey_workflow_state": "running", "survey_running": True,
            "survey_product_status": "paused",
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": False,
            "survey_product_source_active": False,
            "survey_scan_rejected": 0, "survey_scan_dropped": 0,
            "survey_ble_scan_rejected": 0, "survey_ble_scan_dropped": 0,
            "survey_dropped": 0, "survey_queue_depth": 0,
            "survey_observations": 17, "survey_product_scan_cycles": 1,
        }
        self.assertEqual([], RUNNER.paused_failures(paused, 17, 1))
        paused["survey_view"] = "detail"
        paused["survey_filter_focused"] = False
        self.assertEqual(
            [], RUNNER.paused_detail_failures(paused, 17, 1)
        )
        paused["survey_product_source_active"] = True
        self.assertTrue(RUNNER.paused_detail_failures(paused, 17, 1))

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

    def test_cid_autodiscovery_requires_exact_admitted_enrollment(self) -> None:
        recovery = {
            "status": "admitted", "enrolled": True,
            "expected_fingerprint": CID, "observed_fingerprint": CID,
            "fingerprint_matched": True,
        }
        self.assertEqual(CID, RUNNER.resolve_expected_cid(None, recovery))
        recovery["observed_fingerprint"] = "0" * 32
        with self.assertRaisesRegex(ValueError, "admitted exact-card"):
            RUNNER.resolve_expected_cid(None, recovery)

    def test_best_effort_cleanup_backs_out_of_live_detail(self) -> None:
        states = [
            {
                "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
                "survey_view": "detail", "survey_product_status": "running",
                "survey_product_backend_open": False,
                "survey_product_storage_mounted": False,
                "survey_product_source_active": True,
            },
            {
                "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
                "survey_view": "list", "survey_product_status": "running",
                "survey_product_backend_open": False,
                "survey_product_storage_mounted": False,
                "survey_product_source_active": True,
            },
            {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
                "survey_product_backend_open": False,
                "survey_product_storage_mounted": False,
                "survey_product_source_active": False,
            },
        ]
        current = {"value": states[0]}

        def fake_query(*_: Any, **__: Any) -> dict[str, Any]:
            return current["value"]

        def fake_action(_: Any, name: str) -> dict[str, Any]:
            self.assertEqual("back", name)
            current["value"] = (
                states[1] if current["value"] is states[0] else states[2]
            )
            return current["value"]

        with patch.object(RUNNER, "query", side_effect=fake_query), patch.object(
                RUNNER, "action", side_effect=fake_action):
            cleanup = RUNNER.best_effort_cleanup(object(), timeout=0.5)
        self.assertTrue(cleanup["complete"])
        self.assertEqual(2, len(cleanup["actions"]))

    def test_wait_ui_state_times_out_with_last_state(self) -> None:
        with patch.object(RUNNER, "query", return_value={"page": "survey"}), \
                patch.object(RUNNER.time, "sleep", return_value=None):
            with self.assertRaisesRegex(TimeoutError, "last state"):
                RUNNER.wait_ui_state(
                    object(), lambda state: state.get("page") == "home",
                    0.001, "not home"
                )

    def test_focus_start_uses_public_plan_navigation(self) -> None:
        states = [
            {
                "page": "survey", "survey_workflow_state": "setup",
                "survey_setup_view": "plan", "survey_setup_selection": 0,
            },
            {
                "page": "survey", "survey_workflow_state": "setup",
                "survey_setup_view": "plan", "survey_setup_selection": 1,
            },
            {
                "page": "survey", "survey_workflow_state": "setup",
                "survey_setup_view": "plan", "survey_setup_selection": 2,
            },
        ]
        calls: list[str] = []

        def fake_action(_: Any, name: str) -> dict[str, Any]:
            calls.append(name)
            return states[len(calls)]

        with patch.object(RUNNER, "query", return_value=states[0]), \
                patch.object(RUNNER, "action", side_effect=fake_action):
            focused = RUNNER.focus_survey_start(object())
        self.assertEqual(2, focused["survey_setup_selection"])
        self.assertEqual(["down", "down"], calls)

    def test_focus_start_rejects_sources_or_stuck_plan(self) -> None:
        stuck = {
            "page": "survey", "survey_workflow_state": "setup",
            "survey_setup_view": "sources", "survey_setup_selection": 0,
        }
        with patch.object(RUNNER, "query", return_value=stuck), \
                patch.object(RUNNER, "action", return_value=stuck):
            with self.assertRaisesRegex(RuntimeError, "public Survey Start"):
                RUNNER.focus_survey_start(object())

    def test_current_product_route_opens_wifi_visit(self) -> None:
        home = {
            "page": "home", "selection": 0, "selected_id": "wifi",
            "runtime_owner": "none", "lease_mask": 0,
        }
        states = [
            {
                "page": "survey", "wifi_product_view": "menu",
                "wifi_product_selection": 0, "runtime_owner": "wifi",
            },
            {
                "page": "survey", "wifi_product_view": "menu",
                "wifi_product_selection": 1, "runtime_owner": "wifi",
            },
            {
                "page": "survey", "wifi_product_view": "menu",
                "wifi_product_selection": 2, "runtime_owner": "wifi",
            },
            {
                "page": "survey", "wifi_product_view": "menu",
                "wifi_product_selection": 3, "runtime_owner": "wifi",
            },
            {
                "page": "survey", "wifi_product_view": "visit",
                "wifi_product_selection": 3, "runtime_owner": "survey",
                "lease_mask": 15, "survey_simulated": False,
                "survey_persistent": True, "survey_product_selected": True,
                "survey_workflow_state": "setup",
                "survey_product_backend_open": False,
                "survey_product_storage_mounted": False,
                "survey_product_cleanup_complete": True,
                "survey_product_worker_ready": True,
                "survey_product_source_active": False,
            },
        ]
        calls: list[str] = []

        def fake_action(_: Any, name: str) -> dict[str, Any]:
            calls.append(name)
            return states[len(calls) - 1]

        trace: list[dict[str, Any]] = []
        with patch.object(RUNNER, "normalize_home", return_value=home), \
                patch.object(RUNNER, "action", side_effect=fake_action):
            setup = RUNNER.open_product_survey_visit(object(), trace)
        self.assertEqual(["right", "down", "down", "down", "right"], calls)
        self.assertEqual([], RUNNER.setup_failures(setup))
        self.assertEqual(states, trace)

    def test_current_product_route_rejects_non_wifi_home(self) -> None:
        with patch.object(
                RUNNER, "normalize_home",
                return_value={"page": "home", "selected_id": "ble"}):
            with self.assertRaisesRegex(RuntimeError, "Home Wi-Fi"):
                RUNNER.open_product_survey_visit(object())

    def test_capture_retries_one_transient_usb_timeout(self) -> None:
        class Device:
            resets = 0

            def reset_input_buffer(self) -> None:
                self.resets += 1

        device = Device()
        completed = {"frame_begin": {}, "frame_end": {}, "state": {}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
                RUNNER, "_capture_once",
                side_effect=[TimeoutError("short frame"), completed]), patch.object(
                    RUNNER, "synchronize_capture_console") as synchronize:
            record = RUNNER.capture(device, Path(directory), "screen")
        self.assertEqual(2, record["transport_attempts"])
        self.assertEqual(1, record["transport_transient_retries"])
        self.assertEqual(["short frame"], record["transport_transient_errors"])
        self.assertEqual(1, device.resets)
        synchronize.assert_called_once_with(device)


if __name__ == "__main__":
    unittest.main()
