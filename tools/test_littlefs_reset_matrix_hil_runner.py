#!/usr/bin/env python3
"""Host tests for LittleFS reset-matrix semantic acceptance."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch


def load_runner() -> Any:
    capture_stub = types.ModuleType("capture_1x_ui")
    capture_stub.PassiveSerial = object
    capture_stub.read_json = lambda *_args, **_kwargs: None
    capture_stub.synchronize_console = lambda *_args, **_kwargs: None
    sys.modules.setdefault("capture_1x_ui", capture_stub)
    path = Path(__file__).with_name("run_1x_littlefs_reset_matrix_hil.py")
    spec = importlib.util.spec_from_file_location("littlefs_reset_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
FINGERPRINT = "a" * 64
RUN_ID = "lfsr-test-b4"


def armed_record(boundary: int = 4) -> dict[str, Any]:
    return {
        "status": "ready",
        "run_id": RUN_ID,
        "boundary": boundary,
        "expected_fingerprint": FINGERPRINT,
        "observed_fingerprint": FINGERPRINT,
        "fingerprint_matched": True,
        "target": "ota1",
        "target_address": RUNNER.OTA1_OFFSET,
        "target_size": RUNNER.OTA1_SIZE,
        "target_inactive": True,
        "initial_generation": 1,
        "initial_observations": 3,
        "continuity_armed": True,
        "format_performed": True,
        "writes_bounded_to_scratch": True,
        "ota1_restore_required": True,
        "product_partition_touched": False,
        "sd_accessed": False,
        "nvs_touched": False,
        "radio_touched": False,
        "reset_injection": True,
        "physical_power_cut": False,
    }


def recovery_record(boundary: int, generation: int) -> dict[str, Any]:
    return {
        "mode": "recovery",
        "status": "valid",
        "run_id": RUN_ID,
        "boundary": boundary,
        "software_reset": True,
        "continuity_valid": True,
        "target": "ota1",
        "target_address": RUNNER.OTA1_OFFSET,
        "target_size": RUNNER.OTA1_SIZE,
        "target_inactive": True,
        "read_permit_status": "permitted",
        "scratch_exists": True,
        "mounted_read_only": True,
        "opened_read_only": True,
        "session_store_io_writable": False,
        "generation_allowed": True,
        "reopened_observations": 3,
        "prior_unchanged": True,
        "bytes_written": 0,
        "file_syncs": 0,
        "directory_syncs": 0,
        "owned_after": 0,
        "cleanup_complete": True,
        "mount_on_boot": False,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "ota1_restore_required": True,
        "product_partition_touched": False,
        "sd_accessed": False,
        "nvs_touched": False,
        "radio_touched": False,
        "reset_injection": True,
        "physical_power_cut": False,
        "recovered_generation": generation,
    }


class LittleFsResetRunnerTests(unittest.TestCase):
    def test_exact_armed_record_passes(self) -> None:
        self.assertFalse(RUNNER.arm_failures(
            armed_record(), FINGERPRINT, RUN_ID, 4))

    def test_arm_requires_exact_target_fingerprint_and_no_side_effects(self) -> None:
        mutations = {
            "fingerprint_matched": False,
            "target_inactive": False,
            "format_performed": False,
            "continuity_armed": False,
            "sd_accessed": True,
            "product_partition_touched": True,
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                record = armed_record()
                record[key] = value
                self.assertTrue(RUNNER.arm_failures(
                    record, FINGERPRINT, RUN_ID, 4))

    def test_expected_generation_policy_for_all_boundaries(self) -> None:
        expected = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2}
        for boundary, generation in expected.items():
            with self.subTest(boundary=boundary):
                self.assertFalse(RUNNER.recovery_failures(
                    recovery_record(boundary, generation), RUN_ID, boundary))

    def test_boundary_five_accepts_prior_or_new(self) -> None:
        self.assertFalse(RUNNER.recovery_failures(
            recovery_record(5, 1), RUN_ID, 5))
        self.assertFalse(RUNNER.recovery_failures(
            recovery_record(5, 2), RUN_ID, 5))

    def test_recovery_rejects_manual_reset_or_write(self) -> None:
        mutations = {
            "software_reset": False,
            "continuity_valid": False,
            "mounted_read_only": False,
            "session_store_io_writable": True,
            "bytes_written": 1,
            "file_syncs": 1,
            "directory_syncs": 1,
            "cleanup_complete": False,
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                record = recovery_record(4, 1)
                record[key] = value
                self.assertTrue(RUNNER.recovery_failures(
                    record, RUN_ID, 4))

    def test_wrong_generation_is_rejected(self) -> None:
        self.assertTrue(RUNNER.recovery_failures(
            recovery_record(6, 1), RUN_ID, 6))

    def test_restore_retries_reads_without_rewriting(self) -> None:
        with TemporaryDirectory() as directory:
            backup = Path(directory) / "backup.bin"
            readback = Path(directory) / "readback.bin"
            backup.write_bytes(b"original-ota1")
            expected = RUNNER.sha256_file(backup)
            stats = {"write_attempts": 0, "read_attempts": 0}
            with (
                patch.object(RUNNER, "esptool") as esptool_mock,
                patch.object(
                    RUNNER, "read_flash_with_retry",
                    return_value=(expected, 3),
                ) as read_mock,
                patch.object(RUNNER.time, "sleep") as sleep_mock,
            ):
                restored = RUNNER.restore_flash_single_write(
                    "port", 230400, RUNNER.OTA1_OFFSET, backup, readback,
                    stats, settle=5.0, read_attempts=6, read_backoff=5.0,
                )
            self.assertEqual(restored, (expected, expected))
            self.assertEqual(stats, {"write_attempts": 1, "read_attempts": 3})
            esptool_mock.assert_called_once()
            read_mock.assert_called_once_with(
                "port", 230400, RUNNER.OTA1_OFFSET, len(b"original-ota1"),
                readback, attempts=6, backoff=5.0,
            )
            sleep_mock.assert_called_once_with(5.0)

    def test_restore_read_exhaustion_still_writes_once(self) -> None:
        with TemporaryDirectory() as directory:
            backup = Path(directory) / "backup.bin"
            readback = Path(directory) / "readback.bin"
            backup.write_bytes(b"original-ota1")
            stats = {"write_attempts": 0, "read_attempts": 0}
            with (
                patch.object(RUNNER, "esptool") as esptool_mock,
                patch.object(
                    RUNNER, "read_flash_with_retry",
                    side_effect=RuntimeError("USB reconnect"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "USB reconnect"):
                    RUNNER.restore_flash_single_write(
                        "port", 230400, RUNNER.OTA1_OFFSET, backup,
                        readback, stats, settle=0.0, read_attempts=6,
                        read_backoff=5.0,
                    )
            self.assertEqual(stats, {"write_attempts": 1, "read_attempts": 6})
            esptool_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
