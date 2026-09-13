#!/usr/bin/env python3
"""Pure contracts for the read-only board-02 profiler."""

from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import profile_hil_board as profile  # noqa: E402


class HilBoardProfileTests(unittest.TestCase):
    def test_runtime_lookup_still_requires_local_installation(self) -> None:
        with tempfile.TemporaryDirectory() as name, \
             mock.patch.object(profile.Path, "home", return_value=Path(name)):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                profile.esptool_python()
            runtime = Path(name) / ".platformio/penv/bin/python"
            runtime.parent.mkdir(parents=True)
            runtime.touch()
            self.assertEqual(runtime, profile.esptool_python())

    def test_only_read_only_rom_commands_are_allowlisted(self) -> None:
        self.assertEqual(
            ("chip-id", "read-mac", "flash-id", "get-security-info"),
            profile.READ_ONLY_COMMANDS)

    def test_canonical_fixture_id_comes_from_base_mac(self) -> None:
        interpreted = profile.interpret_outputs([{
            "returncode": 0,
            "output": (
                "Chip is ESP32-S3\nMAC: aa:bb:cc:dd:ee:ff\n"
                "Detected flash size: 16MB\n"),
        }])
        self.assertEqual("AA:BB:CC:DD:EE:FF", interpreted["mac"])
        self.assertEqual("0000AABBCCDDEEFF", interpreted["fixture_id"])
        self.assertEqual("16MB", interpreted["flash_size"])
        self.assertTrue(interpreted["chip_is_esp32s3"])
        self.assertTrue(interpreted["commands_passed"])

    def test_failed_or_incomplete_output_is_not_accepted(self) -> None:
        interpreted = profile.interpret_outputs([
            {"returncode": 2, "output": "Chip is ESP32-S3"},
        ])
        self.assertFalse(interpreted["commands_passed"])
        self.assertIsNone(interpreted["fixture_id"])
        self.assertIsNone(interpreted["flash_size"])


if __name__ == "__main__":
    unittest.main()
