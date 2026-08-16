#!/usr/bin/env python3
"""Host tests for the manifest, assertions, and visual pre-release gate."""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_prerelease_hil.py")
    spec = importlib.util.spec_from_file_location("prerelease_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class PrereleaseRunnerTests(unittest.TestCase):
    def test_candidate_app_identity_is_read_from_descriptor(self) -> None:
        image = bytearray(288)
        image[0] = 0xE9
        struct.pack_into("<I", image, 32, 0xABCD5432)
        image[176:208] = bytes(range(32))
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "firmware.bin"
            candidate.write_bytes(image)
            self.assertEqual(bytes(range(32)).hex(),
                             RUNNER.app_elf_sha256(candidate))

    def test_candidate_app_identity_rejects_non_esp_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "firmware.bin"
            candidate.write_bytes(b"not-an-esp-image")
            with self.assertRaisesRegex(ValueError, "too short"):
                RUNNER.app_elf_sha256(candidate)

    def test_manifest_validation_rejects_duplicate_scenarios(self) -> None:
        suite = {
            "schema": RUNNER.SUITE_SCHEMA,
            "id": "smoke", "revision": 1, "boot_assert": {},
            "scenarios": [
                {"id": "same", "steps": [{"id": "a", "assert": {}}]},
                {"id": "same", "steps": [{"id": "b", "assert": {}}]},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(suite), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate scenario"):
                RUNNER.load_suite(path)

    def test_manifest_accepts_bounded_diagnostic_query(self) -> None:
        suite = {
            "schema": RUNNER.SUITE_SCHEMA,
            "id": "product", "revision": 1, "boot_assert": {},
            "scenarios": [{
                "id": "export",
                "steps": [{
                    "id": "artifact",
                    "query": {
                        "command": "library.export",
                        "schema": "leshy.library.export.v1",
                        "kind": "artifact",
                    },
                    "assert": {"generation": 2},
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(suite), encoding="utf-8")
            self.assertEqual(suite, RUNNER.load_suite(path))

    def test_manifest_rejects_unsafe_or_ambiguous_query(self) -> None:
        base = {
            "schema": RUNNER.SUITE_SCHEMA,
            "id": "product", "revision": 1, "boot_assert": {},
            "scenarios": [{"id": "export", "steps": []}],
        }
        invalid_steps = [
            {
                "id": "ambiguous", "action": "select",
                "query": {"command": "library.export", "schema": "x", "kind": "y"},
                "assert": {},
            },
            {
                "id": "newline",
                "query": {"command": "library.export\nmetrics", "schema": "x", "kind": "y"},
                "assert": {},
            },
            {
                "id": "capture-query",
                "query": {"command": "library.export", "schema": "x", "kind": "y"},
                "assert": {},
                "capture": {"golden": "frame.zlib"},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            for step in invalid_steps:
                base["scenarios"][0]["steps"] = [step]
                path.write_text(json.dumps(base), encoding="utf-8")
                with self.assertRaises(ValueError):
                    RUNNER.load_suite(path)

    def test_subset_and_numeric_assertions(self) -> None:
        actual = {"page": "home", "lease": 0, "heap": 200000,
                  "nested": {"owner": "none"}}
        expected = {"page": "home", "heap": {"$gte": 131072},
                    "nested": {"owner": {"$in": ["none", "idle"]}}}
        self.assertEqual([], RUNNER.assertion_failures(expected, actual))
        failures = RUNNER.assertion_failures(
            {"lease": 1, "heap": {"$lte": 100000}}, actual)
        self.assertEqual(2, len(failures))

    def test_missing_golden_records_once_then_matches(self) -> None:
        frame = b"\x12\x34" * 8
        with tempfile.TemporaryDirectory() as directory:
            suite_path = Path(directory) / "suite.json"
            suite_path.write_text("{}", encoding="utf-8")
            capture = {"golden": "golden/frame.rgb565.zlib", "mode": "exact"}
            recorded = RUNNER.compare_or_record_golden(
                frame, 4, 2, capture, suite_path, True)
            self.assertEqual("recorded", recorded["status"])
            golden_path = Path(recorded["golden"])
            self.assertEqual(frame, zlib.decompress(golden_path.read_bytes()))
            matched = RUNNER.compare_or_record_golden(
                frame, 4, 2, capture, suite_path, False)
            self.assertTrue(matched["passed"])
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                RUNNER.compare_or_record_golden(
                    frame, 4, 2, capture, suite_path, True)

    def test_masked_exact_does_not_hide_unmasked_change(self) -> None:
        golden = b"\x00\x00" * 8
        with tempfile.TemporaryDirectory() as directory:
            suite_path = Path(directory) / "suite.json"
            suite_path.write_text("{}", encoding="utf-8")
            golden_path = Path(directory) / "golden.zlib"
            golden_path.write_bytes(zlib.compress(golden))
            capture = {"golden": "golden.zlib", "mode": "masked_exact",
                       "masks": [[0, 0, 1, 1]]}
            masked_change = bytearray(golden)
            masked_change[0:2] = b"\xFF\xFF"
            self.assertTrue(RUNNER.compare_or_record_golden(
                bytes(masked_change), 4, 2, capture, suite_path, False)["passed"])
            unmasked_change = bytearray(golden)
            unmasked_change[2:4] = b"\xFF\xFF"
            compared = RUNNER.compare_or_record_golden(
                bytes(unmasked_change), 4, 2, capture, suite_path, False)
            self.assertFalse(compared["passed"])
            self.assertEqual(1, compared["mismatch_pixels"])

    def test_invalid_mask_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "out-of-bounds"):
            RUNNER.masked_frame(b"\0" * 16, 4, 2, [[3, 1, 2, 1]])


if __name__ == "__main__":
    unittest.main()
