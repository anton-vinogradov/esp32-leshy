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
            "survey_product_filesystem_mount_error": 0,
            "survey_product_filesystem_mount_last_failure_error": 257,
            "survey_product_filesystem_mount_attempts": 2,
            "survey_product_filesystem_mount_transient_retries": 1,
            "survey_product_mount_attempts_total": 3,
            "survey_product_mount_successes_total": 2,
        }
        failures: list[str] = []
        CHECKER.verify_product_mount(failures, state, "valid")
        self.assertEqual([], failures)
        for name, value in (
                ("survey_product_backend_open", True),
                ("survey_product_storage_mounted", True),
                ("survey_product_filesystem_mount_error", 257),
                ("survey_product_filesystem_mount_last_failure_error", 0),
                ("survey_product_filesystem_mount_attempts", 4),
                ("survey_product_filesystem_mount_transient_retries", 0),
                ("survey_product_mount_successes_total", 4)):
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
        self.assertNotIn("CoreBluetooth", source)
        self.assertNotIn("external_ble", source)
        self.assertNotIn("subprocess", source)
        self.assertIn('"mac_wifi_control_calls": 0', source)
        self.assertIn('"mac_ble_fixture_calls": 0', source)
        self.assertIn('"fixture_ports_opened": []', source)
        self.assertIn('"application_rx_only": passed', source)
        self.assertNotIn('"passive_receive_only": passed', source)


if __name__ == "__main__":
    unittest.main()
