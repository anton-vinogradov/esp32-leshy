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
        "run_1x_device_lock_recovery_admission_hil.py")
    spec = importlib.util.spec_from_file_location(
        "device_lock_recovery_admission_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class DeviceLockRecoveryAdmissionHilRunnerTests(unittest.TestCase):
    def matrix(self, *, state: str, protected: str, unlock: str,
               configure: str, protected_allowed: bool) -> dict[str, Any]:
        access = {
            operation: protected
            for operation in RUNNER.PROTECTED_OPERATIONS
        }
        access.update({
            operation: "allowed" for operation in RUNNER.SAFE_OPERATIONS
        })
        access["unlock"] = unlock
        access["configure"] = configure
        return {
            "state": state,
            "access": access,
            "protected_all_allowed": protected_allowed,
            "safe_all_allowed": True,
            "protected_content_returned": False,
            "radio_touched": False,
        }

    def test_unconfigured_locked_and_recovery_matrices(self) -> None:
        cases = (
            ("unconfigured", "setup_required", "setup_required",
             "allowed"),
            ("locked", "locked", "allowed", "locked"),
            ("recovery_only", "recovery_required", "recovery_required",
             "locked"),
        )
        for state, protected, unlock, configure in cases:
            record = self.matrix(
                state=state, protected=protected, unlock=unlock,
                configure=configure, protected_allowed=False)
            self.assertEqual([], RUNNER.admission_failures(
                record, state, state=state, protected_access=protected,
                unlock_access=unlock, configure_access=configure,
                protected_allowed=False))

    def test_unlocked_matrix_and_unknown_operation_fail_closed(self) -> None:
        record = self.matrix(
            state="unlocked", protected="allowed", unlock="allowed",
            configure="locked", protected_allowed=True)
        self.assertEqual([], RUNNER.admission_failures(
            record, "unlocked", state="unlocked",
            protected_access="allowed", unlock_access="allowed",
            configure_access="locked", protected_allowed=True))
        record["access"]["unexpected"] = "allowed"
        self.assertTrue(RUNNER.admission_failures(
            record, "unexpected", state="unlocked",
            protected_access="allowed", unlock_access="allowed",
            configure_access="locked", protected_allowed=True))

    def test_retry_timeouts_cover_real_security_delays(self) -> None:
        observed: list[float] = []

        def fake_wait(_device: Any, _predicate: Any, _description: str,
                      timeout: float) -> dict[str, Any]:
            observed.append(timeout)
            return {"status": "locked"}

        original = RUNNER.wait_lock_state
        RUNNER.wait_lock_state = fake_wait
        try:
            for attempt in range(1, 5):
                RUNNER.wait_retry_completion(object(), attempt)
        finally:
            RUNNER.wait_lock_state = original
        self.assertEqual([10.0, 20.0, 70.0, 310.0], observed)

    def test_factory_reset_commands_are_explicitly_bounded(self) -> None:
        class FakeDevice:
            pass

        observed: list[bytes] = []

        def fake_query(_device: Any, command: bytes, _schema: str,
                       _kind: str) -> dict[str, Any]:
            observed.append(command)
            return {}

        original = RUNNER.query
        RUNNER.query = fake_query
        try:
            RUNNER.fixture_command(FakeDevice(), "factory-reset-preview")
            RUNNER.fixture_command(FakeDevice(), "factory-reset-confirm")
            with self.assertRaises(ValueError):
                RUNNER.fixture_command(FakeDevice(), "erase-everything")
        finally:
            RUNNER.query = original
        self.assertEqual([
            b"device-lock.persistence-fixture factory-reset-preview",
            b"device-lock.persistence-fixture factory-reset-confirm",
        ], observed)


if __name__ == "__main__":
    unittest.main()
