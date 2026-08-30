#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)


def load_runner() -> Any:
    path = Path(__file__).with_name(
        "run_1x_device_lock_persistence_hil.py")
    spec = importlib.util.spec_from_file_location(
        "device_lock_persistence_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class DeviceLockPersistenceHilRunnerTests(unittest.TestCase):
    def test_pin_policy_matches_product_policy(self) -> None:
        self.assertTrue(RUNNER.pin_weak(bytearray([0, 0, 0, 0, 0, 0])))
        self.assertTrue(RUNNER.pin_weak(bytearray([1, 2, 3, 4, 5, 6])))
        self.assertTrue(RUNNER.pin_weak(bytearray([6, 5, 4, 3, 2, 1])))
        self.assertFalse(RUNNER.pin_weak(bytearray([7, 0, 4, 2, 8, 1])))

    def test_state_and_full_retry_contracts(self) -> None:
        record = {
            "status": "retry_delay",
            "failure": "wrong_pin",
            "failed_attempts": 1,
            "credential_generation": 2,
            "protected_access": False,
            "worker_active": False,
            "persistence_fixture_active": True,
            "persistence_fixture_cleanup_required": True,
            "radio_touched": False,
            "retry_remaining_ms": 4990,
        }
        self.assertEqual([], RUNNER.state_failures(
            record, "retry", status="retry_delay", failure="wrong_pin",
            failed_attempts=1, generation=2, protected=False,
            fixture_active=True))
        self.assertEqual([], RUNNER.full_retry_failures(
            record, "retry", 5000))
        self.assertTrue(RUNNER.full_retry_failures(
            dict(record, retry_remaining_ms=4000), "retry", 5000))

    def test_fixture_contract_excludes_product_and_whole_nvs(self) -> None:
        record = {
            "operation": "cleanup",
            "status": "cleaned",
            "active": False,
            "cleanup_required": False,
            "fixture_namespace_selected": False,
            "fixture_cleanup_complete": True,
            "product_restored": True,
            "product_namespace_written_or_erased": False,
            "whole_nvs_read_or_copied": False,
            "radio_touched": False,
        }
        self.assertEqual([], RUNNER.fixture_failures(
            record, "cleanup", status="cleaned", operation="cleanup",
            active=False, selected=False, cleaned=True,
            product_restored=True))

    def test_wipe_pin_overwrites_mutable_buffer(self) -> None:
        pin = bytearray([7, 0, 4, 2, 8, 1])
        RUNNER.wipe_pin(pin)
        self.assertEqual(bytearray(6), pin)


if __name__ == "__main__":
    unittest.main()
