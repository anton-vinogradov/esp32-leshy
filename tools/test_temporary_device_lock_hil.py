#!/usr/bin/env python3

from __future__ import annotations

import unittest
import sys
import types
from unittest.mock import patch

capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)

import temporary_device_lock_hil as fixture


class TemporaryDeviceLockHilTests(unittest.TestCase):
    @patch.object(fixture, "home_device")
    @patch.object(fixture, "end_hil")
    @patch.object(fixture, "begin_hil")
    @patch.object(fixture, "protected_ui_fixture_command")
    def test_ram_only_admission_preserves_product_key(
            self, command, begin, end, home) -> None:
        begun = {
            "operation": "begin", "status": "begun", "active": True,
            "ram_only_admission": True, "protected_ui_only": True,
            "credential_written": False, "data_key_replaced": False,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False, "radio_touched": False,
        }
        cleaned = {
            **begun, "operation": "cleanup", "status": "cleaned",
            "active": False,
        }
        command.side_effect = [begun, cleaned]
        begin.return_value = {"kind": "begun", "active": True}
        end.return_value = {"kind": "ended", "active": False}
        home.return_value = {"page": "home"}
        session = fixture.TemporaryProtectedUiAdmissionHil(
            object(), "a" * 64)

        self.assertEqual({"page": "home"}, session.start())
        session.close()

        self.assertTrue(session.cleanup_proven)
        self.assertTrue(session.hil_ended)
        self.assertEqual(
            ["begin", "cleanup"],
            [call.args[1] for call in command.call_args_list],
        )
        evidence = session.evidence()
        self.assertTrue(evidence["ram_only_admission"])
        self.assertFalse(evidence["credential_written"])
        self.assertFalse(evidence["data_key_replaced"])

    @patch.object(fixture, "end_hil")
    @patch.object(fixture, "begin_hil")
    @patch.object(fixture, "protected_ui_fixture_command")
    def test_ram_only_admission_reauthenticates_for_idempotent_cleanup(
            self, command, begin, end) -> None:
        command.side_effect = [
            {"status": "hil_session_required"},
            {
                "operation": "cleanup", "status": "cleaned",
                "active": False, "ram_only_admission": True,
                "protected_ui_only": True, "credential_written": False,
                "data_key_replaced": False,
                "product_namespace_written_or_erased": False,
                "whole_nvs_read_or_copied": False,
                "radio_touched": False,
            },
        ]
        begin.return_value = {"kind": "begun", "active": True}
        end.return_value = {"kind": "ended", "active": False}
        session = fixture.TemporaryProtectedUiAdmissionHil(
            object(), "a" * 64)
        session.fixture_started = True
        session.hil_started = True

        session.close()

        self.assertTrue(session.cleanup_proven)
        begin.assert_called_once_with(
            session.device, session.run_id, session.app_identity)
        end.assert_called_once_with(session.device, session.run_id)

    @patch.object(fixture, "wipe_pin")
    @patch.object(fixture, "end_hil")
    @patch.object(fixture, "fixture_command")
    def test_close_restores_fixture_before_ending_session(
            self, command, end, wipe) -> None:
        events: list[str] = []
        cleanup_report = {
            "operation": "cleanup", "status": "cleaned", "active": False,
            "cleanup_required": False, "fixture_namespace_selected": False,
            "fixture_cleanup_complete": True, "product_restored": True,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False, "radio_touched": False,
        }
        command.side_effect = lambda *_args: (
            events.append("cleanup"), cleanup_report)[1]
        end.side_effect = lambda *_args: (
            events.append("end"), {"kind": "ended", "active": False})[1]
        wipe.side_effect = lambda *_args: events.append("wipe")
        session = fixture.TemporaryDeviceLockHil(object(), "a" * 64)
        session.fixture_started = True
        session.hil_started = True
        session.close()
        self.assertTrue(session.cleanup_proven)
        self.assertTrue(session.hil_ended)
        self.assertEqual(["cleanup", "end", "wipe"], events)
        end.assert_called_once()
        wipe.assert_called_once_with(session.pin)

    @patch.object(fixture, "wipe_pin")
    @patch.object(fixture, "end_hil")
    @patch.object(fixture, "begin_hil")
    @patch.object(fixture, "fixture_command")
    def test_close_reauthenticates_after_firmware_reset(
            self, command, begin, end, wipe) -> None:
        no_session = {"status": "hil_session_required"}
        cleaned = {
            "operation": "cleanup", "status": "cleaned", "active": False,
            "cleanup_required": False, "fixture_namespace_selected": False,
            "fixture_cleanup_complete": True, "product_restored": True,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False, "radio_touched": False,
        }
        command.side_effect = [no_session, cleaned]
        begin.return_value = {"kind": "begun", "active": True}
        end.return_value = {"kind": "ended", "active": False}
        session = fixture.TemporaryDeviceLockHil(object(), "a" * 64)
        session.fixture_started = True
        session.hil_started = True

        session.close()

        self.assertTrue(session.cleanup_proven)
        self.assertTrue(session.hil_ended)
        self.assertEqual(2, command.call_count)
        begin.assert_called_once_with(
            session.device, session.run_id, session.app_identity)
        end.assert_called_once_with(
            session.device, session.run_id)
        wipe.assert_called_once_with(session.pin)


if __name__ == "__main__":
    unittest.main()
