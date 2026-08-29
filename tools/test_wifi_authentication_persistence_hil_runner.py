#!/usr/bin/env python3

from __future__ import annotations

import unittest
from unittest.mock import patch

import run_1x_wifi_authentication_persistence_hil as runner


class WifiAuthenticationPersistenceHilRunnerTests(unittest.TestCase):
    def test_hc22000_summary_accepts_one_wpa02_record(self) -> None:
        payload = b"WPA*02*AA*BB*CC*DD*EE*FF*00\n"
        summary, failures = runner.hc22000_summary(payload)
        self.assertEqual(failures, [])
        self.assertEqual(summary["records"], 1)
        self.assertEqual(summary["format"], "WPA*02")
        self.assertNotIn(payload.decode("ascii").strip(), str(summary))

    def test_hc22000_summary_rejects_raw_or_multiple_records(self) -> None:
        for payload in (
            b"raw", b"WPA*01*AA*BB*CC*DD*EE*FF*00\n",
            b"WPA*02*AA*BB*CC*DD*EE*FF*00\n"
            b"WPA*02*AA*BB*CC*DD*EE*FF*00\n",
        ):
            with self.subTest(payload=payload):
                _, failures = runner.hc22000_summary(payload)
                self.assertTrue(failures)

    def test_ambient_summary_keeps_only_admission_and_safety(self) -> None:
        workflow = {
            "network_list": {
                "authorized_selector": {
                    "status": "selected", "host_selector_attempts": 3,
                    "host_selector_transient_retries": 2,
                },
            },
            "network_detail": {
                "ssid": "private", "identity_hash": 123, "channel": 6,
            },
            "terminal": {
                "state": "result", "report_origin": "ambient_rf",
                "outcome": "inconclusive",
                "capture_cleanup_complete": True,
                "adapter_cleanup_complete": True,
            },
            "capture_terminal": {
                "application_connect_calls": 0,
                "application_raw_tx_calls": 0,
            },
        }
        summary = runner.safe_ambient_summary(workflow)
        self.assertTrue(summary["authorized_selector_selected"])
        self.assertEqual(summary["selector_attempts"], 3)
        self.assertNotIn("'ssid': 'private'", str(summary))
        self.assertNotIn("identity_hash", summary)

    def test_runner_is_hard_bound_to_original_board(self) -> None:
        self.assertEqual(runner.BOARD_PORT, "/dev/cu.usbmodem2101")
        self.assertEqual(runner.FORBIDDEN_FIXTURE_PORT,
                         "/dev/cu.usbmodem1101")
        self.assertNotEqual(runner.BOARD_PORT, runner.FORBIDDEN_FIXTURE_PORT)

    def test_library_navigation_uses_stable_item_identity(self) -> None:
        states = [
            {"page": "home", "selected_id": "wifi"},
            {"page": "home", "selected_id": "ble"},
            {"page": "home", "selected_id": "spectrum24"},
            {"page": "home", "selected_id": "subghz"},
            {"page": "home", "selected_id": "capture"},
            {"page": "home", "selected_id": "targets"},
            {"page": "home", "selected_id": "library"},
            {"page": "library", "selected_id": "library"},
        ]
        current = {"index": 0}

        def fake_query(*args: object, **kwargs: object) -> dict[str, object]:
            return states[current["index"]]

        def fake_action(device: object, name: str) -> dict[str, object]:
            self.assertIn(name, ("down", "right"))
            current["index"] += 1
            return states[current["index"]]

        with patch.object(runner, "query", side_effect=fake_query), patch.object(
                runner, "action", side_effect=fake_action):
            opened = runner.open_home_item(object(), "library", "library")
        self.assertEqual(opened["page"], "library")
        self.assertEqual(current["index"], 7)


if __name__ == "__main__":
    unittest.main()
