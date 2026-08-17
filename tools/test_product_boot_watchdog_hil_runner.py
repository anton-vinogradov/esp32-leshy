#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_product_boot_watchdog_hil.py")
    spec = importlib.util.spec_from_file_location("product_boot_watchdog_hil", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
CID = "FE343253440000002000000055019CB7"
APP = "a" * 64


class ProductBootWatchdogHilRunnerTests(unittest.TestCase):
    def records(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        ready = {
            "version": "test", "app_elf_sha256": APP,
            "buzzer_inactive": True, "input_detected": True,
            "reset_reason_code": 6,
        }
        recovery = {
            "status": "admitted", "enrolled": True,
            "expected_fingerprint": CID, "observed_fingerprint": CID,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "blocked_write_attempts": 0,
            "catalog_admitted": True, "cleanup_complete": True,
            "physical_write_calls": 0, "generation": 48,
            "attempts": 2, "transient_retries": 1,
            "timeout_restarts": 1,
        }
        final = {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "survey_product_backend_open": False,
            "survey_product_cleanup_complete": True,
        }
        return ready, recovery, final

    def test_accepts_exact_hardware_timeout_recovery(self) -> None:
        ready, recovery, final = self.records()
        self.assertEqual([], RUNNER.injection_failures(
            ready, recovery, final, "test", APP, CID
        ))

    def test_rejects_software_reset_missing_timeout_and_leak(self) -> None:
        ready, recovery, final = self.records()
        ready["reset_reason_code"] = 3
        recovery["timeout_restarts"] = 0
        final["lease_mask"] = 12
        failures = RUNNER.injection_failures(
            ready, recovery, final, "test", APP, CID
        )
        self.assertEqual(3, len(failures))

    def test_parser_uses_last_ready_record(self) -> None:
        raw = (
            b'noise\n{"schema":"leshy.boot.v1","kind":"ready",'
            b'"reset_reason_code":3}\n'
            b'{"schema":"leshy.boot.v1","kind":"ready",'
            b'"reset_reason_code":6}\n'
        )
        self.assertEqual(6, RUNNER.parse_ready(raw)["reset_reason_code"])


if __name__ == "__main__":
    unittest.main()
