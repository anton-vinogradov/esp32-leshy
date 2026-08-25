#!/usr/bin/env python3
"""Pure host tests for the one-command two-board infrared HIL flow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_ir_two_board_hil as flow  # noqa: E402
import run_s5_two_board_hil as phase_flow  # noqa: E402


class IrTwoBoardHilTests(unittest.TestCase):
    def test_versions_are_extracted_from_both_projects(self) -> None:
        self.assertRegex(
            flow.read_version(
                ROOT / "firmware/leshy1/platformio.ini", "LESHY1_VERSION"),
            r"^0\.\d+\.\d+[-\w.]*$")
        self.assertEqual(
            "0.3.0-subghz-safe",
            flow.read_version(
                ROOT / "firmware/leshy_fixture/platformio.ini",
                "LESHY_FIXTURE_VERSION"))

    def test_profile_is_bound_to_exact_fixture_port(self) -> None:
        fixture_id = "0000AABBCCDDEEFF"
        profile = {
            "schema": "leshy.hil.board_profile.v1",
            "status": "accepted",
            "accepted_for_fixture_flash": True,
            "port_at_profile": "/dev/fixture",
            "writes_performed": False,
            "flash_erases_performed": 0,
            "flash_bytes_written": 0,
            "ram_stub_uploaded": False,
            "chip": {
                "family": "esp32-s3", "fixture_id": fixture_id,
                "flash_size": "16MB",
            },
            "assembly": {
                "profile": "esp32-div-v2-n16",
                "extension_modules": "none", "antennas_attached": True,
            },
            "operations": [
                {"read_only": True, "returncode": 0} for _ in range(4)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            _, actual_id = flow.load_profile(path, "/dev/fixture")
            self.assertEqual(fixture_id, actual_id)
            with self.assertRaisesRegex(ValueError, "port"):
                flow.load_profile(path, "/dev/other")

    def test_profile_command_requires_explicit_declarations(self) -> None:
        command = flow.profile_command(
            "/dev/fixture", Path("profile.json"), True, True)
        self.assertIn("--declare-standard-v2-no-extensions", command)
        self.assertIn("--declare-antennas-attached", command)

    def test_default_runner_command_flashes_both_exact_images(self) -> None:
        command = flow.runner_command(
            candidate_port="/dev/candidate", fixture_port="/dev/fixture",
            profile=Path("profile.json"), fixture_id="0000AABBCCDDEEFF",
            expected_cid="A" * 32, output=Path("output"),
            source_commit="a" * 40,
            product_version="product", fixture_version="fixture",
            reuse_candidate=False, reuse_fixture=False)
        self.assertIn("candidate=/dev/candidate", command)
        self.assertIn("fixture=/dev/fixture", command)
        self.assertIn("--flash", command)
        self.assertIn("--flash-fixture", command)
        self.assertNotIn("--reuse-exact-flash", command)

    def test_deadline_runner_is_one_command_and_source_bound(self) -> None:
        command = flow.deadline_runner_command(
            candidate_port="/dev/candidate", fixture_port="/dev/fixture",
            profile=Path("profile.json"), fixture_id="0" * 16,
            expected_cid="A" * 32, output=Path("output"),
            source_commit="a" * 40,
            product_version="product", fixture_version="fixture",
            reuse_candidate=False, reuse_fixture=False)
        self.assertIn("run_1x_infrared_store_deadline_hil.py", command[1])
        self.assertIn("--flash", command)
        self.assertIn("--flash-fixture", command)
        self.assertIn("--source-commit", command)
        self.assertIn("--expected-fixture-id", command)

    def test_s5_matrix_builds_once_then_reuses_exact_images(self) -> None:
        self.assertEqual(
            ("infrared-nec-positive", "nrf24-carrier-positive",
             "subghz-ook-positive", "subghz-fsk-positive"),
            phase_flow.MATRIX)
        source_commit = "a" * 40
        candidate_hash = "b" * 64
        fixture_hash = "c" * 64
        run = {
            "passed": True,
            "scenario": {"id": "subghz-ook-positive"},
            "candidate": {
                "source_commit": source_commit,
                "firmware_sha256": candidate_hash,
                "app_elf_sha256": "d" * 64,
            },
            "fixture": {
                "source_commit": source_commit,
                "firmware_sha256": fixture_hash,
                "app_elf_sha256": "e" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            accepted = phase_flow.accepted_child(
                run_path, "subghz-ook-positive", source_commit)
        self.assertEqual(candidate_hash,
                         accepted["candidate_firmware_sha256"])
        self.assertEqual(fixture_hash,
                         accepted["fixture_firmware_sha256"])


if __name__ == "__main__":
    unittest.main()
