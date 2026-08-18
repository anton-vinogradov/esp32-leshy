#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zlib
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("run_1x_stage_demo_s3_hil.py")
SPEC = importlib.util.spec_from_file_location("stage_demo_s3", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StageDemoS3RunnerTests(unittest.TestCase):
    def test_masked_difference_is_removed(self) -> None:
        expected = bytes(MODULE.FRAME_BYTES)
        actual = bytearray(expected)
        offset = (70 * MODULE.WIDTH + 5) * 2
        actual[offset:offset + 2] = b"\xff\xff"
        masks = [[0, 64, 240, 154]]
        self.assertEqual(
            MODULE.masked_frame(bytes(actual), MODULE.WIDTH, MODULE.HEIGHT, masks),
            MODULE.masked_frame(expected, MODULE.WIDTH, MODULE.HEIGHT, masks),
        )

    def test_unmasked_difference_is_detected(self) -> None:
        expected = bytes(MODULE.FRAME_BYTES)
        actual = bytearray(expected)
        actual[0:2] = b"\xff\xff"
        self.assertEqual(MODULE.mismatch_pixels(bytes(actual), expected), 1)

    def test_suite_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = {
                "schema": "leshy.stage_demo_s3.suite.v1",
                "id": "stage-demo-s3", "revision": 1,
                "recording_manifest": "../escape.json",
                "captures": [
                    {"name": name, "golden": f"{name}.zlib",
                     "mode": "exact", "masks": []}
                    for name in MODULE.CAPTURE_NAMES
                ],
            }
            path = root / "suite.json"
            path.write_text(json.dumps(suite), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.validate_suite(path)

    def test_invalid_golden_compression_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite_path = root / "suite.json"
            suite = {
                "schema": "leshy.stage_demo_s3.suite.v1",
                "id": "stage-demo-s3", "revision": 1,
                "recording_manifest": "manifest.json",
                "captures": [
                    {"name": name, "golden": f"{name}.zlib",
                     "mode": "exact", "masks": []}
                    for name in MODULE.CAPTURE_NAMES
                ],
            }
            suite_path.write_text(json.dumps(suite), encoding="utf-8")
            product = root / "product" / "frames"
            product.mkdir(parents=True)
            for name in MODULE.CAPTURE_NAMES:
                (product / f"{name}.rgb565").write_bytes(bytes(MODULE.FRAME_BYTES))
                (root / f"{name}.zlib").write_bytes(b"not-zlib")
            manifest = {
                "schema": MODULE.MANIFEST_SCHEMA,
                "gate_eligible": False,
                "manual_visual_review": "pass",
                "product_run_id": "recording",
                "product_runner_sha256": MODULE.digest(MODULE.PRODUCT_RUNNER),
                "candidate": {
                    "version": "test", "firmware_sha256": "candidate",
                    "app_elf_sha256": "identity",
                },
                "captures": [],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            firmware = root / "firmware.bin"
            firmware.write_bytes(b"candidate")
            original_identity = MODULE.app_elf_sha256
            original_digest = MODULE.digest
            MODULE.app_elf_sha256 = lambda _: "identity"
            MODULE.digest = lambda path: (
                "candidate" if path == firmware else original_digest(path)
            )
            try:
                comparisons, failures = MODULE.compare_goldens(
                    suite_path, suite, root / "product", {
                        "run_id": "gate", "candidate": {"version": "test"}
                    }, firmware
                )
            finally:
                MODULE.app_elf_sha256 = original_identity
                MODULE.digest = original_digest
            self.assertEqual(comparisons, [])
            self.assertTrue(any("invalid golden compression" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
