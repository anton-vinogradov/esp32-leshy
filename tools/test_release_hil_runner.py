#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_release_hil.py")
    spec = importlib.util.spec_from_file_location("release_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
CID = "FE343253440000002000000055019CB7"


class ReleaseHilRunnerTests(unittest.TestCase):
    def test_unenrollment_must_not_touch_sd(self) -> None:
        record = {
            "mode": "unenroll", "status": "valid", "was_enrolled": True,
            "cleared_fingerprint": CID, "nvs_key_removed": True,
            "sd_accessed": False, "sd_data_untouched": True,
            "active_catalog_unchanged": True, "reboot_required": True,
            "physical_write_calls": 0,
        }
        self.assertEqual([], RUNNER.unenroll_failures(record, CID))
        self.assertEqual((True, True, []), RUNNER.unenroll_outcome(record, CID))
        record["sd_accessed"] = True
        self.assertEqual(1, len(RUNNER.unenroll_failures(record, CID)))
        removed, generic_allowed, failures = RUNNER.unenroll_outcome(record, CID)
        self.assertTrue(removed)
        self.assertFalse(generic_allowed)
        self.assertEqual(1, len(failures))

    def test_reenrollment_is_exact_and_read_only(self) -> None:
        record = {
            "mode": "enroll", "status": "valid",
            "expected_fingerprint": CID, "observed_fingerprint": CID,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "write_enabled": False,
            "blocked_write_attempts": 0, "catalog_status": "admitted",
            "catalog_admitted": True, "generation": 8, "observations": 17,
            "enrollment_saved": True, "owned_after": 0,
            "cleanup_complete": True, "physical_write_calls": 0,
        }
        self.assertEqual([], RUNNER.reenroll_failures(record, CID, 8, 17))
        record["write_enabled"] = True
        record["generation"] = 7
        self.assertEqual(2, len(RUNNER.reenroll_failures(record, CID, 8, 17)))

    def test_final_state_requires_enrolled_idle_persistent_library(self) -> None:
        app = "a" * 64
        ready = {
            "version": "1.0.0", "app_elf_sha256": app,
            "buzzer_inactive": True, "input_detected": True,
        }
        recovery = {
            "status": "admitted", "enrolled": True,
            "expected_fingerprint": CID, "observed_fingerprint": CID,
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "blocked_write_attempts": 0,
            "catalog_status": "admitted", "catalog_admitted": True,
            "generation": 4, "observations": 15, "integrity": "valid",
            "owned_after": 0, "cleanup_complete": True,
            "physical_write_calls": 0,
        }
        state = {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "library_persistent": True, "library_simulated": False,
            "library_generation": 4,
        }
        self.assertEqual([], RUNNER.final_failures(
            ready, recovery, state, "1.0.0", app, CID, 4, 15
        ))
        state["lease_mask"] = 1
        self.assertEqual(1, len(RUNNER.final_failures(
            ready, recovery, state, "1.0.0", app, CID, 4, 15
        )))


if __name__ == "__main__":
    unittest.main()
