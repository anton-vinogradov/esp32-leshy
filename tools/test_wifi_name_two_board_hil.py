#!/usr/bin/env python3
"""Pure host checks: exact identity, bounded flash, full restore verification."""
from pathlib import Path
import unittest
from unittest.mock import patch
import run_wifi_name_two_board_hil as runner

class RunnerTests(unittest.TestCase):
    def test_identity_hash_matches_firmware(self):
        self.assertEqual(runner.identity_hash("000000000000"), 2138539933)
        self.assertNotEqual(runner.identity_hash("001122334455"),
                            runner.identity_hash("001122334456"))

    def test_wrong_board_rejected_before_flash(self):
        with patch.object(runner, "serial_metadata", return_value={"serial_number": "AA:BB:CC:DD:EE:FF"}):
            runner.exact_port("/dev/example", "aabbccddeeff")
            with self.assertRaisesRegex(RuntimeError, "identity"):
                runner.exact_port("/dev/example", "000000000000")

    @patch.object(runner, "esptool_environment", return_value={})
    @patch.object(runner.subprocess, "run")
    def test_restore_verifies_all_bytes_before_reset(self, run, environment):
        runner.flash_exact("/dev/fixture", Path("backup.bin"), 0, verify=True)
        self.assertEqual(3, run.call_count)
        calls = run.call_args_list
        self.assertIn("write_flash", calls[0].args[0])
        self.assertIn("verify_flash", calls[1].args[0])
        self.assertIn("watchdog_reset", calls[2].args[0])
        for call in calls:
            self.assertTrue(call.kwargs["check"])
            self.assertLessEqual(call.kwargs["timeout"], 180)
            self.assertIn("/dev/fixture", call.args[0])
        self.assertIn("0x0", calls[1].args[0])

    @patch.object(runner, "esptool_environment", return_value={})
    @patch.object(runner.subprocess, "run", side_effect=RuntimeError("write failed"))
    def test_failed_write_does_not_continue(self, run, environment):
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            runner.flash_exact("/dev/fixture", Path("backup.bin"), 0, verify=True)
        self.assertEqual(1, run.call_count)

if __name__ == "__main__":
    unittest.main()
