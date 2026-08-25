#!/usr/bin/env python3
"""Host tests for compact retained S5 two-board matrix evidence."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import retain_s5_two_board_matrix as retention  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n",
                    encoding="utf-8")


def write_manifest(directory: Path) -> None:
    files = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256")
    (directory / "artifacts.sha256").write_text("".join(
        f"{digest(path)}  {path.relative_to(directory)}\n" for path in files),
        encoding="utf-8")


class S5TwoBoardRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "raw"
        self.source.mkdir()
        self.destination = self.root / "retained"
        self.summary_path = self.root / "acceptance.json"
        self.product = b"product-firmware"
        self.fixture = b"fixture-firmware"
        self.profile = {
            "schema": "leshy.hil.board_profile.v1",
            "accepted_for_fixture_flash": True,
            "writes_performed": False,
            "chip": {"fixture_id": "0000AABBCCDDEEFF"},
        }
        self.profile_bytes = (
            json.dumps(self.profile, sort_keys=True) + "\n").encode()
        self.source_commit = "a" * 40
        self.build_paths: dict[str, dict[str, Path]] = {}
        self.inventory: dict[str, dict[str, dict[str, object]]] = {}
        for role in ("product", "fixture"):
            self.build_paths[role] = {}
            self.inventory[role] = {}
            for name in (
                    "firmware.bin", "firmware.factory.bin",
                    "firmware.elf", "firmware.map"):
                path = self.root / "build" / role / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name == "firmware.bin":
                    payload = self.product if role == "product" else self.fixture
                else:
                    payload = f"{role}:{name}".encode()
                path.write_bytes(payload)
                self.build_paths[role][name] = path
                self.inventory[role][name] = {
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }

        (self.source / "run.json").write_text("{}\n", encoding="utf-8")
        self.child_run_hashes: dict[str, str] = {}
        for scenario_id in retention.MATRIX:
            child = self.source / scenario_id
            (child / "frames").mkdir(parents=True)
            (child / "streams").mkdir()
            (child / "firmware.bin").write_bytes(self.product)
            (child / "fixture.bin").write_bytes(self.fixture)
            (child / "fixture-profile.json").write_bytes(self.profile_bytes)
            write_json(child / "run.json", {"scenario": scenario_id})
            (child / "frames" / "screen.png").write_bytes(
                f"png:{scenario_id}".encode())
            (child / "frames" / "screen.rgb565").write_bytes(b"raw pixels")
            (child / "streams" / "data.ndjson").write_text(
                "{}\n", encoding="utf-8")
            write_manifest(child)
            self.child_run_hashes[scenario_id] = digest(child / "run.json")

        self.matrix = {
            "source_commit": self.source_commit,
            "matrix": list(retention.MATRIX),
            "product_version": "1.0.0-test",
            "fixture_version": "0.3.0-subghz-safe",
            "product_firmware_sha256": hashlib.sha256(
                self.product).hexdigest(),
            "fixture_firmware_sha256": hashlib.sha256(
                self.fixture).hexdigest(),
            "product_app_elf_sha256": "1" * 64,
            "fixture_app_elf_sha256": "2" * 64,
            "fixture_profile_sha256": hashlib.sha256(
                self.profile_bytes).hexdigest(),
            "fixture_id": "0000AABBCCDDEEFF",
            "expected_cid": "F" * 32,
            "candidate_port": "/dev/candidate",
            "fixture_port": "/dev/fixture",
            "build_artifacts": self.inventory,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git_blob(self, _commit: str, relative: str) -> bytes:
        return f"committed:{relative}".encode()

    def retain(self) -> dict[str, object]:
        with mock.patch.object(
                retention, "BUILD_ARTIFACTS", self.build_paths), \
                mock.patch.object(
                    retention, "verify_completed_matrix",
                    return_value=self.matrix), \
                mock.patch.object(
                    retention, "git_blob", side_effect=self.git_blob):
            return retention.retain_matrix(
                self.source, self.destination, self.summary_path,
                require_repository_paths=False)

    def verify(self) -> dict[str, object]:
        with mock.patch.object(
                retention, "BUILD_ARTIFACTS", self.build_paths), \
                mock.patch.object(
                    retention, "verify_completed_matrix",
                    return_value=self.matrix), \
                mock.patch.object(
                    retention, "git_blob", side_effect=self.git_blob):
            return retention.verify_retained_summary(
                self.summary_path, require_repository_bundle=False)

    def test_retains_one_build_set_and_four_compact_children(self) -> None:
        result = self.retain()
        self.assertEqual("pass", result["status"])
        for scenario_id in retention.MATRIX:
            child = self.destination / scenario_id
            self.assertTrue((child / "run.json").is_file())
            self.assertTrue((child / "frames" / "screen.png").is_file())
            self.assertFalse((child / "firmware.bin").exists())
            self.assertFalse((child / "fixture.bin").exists())
            self.assertFalse((child / "fixture-profile.json").exists())
            self.assertFalse((child / "frames" / "screen.rgb565").exists())
        for role, paths in self.build_paths.items():
            for name in paths:
                self.assertTrue(
                    (self.destination / "build" / role / name).is_file())
        self.assertEqual("pass", self.verify()["status"])

        # Git ignores opaque build products. Their manifest-bound absence is
        # accepted, while every tracked machine record remains mandatory.
        (self.destination / "build/product/firmware.bin").unlink()
        self.assertEqual("pass", self.verify()["status"])

        (self.destination / retention.MATRIX[0] /
         "frames/screen.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "artifact mismatch"):
            self.verify()

    def test_rejects_source_child_not_covered_by_its_manifest(self) -> None:
        child = self.source / retention.MATRIX[1]
        (child / "unindexed.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest coverage"):
            self.retain()
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.summary_path.exists())


if __name__ == "__main__":
    unittest.main()
