#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


capture_stub = types.ModuleType("capture_1x_ui")
capture_stub.PassiveSerial = object
capture_stub.synchronize_console = lambda *_args, **_kwargs: None
sys.modules.setdefault("capture_1x_ui", capture_stub)


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_airspace_guard_profiles_hil.py")
    spec = importlib.util.spec_from_file_location(
        "airspace_guard_profiles_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class AirspaceGuardProfilesHilRunnerTests(unittest.TestCase):
    def test_all_three_profile_contracts_are_distinct(self) -> None:
        self.assertEqual(
            ["everyday", "quiet_place", "busy_place"],
            [name for name, _ in RUNNER.PROFILES])
        self.assertEqual(
            [0, 1, 2],
            [policy["profile_selection"]
             for _, policy in RUNNER.PROFILES])
        self.assertEqual(
            [4, 3, 6],
            [policy["disconnect_threshold"]
             for _, policy in RUNNER.PROFILES])

    def test_exact_profile_state_passes_and_wrong_policy_fails(self) -> None:
        name, policy = RUNNER.PROFILES[1]
        state = {
            "schema": RUNNER.STATE_SCHEMA,
            "kind": "state",
            "profile": name,
            "profile_version": 1,
            **policy,
            "passive_only": True,
            "rx_only": True,
            "application_connect_calls": 0,
            "application_raw_tx_calls": 0,
        }
        self.assertEqual([], RUNNER.profile_failures(
            state, name, policy, "quiet"))
        state["disconnect_threshold"] = 4
        self.assertNotEqual([], RUNNER.profile_failures(
            state, name, policy, "quiet"))

    def test_pixel_proof_separates_content_from_static_chrome(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            before = bytearray(RUNNER.WIDTH * RUNNER.HEIGHT * 2)
            after = bytearray(before)
            content_offset = (
                (RUNNER.PROFILE_MUTABLE_TOP * RUNNER.WIDTH + 3) * 2)
            after[content_offset:content_offset + 2] = b"\x01\x02"
            (root / "before.rgb565").write_bytes(before)
            (root / "after.rgb565").write_bytes(after)
            proof = RUNNER.pixel_region_delta(root, "before", "after")
            self.assertEqual(1, proof["changed_pixels"])
            self.assertEqual(1, proof["mutable_changed_pixels"])
            self.assertEqual(0, proof["static_changed_pixels"])

            after[0:2] = b"\x03\x04"
            (root / "after.rgb565").write_bytes(after)
            proof = RUNNER.pixel_region_delta(root, "before", "after")
            self.assertEqual(1, proof["static_changed_pixels"])


if __name__ == "__main__":
    unittest.main()
