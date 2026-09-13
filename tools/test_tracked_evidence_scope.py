#!/usr/bin/env python3
"""Public archive integrity is not interchangeable with a full binary HIL gate."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_tracked_hil_evidence as checker
import hil_evidence


def sha(data):
    return hashlib.sha256(data).hexdigest()


class TrackedScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / "tests/hil/evidence/example"
        self.child = self.bundle / "run"
        self.child.mkdir(parents=True)
        self.summary = self.bundle.with_suffix(".json")
        (self.child / "run.json").write_bytes(b"public observation")
        child_index = (
            f"{sha(b'public observation')}  run.json\n"
            f"{sha(b'opaque image')}  firmware.bin\n").encode()
        (self.child / "artifacts.sha256").write_bytes(child_index)
        index = f"{sha(child_index)}  run/artifacts.sha256\n".encode()
        (self.bundle / "artifacts.sha256").write_bytes(index)
        self.summary.write_text(json.dumps({
            "evidence": {"artifact_index_sha256": sha(index)}}))
        self.tracked = {str(path.relative_to(self.root))
                        for path in self.root.rglob("*") if path.is_file()}

    def check(self):
        with patch.object(checker, "ROOT", self.root), \
             patch.object(checker, "git_paths", return_value=self.tracked), \
             patch("sys.argv", ["checker", "--bundle", str(self.bundle),
                                "--summary", str(self.summary), "--recursive"]), \
             contextlib.redirect_stdout(io.StringIO()):
            return checker.main()

    def test_nested_public_archive_without_opaque_image(self):
        self.assertEqual(0, self.check())

    def test_present_opaque_bytes_are_still_verified(self):
        image = self.child / "firmware.bin"
        image.write_bytes(b"opaque image")
        self.assertEqual(0, self.check())
        image.write_bytes(b"corrupt")
        self.assertEqual(1, self.check())

    def test_missing_or_corrupt_public_proof_fails(self):
        proof = self.child / "run.json"
        proof.unlink()
        self.assertEqual(1, self.check())
        proof.write_bytes(b"corrupt")
        self.assertEqual(1, self.check())

    def test_child_index_cannot_disappear(self):
        (self.child / "artifacts.sha256").unlink()
        self.assertEqual(1, self.check())

    def test_summary_and_parent_bind_child_index(self):
        (self.child / "artifacts.sha256").write_bytes(b"")
        self.assertEqual(1, self.check())
        self.summary.write_text(json.dumps({
            "evidence": {"artifact_index_sha256": "0" * 64}}))
        self.assertEqual(1, self.check())

    def test_unindexed_tracked_proof_fails(self):
        extra = self.child / "unindexed.json"
        extra.write_bytes(b"not indexed")
        self.tracked.add(str(extra.relative_to(self.root)))
        self.assertEqual(1, self.check())

    def test_untracked_public_proof_is_not_optional(self):
        self.tracked.remove(str((self.child / "run.json").relative_to(self.root)))
        self.assertEqual(1, self.check())

    def test_fixture_omission_requires_explicit_tracked_scope(self):
        image = self.bundle / "fixture.bin"
        (self.bundle / "artifacts.sha256").write_text(
            f"{sha(b'fixture')}  fixture.bin\n")
        # A separate empty directory avoids unrelated inventory in this fixture.
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "artifacts.sha256").write_text(
                f"{sha(b'fixture')}  fixture.bin\n")
            with self.assertRaises(ValueError):
                hil_evidence.verify_manifest(root)
            self.assertEqual({"fixture.bin"},
                             hil_evidence.verify_manifest(root, tracked_only=True))
            (root / "fixture.bin").write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                hil_evidence.verify_manifest(root, tracked_only=True)
        with self.assertRaises(ValueError):
            hil_evidence.verify_fixture_identity(image, "a" * 64)
        hil_evidence.verify_fixture_identity(image, "a" * 64, tracked_only=True)
        with self.assertRaises(ValueError):
            hil_evidence.verify_fixture_identity(image, "bad", tracked_only=True)
        image.write_bytes(b"present")
        with patch.object(hil_evidence, "app_elf_sha256", return_value="b" * 64):
            with self.assertRaises(ValueError):
                hil_evidence.verify_fixture_identity(image, "a" * 64, tracked_only=True)


if __name__ == "__main__":
    unittest.main()
