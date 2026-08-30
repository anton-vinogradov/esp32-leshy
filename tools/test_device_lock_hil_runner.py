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
    path = Path(__file__).with_name("run_1x_device_lock_hil.py")
    spec = importlib.util.spec_from_file_location("device_lock_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class DeviceLockHilRunnerTests(unittest.TestCase):
    def test_benchmark_requires_success_bounds_and_no_heap_leak(self) -> None:
        valid = {
            "benchmark_requested": True,
            "benchmark_complete": True,
            "benchmark_success": True,
            "benchmark_elapsed_us": 850_000,
            "benchmark_heap_before": 100_000,
            "benchmark_heap_after": 100_000,
            "persistence_touched_by_benchmark": False,
            "radio_touched": False,
            "worker_active": False,
        }
        self.assertEqual([], RUNNER.benchmark_failures(valid))
        broken = dict(valid, benchmark_heap_after=99_999)
        self.assertTrue(RUNNER.benchmark_failures(broken))

    def test_lock_state_comparison_is_exact_for_persistent_fields(self) -> None:
        before = {
            "status": "locked", "failure": "wrong_pin",
            "failed_attempts": 2, "credential_generation": 4,
            "protected_access": False,
        }
        self.assertEqual(
            [], RUNNER.lock_state_unchanged_failures(before, dict(before)))
        after = dict(before, failed_attempts=3)
        self.assertTrue(RUNNER.lock_state_unchanged_failures(before, after))


if __name__ == "__main__":
    unittest.main()

