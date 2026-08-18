#!/usr/bin/env python3
"""Host tests for fail-closed LittleFS parity runner assertions."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_1x_littlefs_parity_hil as runner
from run_1x_littlefs_parity_hil import (
    OTA1_OFFSET,
    OTA1_SIZE,
    parity_failures,
)


HASH = "a" * 64
RUN_ID = "lfs-0123456789abcdef"


def valid_record() -> dict[str, object]:
    return {
        "status": "valid", "explicitly_disposable": True,
        "target": "ota1", "expected_fingerprint": HASH,
        "observed_fingerprint": HASH, "fingerprint_matched": True,
        "run_id": RUN_ID, "target_address": OTA1_OFFSET,
        "target_size": OTA1_SIZE, "running_address": 0x10000,
        "boot_address": 0x10000, "target_inactive": True,
        "ota1_restore_required": True, "ota1_restored": False,
        "partition_table_modified": False,
        "product_partition_touched": False, "nvs_touched": False,
        "sd_accessed": False, "radio_touched": False,
        "format_allowed": True, "format_performed": True,
        "mounted_writable": True, "remounted_read_only": True,
        "reopened_read_only": True, "permit_status": "permitted",
        "scratch_preexisting_after_format": False,
        "byte_limit": 1024 * 1024, "file_syncs": 96,
        "directory_syncs": 96, "file_sync_covers_directory": True,
        "commit_samples_requested": 32, "commit_samples_completed": 32,
        "fixture_observations": 64, "storage_rate_target_met": True,
        "pre_remount_status": "valid", "pre_remount_generation": 32,
        "post_remount_status": "valid", "post_remount_generation": 32,
        "post_remount_observations": 64, "owned_during": 4,
        "owned_after": 0, "cleanup_complete": True,
        "reset_injection": False, "physical_power_cut": False,
        "filesystem_capacity_bytes": OTA1_SIZE,
        "free_before": 4_000_000, "free_after": 3_900_000,
        "bytes_written": 100_000, "mount_us": 500_000,
        "commit_total_us": 320_000, "commit_min_us": 8_000,
        "commit_p50_us": 9_000, "commit_p95_us": 11_000,
        "commit_p99_us": 12_000, "commit_max_us": 12_000,
        "fixture_segment_bytes": 2_048,
        "encoded_payload_bytes_per_second": 204_800,
        "required_encoded_bytes_per_second": 2_184,
        "heap_free_before": 200_000, "heap_free_after": 200_000,
        "heap_min_free": 180_000,
    }


class LittleFsParityFailuresTests(unittest.TestCase):
    def test_accepts_exact_safe_result(self) -> None:
        self.assertEqual(parity_failures(valid_record(), HASH, RUN_ID), [])

    def test_rejects_active_target(self) -> None:
        value = valid_record()
        value["target_inactive"] = False
        self.assertTrue(parity_failures(value, HASH, RUN_ID))

    def test_rejects_product_partition_touch(self) -> None:
        value = valid_record()
        value["product_partition_touched"] = True
        self.assertTrue(parity_failures(value, HASH, RUN_ID))

    def test_rejects_incomplete_samples(self) -> None:
        value = valid_record()
        value["commit_samples_completed"] = 31
        self.assertTrue(parity_failures(value, HASH, RUN_ID))

    def test_rejects_non_monotonic_percentiles(self) -> None:
        value = valid_record()
        value["commit_p95_us"] = 7_000
        self.assertTrue(parity_failures(value, HASH, RUN_ID))

    def test_rejects_rate_below_target(self) -> None:
        value = valid_record()
        value["encoded_payload_bytes_per_second"] = 2_000
        self.assertTrue(parity_failures(value, HASH, RUN_ID))

    def test_restore_retries_transient_readback_failure(self) -> None:
        with TemporaryDirectory() as directory:
            backup = Path(directory) / "backup.bin"
            readback = Path(directory) / "readback.bin"
            backup.write_bytes(b"original-ota1")
            expected = runner.sha256_file(backup)
            with (
                patch.object(runner, "esptool") as esptool_mock,
                patch.object(
                    runner, "read_flash", side_effect=[OSError("reset"), expected]
                ) as read_mock,
                patch.object(runner.time, "sleep") as sleep_mock,
            ):
                restored = runner.restore_flash(
                    "port", 460800, OTA1_OFFSET, backup, readback,
                    attempts=3, backoff=0.01,
                )
            self.assertEqual(restored, (expected, expected, 2))
            self.assertEqual(esptool_mock.call_count, 2)
            self.assertEqual(read_mock.call_count, 2)
            sleep_mock.assert_called_once_with(0.01)

    def test_restore_exhaustion_keeps_backup(self) -> None:
        with TemporaryDirectory() as directory:
            backup = Path(directory) / "backup.bin"
            readback = Path(directory) / "readback.bin"
            backup.write_bytes(b"original-ota1")
            with (
                patch.object(runner, "esptool"),
                patch.object(runner, "read_flash", side_effect=OSError("reset")),
                patch.object(runner.time, "sleep"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "remained unverified after 3 attempts"
                ):
                    runner.restore_flash(
                        "port", 460800, OTA1_OFFSET, backup, readback,
                        attempts=3, backoff=0.0,
                    )
            self.assertTrue(backup.is_file())

    def test_flash_read_retries_and_removes_partial_output(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "readback.bin"
            calls = 0

            def read_side_effect(*_args: object) -> str:
                nonlocal calls
                calls += 1
                if calls == 1:
                    output.write_bytes(b"partial")
                    raise OSError("serial noise")
                return HASH

            with (
                patch.object(runner, "read_flash", side_effect=read_side_effect),
                patch.object(runner.time, "sleep") as sleep_mock,
            ):
                observed = runner.read_flash_with_retry(
                    "port", 230400, OTA1_OFFSET, OTA1_SIZE, output,
                    attempts=3, backoff=0.01,
                )
            self.assertEqual(observed, (HASH, 2))
            sleep_mock.assert_called_once_with(0.01)


if __name__ == "__main__":
    unittest.main()
