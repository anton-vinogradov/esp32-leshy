#!/usr/bin/env python3
"""Host-only validation for the positive Automation trust HIL inputs."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from automation_trust_public_bundle import load_public_bundle


class PublicBundleValidationTest(unittest.TestCase):
    def write_fixture(self, root: Path) -> tuple[Path, Path]:
        bundle = bytes(range(128))
        digest = hashlib.sha256(bundle).hexdigest()
        bundle_path = root / "automation-owner.lhak"
        metadata_path = root / "automation-owner.json"
        bundle_path.write_bytes(bundle)
        metadata_path.write_text(json.dumps({
            "schema": "leshy.automation.trust_bundle.v1",
            "algorithm": "ecdsa_p256_sha256",
            "bundle_bytes": 128,
            "bundle_sha256": digest,
            "contains_private_key": False,
            "key_id": digest[:16],
            "public_key_sha256": digest,
            "label": "GitHub owner key",
        }), encoding="utf-8")
        return bundle_path, metadata_path

    def test_accepts_exact_public_bundle_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle_path, metadata_path = self.write_fixture(Path(temporary))
            bundle, metadata = load_public_bundle(bundle_path, metadata_path)
            self.assertEqual(len(bundle), 128)
            self.assertFalse(metadata["contains_private_key"])

    def test_rejects_private_key_marker_and_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_path, metadata_path = self.write_fixture(root)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["contains_private_key"] = True
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_public_bundle(bundle_path, metadata_path)
            metadata["contains_private_key"] = False
            metadata["bundle_sha256"] = "0" * 64
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_public_bundle(bundle_path, metadata_path)


if __name__ == "__main__":
    unittest.main()
