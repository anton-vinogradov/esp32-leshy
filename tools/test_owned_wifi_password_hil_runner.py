#!/usr/bin/env python3
"""Focused tests for the current Wi-Fi password-check HIL coordinator."""

from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.Serial = object
    serial_stub.SerialException = OSError
    sys.modules["serial"] = serial_stub

import run_1x_owned_wifi_password_check_hil as runner
import test_owned_wifi_evidence_verifier as fixture


class OwnedWifiPasswordHilRunnerTests(unittest.TestCase):
    def test_current_network_list_is_volatile_until_explicit_save(self) -> None:
        preparing = {
            "page": "survey", "wifi_product_view": "networks",
            "runtime_owner": "wifi", "lease_mask": 15,
            "survey_product_selected_source_mask": 1,
        }
        live = {
            "wifi_product_view": "networks",
            "survey_workflow_state": "running",
            "survey_product_worker_ready": True,
            "wifi_networks_strongest_first": True,
            "wifi_networks_unique": 3,
            "survey_product_wifi_scan_cycles": 1,
            "runtime_owner": "wifi", "lease_mask": 15,
            "survey_product_status": "running",
            "survey_product_active_source_mask": 1,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_store_open_attempted": False,
            "survey_product_store_status": "permitted",
            "survey_product_admission_status": "permitted",
            "survey_product_filesystem_mount_stage": "idle",
            "survey_product_filesystem_bus_initialize_error": 0,
            "survey_product_filesystem_drive_available_before_vfs": False,
            "survey_product_filesystem_mount_attempts": 0,
            "survey_product_filesystem_mount_transient_retries": 0,
            "survey_product_filesystem_mount_error": 0,
            "survey_product_filesystem_mount_last_failure_error": 0,
            "survey_scan_status": "valid", "survey_scan_dropped": 0,
        }
        detail_ui = {
            "wifi_product_view": "network_detail",
            "wifi_network_navigation_locked": False,
            "wifi_network_focus_user_owned": True,
            "runtime_owner": "wifi", "lease_mask": 15,
        }
        detail = {
            "active": True, "passive": True,
            "active_probe_allowed": False,
            "identity_hash": 1, "channel": 6,
        }
        intro_ui = {
            "wifi_product_view": "password_check_intro",
            "runtime_event": "wifi_password_check_intro",
            "survey_workflow_state": "running",
            "runtime_owner": "wifi", "lease_mask": 15,
        }
        diagnostics = {}
        with mock.patch.object(
                runner.authentication, "action",
                side_effect=(preparing, detail_ui, intro_ui)) as action, \
                mock.patch.object(
                    runner.authentication, "wait_ui_state",
                    return_value=live), \
                mock.patch.object(
                    runner.authentication, "select_authorized_network",
                    return_value={"status": "selected"}), \
                mock.patch.object(
                    runner.authentication, "read_only_query",
                    return_value=detail):
            selected, selected_ui, selected_detail = \
                runner.current_network_detail(
                    object(), [], "current", "0123456789abcdef", diagnostics)
        self.assertIs(live, selected)
        self.assertIs(detail_ui, selected_ui)
        self.assertIs(detail, selected_detail)
        self.assertFalse(selected_ui["wifi_network_navigation_locked"])
        self.assertTrue(selected_ui["wifi_network_focus_user_owned"])
        self.assertEqual(3, action.call_count)
        self.assertEqual("volatile_list_mount_on_save_only",
                         diagnostics["current"]["policy"])

    def test_public_export_runs_through_guided_privacy_boundary(self) -> None:
        payload = (fixture.HASHCAT_REFERENCE_PMKID + "\n").encode("ascii")
        report = runner.run_guided_check(payload)
        self.assertEqual("weak_password_match", report["outcome"])
        self.assertFalse(report["privacy"]["plaintext_retained"])
        self.assertEqual(0, report["side_effects"]["network_operations"])

    def test_cold_library_export_traverses_explicit_ready_step(self) -> None:
        generation = 11

        def state(view: str) -> dict[str, object]:
            return {
                "page": "library", "library_view": view,
                "library_generation": generation,
                "library_selected_kind": "session",
                "library_persistent": True,
                "runtime_owner": "library", "lease_mask": 5,
            }

        with mock.patch.object(
                runner.persistence, "open_home_item",
                return_value=state("list")), mock.patch.object(
                    runner.persistence, "action",
                    side_effect=(state("detail"), state("actions"),
                                 state("export_ready"))) as action:
            navigation = runner.persistence.open_library_export_ready(
                object(), generation)
        self.assertEqual(3, action.call_count)
        self.assertEqual("export_ready",
                         navigation["export_ready"]["view"])

    def test_cold_library_exit_traverses_all_four_levels(self) -> None:
        generation = 11

        def library(view: str) -> dict[str, object]:
            return {
                "page": "library", "library_view": view,
                "library_generation": generation,
                "library_selected_kind": "session",
                "runtime_owner": "library", "lease_mask": 5,
            }

        home = {"page": "home", "runtime_owner": "none", "lease_mask": 0}
        with mock.patch.object(
                runner.persistence, "action",
                side_effect=(library("actions"), library("detail"),
                             library("list"), home)) as action:
            navigation = runner.persistence.close_library_export_to_home(
                object(), generation)
        self.assertEqual(4, action.call_count)
        self.assertEqual("home", navigation["home"]["page"])


if __name__ == "__main__":
    unittest.main()
