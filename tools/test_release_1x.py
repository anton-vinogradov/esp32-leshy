#!/usr/bin/env python3
"""Host contracts for the one-command 1.x release gate."""

from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any


def load_module() -> Any:
    path = Path(__file__).with_name("release_1x.py")
    spec = importlib.util.spec_from_file_location("release_1x", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RELEASE = load_module()


class ReleaseOneContracts(unittest.TestCase):
    def test_semver_and_stable_release_contract(self) -> None:
        self.assertEqual(RELEASE.parse_semver("1.2.3")[:3], (1, 2, 3))
        self.assertEqual(
            RELEASE.parse_semver("0.37.0-prerelease-test+board.1")[3:],
            ("prerelease-test", "board.1"),
        )
        for invalid in ("v1.2.3", "1.2", "01.2.3", "1.02.3", "1.2.3-"):
            with self.subTest(invalid=invalid), self.assertRaises(RELEASE.ReleaseError):
                RELEASE.parse_semver(invalid)
        RELEASE.require_stable_release_version("1.2.3")
        for non_release in ("0.9.9", "1.2.3-rc.1", "1.2.3+rebuilt"):
            with self.subTest(non_release=non_release), self.assertRaises(
                RELEASE.ReleaseError
            ):
                RELEASE.require_stable_release_version(non_release)

    def test_run_title_binds_version_and_unique_invocation(self) -> None:
        self.assertEqual(
            RELEASE.parse_run_title("prerelease-hil / 1.4.0 / 20260817T120000Z-deadbeef"),
            ("1.4.0", "20260817T120000Z-deadbeef"),
        )
        for invalid in (
            "release / 1.4.0 / request",
            "prerelease-hil / v1.4.0 / request",
            "prerelease-hil / 1.4.0",
            "prerelease-hil / 1.4.0 / request / extra",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(RELEASE.ReleaseError):
                RELEASE.parse_run_title(invalid)

    def test_candidate_set_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in RELEASE.CANDIDATE_FILES:
                (root / name).write_bytes(name.encode("ascii"))
            self.assertEqual(
                {path.name for path in RELEASE.verify_downloaded_candidate(root)},
                RELEASE.CANDIDATE_FILES,
            )
            (root / "unattested.bin").write_bytes(b"extra")
            with self.assertRaisesRegex(RELEASE.ReleaseError, "unexpected candidate"):
                RELEASE.verify_downloaded_candidate(root)

    def test_explicit_serial_port_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            port = Path(directory) / "cu.usbmodem-test"
            port.touch()
            self.assertEqual(RELEASE.discover_serial_port(str(port)), str(port))
            with self.assertRaisesRegex(RELEASE.ReleaseError, "does not exist"):
                RELEASE.discover_serial_port(str(port) + "-missing")

    def test_tar_extraction_rejects_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "malicious.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                member = tarfile.TarInfo("../escaped")
                payload = b"nope"
                member.size = len(payload)
                output.addfile(member, io.BytesIO(payload))
            destination = root / "extract"
            destination.mkdir()
            with self.assertRaisesRegex(RELEASE.ReleaseError, "unsafe archive"):
                RELEASE.safe_extract_tar(archive, destination)
            self.assertFalse((root / "escaped").exists())

    def test_tar_extraction_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "link.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                member = tarfile.TarInfo("link")
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/outside"
                output.addfile(member)
            destination = root / "extract"
            destination.mkdir()
            with self.assertRaisesRegex(RELEASE.ReleaseError, "unsupported archive"):
                RELEASE.safe_extract_tar(archive, destination)

    def test_workflow_and_legacy_release_ownership_are_explicit(self) -> None:
        workflow = (RELEASE.ROOT / ".github/workflows/prerelease-hil.yml").read_text(
            encoding="utf-8"
        )
        legacy = (RELEASE.ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        legacy_script = (RELEASE.ROOT / "tools/release.sh").read_text(encoding="utf-8")
        self.assertIn("run-name: prerelease-hil / ${{ inputs.version }}", workflow)
        self.assertIn("request_id:", workflow)
        self.assertIn("hil_port:", workflow)
        self.assertIn("runner_label:", workflow)
        self.assertIn("leshy-request-", workflow)
        self.assertIn("firmware.factory.bin", workflow)
        self.assertIn("tags: ['v0.*']", legacy)
        self.assertIn("git tag -l 'v0.*'", legacy_script)
        self.assertIn("tools/release_1x.py for 1.x", legacy_script)


if __name__ == "__main__":
    unittest.main()
