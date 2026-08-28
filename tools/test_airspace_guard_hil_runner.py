#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_airspace_guard_hil.py")
    spec = importlib.util.spec_from_file_location(
        "airspace_guard_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
START_RUNNER_SOURCE = Path(__file__).with_name(
    "run_1x_airspace_guard_start_regression_hil.py").read_text()


def valid_result_state() -> dict[str, Any]:
    return {
        "capture_state": "result",
        "load_status": "ready",
        "elevated_noise_low_confidence": True,
        "noise_samples_dropped": 0,
        "noise_samples_malformed": 0,
        "malformed_frames": 0,
        "source_read_failures": 0,
        "source_frames_dropped": 0,
        "findings_dropped": 0,
        "inspection_truncated": False,
        "wifi_capture_state": "complete",
        "wifi_driver_error": 0,
        "wifi_cleanup_complete": True,
        "wifi_monitor_active": False,
        "wifi_disconnects_dropped": 0,
        "wifi_identity_dropped": 0,
        "wifi_noise_dropped": 0,
        "wifi_receive_invalid_frames": 0,
        "wifi_identity_malformed_envelope": 0,
        "wifi_identity_malformed_addressing": 0,
        "wifi_identity_malformed_elements": 0,
        "wifi_invalid_frames": 0,
        "wifi_identity_retention_complete": True,
        "wifi_noise_retention_complete": True,
        "ble_worker_control": 0,
        "ble_worker_ready": True,
        "ble_worker_valid": True,
        "ble_worker_status": "complete",
        "ble_cleanup_complete": True,
        "ble_capacity_drop_requested": False,
        "ble_capacity_drop_injected": False,
        "ble_scan_status": "valid",
        "ble_scan_attempts": 1,
        "ble_scan_transient_retries": 0,
        "ble_scan_observed": 10,
        "ble_scan_reported": 10,
        "ble_scan_read": 10,
        "ble_scan_accepted": 10,
        "ble_scan_rejected": 0,
        "ble_scan_dropped": 0,
        "ble_retention_observed": 10,
        "ble_retention_retained": 4,
        "ble_retention_dropped": 0,
        "ble_retention_malformed": 0,
        "survey_queues_released": True,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
        "evidence_incomplete": False,
        "outcome": "finding",
        "source_frames_observed": 14,
        "wifi_frames_reported": 4,
        "frames_available": 8,
        "frames_inspected": 8,
        "ble_records": 4,
        "noise_samples_observed": 0,
        "noise_samples_available": 0,
        "noise_samples_inspected": 0,
        "wifi_identity_retained": 4,
        "wifi_identity_projected": 4,
        "finding_mask": 16,
        "finding_count": 1,
    }


class AirspaceGuardHilRunnerTests(unittest.TestCase):
    def test_candidate_verification_is_false_before_fixture_or_flash(self) -> None:
        self.assertFalse(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=True, reuse_exact_requested=False,
            flash_completed=False, exact_boot_verified=False))

    def test_candidate_verification_is_false_after_flash_failure(self) -> None:
        self.assertFalse(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=True, reuse_exact_requested=False,
            flash_completed=False, exact_boot_verified=True))

    def test_candidate_verification_is_false_after_boot_failure(self) -> None:
        self.assertFalse(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=True, reuse_exact_requested=False,
            flash_completed=True, exact_boot_verified=False))

    def test_candidate_verification_accepts_fresh_exact_boot(self) -> None:
        self.assertTrue(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=True, reuse_exact_requested=False,
            flash_completed=True, exact_boot_verified=True))

    def test_candidate_verification_accepts_reuse_only_after_exact_boot(
            self) -> None:
        self.assertFalse(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=False, reuse_exact_requested=True,
            flash_completed=False, exact_boot_verified=False))
        self.assertTrue(RUNNER.candidate_verification_succeeded(
            fresh_flash_requested=False, reuse_exact_requested=True,
            flash_completed=False, exact_boot_verified=True))

    def test_both_runners_serialize_only_verified_candidate(self) -> None:
        full_source = Path(RUNNER.__file__).read_text()
        for source in (full_source, START_RUNNER_SOURCE):
            self.assertIn('"flashed": candidate_verified', source)
            self.assertNotIn('"flashed": True', source)
            self.assertIn('"single_flash": candidate_verified', source)
            self.assertIn('"passive_receive_only": passed', source)

    def test_ble_fixture_requires_exact_advertising_state(self) -> None:
        fixture = {
            "kind": "macos_corebluetooth",
            "label": "Keenetic-5070",
            "terminated": True,
            "states": [{
                "schema": RUNNER.MACOS_BLE_FIXTURE_SCHEMA,
                "state": "advertising",
                "label": "Keenetic-5070",
                "pid": 123,
            }],
        }
        self.assertTrue(
            RUNNER.deterministic_ble_fixture_succeeded(fixture))
        for field, value in (
                ("state", "unsupported"),
                ("schema", "wrong.schema"),
                ("label", "wrong-label")):
            with self.subTest(field=field):
                invalid = {
                    **fixture,
                    "states": [{**fixture["states"][0], field: value}],
                }
                self.assertFalse(
                    RUNNER.deterministic_ble_fixture_succeeded(invalid))

    def test_ble_fixture_requires_termination_and_one_state(self) -> None:
        base = {
            "kind": "macos_corebluetooth",
            "label": "Keenetic-5070",
            "terminated": False,
            "states": [{
                "schema": RUNNER.MACOS_BLE_FIXTURE_SCHEMA,
                "state": "advertising",
                "label": "Keenetic-5070",
            }],
        }
        self.assertFalse(RUNNER.deterministic_ble_fixture_succeeded(base))
        self.assertFalse(RUNNER.deterministic_ble_fixture_succeeded({
            **base, "terminated": True, "states": [],
        }))
        self.assertFalse(RUNNER.deterministic_ble_fixture_succeeded({
            **base, "terminated": True,
            "states": [base["states"][0], base["states"][0]],
        }))

    def test_complete_result_accounting_passes(self) -> None:
        self.assertEqual([], RUNNER.result_failures(
            valid_result_state(), "complete"))

    def test_bounded_ble_capacity_loss_is_visible_not_erased(self) -> None:
        state = valid_result_state()
        state.update({
            "source_frames_dropped": 9,
            "ble_worker_status": "incomplete_evidence",
            "ble_scan_accepted": 1,
            "ble_scan_dropped": 9,
            "ble_retention_retained": 1,
            "ble_retention_dropped": 9,
            "ble_capacity_drop_requested": True,
            "ble_capacity_drop_injected": True,
            "evidence_incomplete": True,
            "frames_available": 5,
            "frames_inspected": 5,
            "ble_records": 1,
        })
        self.assertEqual([], RUNNER.result_failures(
            state, "capacity_loss"))
        self.assertEqual([], RUNNER.exact_capacity_one_failures(
            state, "capacity_loss"))

    def test_old_natural_capacity_loss_cannot_prove_capacity_one(self) -> None:
        state = valid_result_state()
        state.update({
            "source_frames_dropped": 1,
            "ble_worker_status": "incomplete_evidence",
            "ble_scan_accepted": 9,
            "ble_scan_dropped": 1,
            "ble_retention_dropped": 1,
            "ble_capacity_drop_requested": True,
            "ble_capacity_drop_injected": True,
            "evidence_incomplete": True,
        })
        self.assertEqual([], RUNNER.result_failures(
            state, "old_natural_capacity_loss"))
        failures = RUNNER.exact_capacity_one_failures(
            state, "old_natural_capacity_loss")
        self.assertTrue(any(
            "ble_scan_accepted" in failure for failure in failures))

    def test_ble_capacity_loss_must_match_source_uncertainty(self) -> None:
        state = valid_result_state()
        state.update({
            "ble_worker_status": "incomplete_evidence",
            "ble_scan_accepted": 9,
            "ble_scan_dropped": 1,
            "ble_retention_dropped": 1,
            "ble_capacity_drop_requested": True,
            "ble_capacity_drop_injected": True,
            "evidence_incomplete": True,
        })
        failures = RUNNER.result_failures(state, "capacity_loss")
        self.assertTrue(any(
            "external_uncertainty_accounting" in failure
            for failure in failures))

    def test_wifi_uncertainty_does_not_change_ble_worker_status(self) -> None:
        state = valid_result_state()
        state.update({
            "wifi_identity_malformed_elements": 1,
            "wifi_invalid_frames": 1,
            "source_frames_dropped": 1,
            "wifi_identity_retention_complete": False,
            "wifi_noise_retention_complete": False,
            "evidence_incomplete": True,
        })
        self.assertEqual([], RUNNER.result_failures(
            state, "wifi_uncertainty"))

    def test_transport_and_malformed_fields_are_independent_proofs(self) -> None:
        for field, value in (
                ("ble_scan_status", "scan_timed_out"),
                ("ble_cleanup_complete", False),
                ("ble_retention_malformed", 1),
                ("ble_scan_attempts", 3),
                ("source_frames_observed", 13)):
            with self.subTest(field=field):
                state = valid_result_state()
                state[field] = value
                self.assertNotEqual([], RUNNER.result_failures(
                    state, field))

    def test_navigation_action_recovers_lost_ack_without_replay(self) -> None:
        device = object()
        recovered = {"page": "survey", "wifi_product_view": "menu"}
        with patch.object(
                RUNNER, "raw_action",
                side_effect=TimeoutError("lost UI ACK")) as raw_action, \
                patch.object(
                    RUNNER, "read_only_query",
                    return_value=recovered) as read_state:
            state = RUNNER.action(device, "right")
        raw_action.assert_called_once_with(device, "right", timeout=15.0)
        read_state.assert_called_once_with(
            device, b"ui.state", "leshy.ui.v1", "state",
            timeout=5.0, maximum_attempts=3)
        self.assertIs(recovered, state)
        self.assertFalse(state["host_navigation_ack_received"])
        self.assertEqual(1, state["host_navigation_action_writes"])
        self.assertEqual(0, state["host_navigation_action_replays"])

    def test_navigation_action_records_normal_ack(self) -> None:
        device = object()
        acknowledged = {"page": "survey", "wifi_product_view": "menu"}
        with patch.object(
                RUNNER, "raw_action", return_value=acknowledged) as raw_action, \
                patch.object(RUNNER, "read_only_query") as read_state:
            state = RUNNER.action(device, "right", timeout=2.0)
        raw_action.assert_called_once_with(device, "right", timeout=2.0)
        read_state.assert_not_called()
        self.assertIs(acknowledged, state)
        self.assertTrue(state["host_navigation_ack_received"])
        self.assertEqual(0, state["host_navigation_action_replays"])

    def test_read_only_query_retries_one_transport_timeout(self) -> None:
        device = types.SimpleNamespace(reset_input_buffer=lambda: None)
        expected = {"schema": "state.v1", "kind": "state"}
        with patch.object(
                RUNNER, "query",
                side_effect=[TimeoutError("lost response"), expected]), \
                patch.object(RUNNER, "synchronize_console") as synchronize:
            record = RUNNER.read_only_query(
                device, b"state", "state.v1", "state")
        self.assertEqual(2, record["host_transport_attempts"])
        self.assertEqual(1, record["host_transport_transient_retries"])
        self.assertEqual(
            ["lost response"], record["host_transport_transient_errors"])
        synchronize.assert_called_once_with(device, 10.0)

    def test_hil_begin_recovers_lost_ack_without_replay(self) -> None:
        device = object()
        state = {
            "schema": RUNNER.HIL_SESSION_SCHEMA,
            "kind": "state",
            "status": "active",
            "session_id": "1" * 32,
            "active": True,
            "app_elf_sha256": "2" * 64,
            "firmware_version": "1.0.0-dev.242",
        }
        with patch.object(
                RUNNER, "query", side_effect=TimeoutError("lost begin ACK")) \
                as begin, patch.object(
                    RUNNER, "read_only_query", return_value=state) as read_state:
            recovered = RUNNER.begin_hil_session(
                device, "1" * 32, "2" * 64, "1.0.0-dev.242")
        begin.assert_called_once()
        read_state.assert_called_once_with(
            device, b"hil.state", RUNNER.HIL_SESSION_SCHEMA, "state")
        self.assertFalse(recovered["host_begin_ack_received"])
        self.assertEqual(1, recovered["host_begin_action_writes"])
        self.assertEqual(0, recovered["host_begin_action_replays"])

    def test_hil_end_recovers_lost_ack_from_inactive_state(self) -> None:
        device = object()
        active = {
            "app_elf_sha256": "2" * 64,
            "session_id": "1" * 32,
            "active": True,
        }
        inactive = {
            "app_elf_sha256": "2" * 64,
            "session_id": "",
            "active": False,
        }
        with patch.object(
                RUNNER, "read_only_query",
                side_effect=[active, inactive]) as read_state, patch.object(
                    RUNNER, "query", side_effect=TimeoutError("lost end ACK")) \
                as end:
            recovered = RUNNER.end_hil_session(
                device, "1" * 32, "2" * 64)
        end.assert_called_once()
        self.assertEqual(2, read_state.call_count)
        self.assertFalse(recovered["active"])
        self.assertFalse(recovered["host_end_ack_received"])
        self.assertEqual(1, recovered["host_end_action_writes"])
        self.assertEqual(0, recovered["host_end_action_replays"])
        self.assertEqual("1" * 32,
                         recovered["host_end_requested_session_id"])

    def test_terminal_hil_end_runs_even_when_clear_fails(self) -> None:
        device = object()
        ended = {"active": False}
        with patch.object(
                RUNNER, "query", side_effect=RuntimeError("clear failed")), \
                patch.object(
                    RUNNER, "end_hil_session", return_value=ended) as end:
            cleared, result, errors = RUNNER.terminal_hil_cleanup(
                device, "1" * 32, "2" * 64)
        end.assert_called_once_with(device, "1" * 32, "2" * 64)
        self.assertEqual({}, cleared)
        self.assertIs(ended, result)
        self.assertEqual(1, len(errors))
        self.assertIn("capacity_drop_clear", errors[0])


if __name__ == "__main__":
    unittest.main()
