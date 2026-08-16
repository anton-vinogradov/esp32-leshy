#!/usr/bin/env python3
"""Host tests for the fail-closed SD reset-runner retry policy."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    sys.modules.setdefault("serial", serial_stub)

    capture_stub = types.ModuleType("capture_1x_ui")
    capture_stub.PassiveSerial = object
    capture_stub.read_json = lambda *_args, **_kwargs: None
    capture_stub.synchronize_console = lambda *_args, **_kwargs: None
    sys.modules.setdefault("capture_1x_ui", capture_stub)

    path = Path(__file__).with_name("run_1x_sd_reset_matrix.py")
    spec = importlib.util.spec_from_file_location("sd_reset_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
RUN_ID = "retry-policy-b4"
BOUNDARY = 4


def transient_record() -> dict[str, Any]:
    return {
        "schema": RUNNER.SCHEMA,
        "kind": "result",
        "mode": "recovery",
        "status": "failed",
        "run_id": RUN_ID,
        "boundary": BOUNDARY,
        "software_reset": True,
        "fingerprint_matched": False,
        "read_permit_status": "missing_media",
        "session_store_io_writable": False,
        "bytes_written": 0,
        "file_syncs": 0,
        "directory_syncs": 0,
        "owned_after": 0,
        "cleanup_complete": True,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "reset_injection": True,
        "physical_power_cut": False,
        "radio_tx_commands": 0,
    }


def valid_record() -> dict[str, Any]:
    record = transient_record()
    record.update({
        "status": "valid",
        "fingerprint_matched": True,
        "read_permit_status": "permitted",
        "scratch_exists": True,
        "opened_read_only": True,
        "generation_allowed": True,
        "reopened_observations": 3,
        "prior_unchanged": True,
    })
    return record


class RetryPolicyTests(unittest.TestCase):
    def test_exact_transient_is_retryable(self) -> None:
        self.assertTrue(RUNNER.retryable_media_readiness(
            transient_record(), RUN_ID, BOUNDARY))

    def test_any_side_effect_or_identity_drift_is_not_retryable(self) -> None:
        mutations = {
            "run_id": "other",
            "boundary": 5,
            "fingerprint_matched": True,
            "read_permit_status": "fingerprint_mismatch",
            "bytes_written": 1,
            "file_syncs": 1,
            "directory_syncs": 1,
            "owned_after": 12,
            "cleanup_complete": False,
            "format_allowed": True,
            "existing_paths_deleted": True,
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                record = transient_record()
                record[key] = value
                self.assertFalse(RUNNER.retryable_media_readiness(
                    record, RUN_ID, BOUNDARY))

    def test_transient_retries_then_accepts_valid_record(self) -> None:
        queue = [transient_record(), valid_record()]
        sleeps: list[float] = []
        original_read = RUNNER.read_recovery
        original_sleep = RUNNER.time.sleep
        RUNNER.read_recovery = lambda *_args: queue.pop(0)
        RUNNER.time.sleep = sleeps.append
        try:
            recovery, mismatches, attempts = RUNNER.recover_with_retry(
                "unused", "unused", RUN_ID, BOUNDARY, 1.0, 3, 1.5)
        finally:
            RUNNER.read_recovery = original_read
            RUNNER.time.sleep = original_sleep
        self.assertEqual("valid", recovery["status"])
        self.assertFalse(mismatches)
        self.assertEqual(2, len(attempts))
        self.assertEqual([1.5], sleeps)

    def test_non_readiness_failure_stops_without_retry(self) -> None:
        record = transient_record()
        record["read_permit_status"] = "fingerprint_mismatch"
        sleeps: list[float] = []
        original_read = RUNNER.read_recovery
        original_sleep = RUNNER.time.sleep
        RUNNER.read_recovery = lambda *_args: record
        RUNNER.time.sleep = sleeps.append
        try:
            _recovery, mismatches, attempts = RUNNER.recover_with_retry(
                "unused", "unused", RUN_ID, BOUNDARY, 1.0, 3, 1.0)
        finally:
            RUNNER.read_recovery = original_read
            RUNNER.time.sleep = original_sleep
        self.assertTrue(mismatches)
        self.assertEqual(1, len(attempts))
        self.assertFalse(sleeps)


if __name__ == "__main__":
    unittest.main()
