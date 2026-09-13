#!/usr/bin/env python3
"""Tracked mode may lack declared build bytes, never public proof or wrong bytes."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import check_worker_deadline_acceptance as wifi
import check_worker_deadline_ble_acceptance as ble


class EvidenceScopeTests(unittest.TestCase):
    def test_full_vs_tracked_and_tampered(self):
        for checker in (wifi, ble):
            with self.subTest(checker=checker.__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = {"run.json": b"public proof", "firmware.bin": b"local image",
                        "firmware.map": b"local map"}
                (root / "artifacts.sha256").write_text("".join(
                    f"{hashlib.sha256(value).hexdigest()}  {name}\n" for name, value in data.items()))
                (root / "run.json").write_bytes(data["run.json"])
                with patch.object(checker, "BUNDLE", root):
                    failures = []
                    checker.verify_manifest(failures)
                    self.assertTrue(failures)  # Full remains fail closed.
                    failures = []
                    checker.verify_manifest(failures, tracked_only=True)
                    self.assertEqual([], failures)
                    (root / "firmware.bin").write_bytes(b"tampered")
                    failures = []
                    checker.verify_manifest(failures, tracked_only=True)
                    self.assertTrue(failures)  # Present bytes are always rehashed.
                    for name, value in data.items(): (root / name).write_bytes(value)
                    failures = []
                    checker.verify_manifest(failures)
                    self.assertEqual([], failures)
                    (root / "run.json").unlink()
                    failures = []
                    checker.verify_manifest(failures, tracked_only=True)
                    self.assertTrue(failures)  # Public proof is never optional.


if __name__ == "__main__":
    unittest.main()
