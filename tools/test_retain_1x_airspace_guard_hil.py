#!/usr/bin/env python3
"""Unit tests for exact Airspace Guard retention and promotion."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import check_airspace_guard_hil_acceptance as acceptance
import retain_1x_airspace_guard_hil as retention
import test_airspace_guard_hil_acceptance as positive_fixture


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def manifest(bundle: Path) -> None:
    files = sorted(
        path for path in bundle.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    )
    (bundle / "artifacts.sha256").write_text(
        "".join(
            f"{digest(path)}  {path.relative_to(bundle)}\n" for path in files
        ), encoding="utf-8")


def cleanup() -> dict[str, object]:
    return {
        "complete": True,
        "errors": [],
        "final_state": {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "safety_state": "armed", "safety_latched": False,
        },
    }


def candidate(version: str, source: str, firmware: str,
              app: str, flash_mode: str) -> dict[str, object]:
    return {
        "version": version, "source_commit": source,
        "firmware_sha256": firmware, "app_elf_sha256": app,
        "flashed": True, "flash_mode": flash_mode,
    }


class AirspaceRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.positive_case = positive_fixture.AirspaceAcceptanceTests(
            methodName="test_exact_full_bundle_and_retained_failure_pass")
        self.positive_case.setUp()
        self.positive_case.write_bundle()
        self.positive = self.positive_case.bundle
        self.firmware = self.positive_case.firmware
        self.app = positive_fixture.APP
        self.source = positive_fixture.SOURCE
        self.runner = positive_fixture.RUNNER_SHA
        self.committed_runner_sha256 = acceptance.committed_runner_sha256
        acceptance.committed_runner_sha256 = lambda _commit: self.runner
        self.failed_source = "a" * 40
        self.failed_241_source = "b" * 40
        self.delta = self.root / "delta239"
        self.full239 = self.root / "full239"
        self.full241 = self.root / "full241"
        for path in (self.delta, self.full239, self.full241):
            path.mkdir()
            (path / "firmware.bin").write_bytes(
                self.positive_case.firmware_bytes)
        self.build_precursors()
        self.destination = self.root / "retained-positive"
        self.negative239 = self.root / "retained-239.json"
        self.negative241 = self.root / "retained-241.json"
        self.expectations = self.root / "retained-acceptance.json"

        patches = {
            "FAILED_SOURCE": self.failed_source,
            "FAILED_FIRMWARE": self.firmware,
            "FAILED_APP": self.app,
            "FAILED_DELTA_RUN": digest(self.delta / "run.json"),
            "FAILED_FULL_RUN": digest(self.full239 / "run.json"),
            "FAILED_FULL_INDEX": digest(self.full239 / "artifacts.sha256"),
            "FAILED_241_SOURCE": self.failed_241_source,
            "FAILED_241_FIRMWARE": self.firmware,
            "FAILED_241_APP": self.app,
            "FAILED_241_FULL_RUN": digest(self.full241 / "run.json"),
            "FAILED_241_FULL_INDEX": digest(
                self.full241 / "artifacts.sha256"),
            "FAILED_241_RUNNER": "3" * 64,
        }
        self.patchers = [
            mock.patch.object(acceptance, name, value)
            for name, value in patches.items()
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        acceptance.committed_runner_sha256 = self.committed_runner_sha256
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.positive_case.tearDown()
        self.temporary.cleanup()

    def build_precursors(self) -> None:
        delta = {
            "schema": "leshy.airspace_guard_start_regression_hil.run.v1",
            "passed": True, "gate_eligible": False, "failures": [],
            "candidate": candidate(
                acceptance.FAILED_VERSION, self.failed_source, self.firmware,
                self.app, "fresh"),
        }
        write_json(self.delta / "run.json", delta)
        manifest(self.delta)

        first239 = {
            "capture_state": "failed", "load_status": "invalid_report",
            "ble_worker_status": "complete", "ble_worker_valid": True,
            "ble_scan_status": "valid", "ble_retention_retained": 49,
            "ble_retention_dropped": 0, "findings_dropped": 0,
        }
        second239 = {
            "capture_state": "result", "load_status": "ready",
            "ble_records": 53, "findings_dropped": 0,
        }
        full239 = {
            "schema": acceptance.RUN_SCHEMA,
            "passed": False, "gate_eligible": False,
            "candidate": candidate(
                acceptance.FAILED_VERSION, self.failed_source, self.firmware,
                self.app, "reuse_exact"),
            "result_first": first239, "result_second": second239,
            "cleanup_after": cleanup(),
        }
        write_json(self.full239 / "run.json", full239)
        manifest(self.full239)

        first241 = {
            "capture_state": "result", "load_status": "ready",
            "ble_worker_status": "complete", "ble_worker_valid": True,
            "ble_scan_status": "valid", "ble_scan_dropped": 0,
            "ble_retention_retained": 54, "ble_retention_dropped": 0,
            "frames_available": 74, "findings_dropped": 0,
        }
        second241 = {
            "capture_state": "failed", "load_status": "ready",
            "ble_worker_status": "incomplete_evidence",
            "ble_worker_valid": False, "ble_scan_status": "valid",
            "ble_scan_observed": 1296, "ble_scan_reported": 1296,
            "ble_scan_read": 1296, "ble_scan_accepted": 1295,
            "ble_scan_rejected": 0, "ble_scan_dropped": 1,
            "ble_retention_observed": 1296, "ble_retention_valid": 1296,
            "ble_retention_retained": 64, "ble_retention_dropped": 1,
            "ble_retention_malformed": 0, "evidence_incomplete": True,
            "outcome": "inconclusive", "source_frames_observed": 0,
            "source_frames_dropped": 0, "frames_available": 0,
            "ble_records": 0, "findings_dropped": 0,
        }
        full241 = {
            "schema": acceptance.RUN_SCHEMA,
            "passed": False, "gate_eligible": False,
            "runner_source_sha256": "3" * 64,
            "candidate": candidate(
                acceptance.FAILED_241_VERSION, self.failed_241_source,
                self.firmware, self.app, "reuse_exact"),
            "result_first": first241, "result_second": second241,
            "cleanup_after": cleanup(),
        }
        write_json(self.full241 / "run.json", full241)
        manifest(self.full241)

    def args(self) -> argparse.Namespace:
        return retention.parse_args([
            "--positive", str(self.positive),
            "--dev239-delta", str(self.delta),
            "--dev239-full", str(self.full239),
            "--dev241-full", str(self.full241),
            "--expected-source-commit", self.source,
            "--expected-firmware-sha256", self.firmware,
            "--expected-app-elf-sha256", self.app,
            "--expected-runner-sha256", self.runner,
            "--destination", str(self.destination),
            "--negative-dev239", str(self.negative239),
            "--negative-dev241", str(self.negative241),
            "--expectations", str(self.expectations),
        ])

    def outputs(self) -> tuple[Path, ...]:
        return (self.destination, self.negative239, self.negative241,
                self.expectations)

    def test_exact_inputs_retain_and_pass_acceptance(self) -> None:
        result = retention.retain(self.args())
        self.assertEqual("retained", result["status"])
        self.assertTrue(all(path.exists() for path in self.outputs()))
        check_args = acceptance.parse_args([
            "--expectations", str(self.expectations),
            "--positive", str(self.destination),
            "--negative-dev239", str(self.negative239),
            "--negative-dev241", str(self.negative241),
        ])
        self.assertEqual([], acceptance.check(check_args))

    def test_cli_parse_and_main_dispatch(self) -> None:
        argv = [
            "--positive", str(self.positive),
            "--dev239-delta", str(self.delta),
            "--dev239-full", str(self.full239),
            "--dev241-full", str(self.full241),
            "--expected-source-commit", self.source,
            "--expected-firmware-sha256", self.firmware,
            "--expected-app-elf-sha256", self.app,
            "--expected-runner-sha256", self.runner,
            "--destination", str(self.destination),
            "--negative-dev239", str(self.negative239),
            "--negative-dev241", str(self.negative241),
            "--expectations", str(self.expectations),
        ]
        parsed = retention.parse_args(argv)
        self.assertEqual(self.app, parsed.expected_app_elf_sha256)
        expected = {"schema": "test", "status": "retained"}
        output = StringIO()
        with mock.patch.object(retention, "retain", return_value=expected) as retain:
            with redirect_stdout(output):
                self.assertEqual(0, retention.main(argv))
        retain.assert_called_once()
        self.assertEqual(expected, json.loads(output.getvalue()))

    def test_cli_help_is_available(self) -> None:
        with redirect_stdout(StringIO()):
            with self.assertRaisesRegex(SystemExit, "0"):
                retention.parse_args(["--help"])

    def test_source_manifest_tamper_leaves_no_outputs(self) -> None:
        (self.full241 / "firmware.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            retention.retain(self.args())
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_positive_semantic_tamper_is_rejected_before_promotion(self) -> None:
        run_path = self.positive / "run.json"
        run = json.loads(run_path.read_text())
        run["capacity_drop_clear"]["armed"] = True
        write_json(run_path, run)
        manifest(self.positive)
        with self.assertRaisesRegex(ValueError, "capacity_drop_clear.armed"):
            retention.retain(self.args())
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_precursor_rewrite_with_valid_manifest_is_rejected(self) -> None:
        run_path = self.full239 / "run.json"
        run = json.loads(run_path.read_text())
        run["result_second"]["ble_records"] = 52
        write_json(run_path, run)
        manifest(self.full239)
        with self.assertRaisesRegex(ValueError, "exact run hash mismatch"):
            retention.retain(self.args())
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_existing_destination_is_never_replaced(self) -> None:
        self.negative239.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "destination already exists"):
            retention.retain(self.args())
        self.assertEqual("keep", self.negative239.read_text())
        self.assertFalse(self.destination.exists())

    def test_stale_expected_runner_is_rejected_before_promotion(self) -> None:
        args = self.args()
        args.expected_runner_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "current HIL runner"):
            retention.retain(args)
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_promotion_rolls_back_completed_moves(self) -> None:
        stage = self.root / "stage"
        stage.mkdir()
        first = stage / "first"
        second = stage / "second"
        first.write_text("one", encoding="utf-8")
        second.write_text("two", encoding="utf-8")
        out_first = self.root / "out-first"
        out_second = self.root / "out-second"
        original = Path.replace

        def flaky(path: Path, target: Path) -> Path:
            if path == second:
                raise OSError("injected promotion failure")
            return original(path, target)

        with mock.patch.object(Path, "replace", flaky):
            with self.assertRaisesRegex(OSError, "promotion failure"):
                retention.promote(
                    [(first, out_first), (second, out_second)], stage)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertFalse(out_first.exists())
        self.assertFalse(out_second.exists())


if __name__ == "__main__":
    unittest.main()
