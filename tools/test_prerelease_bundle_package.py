#!/usr/bin/env python3
"""Host tests for deterministic pre-release evidence packaging."""

from __future__ import annotations

import importlib.util
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any


def load_module() -> Any:
    path = Path(__file__).with_name("package_1x_prerelease_bundle.py")
    spec = importlib.util.spec_from_file_location("prerelease_bundle_package", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PACKAGE = load_module()


class BundlePackageTests(unittest.TestCase):
    def test_archive_is_deterministic_and_rooted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            (bundle / "nested").mkdir(parents=True)
            (bundle / "run.json").write_text("{}\n", encoding="utf-8")
            (bundle / "nested" / "frame.raw").write_bytes(b"pixels")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            first_result = PACKAGE.package_bundle(bundle, first)
            second_result = PACKAGE.package_bundle(bundle, second)

            self.assertEqual(first_result["sha256"], second_result["sha256"])
            with tarfile.open(first, "r:gz") as archive:
                self.assertEqual(
                    archive.getnames(),
                    ["hil-bundle/nested/frame.raw", "hil-bundle/run.json"],
                )

    def test_refuses_output_inside_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            bundle.mkdir()
            (bundle / "run.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                PACKAGE.package_bundle(bundle, bundle / "evidence.tar.gz")


if __name__ == "__main__":
    unittest.main()
