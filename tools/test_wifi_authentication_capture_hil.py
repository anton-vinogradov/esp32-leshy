#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.read_json = lambda *_args, **_kwargs: {}
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)


def load(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load(
    "wifi_authentication_capture_hil_runner",
    "run_1x_wifi_authentication_capture_hil.py")
CHECKER = load(
    "wifi_authentication_capture_hil_checker",
    "check_wifi_authentication_capture_hil_run.py")


def terminal_state(outcome: str = "inconclusive") -> dict[str, Any]:
    return {
        "frames_reported": 0,
        "frames_accepted": 0,
        "frames_dropped_capacity": 0,
        "frames_dropped_invalid": 0,
        "frames_observed": 17,
        "frames_ignored": 17,
        "ingress_invalid": 0,
        "candidates": 0,
        "candidates_accepted": 0,
        "candidates_dropped": 0,
        "analysis_frames_reported": 0,
        "analysis_frames_accepted": 0,
        "analysis_dropped_capacity": 0,
        "analysis_dropped_invalid": 0,
        "analysis_accounting_valid": True,
        "outcome": outcome,
        "uncertainty": RUNNER.UNCERTAINTY_NO_EVIDENCE,
        "evidence": 0,
        "peers": 0,
        "complete_peers": 0,
        "pmkids": 0,
        "source_frames": 0,
        "frames_read": 0,
        "data_frames": 0,
        "analysis_frames_ignored": 0,
        "eapol_frames": 0,
        "eapol_key_frames": 0,
        "classified_key_frames": 0,
        "unclassified_key_frames": 0,
        "unsupported_key_frames": 0,
        "sequence_rejected": 0,
        "malformed_frames": 0,
        "truncated_frames": 0,
        "source_read_failures": 0,
        "evidence_dropped": 0,
        "peers_dropped": 0,
        "pmkids_dropped": 0,
        "report_capture_frames_reported": 0,
        "report_capture_frames_accepted": 0,
        "report_capture_frames_dropped_capacity": 0,
        "report_capture_frames_dropped_invalid": 0,
        "state": "result",
        "presenter_view": "inconclusive",
        "presenter_tone": "caution",
        "presenter_evidence_incomplete": True,
        "presenter_report_openable": False,
        "presenter_cleanup_complete": True,
        "presenter_row_count": 4,
        "failure": "none",
    }


def armed_auth_state(armed: bool = True) -> dict[str, Any]:
    return {
        "schema": RUNNER.AUTH_SCHEMA,
        "kind": "state",
        "read_only_query": True,
        "survey_terminal_hold_armed": armed,
        "host_transport_attempts": 1,
        "host_transport_transient_retries": 0,
        "host_transport_transient_errors": [],
    }


def synthetic_controller_state(
        view: str = "outcome", *, content_repaints: int = 10,
        full_repaints: int = 1, chrome_repaints: int = 2,
        repeat_generation: int = 7, **overrides: Any) -> dict[str, Any]:
    presenter = dict(RUNNER.SYNTHETIC_PRESENTER_SEMANTICS[view])
    requested_mask = overrides.get(
        "controller_selected_peer_mask", 0x0f)
    if view == "peer_detail" and requested_mask != 0x0f:
        presenter["tone"] = "caution"
    state = {
        "schema": RUNNER.AUTH_SCHEMA, "kind": "state",
        "read_only_query": True,
        "view": "authentication_capture", "state": "result",
        "failure": "none", "capture_active": False,
        "capture_state": "complete",
        "capture_cleanup_complete": True,
        "adapter_cleanup_complete": True,
        "synthetic": True, "report_origin": "synthetic_hil",
        "generation": 11,
        "outcome": "complete", "uncertainty": 0,
        "evidence": 6, "peers": 2, "complete_peers": 1,
        "pmkids": 1, "source_frames": 6,
        "presenter_view": presenter["view"],
        "presenter_tone": presenter["tone"],
        "presenter_evidence_incomplete": False,
        "presenter_report_openable": True,
        "presenter_cleanup_complete": True,
        "presenter_row_count": presenter["row_count"],
        "presenter_synthetic": True,
        "presenter_synthetic_label_visible": True,
        "presenter_title_semantic": presenter["title"],
        "presenter_headline_semantic": presenter["headline"],
        "presenter_note_semantic": "simulated_data",
        "controller_ready": True, "controller_view": view,
        "controller_action_count": 2,
        "controller_action_selection": 0,
        "controller_selected_action": "details",
        "controller_peer_count": 2,
        "controller_peer_selection": 0,
        "controller_peer_position": 0,
        "controller_selected_peer_mask": 0x0f,
        "controller_selected_peer_evidence_count": 4,
        "controller_evidence_count": 6,
        "controller_evidence_selection": 0,
        "controller_selected_evidence_present": True,
        "controller_selected_evidence_report_index": 0,
        "controller_selected_evidence_source_frame": 0,
        "controller_selected_evidence_message": "message_1",
        "controller_selected_evidence_has_pmkid": True,
        "repeat_requested": False,
        "repeat_request_generation": repeat_generation,
        "production_report_fingerprint": "0123456789abcdef",
        "production_report_fingerprint_scope": "hil_session",
        "production_controller_ready": True,
        "production_controller_view": "outcome",
        "production_controller_action_selection": 0,
        "production_controller_peer_selection": 0,
        "production_controller_evidence_selection": 0,
        "production_controller_report_bound": True,
        "target_selected": True,
        "target_selection_continuity": True,
        "esp_rf_owned_by_foreground": True,
        "content_repaints": content_repaints,
        "full_repaints": full_repaints,
        "chrome_repaints": chrome_repaints,
    }
    state.update(overrides)
    return state


class WifiAuthenticationCaptureHilTests(unittest.TestCase):
    def test_ui_wait_recovers_read_only_transport_timeout(self) -> None:
        device = MagicMock()
        ready = {
            "schema": RUNNER.UI_SCHEMA, "kind": "state",
            "wifi_product_view": "networks",
        }
        with patch.object(
                RUNNER, "query",
                side_effect=(TimeoutError("transient UI ACK loss"), ready)
                ) as query_state, \
                patch.object(RUNNER.time, "sleep"):
            actual = RUNNER.wait_ui_state(
                device,
                lambda state: state.get("wifi_product_view") == "networks",
                5.0, "Networks")
        self.assertEqual(2, query_state.call_count)
        device.reset_input_buffer.assert_called_once_with()
        self.assertEqual(1, actual["host_wait_transport_timeouts"])
        self.assertEqual(
            ["TimeoutError"],
            actual["host_wait_transport_errors"])

    def test_ui_wait_timeout_retains_only_mount_telemetry(self) -> None:
        device = MagicMock()
        preparing = {
            "schema": RUNNER.UI_SCHEMA, "kind": "state",
            "ssid": "private-network",
            "wifi_network_order_hash": 123,
            "survey_product_filesystem_mount_stage": "vfs_mounting",
            "survey_product_filesystem_bus_initialize_error": 0,
            "survey_product_filesystem_drive_available_before_vfs": True,
            "survey_product_filesystem_heap_free_before_bus": 1000,
            "survey_product_filesystem_heap_largest_before_bus": 900,
            "survey_product_filesystem_heap_free_before_vfs": 800,
            "survey_product_filesystem_heap_largest_before_vfs": 700,
        }
        with patch.object(RUNNER, "query", return_value=preparing), \
                patch.object(RUNNER.time, "monotonic",
                             side_effect=(0.0, 0.0, 0.0, 2.0)), \
                patch.object(RUNNER.time, "sleep"):
            with self.assertRaises(RUNNER.UiStateWaitTimeout) as caught:
                RUNNER.wait_ui_state(device, lambda _state: False, 1.0,
                                     "second mount")
        self.assertEqual("vfs_mounting", caught.exception.last_state[
            "survey_product_filesystem_mount_stage"])
        self.assertEqual(0, caught.exception.last_state[
            "survey_product_filesystem_bus_initialize_error"])
        self.assertIs(True, caught.exception.last_state[
            "survey_product_filesystem_drive_available_before_vfs"])
        self.assertNotIn("ssid", caught.exception.last_state)
        self.assertNotIn("wifi_network_order_hash",
                         caught.exception.last_state)

    def test_cleanup_retains_mount_telemetry_without_private_state(self) -> None:
        cleanup = {
            "attempted": True,
            "initial_state": {
                "ssid": "private-network",
                "wifi_device_order_hash": 456,
                "survey_product_filesystem_mount_stage": "vfs_mounting",
                "survey_product_filesystem_bus_initialize_error": 0,
                "survey_product_filesystem_drive_available_before_vfs": True,
                "survey_product_filesystem_heap_free_before_bus": 1000,
            },
            "final_state": {
                "page": "home",
                "survey_product_filesystem_mount_stage": "mounted",
                "survey_product_filesystem_heap_free_before_vfs": 800,
            },
        }
        retained = RUNNER.retain_cleanup_mount_telemetry(cleanup)
        self.assertNotIn("ssid", retained["initial_state"])
        self.assertNotIn("wifi_device_order_hash", retained["initial_state"])
        self.assertEqual({
            "survey_product_filesystem_mount_stage": "vfs_mounting",
            "survey_product_filesystem_bus_initialize_error": 0,
            "survey_product_filesystem_drive_available_before_vfs": True,
            "survey_product_filesystem_heap_free_before_bus": 1000,
        }, retained["filesystem_mount_telemetry"]["initial_state"])
        self.assertEqual("mounted", retained[
            "filesystem_mount_telemetry"]["final_state"][
                "survey_product_filesystem_mount_stage"])

    def test_wifi_menu_preflight_accepts_unsnapshotted_worker_but_quiesces(
            self) -> None:
        state = {
            "page": "survey", "wifi_product_view": "menu",
            "runtime_owner": "wifi", "lease_mask": 15,
            "survey_workflow_state": "setup",
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": True,
            "survey_product_worker_ready": False,
            "survey_product_source_active": False,
            "survey_product_scan_active": False,
        }
        self.assertTrue(RUNNER.wifi_menu_quiescent(state))
        failures: list[str] = []
        CHECKER.verify_wifi_menu_quiescent(failures, state)
        self.assertEqual([], failures)
        initialized = dict(state)
        initialized["survey_product_worker_ready"] = True
        self.assertTrue(RUNNER.wifi_menu_quiescent(initialized))
        failures = []
        CHECKER.verify_wifi_menu_quiescent(failures, initialized)
        self.assertEqual([], failures)
        for name, value in (
                ("survey_product_source_active", True),
                ("survey_product_cleanup_complete", False),
                ("survey_product_backend_open", True),
                ("survey_product_scan_active", True)):
            with self.subTest(name=name):
                changed = dict(state)
                changed[name] = value
                self.assertFalse(RUNNER.wifi_menu_quiescent(changed))
                failures = []
                CHECKER.verify_wifi_menu_quiescent(failures, changed)
                self.assertTrue(failures)

    def test_network_list_requires_eager_worker_runtime_snapshot(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        checker = Path(CHECKER.__file__).read_text(encoding="utf-8")
        self.assertIn(
            'state.get("survey_product_worker_ready") is True', source)
        self.assertIn(
            'cancel_list.get("survey_product_worker_ready") is True', checker)
        self.assertIn(
            'network_list.get("survey_product_worker_ready") is True', checker)

    def test_product_mount_proof_rejects_overlap_and_bad_accounting(self) -> None:
        state = {
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_store_open_attempted": True,
            "survey_product_store_status": "permitted",
            "survey_product_admission_status": "permitted",
            "survey_product_filesystem_mount_stage": "mounted",
            "survey_product_filesystem_bus_initialize_error": 0,
            "survey_product_filesystem_drive_available_before_vfs": True,
            "survey_product_filesystem_mount_error": 0,
            "survey_product_filesystem_mount_last_failure_error": 257,
            "survey_product_filesystem_mount_attempts": 2,
            "survey_product_filesystem_mount_transient_retries": 1,
            "survey_product_mount_attempts_total": 3,
            "survey_product_mount_successes_total": 2,
            "survey_product_filesystem_heap_free_before_bus": 1000,
            "survey_product_filesystem_heap_largest_before_bus": 900,
            "survey_product_filesystem_heap_free_before_vfs": 800,
            "survey_product_filesystem_heap_largest_before_vfs": 700,
        }
        failures: list[str] = []
        CHECKER.verify_product_mount(failures, state, "valid")
        self.assertEqual([], failures)
        for name, value in (
                ("survey_product_backend_open", True),
                ("survey_product_storage_mounted", True),
                ("survey_product_filesystem_mount_error", 257),
                ("survey_product_filesystem_bus_initialize_error", 257),
                ("survey_product_filesystem_drive_available_before_vfs", False),
                ("survey_product_filesystem_mount_last_failure_error", 0),
                ("survey_product_filesystem_mount_attempts", 4),
                ("survey_product_filesystem_mount_transient_retries", 0),
                ("survey_product_mount_successes_total", 4),
                ("survey_product_filesystem_mount_stage", "vfs_mounting"),
                ("survey_product_filesystem_heap_free_before_bus", 0),
                ("survey_product_filesystem_heap_largest_before_bus", 0),
                ("survey_product_filesystem_heap_free_before_vfs", 0),
                ("survey_product_filesystem_heap_largest_before_vfs", 0)):
            with self.subTest(name=name):
                changed = dict(state)
                changed[name] = value
                failures = []
                CHECKER.verify_product_mount(failures, changed, "mutated")
                self.assertTrue(failures)

        first_attempt = dict(state)
        first_attempt["survey_product_filesystem_mount_attempts"] = 1
        first_attempt["survey_product_filesystem_mount_transient_retries"] = 0
        first_attempt["survey_product_filesystem_mount_last_failure_error"] = 0
        failures = []
        CHECKER.verify_product_mount(failures, first_attempt, "first_attempt")
        self.assertEqual([], failures)

    def test_one_shot_hold_has_exact_non_replayed_bounded_contract(self) -> None:
        ack = {
            "schema": RUNNER.AUTH_HOLD_SCHEMA, "kind": "armed",
            "status": "armed", "armed": True, "one_shot": True,
            "replayed": False, "timeout_ms": RUNNER.AUTH_HOLD_TIMEOUT_MS,
            "hil_active": True, "hardware_touched": False,
            "radio_started": False, "storage_mounted": False,
            "storage_written": False,
        }
        with patch.object(RUNNER, "query", return_value=ack) as mutate, \
                patch.object(RUNNER, "read_only_query",
                             return_value=armed_auth_state()) as prove:
            hold = RUNNER.arm_authentication_survey_stop_hold(
                object(), armed_auth_state(False))
        self.assertEqual(1, mutate.call_count)
        self.assertEqual(RUNNER.AUTH_HOLD_ACK_TIMEOUT_S,
                         mutate.call_args.kwargs["timeout"])
        self.assertEqual(1, prove.call_count)
        self.assertEqual(RUNNER.AUTH_HOLD_STATE_TIMEOUT_S,
                         prove.call_args.kwargs["timeout"])
        self.assertEqual(1, prove.call_args.kwargs["maximum_attempts"])
        self.assertEqual(1, hold["host_arm_action_writes"])
        self.assertEqual(0, hold["host_arm_action_replays"])
        hold["host_back_after_arm_ms"] = 20.0
        failures: list[str] = []
        CHECKER.verify_cancel_hold(failures, hold)
        self.assertEqual([], failures)

        replayed = copy.deepcopy(hold)
        replayed["ack"]["replayed"] = True
        failures = []
        CHECKER.verify_cancel_hold(failures, replayed)
        self.assertTrue(failures)
        contradictory_ack = copy.deepcopy(hold)
        contradictory_ack["host_arm_ack_error"] = "impossible"
        failures = []
        CHECKER.verify_cancel_hold(failures, contradictory_ack)
        self.assertTrue(failures)
        timed_out = copy.deepcopy(hold)
        timed_out["host_back_after_arm_ms"] = RUNNER.AUTH_HOLD_TIMEOUT_MS
        failures = []
        CHECKER.verify_cancel_hold(failures, timed_out)
        self.assertTrue(failures)
        for field, value in (
                ("host_arm_ack_timeout_ms", 5_000.0),
                ("host_arm_state_timeout_ms", 5_000.0),
                ("host_arm_elapsed_ms", RUNNER.AUTH_HOLD_TIMEOUT_MS)):
            with self.subTest(field=field):
                unbounded = copy.deepcopy(hold)
                unbounded[field] = value
                failures = []
                CHECKER.verify_cancel_hold(failures, unbounded)
                self.assertTrue(failures)

    def test_lost_hold_ack_is_never_replayed_and_requires_state_proof(self) -> None:
        with patch.object(
                RUNNER, "query", side_effect=TimeoutError("lost ack")) as mutate, \
                patch.object(RUNNER, "read_only_query",
                             return_value=armed_auth_state()):
            hold = RUNNER.arm_authentication_survey_stop_hold(
                object(), armed_auth_state(False))
        self.assertEqual(1, mutate.call_count)
        self.assertFalse(hold["host_arm_ack_received"])
        self.assertEqual("TimeoutError", hold["host_arm_ack_error"])
        hold["host_back_after_arm_ms"] = 10.0
        failures: list[str] = []
        CHECKER.verify_cancel_hold(failures, hold)
        self.assertEqual([], failures)
        contradictory = copy.deepcopy(hold)
        contradictory["ack"] = {"replayed": True}
        failures = []
        CHECKER.verify_cancel_hold(failures, contradictory)
        self.assertTrue(failures)

        with patch.object(RUNNER, "query", side_effect=TimeoutError("lost")), \
                patch.object(RUNNER, "read_only_query",
                             return_value=armed_auth_state(False)):
            with self.assertRaisesRegex(RuntimeError, "was not armed"):
                RUNNER.arm_authentication_survey_stop_hold(
                    object(), armed_auth_state(False))

        with self.assertRaisesRegex(
                RuntimeError, "authentication_hil_hold_pre_arm"):
            RUNNER.arm_authentication_survey_stop_hold(
                object(), armed_auth_state(True))

    def test_time_critical_navigation_is_one_write_and_bounded(self) -> None:
        device = MagicMock()
        ack = {
            "schema": RUNNER.UI_SCHEMA, "kind": "state",
            "action": "right", "changed": True,
        }
        armed_at = RUNNER.time.monotonic()
        with patch.object(RUNNER, "read_expected_ui_action_ack",
                          return_value=ack) as receive:
            record = RUNNER.bounded_hold_navigation(
                device, "right", armed_at, lambda _state: True)
        device.write.assert_called_once_with(b"ui.key right\n")
        device.flush.assert_called_once_with()
        self.assertEqual(RUNNER.AUTH_HOLD_NAV_ACK_TIMEOUT_S,
                         receive.call_args.args[2])
        failures: list[str] = []
        CHECKER.verify_bounded_hold_navigation(
            failures, record, "right", "test")
        self.assertEqual([], failures)
        contradictory_ack = copy.deepcopy(record)
        contradictory_ack["host_navigation_ack_error"] = "impossible"
        failures = []
        CHECKER.verify_bounded_hold_navigation(
            failures, contradictory_ack, "right", "contradictory ACK")
        self.assertTrue(failures)

        device = MagicMock()
        with patch.object(RUNNER, "read_expected_ui_action_ack",
                          side_effect=TimeoutError("lost right")):
            lost = RUNNER.bounded_hold_navigation(
                device, "right", RUNNER.time.monotonic(),
                lambda _state: True)
        self.assertFalse(lost["host_navigation_ack_received"])
        self.assertEqual(1, lost["host_navigation_action_writes"])
        self.assertEqual(0, lost["host_navigation_action_replays"])
        failures = []
        CHECKER.verify_bounded_hold_navigation(
            failures, lost, "right", "lost")
        self.assertEqual([], failures)
        lost["action"] = "right"
        failures = []
        CHECKER.verify_bounded_hold_navigation(
            failures, lost, "right", "contradictory")
        self.assertTrue(failures)

    def test_bounded_ack_reader_skips_same_action_stale_semantics(self) -> None:
        stale = {
            "schema": RUNNER.UI_SCHEMA, "kind": "state",
            "action": "right", "wifi_product_view": "network_detail",
            "runtime_event": "wifi_network_detail",
        }
        current = {
            "schema": RUNNER.UI_SCHEMA, "kind": "state",
            "action": "right",
            "wifi_product_view": "authentication_capture",
            "runtime_event": "authentication_waiting_for_survey_stop",
        }
        expected = lambda state: (
            state.get("wifi_product_view") == "authentication_capture" and
            state.get("runtime_event") ==
                "authentication_waiting_for_survey_stop")
        with patch.object(RUNNER, "read_json",
                          side_effect=(stale, current)) as receive:
            actual = RUNNER.read_expected_ui_action_ack(
                object(), "right", 0.25, expected)
        self.assertEqual(current, actual)
        self.assertEqual(2, receive.call_count)

    def test_start_wait_accepts_all_terminal_start_observations(self) -> None:
        for state in ("running", "result", "failed"):
            with self.subTest(state=state):
                self.assertTrue(RUNNER.authentication_start_state({
                    "state": state,
                }))
        self.assertFalse(RUNNER.authentication_start_state({
            "state": "waiting_for_survey_stop",
        }))

    def test_start_failure_retains_exact_driver_stage_and_heap(self) -> None:
        diagnostics = {
            "authentication": {
                "state": "failed", "failure": "start_failed",
                "adapter_failure_stage": "wifi_init",
                "adapter_driver_error": 257,
                "adapter_heap_free_before_init": 120000,
                "adapter_heap_largest_before_init": 60000,
            },
            "capture": {
                "schema": RUNNER.CAPTURE_SCHEMA, "kind": "state",
                "driver_error": 257,
            },
        }
        self.assertEqual([], RUNNER.start_failure_diagnostic_failures(
            diagnostics))
        failures: list[str] = []
        CHECKER.verify_start_failure_diagnostics(failures, diagnostics)
        self.assertEqual([], failures)

        for mutation in (
                {"adapter_failure_stage": "none"},
                {"adapter_driver_error": None},
                {"adapter_driver_error": 0},
                {"adapter_heap_free_before_init": 0}):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(diagnostics)
                changed["authentication"].update(mutation)
                self.assertTrue(
                    RUNNER.start_failure_diagnostic_failures(changed))
                failures = []
                CHECKER.verify_start_failure_diagnostics(failures, changed)
                self.assertTrue(failures)

        teardown_failure = copy.deepcopy(diagnostics)
        teardown_failure["authentication"].update({
            "failure": "result_before_cleanup",
            "adapter_failure_stage": "none",
            "adapter_driver_error": 0,
            "adapter_heap_free_before_init": 0,
            "adapter_heap_largest_before_init": 0,
        })
        teardown_failure["capture"]["driver_error"] = 0
        self.assertEqual([], RUNNER.start_failure_diagnostic_failures(
            teardown_failure))
        failures = []
        CHECKER.verify_start_failure_diagnostics(
            failures, teardown_failure)
        self.assertEqual([], failures)

    def test_final_diagnostics_are_independent_and_best_effort(self) -> None:
        records = {
            b"input.state": {"status": "ready"},
            b"storage.product.boot-recovery": {"status": "admitted"},
        }

        def read(_device: Any, command: bytes, *_args: Any,
                 **_kwargs: Any) -> dict[str, Any]:
            if command == b"hardware.safe-outputs":
                raise TimeoutError("safe output query timed out")
            return records[command]

        with patch.object(RUNNER, "read_only_query", side_effect=read):
            retained, errors = RUNNER.best_effort_final_diagnostics(object())
        self.assertEqual({
            "input": {"status": "ready"},
            "recovery": {"status": "admitted"},
        }, retained)
        self.assertEqual(1, len(errors))
        self.assertIn("safe_outputs", errors[0])

    def test_private_target_fields_are_scrubbed_before_retention(self) -> None:
        live = {
            "target_bssid": "00:11:22:33:44:55",
            "nested": [{"identity_hash": 123}, {"channel": 6}],
            "wifi_network_order_hash": 0x12345678,
            "wifi_device_order_hash": 0x87654321,
            "privacy": {"generic_target_ui": True},
        }
        retained = RUNNER.scrub_private_target_identifiers(live)
        self.assertEqual({
            "nested": [{}, {"channel": 6}],
            "privacy": {"generic_target_ui": True},
        }, retained)
        self.assertEqual([], RUNNER.private_target_failures(retained))
        safe = RUNNER.privacy_safe_repr(live)
        self.assertNotIn("order_hash", safe)
        self.assertNotIn("identity_hash", safe)

    def test_capture_sidecar_and_screens_record_are_scrubbed(self) -> None:
        live = {
            "frame_begin": {
                "target_bssid": "00:11:22:33:44:55",
                "status": "selected 00:11:22:33:44:55",
            },
            "state": {"ssid": "private-network", "channel": 6},
        }
        def fake_capture(_device: Any, frames: Path, name: str,
                         *, record_transform: Any) -> dict[str, Any]:
            retained = record_transform(live)
            RUNNER.write_json(frames / f"{name}.json", retained)
            return retained

        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(RUNNER, "capture", side_effect=fake_capture):
            frames = Path(temporary)
            retained = RUNNER.capture_evidence_safe(
                object(), frames, "wifi-auth-running")
            sidecar = json.loads(
                (frames / "wifi-auth-running.json").read_text(
                    encoding="utf-8"))
        self.assertEqual(retained, sidecar)
        self.assertNotIn("target_bssid", retained["frame_begin"])
        self.assertNotIn("ssid", retained["state"])
        self.assertEqual(
            "selected <redacted-private-identifier>",
            retained["frame_begin"]["status"])
        self.assertEqual([], RUNNER.private_target_failures(retained))

    def test_capture_sanitizer_failure_leaves_no_frame_artifacts(self) -> None:
        def fake_capture(_device: Any, frames: Path, name: str,
                         *, record_transform: Any) -> dict[str, Any]:
            (frames / f"{name}.rgb565").write_bytes(b"private framebuffer")
            (frames / f"{name}.png").write_bytes(b"private screenshot")
            return record_transform({"state": {"ssid": "private-network"}})

        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(RUNNER, "capture", side_effect=fake_capture), \
                patch.object(
                    RUNNER, "scrub_private_target_identifiers",
                    side_effect=RuntimeError("synthetic sanitizer crash")):
            frames = Path(temporary)
            for suffix in ("json", "png", "rgb565"):
                (frames / f"wifi-auth-running.{suffix}").write_bytes(
                    b"unsanitized stale data")
            with self.assertRaisesRegex(RuntimeError, "sanitizer crash"):
                RUNNER.capture_evidence_safe(
                    object(), frames, "wifi-auth-running")
            for suffix in ("json", "png", "rgb565"):
                self.assertFalse(
                    (frames / f"wifi-auth-running.{suffix}").exists())

    def test_private_target_checker_rejects_keys_and_mac_values(self) -> None:
        for value in (
                {"identity_hash": 123},
                {"wifi_network_order_hash": 123},
                {"wifi_device_order_hash": 456},
                {"safe_key": "00:11:22:33:44:55"},
                {"nested": [{"target_bssid": "redacted"}]}):
            with self.subTest(value=value):
                self.assertTrue(RUNNER.private_target_failures(value))
                failures: list[str] = []
                CHECKER.verify_private_target_absent(failures, value)
                self.assertTrue(failures)

    def test_privacy_failure_cannot_return_a_stale_pass(self) -> None:
        failures = ["privacy: synthetic post-scrub rejection"]
        retained, final_passed = RUNNER.finalize_evidence_result({
            "passed": True,
            "gate_eligible": True,
            "failures": [],
            "scope": {"application_rx_only": True},
        }, failures, True)
        self.assertFalse(final_passed)
        self.assertFalse(retained["passed"])
        self.assertFalse(retained["gate_eligible"])
        self.assertFalse(retained["scope"]["application_rx_only"])
        self.assertTrue(retained["failures"])

    def test_no_ambient_eapol_is_honestly_inconclusive(self) -> None:
        state = terminal_state()
        self.assertEqual([], RUNNER.ingress_accounting_failures(
            state, "terminal"))
        failures: list[str] = []
        CHECKER.verify_ingress(failures, state)
        self.assertEqual([], failures)

    def test_no_evidence_cannot_be_incomplete_or_complete(self) -> None:
        for outcome in ("incomplete", "complete"):
            with self.subTest(outcome=outcome):
                state = terminal_state(outcome)
                self.assertTrue(RUNNER.ingress_accounting_failures(
                    state, "terminal"))
                failures: list[str] = []
                CHECKER.verify_ingress(failures, state)
                self.assertTrue(failures)

    def test_capacity_or_invalid_loss_cannot_be_conclusive(self) -> None:
        state = terminal_state("incomplete")
        state.update({
            "frames_observed": 8,
            "frames_ignored": 5,
            "ingress_invalid": 1,
            "candidates": 2,
            "candidates_accepted": 1,
            "candidates_dropped": 1,
            "frames_reported": 2,
            "frames_accepted": 1,
            "frames_dropped_capacity": 1,
            "evidence": 1,
            "uncertainty": 4,
            "analysis_frames_reported": 3,
            "analysis_frames_accepted": 1,
            "analysis_dropped_capacity": 1,
            "analysis_dropped_invalid": 1,
            "source_frames": 1,
            "frames_read": 1,
            "data_frames": 1,
            "analysis_frames_ignored": 0,
            "eapol_frames": 1,
            "eapol_key_frames": 1,
            "classified_key_frames": 1,
            "report_capture_frames_reported": 3,
            "report_capture_frames_accepted": 1,
            "report_capture_frames_dropped_capacity": 1,
            "report_capture_frames_dropped_invalid": 1,
            "presenter_view": "result",
            "presenter_evidence_incomplete": False,
        })
        self.assertTrue(any(
            "inconclusive" in failure for failure in
            RUNNER.ingress_accounting_failures(state, "terminal")))
        failures: list[str] = []
        CHECKER.verify_ingress(failures, state)
        self.assertTrue(any("conclusive" in failure for failure in failures))

    def test_exact_ingress_partitions_are_required(self) -> None:
        state = terminal_state()
        state["frames_observed"] += 1
        self.assertTrue(any(
            "ingress_accounting" in failure for failure in
            RUNNER.ingress_accounting_failures(state, "terminal")))
        failures: list[str] = []
        CHECKER.verify_ingress(failures, state)
        self.assertTrue(any("ingress accounting" in failure
                            for failure in failures))

    def test_static_chrome_delta_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frames = Path(temporary)
            first = bytearray(RUNNER.WIDTH * RUNNER.HEIGHT * 2)
            second = bytearray(first)
            content_offset = (40 * RUNNER.WIDTH + 20) * 2
            chrome_offset = (4 * RUNNER.WIDTH + 4) * 2
            second[content_offset] = 1
            (frames / "before.rgb565").write_bytes(first)
            (frames / "after.rgb565").write_bytes(second)
            self.assertEqual({
                "content_changed_pixels": 1,
                "static_chrome_changed_pixels": 0,
            }, RUNNER.pixel_changes(frames, "before", "after"))
            second[chrome_offset] = 1
            (frames / "after.rgb565").write_bytes(second)
            self.assertEqual(1, RUNNER.pixel_changes(
                frames, "before", "after")["static_chrome_changed_pixels"])

    def test_stale_terminal_header_is_rejected_from_physical_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frames = Path(temporary)
            running = bytearray(RUNNER.WIDTH * RUNNER.HEIGHT * 2)
            stale_header_result = bytearray(running)
            content_offset = (40 * RUNNER.WIDTH + 20) * 2
            stale_header_result[content_offset] = 1
            (frames / "wifi-auth-running-second.rgb565").write_bytes(running)
            (frames / "wifi-auth-result.rgb565").write_bytes(
                stale_header_result)
            stale = RUNNER.terminal_pixel_changes(
                frames, "wifi-auth-running-second", "wifi-auth-result")
            self.assertTrue(RUNNER.terminal_pixel_delta_failures(
                stale, "terminal"))
            self.assertEqual(stale, CHECKER.terminal_pixel_changes(frames))
            failures: list[str] = []
            CHECKER.verify_terminal_pixel_delta(failures, stale)
            self.assertTrue(any("title stayed stale" in failure
                                for failure in failures))
            self.assertTrue(any("status stayed stale" in failure
                                for failure in failures))

            title_offset = (RUNNER.TITLE_Y0 * RUNNER.WIDTH +
                            RUNNER.TITLE_X0) * 2
            status_offset = (RUNNER.STATUS_Y0 * RUNNER.WIDTH +
                             RUNNER.STATUS_X0) * 2
            valid_result = bytearray(stale_header_result)
            valid_result[title_offset] = 1
            valid_result[status_offset] = 1
            (frames / "wifi-auth-result.rgb565").write_bytes(valid_result)
            valid = RUNNER.terminal_pixel_changes(
                frames, "wifi-auth-running-second", "wifi-auth-result")
            self.assertEqual(valid, CHECKER.terminal_pixel_changes(frames))
            self.assertEqual([], RUNNER.terminal_pixel_delta_failures(
                valid, "terminal"))
            failures = []
            CHECKER.verify_terminal_pixel_delta(failures, valid)
            self.assertEqual([], failures)

            unexpected_offset = (4 * RUNNER.WIDTH + 4) * 2
            valid_result[unexpected_offset] = 1
            (frames / "wifi-auth-result.rgb565").write_bytes(valid_result)
            unexpected = RUNNER.terminal_pixel_changes(
                frames, "wifi-auth-running-second", "wifi-auth-result")
            self.assertEqual(
                unexpected, CHECKER.terminal_pixel_changes(frames))
            self.assertTrue(RUNNER.terminal_pixel_delta_failures(
                unexpected, "terminal"))
            failures = []
            CHECKER.verify_terminal_pixel_delta(failures, unexpected)
            self.assertTrue(any("unexpected static chrome" in failure
                                for failure in failures))

    def test_analyzer_partition_is_fail_closed(self) -> None:
        state = terminal_state()
        state.update({
            "source_frames": 1,
            "frames_read": 1,
            "data_frames": 1,
            "analysis_frames_ignored": 1,
            "report_capture_frames_accepted": 1,
        })
        self.assertTrue(RUNNER.report_accounting_failures(
            state, "terminal"))
        failures: list[str] = []
        CHECKER.verify_report(failures, state)
        self.assertTrue(failures)

    def test_live_repaint_requires_only_content_progress(self) -> None:
        before = {
            "generation": 3, "content_repaints": 2,
            "full_repaints": 1, "chrome_repaints": 1,
        }
        after = {
            "generation": 3, "content_repaints": 3,
            "full_repaints": 1, "chrome_repaints": 1,
        }
        self.assertEqual([], RUNNER.repaint_delta_failures(
            before, after, "live"))
        failures: list[str] = []
        CHECKER.verify_repaint_delta(failures, before, after)
        self.assertEqual([], failures)
        after["chrome_repaints"] = 2
        self.assertTrue(RUNNER.repaint_delta_failures(
            before, after, "live"))
        failures = []
        CHECKER.verify_repaint_delta(failures, before, after)
        self.assertTrue(failures)

    def test_presenter_outcome_projection_is_exact(self) -> None:
        state = terminal_state()
        self.assertEqual([], RUNNER.presenter_failures(state, "terminal"))
        failures: list[str] = []
        CHECKER.verify_presenter(failures, state, "terminal")
        self.assertEqual([], failures)
        state["presenter_report_openable"] = True
        self.assertTrue(RUNNER.presenter_failures(state, "terminal"))
        failures = []
        CHECKER.verify_presenter(failures, state, "terminal")
        self.assertTrue(failures)

    def test_boot_and_recovery_are_bound_to_exact_candidate_and_cid(self) -> None:
        identity = "a" * 64
        cid = "B" * 32
        boot = {
            "schema": "leshy.boot.v1", "kind": "ready",
            "version": "dev.test", "app_elf_sha256": identity,
            "buzzer_inactive": True, "input_detected": True,
            "input_probe_attempts": 2,
            "input_probe_transient_retries": 1,
            "heap_total": 100, "heap_free": 80, "heap_min_free": 70,
        }
        recovery = {
            "schema": "leshy.storage.product_boot_recovery.v1",
            "kind": "state", "status": "admitted", "enrolled": True,
            "expected_fingerprint": cid, "observed_fingerprint": cid,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "write_enabled": False,
            "blocked_write_attempts": 0, "catalog_admitted": True,
            "cleanup_complete": True, "physical_write_calls": 0,
            "attempts": 1, "transient_retries": 0,
            "generation": 3, "observations": 9,
        }
        run = {
            "boot": boot,
            "boot_metrics_samples": [dict(boot), dict(boot)],
            "recovery_before": recovery,
            "recovery_after": dict(recovery),
        }
        failures: list[str] = []
        CHECKER.verify_boot_and_recovery(
            failures, run, identity, "dev.test", cid)
        self.assertEqual([], failures)
        run["recovery_after"]["observed_fingerprint"] = "C" * 32
        failures = []
        CHECKER.verify_boot_and_recovery(
            failures, run, identity, "dev.test", cid)
        self.assertTrue(failures)

    def test_hil_session_requires_exact_ack_semantics_and_continuity(self) -> None:
        identity = "a" * 64
        run_id = "b" * 32
        run = {
            "run_id": run_id,
            "hil_session": {
                "begin": {
                    "schema": "leshy.hil.session.v1",
                    "kind": "begun", "status": "begun", "active": True,
                    "session_id": run_id, "app_elf_sha256": identity,
                    "firmware_version": "dev.test", "ui_revision": 4,
                    "host_begin_action_writes": 1,
                    "host_begin_action_replays": 0,
                    "host_begin_ack_received": True,
                },
                "end": {
                    "schema": "leshy.hil.session.v1",
                    "kind": "ended", "status": "ended", "active": False,
                    "session_id": run_id, "app_elf_sha256": identity,
                    "firmware_version": "dev.test", "ui_revision": 9,
                    "host_end_requested_session_id": run_id,
                    "host_end_action_writes": 1,
                    "host_end_action_replays": 0,
                    "host_end_ack_received": True,
                },
            },
        }
        failures: list[str] = []
        CHECKER.verify_hil_session(failures, run, identity, "dev.test")
        self.assertEqual([], failures)
        for path, value in (
                (("begin", "schema"), "synthetic"),
                (("begin", "status"), "active"),
                (("end", "session_id"), ""),
                (("end", "ui_revision"), 3)):
            with self.subTest(path=path):
                changed = copy.deepcopy(run)
                changed["hil_session"][path[0]][path[1]] = value
                failures = []
                CHECKER.verify_hil_session(
                    failures, changed, identity, "dev.test")
                self.assertTrue(failures)

    def test_lost_ack_session_requires_state_and_error(self) -> None:
        identity = "a" * 64
        run_id = "b" * 32
        run = {
            "run_id": run_id,
            "hil_session": {
                "begin": {
                    "schema": "leshy.hil.session.v1",
                    "kind": "state", "status": "active", "active": True,
                    "session_id": run_id, "app_elf_sha256": identity,
                    "firmware_version": "dev.test", "ui_revision": 7,
                    "host_begin_action_writes": 1,
                    "host_begin_action_replays": 0,
                    "host_begin_ack_received": False,
                    "host_begin_ack_error": "timeout",
                },
                "end": {
                    "schema": "leshy.hil.session.v1",
                    "kind": "state", "status": "inactive",
                    "active": False, "session_id": "",
                    "app_elf_sha256": identity,
                    "firmware_version": "dev.test", "ui_revision": 8,
                    "host_end_requested_session_id": run_id,
                    "host_end_action_writes": 2,
                    "host_end_action_replays": 1,
                    "host_end_ack_received": False,
                    "host_end_ack_error": "timeout",
                },
            },
        }
        failures: list[str] = []
        CHECKER.verify_hil_session(failures, run, identity, "dev.test")
        self.assertEqual([], failures)
        del run["hil_session"]["end"]["host_end_ack_error"]
        failures = []
        CHECKER.verify_hil_session(failures, run, identity, "dev.test")
        self.assertTrue(failures)

    def test_synthetic_terminal_back_is_direct_and_fail_closed(self) -> None:
        identity = "a" * 64
        run_id = "b" * 32
        auth_resource = {
            name: None for name in RUNNER.AUTH_RESOURCE_FIELDS
        }
        auth_resource.update({
            "schema": RUNNER.AUTH_SCHEMA, "kind": "state",
            "read_only_query": True, "generation": 12,
            "capture_state": "complete", "capture_active": False,
            "capture_cleanup_complete": True,
            "adapter_cleanup_complete": True,
            "esp_rf_owned_by_foreground": True,
            "target_selected": True, "target_selection_continuity": True,
            "channel": 6, "duration_ms": 10_000,
            "maximum_frames": 16, "snap_length": 256,
            "production_report_fingerprint": "0123456789abcdef",
            "production_report_fingerprint_scope": "hil_session",
            "production_controller_ready": True,
            "production_controller_view": "outcome",
            "production_controller_action_selection": 0,
            "production_controller_peer_selection": 0,
            "production_controller_evidence_selection": 0,
            "production_controller_report_bound": True,
        })
        capture = {
            "schema": RUNNER.CAPTURE_SCHEMA, "kind": "state",
            "state": "complete", "passive_only": True, "rx_only": True,
            "application_connect_calls": 0, "application_raw_tx_calls": 0,
            "storage_written": False, "cleanup_complete": True,
            "lease_mask": 15,
        }
        boot_recovery = {
            "schema": "leshy.storage.product_boot_recovery.v1",
            "kind": "state", "write_enabled": False,
            "cleanup_complete": True, "owned_after": 0, "generation": 3,
        }
        resource = {
            "auth_resource": auth_resource,
            "capture": capture,
            "boot_recovery": boot_recovery,
        }
        fixture = {
            "schema": RUNNER.SYNTHETIC_FIXTURE_SCHEMA,
            "kind": "loaded", "status": "loaded", "loaded": True,
            "synthetic": True, "profile": "full",
            "report_identity": "wifi-auth-ui-full-v1",
            "report_origin": "synthetic_hil", "one_shot": True,
            "replayed": False, "hil_active": True,
            "display_touched": True, "rf_hardware_touched": False,
            "radio_started": False, "storage_mounted": False,
            "storage_written": False, "connect_calls": 0,
            "raw_tx_calls": 0, "generation": 12,
            "host_fixture_action_writes": 1,
            "host_fixture_action_replays": 0,
            "host_fixture_ack_received": True,
        }
        replay = dict(fixture)
        replay.update({
            "kind": "error", "status": "replay_rejected",
            "loaded": False, "replayed": True, "display_touched": False,
        })
        outcome = dict(auth_resource)
        outcome.update({
            "view": "authentication_capture", "state": "result",
            "failure": "none", "synthetic": True,
            "report_origin": "synthetic_hil", "outcome": "complete",
            "uncertainty": 0, "evidence": 6, "peers": 2,
            "complete_peers": 1, "pmkids": 1, "source_frames": 6,
            "presenter_view": "result", "presenter_tone": "positive",
            "presenter_evidence_incomplete": False,
            "presenter_report_openable": True,
            "presenter_cleanup_complete": True, "presenter_row_count": 4,
            "presenter_synthetic": True,
            "presenter_synthetic_label_visible": True,
            "presenter_title_semantic": "capture_result",
            "presenter_headline_semantic": "full_handshake",
            "presenter_note_semantic": "simulated_data",
            "controller_ready": True, "controller_view": "outcome",
            "controller_action_count": 2,
            "controller_action_selection": 0,
            "controller_selected_action": "details",
            "controller_peer_count": 2, "controller_peer_selection": 0,
            "controller_peer_position": 0,
            "controller_selected_peer_mask": 0x0f,
            "controller_selected_peer_evidence_count": 4,
            "controller_evidence_count": 6,
            "controller_evidence_selection": 0,
            "controller_selected_evidence_present": True,
            "controller_selected_evidence_report_index": 0,
            "controller_selected_evidence_source_frame": 0,
            "controller_selected_evidence_message": "message_1",
            "controller_selected_evidence_has_pmkid": True,
            "repeat_requested": False, "repeat_request_generation": 1,
        })
        back_state = dict(auth_resource)
        back_state.update({
            "view": "menu", "state": "idle", "synthetic": False,
            "report_origin": "none", "repeat_requested": False,
            "repeat_request_generation": 1, "failure": "none",
            "cancel_pending": False, "back_during_wait_observed": False,
            "survey_worker_deadline_armed": False,
        })
        proof = {
            "schema":
                "leshy.wifi.authentication.synthetic_back_cleanup.v1",
            "session_cycle": {
                "end": {
                    "schema": "leshy.hil.session.v1", "active": False,
                    "app_elf_sha256": identity,
                    "host_end_requested_session_id": run_id,
                    "host_end_action_writes": 1,
                    "host_end_action_replays": 0,
                },
                "begin": {
                    "schema": "leshy.hil.session.v1", "active": True,
                    "session_id": run_id, "app_elf_sha256": identity,
                    "firmware_version": "dev.test",
                    "host_begin_action_writes": 1,
                    "host_begin_action_replays": 0,
                },
            },
            "ambient": {
                "terminal": {
                    "state": "result", "synthetic": False,
                    "report_origin": "ambient_rf", "passive": True,
                    "tx_path": False, "connect_path": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                },
                "capture_terminal": dict(capture),
            },
            "fixture": fixture, "replay_rejected": replay,
            "baseline_resource": resource,
            "loaded_resource": copy.deepcopy(resource),
            "outcome": outcome,
            "back_action": {
                "host_navigation_action_writes": 1,
                "host_navigation_action_replays": 0,
                "wifi_product_view": "menu", "runtime_owner": "wifi",
                "lease_mask": 15, "changed": True,
            },
            "back_state": back_state,
            "back_resource": copy.deepcopy(resource),
            "back_delayed": copy.deepcopy(back_state),
            "home": {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            },
            "production_continuity": auth_resource,
            "boot_recovery_continuity": True,
            "product_storage_writes_measured": False,
            "static_no_storage_api_contract_required": True,
        }
        run = {"run_id": run_id, "synthetic_back_cleanup": proof}
        failures: list[str] = []
        CHECKER.verify_synthetic_terminal_back_cleanup(
            failures, run, identity, "dev.test")
        self.assertEqual([], failures)
        for path, value in (
                (("back_action", "changed"), False),
                (("back_state", "synthetic"), True),
                (("back_state", "repeat_requested"), True),
                (("back_delayed", "generation"), 13),
                (("product_storage_writes_measured",), True),
                (("session_cycle", "begin", "active"), False),
                (("outcome", "production_report_fingerprint"),
                 "fedcba9876543210")):
            with self.subTest(path=path):
                changed = copy.deepcopy(run)
                target = changed["synthetic_back_cleanup"]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                failures = []
                CHECKER.verify_synthetic_terminal_back_cleanup(
                    failures, changed, identity, "dev.test")
                self.assertTrue(failures)

    def test_synthetic_fixture_is_one_exact_non_replayed_mutation(self) -> None:
        loaded = {
            "schema": RUNNER.SYNTHETIC_FIXTURE_SCHEMA,
            "kind": "loaded", "status": "loaded", "loaded": True,
            "synthetic": True, "profile": "full",
            "report_identity": "wifi-auth-ui-full-v1",
            "report_origin": "synthetic_hil", "one_shot": True,
            "replayed": False, "hil_active": True,
            "display_touched": True, "rf_hardware_touched": False,
            "radio_started": False,
            "storage_mounted": False, "storage_written": False,
            "connect_calls": 0, "raw_tx_calls": 0, "generation": 11,
        }
        replay = dict(loaded)
        replay.update({
            "kind": "error", "status": "replay_rejected",
            "loaded": False, "replayed": True, "display_touched": False,
        })
        with patch.object(RUNNER, "query", side_effect=(loaded, replay)) \
                as query_fixture:
            retained_loaded = RUNNER.load_synthetic_report_once(object())
            retained_replay = RUNNER.reject_synthetic_report_replay(object())
        self.assertEqual(2, query_fixture.call_count)
        for call, kind in zip(query_fixture.call_args_list,
                              ("loaded", "error")):
            self.assertEqual(
                RUNNER.SYNTHETIC_FIXTURE_COMMAND, call.args[1])
            self.assertEqual(RUNNER.SYNTHETIC_FIXTURE_SCHEMA, call.args[2])
            self.assertEqual(kind, call.args[3])
        self.assertEqual(1, retained_loaded["host_fixture_action_writes"])
        self.assertEqual(0, retained_loaded["host_fixture_action_replays"])
        failures: list[str] = []
        CHECKER.verify_synthetic_fixture_ack(failures, retained_loaded)
        CHECKER.verify_synthetic_replay_rejected(
            failures, retained_replay)
        self.assertEqual([], failures)
        for field, value in (
                ("display_touched", False),
                ("rf_hardware_touched", True), ("radio_started", True),
                ("storage_written", True), ("connect_calls", 1),
                ("raw_tx_calls", 1), ("report_origin", "ambient_rf"),
                ("host_fixture_action_replays", 1)):
            with self.subTest(field=field):
                changed = dict(retained_loaded)
                changed[field] = value
                failures = []
                CHECKER.verify_synthetic_fixture_ack(failures, changed)
                self.assertTrue(failures)

    def test_synthetic_controller_state_and_masks_are_exact(self) -> None:
        state = synthetic_controller_state()
        self.assertEqual([], RUNNER.synthetic_controller_failures(
            state, "outcome", "outcome", repeat_request_generation=7))
        failures: list[str] = []
        CHECKER.verify_synthetic_controller_state(
            failures, state, "outcome", "outcome",
            repeat_request_generation=7)
        self.assertEqual([], failures)

        partial = synthetic_controller_state(
            "peer_detail", controller_peer_selection=1,
            controller_peer_position=1,
            controller_selected_peer_mask=0x03,
            controller_selected_peer_evidence_count=2)
        self.assertEqual([], RUNNER.synthetic_controller_failures(
            partial, "partial", "peer_detail", peer_selection=1,
            peer_position=1, peer_mask=0x03, peer_evidence=2,
            repeat_request_generation=7))
        failures = []
        CHECKER.verify_synthetic_controller_state(
            failures, partial, "partial", "peer_detail", peer_selection=1,
            peer_position=1, peer_mask=0x03, peer_evidence=2,
            repeat_request_generation=7)
        self.assertEqual([], failures)
        for field, value in (
                ("presenter_view", "actions"),
                ("presenter_tone", "caution"),
                ("presenter_row_count", 3),
                ("presenter_synthetic", False),
                ("presenter_synthetic_label_visible", False),
                ("presenter_title_semantic", "authentication_actions"),
                ("presenter_headline_semantic", "partial_handshake"),
                ("presenter_note_semantic", "none")):
            with self.subTest(presenter_field=field):
                changed = dict(state)
                changed[field] = value
                self.assertTrue(RUNNER.synthetic_controller_failures(
                    changed, "outcome", "outcome",
                    repeat_request_generation=7))
                failures = []
                CHECKER.verify_synthetic_controller_state(
                    failures, changed, "outcome", "outcome",
                    repeat_request_generation=7)
                self.assertTrue(failures)
        partial["controller_selected_peer_mask"] = 0
        self.assertTrue(RUNNER.synthetic_controller_failures(
            partial, "partial", "peer_detail", peer_selection=1,
            peer_position=1, peer_mask=0x03, peer_evidence=2,
            repeat_request_generation=7))

    def test_synthetic_navigation_rejects_full_clear_and_static_pixels(
            self) -> None:
        before = synthetic_controller_state(
            content_repaints=10, full_repaints=2, chrome_repaints=3)
        after = synthetic_controller_state(
            "actions", content_repaints=11, full_repaints=2,
            chrome_repaints=4)
        self.assertEqual([], RUNNER.navigation_repaint_failures(
            before, after, "edge", expected_chrome_delta=1))
        failures: list[str] = []
        CHECKER.verify_navigation_repaint(
            failures, before, after, "edge", 1)
        self.assertEqual([], failures)
        after["full_repaints"] = 3
        self.assertTrue(RUNNER.navigation_repaint_failures(
            before, after, "edge", expected_chrome_delta=1))
        failures = []
        CHECKER.verify_navigation_repaint(
            failures, before, after, "edge", 1)
        self.assertTrue(failures)

        pixels = {
            "content_changed_pixels": 1, "title_changed_pixels": 1,
            "status_changed_pixels": 0,
            "footer_changed_pixels": 1,
            "unexpected_static_chrome_changed_pixels": 0,
        }
        self.assertEqual([], RUNNER.navigation_pixel_delta_failures(
            pixels, "edge", title_change_required=True,
            footer_change_required=True))
        failures = []
        CHECKER.verify_navigation_pixel_delta(
            failures, pixels, "edge", True, True)
        self.assertEqual([], failures)
        pixels["unexpected_static_chrome_changed_pixels"] = 1
        self.assertTrue(RUNNER.navigation_pixel_delta_failures(
            pixels, "edge", title_change_required=True,
            footer_change_required=True))
        failures = []
        CHECKER.verify_navigation_pixel_delta(
            failures, pixels, "edge", True, True)
        self.assertTrue(failures)

    def test_footer_is_dynamic_but_neighboring_chrome_is_static(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frames = Path(temporary)
            size = RUNNER.WIDTH * RUNNER.HEIGHT * 2
            before = bytearray(size)
            after = bytearray(size)
            footer_offset = (
                RUNNER.FOOTER_Y0 * RUNNER.WIDTH + RUNNER.FOOTER_X0) * 2
            after[footer_offset] = 1
            static_offset = (
                (RUNNER.FOOTER_Y0 - 1) * RUNNER.WIDTH +
                RUNNER.FOOTER_X0) * 2
            after[static_offset] = 1
            (frames / "before.rgb565").write_bytes(before)
            (frames / "after.rgb565").write_bytes(after)
            delta = CHECKER.screen_pixel_changes(frames, "before", "after")
        self.assertIsNotNone(delta)
        self.assertEqual(1, delta["footer_changed_pixels"])
        self.assertEqual(
            1, delta["unexpected_static_chrome_changed_pixels"])

    def test_cap049_requires_exactly_one_fresh_app_flash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            firmware = Path(temporary) / "firmware.bin"
            firmware.write_bytes(b"app")
            output = Path(temporary) / "must-not-exist"
            argv = [
                "runner", "--port", RUNNER.BOARD_PORT,
                "--firmware", str(firmware),
                "--expected-version", "dev.test", "--expected-cid",
                "0" * 32, "--source-commit", "0" * 40,
                "--output", str(output), "--reuse-exact-flash",
            ]
            with patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
                RUNNER.main()
            self.assertFalse(output.exists())
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        self.assertEqual(1, source.count("flash_candidate("))

    def test_ambient_and_synthetic_proofs_are_disjoint_and_fail_closed(
            self) -> None:
        edges = (
            ("outcome", "actions_right", 1),
            ("actions_right", "outcome_left", 1),
            ("outcome_left", "actions_select", 1),
            ("actions_select", "outcome_back", 1),
            ("outcome_back", "actions_details", 1),
            ("actions_details", "actions_repeat", 0),
            ("actions_repeat", "actions_details_again", 0),
            ("actions_details_again", "peer_first", 1),
            ("peer_first", "peer_second", 0),
            ("peer_second", "peer_first_again", 0),
            ("peer_first_again", "evidence_list", 1),
            ("evidence_list", "evidence_second", 0),
            ("evidence_second", "evidence_first_again", 0),
            ("evidence_first_again", "evidence_detail", 1),
            ("evidence_detail", "evidence_list_back", 1),
            ("evidence_list_back", "peer_back", 1),
            ("peer_back", "actions_back", 1),
            ("actions_back", "repeat_selected", 0),
        )
        views = {
            "outcome": "outcome", "actions_right": "actions",
            "outcome_left": "outcome", "actions_select": "actions",
            "outcome_back": "outcome", "actions_details": "actions",
            "actions_repeat": "actions",
            "actions_details_again": "actions",
            "peer_first": "peer_detail", "peer_second": "peer_detail",
            "peer_first_again": "peer_detail",
            "evidence_list": "evidence_list",
            "evidence_second": "evidence_list",
            "evidence_first_again": "evidence_list",
            "evidence_detail": "evidence_detail",
            "evidence_list_back": "evidence_list",
            "peer_back": "peer_detail", "actions_back": "actions",
            "repeat_selected": "actions",
        }
        overrides = {
            "actions_repeat": {
                "controller_action_selection": 1,
                "controller_selected_action": "repeat"},
            "peer_second": {
                "controller_peer_selection": 1,
                "controller_peer_position": 1,
                "controller_selected_peer_mask": 0x03,
                "controller_selected_peer_evidence_count": 2},
            "evidence_second": {
                "controller_evidence_selection": 1,
                "controller_selected_evidence_report_index": 1,
                "controller_selected_evidence_source_frame": 1,
                "controller_selected_evidence_message": "message_2",
                "controller_selected_evidence_has_pmkid": False},
            "repeat_selected": {
                "controller_action_selection": 1,
                "controller_selected_action": "repeat"},
        }
        navigation: dict[str, dict[str, Any]] = {
            "outcome": synthetic_controller_state(
                content_repaints=1, full_repaints=1, chrome_repaints=1),
        }
        content = 1
        chrome = 1
        for before, after, chrome_delta in edges:
            self.assertIn(before, navigation)
            content += 1
            chrome += chrome_delta
            navigation[after] = synthetic_controller_state(
                views[after], content_repaints=content,
                full_repaints=1, chrome_repaints=chrome,
                **overrides.get(after, {}))
        repeat_request = {
            "schema": RUNNER.AUTH_SCHEMA, "kind": "state",
            "read_only_query": True,
            "view": "menu", "state": "idle",
            "synthetic": False, "report_origin": "none",
            "generation": 11, "repeat_requested": True,
            "repeat_request_generation": 8,
            "capture_state": "complete",
            "capture_active": False, "capture_cleanup_complete": True,
            "adapter_cleanup_complete": True, "failure": "none",
            "passive": True, "tx_path": False, "connect_path": False,
            "esp_rf_owned_by_foreground": True,
            "target_selected": True,
            "target_selection_continuity": True,
            "production_report_fingerprint": "0123456789abcdef",
            "production_report_fingerprint_scope": "hil_session",
            "production_controller_ready": True,
            "production_controller_view": "outcome",
            "production_controller_action_selection": 0,
            "production_controller_peer_selection": 0,
            "production_controller_evidence_selection": 0,
            "production_controller_report_bound": True,
        }
        navigation["repeat_request"] = repeat_request
        fixture = {
            "schema": RUNNER.SYNTHETIC_FIXTURE_SCHEMA,
            "kind": "loaded", "status": "loaded", "loaded": True,
            "synthetic": True, "profile": "full",
            "report_identity": "wifi-auth-ui-full-v1",
            "report_origin": "synthetic_hil", "one_shot": True,
            "replayed": False, "hil_active": True,
            "display_touched": True, "rf_hardware_touched": False,
            "radio_started": False,
            "storage_mounted": False, "storage_written": False,
            "connect_calls": 0, "raw_tx_calls": 0, "generation": 11,
            "host_fixture_action_writes": 1,
            "host_fixture_action_replays": 0,
            "host_fixture_ack_received": True,
        }
        replay = dict(fixture)
        replay.update({
            "kind": "error", "status": "replay_rejected",
            "loaded": False, "replayed": True, "display_touched": False,
        })
        ambient_terminal = {
            "state": "result", "synthetic": False,
            "report_origin": "ambient_rf", "generation": 11,
            "outcome": "inconclusive", "evidence": 0,
        }
        capture_terminal = {
            "state": "complete", "cleanup_complete": True,
        }
        ambient = {
            "schema": "leshy.wifi.authentication.ambient_rf_proof.v1",
            "synthetic": False, "report_origin": "ambient_rf",
            "generation": 11, "outcome": "inconclusive", "evidence": 0,
            "capture_state": "complete", "capture_cleanup_complete": True,
            "application_connect_calls": 0,
            "application_raw_tx_calls": 0,
            "ambient_eapol_required": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = root / "frames"
            frames.mkdir()
            size = RUNNER.WIDTH * RUNNER.HEIGHT * 2

            def frame(content_value: int, title_value: int,
                      footer_value: int, note_value: int = 0) -> bytes:
                value = bytearray(size)
                value[(40 * RUNNER.WIDTH + 20) * 2] = content_value
                value[(RUNNER.TITLE_Y0 * RUNNER.WIDTH +
                       RUNNER.TITLE_X0) * 2] = title_value
                value[(RUNNER.FOOTER_Y0 * RUNNER.WIDTH + 20) * 2] = \
                    footer_value
                if note_value:
                    for y in range(RUNNER.NOTE_Y0, RUNNER.NOTE_Y0 + 8):
                        for x in range(
                                RUNNER.NOTE_X0, RUNNER.NOTE_X0 + 50):
                            value[(y * RUNNER.WIDTH + x) * 2] = note_value
                return bytes(value)

            physical = {
                "wifi-auth-result": frame(0, 0, 0, 1),
                "wifi-auth-synthetic-outcome": frame(1, 1, 1, 2),
                "wifi-auth-synthetic-actions": frame(2, 2, 2),
                "wifi-auth-synthetic-peer-first": frame(3, 3, 3),
                "wifi-auth-synthetic-peer-second": frame(4, 3, 3),
                "wifi-auth-synthetic-evidence-list": frame(5, 4, 4),
                "wifi-auth-synthetic-evidence-detail": frame(6, 5, 5),
            }
            for name, data in physical.items():
                (frames / f"{name}.rgb565").write_bytes(data)
            pixel_specs = {
                "outcome_to_actions": (
                    "wifi-auth-synthetic-outcome",
                    "wifi-auth-synthetic-actions"),
                "actions_to_peer": (
                    "wifi-auth-synthetic-actions",
                    "wifi-auth-synthetic-peer-first"),
                "peer_first_to_second": (
                    "wifi-auth-synthetic-peer-first",
                    "wifi-auth-synthetic-peer-second"),
                "evidence_list_to_detail": (
                    "wifi-auth-synthetic-evidence-list",
                    "wifi-auth-synthetic-evidence-detail"),
            }
            deltas = {
                name: CHECKER.screen_pixel_changes(frames, before, after)
                for name, (before, after) in pixel_specs.items()
            }
            note_delta = CHECKER.pixel_region_proof(
                frames, "wifi-auth-result", "wifi-auth-synthetic-outcome",
                x0=RUNNER.NOTE_X0, x1=RUNNER.NOTE_X1,
                y0=RUNNER.NOTE_Y0, y1=RUNNER.NOTE_Y1)
            auth_resource = {
                name: None for name in RUNNER.AUTH_RESOURCE_FIELDS
            }
            auth_resource.update({
                "schema": RUNNER.AUTH_SCHEMA, "kind": "state",
                "read_only_query": True, "generation": 11,
                "capture_state": "complete", "capture_active": False,
                "capture_cleanup_complete": True,
                "adapter_cleanup_complete": True,
                "esp_rf_owned_by_foreground": True,
                "target_selected": True,
                "target_selection_continuity": True,
                "production_report_fingerprint": "0123456789abcdef",
                "production_report_fingerprint_scope": "hil_session",
                "production_controller_ready": True,
                "production_controller_view": "outcome",
                "production_controller_action_selection": 0,
                "production_controller_peer_selection": 0,
                "production_controller_evidence_selection": 0,
                "production_controller_report_bound": True,
            })
            capture_resource = {
                "schema": RUNNER.CAPTURE_SCHEMA, "kind": "state",
                "state": "complete", "passive_only": True,
                "rx_only": True, "application_connect_calls": 0,
                "application_raw_tx_calls": 0,
                "storage_written": False, "cleanup_complete": True,
                "lease_mask": 15,
            }
            storage_resource = {
                "schema": "leshy.storage.product_boot_recovery.v1",
                "kind": "state", "write_enabled": False,
                "physical_write_calls": 0, "cleanup_complete": True,
                "owned_after": 0, "generation": 3,
            }
            resource_snapshot = {
                "auth_resource": auth_resource,
                "capture": capture_resource,
                "boot_recovery": storage_resource,
            }
            run = {
                "auth_terminal": ambient_terminal,
                "capture_terminal": capture_terminal,
                "ambient_rf_proof": ambient,
                "synthetic_ui_proof": {
                    "schema":
                        "leshy.wifi.authentication.synthetic_ui_proof.v1",
                    "synthetic": True, "report_origin": "synthetic_hil",
                    "export_eligibility": "not_evaluated",
                    "right_select_equivalent": True,
                    "left_back_equivalent": True,
                    "fixture": fixture, "replay_rejected": replay,
                    "side_effects": {
                        "schema":
                            "leshy.wifi.authentication.synthetic_side_effects.v1",
                        "production_continuity_proven": True,
                        "boot_recovery_continuity": True,
                        "product_storage_writes_measured": False,
                        "static_no_storage_api_contract_required": True,
                        "before": resource_snapshot,
                        "after": copy.deepcopy(resource_snapshot),
                    },
                    "ambient_to_synthetic_note": note_delta,
                    "navigation": navigation,
                    "repeat_request": repeat_request,
                    "repeat_resource": copy.deepcopy(resource_snapshot),
                    "repeat_delayed": copy.deepcopy(repeat_request),
                    "production_continuity": copy.deepcopy(auth_resource),
                    "repeat_action": {
                        "host_navigation_action_writes": 1,
                        "host_navigation_action_replays": 0,
                        "host_navigation_ack_received": True,
                        "action": "select", "changed": True,
                    },
                    "pixel_deltas": deltas,
                },
            }
            failures: list[str] = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, run, root)
            self.assertEqual([], failures)

            changed = copy.deepcopy(run)
            changed["ambient_rf_proof"]["synthetic"] = True
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)
            changed = copy.deepcopy(run)
            changed["synthetic_ui_proof"]["export_eligibility"] = "eligible"
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)
            for field, value in (
                    ("product_storage_writes_measured", True),
                    ("static_no_storage_api_contract_required", False),
                    ("boot_recovery_continuity", False)):
                with self.subTest(scope_field=field):
                    changed = copy.deepcopy(run)
                    changed["synthetic_ui_proof"]["side_effects"][field] = value
                    failures = []
                    CHECKER.verify_ambient_and_synthetic_proofs(
                        failures, changed, root)
                    self.assertTrue(failures)
            for section, field, value in (
                    ("capture", "application_connect_calls", 1),
                    ("capture", "application_raw_tx_calls", 1),
                    ("boot_recovery", "generation", 4),
                    ("auth_resource", "esp_rf_owned_by_foreground", False)):
                with self.subTest(side_effect=f"{section}.{field}"):
                    changed = copy.deepcopy(run)
                    changed["synthetic_ui_proof"]["side_effects"]["after"][
                        section][field] = value
                    failures = []
                    CHECKER.verify_ambient_and_synthetic_proofs(
                        failures, changed, root)
                    self.assertTrue(failures)
            changed = copy.deepcopy(run)
            changed["synthetic_ui_proof"]["navigation"]["outcome"][
                "presenter_synthetic_label_visible"] = False
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)
            changed = copy.deepcopy(run)
            changed["synthetic_ui_proof"]["ambient_to_synthetic_note"][
                "changed_pixels"] = 0
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)
            for field, value in (
                    ("changed_pixels", 79), ("changed_rows", 6),
                    ("changed_columns", 31), ("bbox_width", 39)):
                with self.subTest(note_footprint=field):
                    changed = copy.deepcopy(run)
                    changed["synthetic_ui_proof"][
                        "ambient_to_synthetic_note"][field] = value
                    failures = []
                    CHECKER.verify_ambient_and_synthetic_proofs(
                        failures, changed, root)
                    self.assertTrue(failures)
            changed = copy.deepcopy(run)
            changed["synthetic_ui_proof"]["navigation"]["peer_second"][
                "production_report_fingerprint"] = "fedcba9876543210"
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)
            changed = copy.deepcopy(run)
            changed["synthetic_ui_proof"]["repeat_delayed"][
                "repeat_requested"] = False
            failures = []
            CHECKER.verify_ambient_and_synthetic_proofs(
                failures, changed, root)
            self.assertTrue(failures)

    def test_post_hil_end_is_inactive_home_and_privacy_closed(self) -> None:
        run = {"post_hil_end": {
            "hil": {
                "schema": "leshy.hil.session.v1", "kind": "state",
                "active": False,
            },
            "ui": {
                "schema": "leshy.ui.v1", "kind": "state",
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            },
            "auth": {
                "schema": RUNNER.AUTH_SCHEMA, "kind": "state",
                "read_only_query": True, "view": "menu", "state": "idle",
                "synthetic": False,
                "production_report_fingerprint": "unavailable",
                "production_report_fingerprint_scope": "none",
            },
        }}
        failures: list[str] = []
        CHECKER.verify_post_hil_end(failures, run)
        self.assertEqual([], failures)
        for section, field, value in (
                ("hil", "active", True),
                ("ui", "lease_mask", 15),
                ("auth", "production_report_fingerprint",
                 "0123456789abcdef")):
            with self.subTest(post_hil=f"{section}.{field}"):
                changed = copy.deepcopy(run)
                changed["post_hil_end"][section][field] = value
                failures = []
                CHECKER.verify_post_hil_end(failures, changed)
                self.assertTrue(failures)
    def test_fixture_port_is_rejected_before_output_or_serial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist"
            argv = [
                "runner", "--port", RUNNER.FORBIDDEN_FIXTURE_PORT,
                "--firmware", str(Path(temporary) / "missing.bin"),
                "--expected-version", "dev.test", "--expected-cid",
                "0" * 32, "--source-commit", "0" * 40,
                "--output", str(output), "--reuse-exact-flash",
            ]
            with patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
                RUNNER.main()
            self.assertFalse(output.exists())

    def test_runner_contains_no_host_radio_fixture(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        checker_source = Path(CHECKER.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CoreBluetooth", source)
        self.assertNotIn("external_ble", source)
        self.assertNotIn("subprocess", source)
        self.assertIn('"mac_wifi_control_calls": 0', source)
        self.assertIn('"mac_ble_fixture_calls": 0', source)
        self.assertIn('"fixture_ports_opened": []', source)
        self.assertIn('"application_rx_only": passed', source)
        self.assertNotIn('"passive_receive_only": passed', source)
        self.assertNotIn('"storage_write_authorized": False', source)
        self.assertNotIn(
            'scope.get("storage_write_authorized") is False', checker_source)
        self.assertIn('"product_storage_writes_measured": False', source)
        self.assertIn(
            '"static_no_storage_api_contract_required": True', source)
        self.assertIn('"storage_write_authorized" not in scope', checker_source)


if __name__ == "__main__":
    unittest.main()
