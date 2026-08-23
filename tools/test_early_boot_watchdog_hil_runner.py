#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any

import serial


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_early_boot_watchdog_hil.py")
    spec = importlib.util.spec_from_file_location(
        "early_boot_watchdog_hil", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
APP = "a" * 64


class EarlyBootWatchdogHilRunnerTests(unittest.TestCase):
    def records(self) -> tuple[dict[str, Any], ...]:
        armed = {
            "status": "ready", "stage": "before_setup",
            "watchdog_timeout_ms": 5000, "outputs_inactive": True,
            "filesystem_write_attempted": False, "physical_write_calls": 0,
        }
        ready = {
            "version": "test", "app_elf_sha256": APP,
            "buzzer_inactive": True, "input_detected": True,
            "input_probe_attempts": 2,
            "input_probe_transient_retries": 1,
            "reset_reason_code": 6,
        }
        safety = {
            "state": "latched", "reason": "runtime_watchdog",
            "armed": True, "latched": True, "clear_pending": False,
            "trip_count": 1, "emergency_quiesce_count": 1,
            "startup_guard_tripped": True,
            "buzzer_inactive": True, "nrf_ce_inactive": True,
            "runtime_owner": "none", "lease_mask": 0,
            "automatic_clear": False,
        }
        ui = {
            "page": "safe_mode", "safety_latched": True,
            "runtime_owner": "none", "lease_mask": 0,
        }
        outputs = {
            "buzzer_inactive": True, "nrf_ce_inactive": True,
            "software_quiesce_complete": True,
            "physical_rail_kill_available": False,
            "cc1101_hard_kill_available": False,
        }
        recovery = {
            "status": "safety_latched", "cleanup_complete": True,
            "physical_write_calls": 0, "owned_after": 0,
        }
        return armed, ready, safety, ui, outputs, recovery

    def test_accepts_exact_pre_display_watchdog_latch(self) -> None:
        self.assertEqual([], RUNNER.early_boot_injection_failures(
            *self.records(), "test", APP
        ))

    def test_rejects_wrong_stage_software_reset_and_missing_quiesce(self) -> None:
        records = list(self.records())
        records[0]["stage"] = "after_setup"
        records[1]["reset_reason_code"] = 3
        records[2]["emergency_quiesce_count"] = 0
        failures = RUNNER.early_boot_injection_failures(
            *records, "test", APP
        )
        self.assertEqual(3, len(failures))

    def test_rejects_unsafe_outputs_and_storage_cleanup(self) -> None:
        records = list(self.records())
        records[4]["nrf_ce_inactive"] = False
        records[5]["physical_write_calls"] = 1
        failures = RUNNER.early_boot_injection_failures(
            *records, "test", APP
        )
        self.assertEqual(2, len(failures))

    def test_capture_reopens_native_usb_after_watchdog_reset(self) -> None:
        ready = (
            b'ESP-ROM\n'
            b'{"schema":"leshy.boot.v1","kind":"ready"}\n'
        )

        class FakePort:
            def __init__(self, chunks: list[bytes | Exception]) -> None:
                self.chunks = chunks
                self.closed = False

            @property
            def in_waiting(self) -> int:
                return 1

            def read(self, _: int) -> bytes:
                value = self.chunks.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value

            def close(self) -> None:
                self.closed = True

        ports = [
            FakePort([b"pre-reset\n", serial.SerialException("gone")]),
            FakePort([ready]),
        ]

        raw, ready_ms, disconnects, open_attempts = (
            RUNNER.capture_reconnecting_until_ready(
                "/dev/fake", 1.0, serial_factory=lambda: ports.pop(0),
                settle_seconds=0.0, retry_seconds=0.0,
            )
        )

        self.assertIn(b"pre-reset", raw)
        self.assertIn(b'"kind":"ready"', raw)
        self.assertIsNotNone(ready_ms)
        self.assertEqual(1, disconnects)
        self.assertEqual(2, open_attempts)

    def test_capture_retries_port_reenumeration_open(self) -> None:
        ready = b'{"schema":"leshy.boot.v1","kind":"ready"}\n'

        class FakePort:
            in_waiting = 1

            def read(self, _: int) -> bytes:
                return ready

            def close(self) -> None:
                pass

        attempts = 0

        def factory() -> FakePort:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise serial.SerialException("not enumerated")
            return FakePort()

        raw, ready_ms, disconnects, open_attempts = (
            RUNNER.capture_reconnecting_until_ready(
                "/dev/fake", 1.0, serial_factory=factory,
                settle_seconds=0.0, retry_seconds=0.0,
            )
        )

        self.assertEqual(ready, raw)
        self.assertIsNotNone(ready_ms)
        self.assertEqual(0, disconnects)
        self.assertEqual(2, open_attempts)


if __name__ == "__main__":
    unittest.main()
