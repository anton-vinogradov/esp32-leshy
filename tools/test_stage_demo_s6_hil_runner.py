#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("run_1x_stage_demo_s6_hil.py")
SPEC = importlib.util.spec_from_file_location("stage_demo_s6", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


EXPECTED = {
    "version": "0.test",
    "firmware_sha256": "f" * 64,
    "app_elf_sha256": "e" * 64,
}
CID = MODULE.EXPECTED_CID
SOURCE = "c" * 40


def product(before: int, after: int, *, flashed: bool) -> dict:
    return {
        "schema": "leshy.product_survey_hil.run.v1",
        "passed": True,
        "gate_eligible": flashed,
        "failures": [],
        "expected_cid": CID,
        "candidate": {**EXPECTED, "flashed": flashed},
        "release_cycle": True,
        "boot_before": {"recovery": {"generation": before}},
        "committed": {
            "survey_generation": after,
            "survey_observations": 12,
        },
        "final_state": {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
        },
        "cleanup_before_reboot": {"complete": True},
        "cleanup_final": {"complete": True},
    }


def targets() -> dict:
    rows = [{"selected_change_class": "unchanged"} for _ in range(3)]
    details = [{"view": "compare_detail"} for _ in range(3)]
    return {
        "schema": "leshy.targets_evidence_hil.run.v1",
        "status": "pass",
        "source_commit": SOURCE,
        "exact_cid": CID,
        "candidate": EXPECTED.copy(),
        "flash_count": 0,
        "exact_flash_reused": True,
        "generations": [11, 12],
        "targets": {
            "list": {"comparison_count": 3},
            "rows": rows,
            "evidence_details": details,
        },
        "storage_write_calls": 0,
        "radio_tx_commands": 0,
        "cleanup": {"complete": True},
    }


def companion() -> dict:
    return {
        "schema": "leshy.companion_usb_delta_hil.run.v1",
        "status": "pass",
        "source_commit": SOURCE,
        "exact_cid": CID,
        "candidate": EXPECTED.copy(),
        "flash_count": 0,
        "exact_flash_reused": True,
        "sessions": {"details": [{"generation": 11}, {"generation": 12}]},
        "targets": {"compare_count": 3},
        "offline_snapshot": {
            "canonical_round_trip": True,
            "counts": {"sessions": 2, "targets": 3, "comparison_items": 3},
            "snapshot_id": "a" * 64,
            "bytes": 1024,
        },
        "host_network_tools_invoked": False,
        "active_mac_wifi_touched": False,
        "wifi_softap_started": False,
        "raw_radio_tx_commands": 0,
        "storage_write_commands": 0,
        "cleanup": {"complete": True},
    }


class StageDemoS6RunnerTests(unittest.TestCase):
    def test_valid_path_requires_one_flash_and_every_evidence(self) -> None:
        summary, failures = MODULE.validate_children(
            product(10, 11, flashed=True),
            product(11, 12, flashed=False),
            targets(), companion(), EXPECTED, CID, SOURCE,
        )
        self.assertEqual(failures, [])
        self.assertEqual(summary["baseline_generation"], 11)
        self.assertEqual(summary["repeat_generation"], 12)
        self.assertEqual(summary["evidence_views_opened"], 3)

    def test_noncontiguous_survey_pair_fails_closed(self) -> None:
        summary, failures = MODULE.validate_children(
            product(10, 11, flashed=True),
            product(12, 13, flashed=False),
            targets(), companion(), EXPECTED, CID, SOURCE,
        )
        self.assertTrue(any("contiguous" in item for item in failures))
        self.assertEqual(summary["baseline_generation"], 11)

    def test_unopened_comparison_evidence_fails_closed(self) -> None:
        broken_targets = copy.deepcopy(targets())
        broken_targets["targets"]["evidence_details"].pop()
        _, failures = MODULE.validate_children(
            product(10, 11, flashed=True),
            product(11, 12, flashed=False),
            broken_targets, companion(), EXPECTED, CID, SOURCE,
        )
        self.assertTrue(any("every-conclusion" in item for item in failures))

    def test_commands_flash_only_baseline_and_never_request_network(self) -> None:
        args = SimpleNamespace(
            port="/dev/cu.test", firmware=Path("firmware.bin"),
            elf=Path("firmware.elf"), map=Path("firmware.map"),
            expected_version="0.test", expected_cid=CID,
            source_commit=SOURCE, flash_baud=460800,
        )
        commands = [
            MODULE.product_command(args, Path("baseline"), True),
            MODULE.product_command(args, Path("repeat"), False),
            MODULE.targets_command(args, Path("targets")),
            MODULE.companion_command(args, Path("companion")),
        ]
        self.assertEqual(sum("--flash" in command for command in commands), 1)
        self.assertNotIn("--flash", commands[1])
        self.assertIn("--reuse-exact-flash", commands[2])
        self.assertIn("--open-every-evidence", commands[2])
        self.assertIn("--reuse-exact-flash", commands[3])
        forbidden = {"networksetup", "airport", "ifconfig", "route", "scutil"}
        self.assertFalse(any(forbidden.intersection(command) for command in commands))


if __name__ == "__main__":
    unittest.main()
