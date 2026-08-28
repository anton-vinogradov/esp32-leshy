#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def load(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ACCEPTANCE = load(
    "check_wifi_authentication_capture_hil_acceptance",
    "check_wifi_authentication_capture_hil_acceptance.py")
RETENTION = load(
    "retain_1x_wifi_authentication_capture_hil",
    "retain_1x_wifi_authentication_capture_hil.py")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class WifiAuthenticationCaptureRetentionTests(unittest.TestCase):
    source_commit = "1" * 40
    app = "2" * 64
    run_id = "3" * 32

    def make_bundle(self, parent: Path) -> tuple[Path, dict[str, str]]:
        bundle = parent / "source"
        bundle.mkdir()
        firmware = b"synthetic ESP image used only under mocked parser"
        firmware_sha = sha(firmware)
        runner_sha = RETENTION.digest(RETENTION.CURRENT_RUNNER)
        run = {
            "schema": ACCEPTANCE.RUN_SCHEMA,
            "run_id": self.run_id,
            "runner_source_sha256": runner_sha,
            "passed": True,
            "gate_eligible": True,
            "failures": [],
            "expected_cid": ACCEPTANCE.CID,
            "candidate": {
                "version": ACCEPTANCE.VERSION,
                "source_commit": self.source_commit,
                "firmware_sha256": firmware_sha,
                "app_elf_sha256": self.app,
                "flashed": True,
                "flash_completed": False,
                "exact_boot_verified": True,
                "flash_mode": "reuse_exact",
            },
        }
        (bundle / "firmware.bin").write_bytes(firmware)
        (bundle / "run.json").write_text(
            json.dumps(run, sort_keys=True) + "\n", encoding="utf-8")
        lines = []
        for name in ("firmware.bin", "run.json"):
            lines.append(f"{RETENTION.digest(bundle / name)}  {name}")
        (bundle / "artifacts.sha256").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        return bundle, {
            "version": ACCEPTANCE.VERSION,
            "cid": ACCEPTANCE.CID,
            "source": self.source_commit,
            "firmware": firmware_sha,
            "app": self.app,
            "runner": runner_sha,
        }

    def acceptance_args(self, bundle: Path, marker: Path,
                        expected: dict[str, str]) -> Any:
        return ACCEPTANCE.parse_args([
            "--positive", str(bundle),
            "--expectations", str(marker),
            "--expected-version", expected["version"],
            "--expected-cid", expected["cid"],
            "--expected-source-commit", expected["source"],
            "--expected-firmware-sha256", expected["firmware"],
            "--expected-app-elf-sha256", expected["app"],
            "--expected-runner-sha256", expected["runner"],
        ])

    def marker(self, bundle: Path, expected: dict[str, str]) -> dict[str, str]:
        return {
            "schema": ACCEPTANCE.EXPECTATIONS_SCHEMA,
            "version": expected["version"],
            "expected_cid": expected["cid"],
            "run_id": self.run_id,
            "source_commit": expected["source"],
            "firmware_sha256": expected["firmware"],
            "app_elf_sha256": expected["app"],
            "runner_source_sha256": expected["runner"],
            "positive_run_sha256": RETENTION.digest(bundle / "run.json"),
            "positive_artifact_index_sha256": RETENTION.digest(
                bundle / "artifacts.sha256"),
        }

    def rewrite_run(self, bundle: Path, run: dict[str, Any]) -> None:
        (bundle / "run.json").write_text(
            json.dumps(run, sort_keys=True) + "\n", encoding="utf-8")
        self.rebuild_manifest(bundle)

    def rebuild_manifest(self, bundle: Path) -> None:
        lines = []
        for path in sorted(bundle.rglob("*")):
            if path.is_file() and path.name != "artifacts.sha256":
                name = path.relative_to(bundle).as_posix()
                lines.append(f"{RETENTION.digest(path)}  {name}")
        (bundle / "artifacts.sha256").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def retain_args(self, bundle: Path, parent: Path,
                    expected: dict[str, str]) -> Any:
        return RETENTION.parse_args([
            "--positive", str(bundle),
            "--expected-version", expected["version"],
            "--expected-cid", expected["cid"],
            "--expected-source-commit", expected["source"],
            "--expected-firmware-sha256", expected["firmware"],
            "--expected-app-elf-sha256", expected["app"],
            "--expected-runner-sha256", expected["runner"],
            "--destination", str(parent / "retained"),
            "--expectations", str(parent / "acceptance.json"),
        ])

    def test_acceptance_recomputes_pins_and_invokes_semantic_checker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            marker = parent / "pins.json"
            marker.write_text(
                json.dumps(self.marker(bundle, expected)) + "\n",
                encoding="utf-8")
            args = self.acceptance_args(bundle, marker, expected)
            with patch.object(ACCEPTANCE, "app_elf_sha256",
                              return_value=expected["app"]), \
                    patch.object(ACCEPTANCE, "run_semantic_checker",
                                 return_value=[]) as semantic:
                self.assertEqual([], ACCEPTANCE.check(args))
                semantic.assert_called_once()

            (bundle / "run.json").write_text("{}\n", encoding="utf-8")
            with patch.object(ACCEPTANCE, "app_elf_sha256",
                              return_value=expected["app"]), \
                    patch.object(ACCEPTANCE, "run_semantic_checker",
                                 return_value=[]):
                failures = ACCEPTANCE.check(args)
            self.assertTrue(any("pin mismatch" in failure or
                                "artifact hash mismatch" in failure
                                for failure in failures))

    def test_acceptance_rejects_mismatched_marker_and_semantic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            marker = parent / "pins.json"
            value = self.marker(bundle, expected)
            value["source_commit"] = "4" * 40
            marker.write_text(json.dumps(value) + "\n", encoding="utf-8")
            args = self.acceptance_args(bundle, marker, expected)
            self.assertTrue(any("exact pin mismatch" in failure
                                for failure in ACCEPTANCE.check(args)))

            value["source_commit"] = expected["source"]
            marker.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with patch.object(ACCEPTANCE, "app_elf_sha256",
                              return_value=expected["app"]), \
                    patch.object(ACCEPTANCE, "run_semantic_checker",
                                 return_value=["semantic rejection"]):
                failures = ACCEPTANCE.check(args)
            self.assertIn("semantic rejection", failures)

    def test_acceptance_rejects_symlink_trust_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            marker = parent / "pins.json"
            marker.write_text(
                json.dumps(self.marker(bundle, expected)) + "\n",
                encoding="utf-8")

            bundle_link = parent / "bundle-link"
            bundle_link.symlink_to(bundle, target_is_directory=True)
            bundle_failures = ACCEPTANCE.check(
                self.acceptance_args(bundle_link, marker, expected))
            self.assertTrue(any(
                "regular bundle directory required" in failure
                for failure in bundle_failures))

            marker_link = parent / "pins-link.json"
            marker_link.symlink_to(marker)
            marker_failures = ACCEPTANCE.check(
                self.acceptance_args(bundle, marker_link, expected))
            self.assertIn(
                "expectations: regular JSON file required", marker_failures)

    def test_retention_stages_bundle_and_exact_acceptance_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            args = self.retain_args(bundle, parent, expected)
            with patch.object(ACCEPTANCE, "app_elf_sha256",
                              return_value=expected["app"]), \
                    patch.object(ACCEPTANCE, "run_semantic_checker",
                                 return_value=[]):
                result = RETENTION.retain(args)
            destination = parent / "retained"
            marker = parent / "acceptance.json"
            self.assertEqual("retained", result["status"])
            self.assertTrue(destination.is_dir())
            self.assertEqual(self.marker(destination, expected),
                             json.loads(marker.read_text(encoding="utf-8")))
            self.assertEqual(
                (bundle / "run.json").read_bytes(),
                (destination / "run.json").read_bytes())

    def test_retention_rejects_tamper_without_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            args = self.retain_args(bundle, parent, expected)
            (bundle / "firmware.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "manifest rejected"):
                RETENTION.retain(args)
            self.assertFalse((parent / "retained").exists())
            self.assertFalse((parent / "acceptance.json").exists())

    def test_retention_rejects_private_target_identifiers(self) -> None:
        for leak in (
                {"target_bssid": "00:11:22:33:44:55"},
                {"identity_hash": 0x12345678},
                {"innocent_name": "00:11:22:33:44:55"}):
            with self.subTest(leak=leak), \
                    tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary)
                bundle, expected = self.make_bundle(parent)
                run = json.loads(
                    (bundle / "run.json").read_text(encoding="utf-8"))
                run["privacy_probe"] = leak
                self.rewrite_run(bundle, run)
                args = self.retain_args(bundle, parent, expected)
                with self.assertRaisesRegex(
                        ValueError, "private target evidence rejected"):
                    RETENTION.retain(args)
                self.assertFalse((parent / "retained").exists())
                self.assertFalse((parent / "acceptance.json").exists())

    def test_acceptance_and_retention_reject_private_frame_json(self) -> None:
        for leak in (
                {"state": {"SSID": "private-network"}},
                {"frame_begin": {"value": "00:11:22:33:44:55"}}):
            with self.subTest(leak=leak), \
                    tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary)
                bundle, expected = self.make_bundle(parent)
                frames = bundle / "frames"
                frames.mkdir()
                (frames / "wifi-auth-result.json").write_text(
                    json.dumps(leak, sort_keys=True) + "\n",
                    encoding="utf-8")
                self.rebuild_manifest(bundle)
                marker = parent / "pins.json"
                marker.write_text(
                    json.dumps(self.marker(bundle, expected)) + "\n",
                    encoding="utf-8")
                failures = ACCEPTANCE.check(
                    self.acceptance_args(bundle, marker, expected))
                self.assertTrue(any(
                    "frames/wifi-auth-result.json" in failure and
                    ("private target" in failure or "MAC-like" in failure)
                    for failure in failures))
                args = self.retain_args(bundle, parent, expected)
                with self.assertRaisesRegex(
                        ValueError, "private target evidence rejected"):
                    RETENTION.retain(args)
                self.assertFalse((parent / "retained").exists())
                self.assertFalse((parent / "acceptance.json").exists())

    def test_retention_rejects_semantic_failure_and_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            bundle, expected = self.make_bundle(parent)
            args = self.retain_args(bundle, parent, expected)
            with patch.object(ACCEPTANCE, "app_elf_sha256",
                              return_value=expected["app"]), \
                    patch.object(ACCEPTANCE, "run_semantic_checker",
                                 return_value=["semantic rejection"]):
                with self.assertRaisesRegex(ValueError,
                                            "staged acceptance failed"):
                    RETENTION.retain(args)
            self.assertFalse((parent / "retained").exists())
            self.assertFalse((parent / "acceptance.json").exists())
            (parent / "retained").mkdir()
            with self.assertRaisesRegex(ValueError,
                                        "destination already exists"):
                RETENTION.retain(args)


if __name__ == "__main__":
    unittest.main()
