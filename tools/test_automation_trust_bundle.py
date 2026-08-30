#!/usr/bin/env python3
"""Regression tests for the public-only GitHub enrollment bundle builder."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_automation_trust_bundle import build_bundle, read_spki_p256


class AutomationTrustBundleTests(unittest.TestCase):
    def test_p256_spki_build_is_deterministic_and_public_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(private_key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True,
                capture_output=True,
            )
            point = read_spki_p256(public_key)
            first, metadata = build_bundle(point, "GitHub owner key")
            second, repeated = build_bundle(point, "GitHub owner key")
            self.assertEqual(first, second)
            self.assertEqual(metadata, repeated)
            self.assertEqual(len(first), 128)
            self.assertEqual(first[:4], b"LHAK")
            self.assertEqual(first[8:16], hashlib.sha256(point).digest()[:8])
            self.assertFalse(metadata["contains_private_key"])
            self.assertNotIn(private_key.read_bytes(), first)
            self.assertEqual(
                metadata["bundle_sha256"], hashlib.sha256(first).hexdigest()
            )
            json.dumps(metadata)

    def test_wrong_curve_and_unsafe_label_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-384", "-out", str(private_key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True,
                capture_output=True,
            )
            with self.assertRaisesRegex(ValueError, "only P-256"):
                read_spki_p256(public_key)
        with self.assertRaisesRegex(ValueError, "printable ASCII"):
            build_bundle(bytes([4]) + bytes(range(1, 65)), "bad\nlabel")


if __name__ == "__main__":
    unittest.main()
