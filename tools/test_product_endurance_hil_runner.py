#!/usr/bin/env python3
"""Host tests for the foreground product endurance orchestration policy."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_product_endurance_hil.py")
    spec = importlib.util.spec_from_file_location("product_endurance_hil", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "a" * 64
APP = "b" * 64
VERSION = "0.48.0-product-boot-timeout-measure"
HEAP = (276312, 227876, 194956)


def ready() -> dict[str, Any]:
    return {
        "heap_total": HEAP[0], "heap_free": HEAP[1],
        "heap_min_free": HEAP[2],
    }


def cycle(before: int, after: int, observations_before: int,
          observations_after: int, flashed: bool) -> dict[str, Any]:
    recovery_before = {
        "generation": before, "observations": observations_before,
        "attempts": 1, "transient_retries": 0,
    }
    recovery_after = {
        "generation": after, "observations": observations_after,
        "blocked_write_attempts": 0, "physical_write_calls": 0,
        "cleanup_complete": True, "read_only_guaranteed": True,
        "attempts": 1, "transient_retries": 0,
    }
    committed = {
        "survey_generation": after,
        "survey_observations": observations_after,
        "survey_scan_accepted": observations_after,
        "survey_forwarded": observations_after,
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_dropped": 0,
    }
    return {
        "schema": "leshy.product_survey_hil.run.v1",
        "run_id": f"run-{after}",
        "passed": True,
        "candidate": {
            "firmware_sha256": FIRMWARE, "app_elf_sha256": APP,
            "version": VERSION, "flashed": flashed,
        },
        "expected_cid": CID,
        "boot_before": {
            "ready": ready(), "recovery": recovery_before,
            "timing": {"ready_marker_ms": 720.0},
        },
        "running": {
            "survey_product_identity_attempts": 1,
            "survey_product_identity_transient_retries": 0,
        },
        "committed": committed,
        "boot_after": {
            "ready": ready(), "recovery": recovery_after,
            "timing": {"ready_marker_ms": 730.0},
        },
        "library_export": {
            "generation": after, "persistent": True, "simulated": False,
            "integrity": "valid", "radio_touched": False,
            "session": {"observations": observations_after},
        },
        "final_state": {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "survey_product_backend_open": False,
            "survey_product_cleanup_complete": True,
        },
        "captures": {
            "committed": {}, "export": {}, "running": {}, "setup": {},
        },
    }


class EnduranceRunnerTests(unittest.TestCase):
    def summarize(self, value: dict[str, Any], number: int,
                  cid: str | None, generation: int | None,
                  observations: int | None, heap: tuple[int, int, int] | None,
                  flashed: bool) -> tuple[dict[str, Any], list[str], str | None,
                                           tuple[int, int, int] | None]:
        return RUNNER.summarize_cycle(
            value, number, FIRMWARE, APP, VERSION, cid, generation,
            observations, heap, flashed,
        )

    def test_two_continuous_exact_cycles_pass(self) -> None:
        first, failures, cid, heap = self.summarize(
            cycle(6, 7, 16, 23, True), 1, None, None, None, None, True
        )
        self.assertFalse(failures)
        self.assertTrue(first["passed"])
        second, failures, _, _ = self.summarize(
            cycle(7, 8, 23, 21, False), 2, cid, 7, 23, heap, False
        )
        self.assertFalse(failures)
        self.assertTrue(second["passed"])

    def test_identity_generation_and_heap_drift_fail_closed(self) -> None:
        value = cycle(8, 10, 21, 19, False)
        value["candidate"]["app_elf_sha256"] = "c" * 64
        value["boot_after"]["ready"]["heap_free"] -= 4
        _summary, failures, _, _ = self.summarize(
            value, 3, CID, 8, 21, HEAP, False
        )
        combined = "\n".join(failures)
        self.assertIn("candidate.app_elf_sha256", combined)
        self.assertIn("generation_after", combined)
        self.assertIn("heap", combined)

    def test_drop_leak_and_slow_boot_fail_closed(self) -> None:
        value = cycle(8, 9, 21, 20, False)
        value["committed"]["survey_scan_dropped"] = 1
        value["final_state"]["lease_mask"] = 4
        value["boot_after"]["timing"]["ready_marker_ms"] = 1501.0
        _summary, failures, _, _ = self.summarize(
            value, 3, CID, 8, 21, HEAP, False
        )
        combined = "\n".join(failures)
        self.assertIn("survey_scan_dropped", combined)
        self.assertIn("final_state.lease_mask", combined)
        self.assertIn("ready_after_ms", combined)

    def test_release_policy_has_non_weakenable_floor(self) -> None:
        valid, failures = RUNNER.release_policy(True, True, 28800, 32)
        self.assertTrue(valid)
        self.assertFalse(failures)
        valid, failures = RUNNER.release_policy(False, False, 28799, 31)
        self.assertFalse(valid)
        self.assertEqual(4, len(failures))


if __name__ == "__main__":
    unittest.main()
