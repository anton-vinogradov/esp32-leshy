#!/usr/bin/env python3
"""Host tests for fail-closed pre-release evidence verification."""

from __future__ import annotations

import importlib.util
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Any


def load_module() -> Any:
    path = Path(__file__).with_name("verify_1x_prerelease_bundle.py")
    spec = importlib.util.spec_from_file_location("prerelease_bundle_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFIER = load_module()
VERSION = "1.0.0-rc.1"
RUN_ID = "0123456789abcdef0123456789abcdef"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def refresh_index(bundle: Path) -> None:
    lines = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name not in {
            "artifacts.sha256", "runner-result.json"
        }:
            relative = path.relative_to(bundle).as_posix()
            lines.append(f"{VERIFIER.sha256_file(path)}  {relative}")
    payload = "\n".join(lines) + "\n"
    (bundle / "artifacts.sha256").write_text(payload, encoding="utf-8")
    runner_result = VERIFIER.load_object(bundle / "runner-result.json")
    runner_result["bundle_sha256"] = VERIFIER.hashlib.sha256(
        payload.encode()
    ).hexdigest()
    write_json(bundle / "runner-result.json", runner_result)


def fixture(root: Path) -> tuple[Path, Path]:
    bundle = root / "bundle"
    bundle.mkdir()
    candidate = root / "firmware.bin"
    image = bytearray(288)
    image[0] = 0xE9
    struct.pack_into("<I", image, 32, 0xABCD5432)
    image[176:208] = bytes(range(32))
    candidate.write_bytes(image)
    embedded_candidate = bundle / "candidate" / "firmware.bin"
    embedded_candidate.parent.mkdir()
    shutil.copyfile(candidate, embedded_candidate)
    candidate_hash = VERIFIER.sha256_file(candidate)
    app_elf_sha = bytes(range(32)).hex()
    write_json(bundle / "candidate-manifest.json", {
        "schema": "leshy.prerelease.candidate.v2",
        "firmware": "candidate/firmware.bin",
        "firmware_sha256": candidate_hash, "app_elf_sha256": app_elf_sha,
        "flashed_by_runner": True, "run_id": RUN_ID,
    })
    write_json(bundle / "run.json", {
        "schema": "leshy.prerelease.run.v2", "passed": True,
        "gate_eligible": True, "suite_id": "device-smoke", "suite_revision": 1,
        "run_id": RUN_ID,
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": app_elf_sha,
        "boot": {"ready": {"version": VERSION,
                            "app_elf_sha256": app_elf_sha}},
        "hil_session": {
            "begin": {"status": "begun", "session_id": RUN_ID,
                      "active": True, "app_elf_sha256": app_elf_sha},
            "end": {"status": "ended", "session_id": RUN_ID,
                    "active": False, "app_elf_sha256": app_elf_sha},
        },
    })
    lines = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file():
            relative = path.relative_to(bundle).as_posix()
            lines.append(f"{VERIFIER.sha256_file(path)}  {relative}")
    index_payload = "\n".join(lines) + "\n"
    (bundle / "artifacts.sha256").write_text(index_payload, encoding="utf-8")
    write_json(bundle / "runner-result.json", {
        "schema": "leshy.prerelease.runner_result.v1",
        "candidate_sha256": candidate_hash, "suite_id": "device-smoke",
        "app_elf_sha256": app_elf_sha,
        "run_id": RUN_ID,
        "suite_revision": 1, "passed": True,
        "bundle_sha256": VERIFIER.hashlib.sha256(index_payload.encode()).hexdigest(),
        "trust_status": "unsigned_local_result",
    })
    return bundle, candidate


class BundleVerifierTests(unittest.TestCase):
    def verify(self, bundle: Path, candidate: Path, allow: bool = True) -> dict[str, Any]:
        return VERIFIER.verify_bundle(
            bundle, candidate, "device-smoke", 1, VERSION, allow)

    def test_development_bundle_is_verified_but_not_release_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            result = self.verify(bundle, candidate)
            self.assertTrue(result["verified"])
            self.assertTrue(result["development_verified"])
            self.assertFalse(result["release_eligible"])

    def test_unsigned_bundle_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            result = self.verify(bundle, candidate, allow=False)
            self.assertFalse(result["verified"])
            self.assertIn("unsigned local runner result is not accepted by itself",
                          result["failures"])

    def test_artifact_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            (bundle / "run.json").write_text("{}\n", encoding="utf-8")
            result = self.verify(bundle, candidate)
            self.assertFalse(result["verified"])
            self.assertIn("artifact hash mismatch: run.json", result["failures"])

    def test_different_candidate_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            candidate.write_bytes(b"different")
            result = self.verify(bundle, candidate)
            self.assertFalse(result["verified"])
            self.assertIn("candidate file does not match run", result["failures"])

    def test_mixed_hil_session_is_detected_even_with_rehashed_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            run = VERIFIER.load_object(bundle / "run.json")
            run["hil_session"]["end"]["session_id"] = (
                "fedcba9876543210fedcba9876543210"
            )
            write_json(bundle / "run.json", run)
            refresh_index(bundle)
            result = self.verify(bundle, candidate)
            self.assertFalse(result["verified"])
            self.assertIn("HIL session end binding mismatch", result["failures"])

    def test_local_result_can_never_claim_release_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            runner_result = VERIFIER.load_object(bundle / "runner-result.json")
            runner_result["gate_eligible"] = True
            write_json(bundle / "runner-result.json", runner_result)
            result = self.verify(bundle, candidate)
            self.assertTrue(result["verified"])
            self.assertFalse(result["release_eligible"])

    def test_ad_hoc_local_signature_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, candidate = fixture(Path(directory))
            runner_result = VERIFIER.load_object(bundle / "runner-result.json")
            runner_result["trust_status"] = "signed_ed25519"
            write_json(bundle / "runner-result.json", runner_result)
            result = self.verify(bundle, candidate)
            self.assertFalse(result["verified"])
            self.assertIn(
                "unsupported local-result trust status: 'signed_ed25519'",
                result["failures"],
            )


if __name__ == "__main__":
    unittest.main()
