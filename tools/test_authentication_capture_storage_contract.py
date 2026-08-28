#!/usr/bin/env python3
"""Adversarial tests for the authentication capture storage contract."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_authentication_capture_storage_contract.py"
SPEC = importlib.util.spec_from_file_location("auth_storage_contract",
                                              CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class AuthenticationCaptureStorageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codec_header = CHECKER.CODEC_HEADER.read_text(encoding="utf-8")
        cls.codec_source = CHECKER.CODEC_SOURCE.read_text(encoding="utf-8")
        cls.store_header = CHECKER.STORE_HEADER.read_text(encoding="utf-8")
        cls.store_source = CHECKER.STORE_SOURCE.read_text(encoding="utf-8")
        cls.host_test = CHECKER.HOST_TEST.read_text(encoding="utf-8")

    def failures(self, **changes: str) -> list[str]:
        return CHECKER.check_sources(
            changes.get("codec_header", self.codec_header),
            changes.get("codec_source", self.codec_source),
            changes.get("store_header", self.store_header),
            changes.get("store_source", self.store_source),
            changes.get("host_test", self.host_test),
        )

    def test_repository_contract_passes(self) -> None:
        self.assertEqual([], self.failures())

    def test_schema_four_removal_is_rejected(self) -> None:
        source = self.codec_source.replace(
            "schemaVersion != kWifiFrameSegmentSchemaVersion",
            "schemaVersion != 404", 1)
        self.assertNotEqual(source, self.codec_source)
        self.assertTrue(any("schema4/8" in item
                            for item in self.failures(codec_source=source)))

    def test_schema_eight_generic_open_removal_is_rejected(self) -> None:
        source = self.codec_source.replace(
            "(schemaVersion != kWifiFrameSegmentSchemaVersion &&\n"
            "         schemaVersion != "
            "kAuthenticationCaptureSegmentSchemaVersion)",
            "(schemaVersion != kWifiFrameSegmentSchemaVersion)", 1)
        self.assertNotEqual(source, self.codec_source)
        self.assertTrue(any("schema4/8" in item
                            for item in self.failures(codec_source=source)))

    def test_accounting_validation_removal_is_rejected(self) -> None:
        source = self.codec_source.replace(
            "accounted != provenance.framesReported",
            "false", 1)
        self.assertNotEqual(source, self.codec_source)
        self.assertTrue(any("framesReported" in item
                            for item in self.failures(codec_source=source)))

    def test_known_empty_ssid_acceptance_is_rejected(self) -> None:
        source = self.codec_source.replace(
            "(provenance.ssidKnown && provenance.ssidLength == 0) ||", "", 1)
        self.assertNotEqual(source, self.codec_source)
        self.assertTrue(any("ssidKnown" in item
                            for item in self.failures(codec_source=source)))

    def test_parallel_backend_is_rejected(self) -> None:
        source = self.store_source + "\nclass StoreCommitBackend {};\n"
        self.assertTrue(any("parallel" in item
                            for item in self.failures(store_source=source)))

    def test_platform_dependency_is_rejected(self) -> None:
        source = '#include "platform/arduino/ArduinoEntry.h"\n' + \
            self.store_source
        self.assertTrue(any("platform" in item
                            for item in self.failures(store_source=source)))

    def test_dynamic_allocation_is_rejected(self) -> None:
        source = self.codec_source + "\nauto leaked = new int;\n"
        self.assertTrue(any("dynamic allocation" in item
                            for item in self.failures(codec_source=source)))


if __name__ == "__main__":
    unittest.main()
