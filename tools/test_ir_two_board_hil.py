#!/usr/bin/env python3
"""Pure host tests for the one-command two-board infrared HIL flow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_ir_two_board_hil as flow  # noqa: E402
import run_s5_two_board_hil as phase_flow  # noqa: E402


def passing_matrix_child(scenario_id: str, source_commit: str,
                         candidate_hash: str, fixture_hash: str,
                         reused: bool) -> dict[str, object]:
    return {
        "schema": phase_flow.CHILD_SCHEMA,
        "runner_source_sha256": "9" * 64,
        "passed": True,
        "failures": [],
        "gate_eligible": True,
        "checkpoint": phase_flow.CHECKPOINTS[scenario_id],
        "expected_cid": "F" * 32,
        "scenario": {
            "id": scenario_id,
            "sha256": phase_flow.sha256_file(flow.SCENARIOS[scenario_id]),
        },
        "ports": {
            "candidate": "/dev/candidate",
            "fixture": "/dev/fixture",
        },
        "candidate": {
            "version": "product",
            "source_commit": source_commit,
            "firmware_sha256": candidate_hash,
            "app_elf_sha256": "d" * 64,
            "flashed": not reused,
            "exact_flash_reused": reused,
        },
        "fixture": {
            "version": "fixture",
            "source_commit": source_commit,
            "firmware_sha256": fixture_hash,
            "app_elf_sha256": "e" * 64,
            "profile_sha256": "f" * 64,
            "fixture_id": "0000AABBCCDDEEFF",
            "flashed": not reused,
            "exact_flash_reused": reused,
            "cleanup": {
                "state": "stopped",
                "output_inactive": True,
                "ir_tx_inactive": True,
                "nrf_ce_inactive": True,
                "nrf_powered_down": True,
                "cc_transmit_active": False,
                "cc_idle": True,
                "cc_power_cleared": True,
                "cc_tx_fifo_cleared": True,
            },
        },
        "cleanup": {"complete": True},
        "reports": {phase_flow.FINAL_REPORTS[scenario_id]: {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
        }},
    }


def passing_build_artifacts(candidate_hash: str,
                            fixture_hash: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for role, firmware_hash in (
            ("product", candidate_hash), ("fixture", fixture_hash)):
        result[role] = {
            name: {
                "bytes": 1024,
                "sha256": firmware_hash if name == "firmware.bin"
                else ("7" if role == "product" else "8") * 64,
            }
            for name in phase_flow.BUILD_ARTIFACTS[role]
        }
    return result


class IrTwoBoardHilTests(unittest.TestCase):
    def test_versions_are_extracted_from_both_projects(self) -> None:
        self.assertRegex(
            flow.read_version(
                ROOT / "firmware/leshy1/platformio.ini", "LESHY1_VERSION"),
            r"^\d+\.\d+\.\d+[-\w.]*$")
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
        scenario_path = flow.SCENARIOS["subghz-ook-positive"]
        run = {
            "schema": phase_flow.CHILD_SCHEMA,
            "passed": True,
            "failures": [],
            "gate_eligible": True,
            "checkpoint": phase_flow.CHECKPOINTS["subghz-ook-positive"],
            "expected_cid": "F" * 32,
            "scenario": {
                "id": "subghz-ook-positive",
                "sha256": phase_flow.sha256_file(scenario_path),
            },
            "ports": {
                "candidate": "/dev/candidate",
                "fixture": "/dev/fixture",
            },
            "candidate": {
                "version": "product",
                "source_commit": source_commit,
                "firmware_sha256": candidate_hash,
                "app_elf_sha256": "d" * 64,
                "flashed": False,
                "exact_flash_reused": True,
            },
            "fixture": {
                "version": "fixture",
                "source_commit": source_commit,
                "firmware_sha256": fixture_hash,
                "app_elf_sha256": "e" * 64,
                "profile_sha256": "f" * 64,
                "fixture_id": "0000AABBCCDDEEFF",
                "flashed": False,
                "exact_flash_reused": True,
                "cleanup": {
                    "state": "stopped",
                    "output_inactive": True,
                    "ir_tx_inactive": True,
                    "nrf_ce_inactive": True,
                    "nrf_powered_down": True,
                    "cc_transmit_active": False,
                    "cc_idle": True,
                    "cc_power_cleared": True,
                    "cc_tx_fifo_cleared": True,
                },
            },
            "cleanup": {"complete": True},
            "reports": {"final": {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            }},
        }
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            accepted = phase_flow.accepted_child(
                run_path, "subghz-ook-positive", source_commit,
                product_version="product", fixture_version="fixture",
                expected_cid="F" * 32,
                candidate_port="/dev/candidate",
                fixture_port="/dev/fixture",
                fixture_id="0000AABBCCDDEEFF",
                candidate_firmware_sha256=candidate_hash,
                fixture_firmware_sha256=fixture_hash,
                candidate_reused=True, fixture_reused=True)
        self.assertEqual(candidate_hash,
                         accepted["candidate_firmware_sha256"])
        self.assertEqual(fixture_hash,
                         accepted["fixture_firmware_sha256"])
        self.assertEqual("f" * 64, accepted["fixture_profile_sha256"])

    def test_s5_matrix_rejects_unproven_fixture_cleanup(self) -> None:
        source_commit = "a" * 40
        scenario_path = flow.SCENARIOS["subghz-fsk-positive"]
        run = {
            "schema": phase_flow.CHILD_SCHEMA,
            "passed": True,
            "failures": [],
            "gate_eligible": True,
            "checkpoint": phase_flow.CHECKPOINTS["subghz-fsk-positive"],
            "scenario": {
                "id": "subghz-fsk-positive",
                "sha256": phase_flow.sha256_file(scenario_path),
            },
            "candidate": {
                "source_commit": source_commit,
                "firmware_sha256": "b" * 64,
                "app_elf_sha256": "c" * 64,
            },
            "fixture": {
                "source_commit": source_commit,
                "firmware_sha256": "d" * 64,
                "app_elf_sha256": "e" * 64,
                "profile_sha256": "f" * 64,
                "cleanup": {
                    "state": "stopped",
                    "output_inactive": True,
                    "ir_tx_inactive": True,
                    "nrf_ce_inactive": True,
                    "nrf_powered_down": True,
                    "cc_transmit_active": False,
                    "cc_idle": True,
                    "cc_power_cleared": False,
                    "cc_tx_fifo_cleared": True,
                },
            },
            "cleanup": {"complete": True},
            "reports": {"final": {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            }},
        }
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixture terminal cleanup"):
                phase_flow.accepted_child(
                    run_path, "subghz-fsk-positive", source_commit)

    def test_completed_s5_matrix_is_reverified_from_child_files(self) -> None:
        source_commit = "a" * 40
        candidate_hash = "b" * 64
        fixture_hash = "c" * 64
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "matrix"
            output.mkdir()
            entries = []
            for index, scenario_id in enumerate(phase_flow.MATRIX):
                run_path = output / scenario_id / "run.json"
                run_path.parent.mkdir()
                run_path.write_text(json.dumps(passing_matrix_child(
                    scenario_id, source_commit, candidate_hash,
                    fixture_hash, index > 0)), encoding="utf-8")
                entries.append(phase_flow.accepted_child(
                    run_path, scenario_id, source_commit,
                    product_version="product", fixture_version="fixture",
                    expected_cid="F" * 32,
                    candidate_port="/dev/candidate",
                    fixture_port="/dev/fixture",
                    fixture_id="0000AABBCCDDEEFF",
                    candidate_firmware_sha256=candidate_hash,
                    fixture_firmware_sha256=fixture_hash,
                    candidate_reused=index > 0, fixture_reused=index > 0,
                    expected_runner_sha256="9" * 64))
            summary = {
                "schema": phase_flow.SCHEMA,
                "runner_source_sha256": phase_flow.sha256_file(
                    Path(phase_flow.__file__).resolve()),
                "status": "pass",
                "passed": True,
                "started_at": "2026-08-25T00:00:00Z",
                "completed_at": "2026-08-25T01:00:00Z",
                "source_commit": source_commit,
                "product_version": "product",
                "fixture_version": "fixture",
                "candidate_port": "/dev/candidate",
                "fixture_port": "/dev/fixture",
                "expected_cid": "F" * 32,
                "fixture_id": "0000AABBCCDDEEFF",
                "fixture_profile": "profile.json",
                "matrix": list(phase_flow.MATRIX),
                "runs": entries,
                "failure": None,
                "product_firmware_sha256": candidate_hash,
                "fixture_firmware_sha256": fixture_hash,
                "build_artifacts": passing_build_artifacts(
                    candidate_hash, fixture_hash),
                "product_app_elf_sha256": "d" * 64,
                "fixture_app_elf_sha256": "e" * 64,
                "fixture_profile_sha256": "f" * 64,
            }
            summary_path = output / "run.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            def committed_blob(commit: str, relative: str) -> str:
                del commit
                if relative == "tools/run_s5_two_board_hil.py":
                    return summary["runner_source_sha256"]
                if relative == "tools/run_hil_scenario.py":
                    return "9" * 64
                return phase_flow.sha256_file(ROOT / relative)

            with mock.patch.object(
                    phase_flow, "git_blob_sha256",
                    side_effect=committed_blob):
                checked = phase_flow.verify_completed_matrix(summary_path)
            self.assertEqual(source_commit, checked["source_commit"])
            relocated = Path(directory) / "relocated"
            output.rename(relocated)
            with mock.patch.object(
                    phase_flow, "git_blob_sha256",
                    side_effect=committed_blob):
                checked = phase_flow.verify_completed_matrix(
                    relocated / "run.json", allow_relocated_children=True)
            self.assertEqual(source_commit, checked["source_commit"])
            output = relocated
            summary["runs"][2]["run_sha256"] = "0" * 64
            summary_path = output / "run.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with mock.patch.object(
                    phase_flow, "git_blob_sha256",
                    side_effect=committed_blob):
                with self.assertRaisesRegex(ValueError, "child run hash"):
                    phase_flow.verify_completed_matrix(
                        summary_path, allow_relocated_children=True)


if __name__ == "__main__":
    unittest.main()
