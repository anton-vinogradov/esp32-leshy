#!/usr/bin/env python3

from __future__ import annotations

import unittest
import json
import shutil
import tempfile
from pathlib import Path

import check_wifi_authentication_persistence_hil_run as checker


ROOT = Path(__file__).resolve().parents[1]
POSITIVE, EXPECTATIONS = checker.evidence_paths("1.0.0-dev.255")


class WifiAuthenticationPersistenceHilEvidenceTests(unittest.TestCase):
    def test_retained_evidence_is_machine_checked(self) -> None:
        self.assertEqual(checker.check(EXPECTATIONS, POSITIVE), [])

    def test_private_identifiers_fail_closed(self) -> None:
        failures: list[str] = []
        checker.verify_private_absent(failures, {
            "safe": {"ssid": "must-not-be-retained"},
            "also_unsafe": "02:11:22:33:44:55",
        })
        self.assertEqual(len(failures), 2)

    def test_missing_retained_artifacts_fail_closed_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            bundle.mkdir()
            expectations = root / "expectations.json"
            shutil.copy2(EXPECTATIONS, expectations)
            marker = json.loads(expectations.read_text(encoding="utf-8"))
            marker["checker_source_sha256"] = checker.digest(checker.CHECKER)
            expectations.write_text(json.dumps(marker), encoding="utf-8")
            (bundle / "artifacts.sha256").write_text(
                marker["firmware_sha256"] + "  firmware.bin\n" +
                marker["positive_run_sha256"] + "  run.json\n",
                encoding="utf-8")
            failures = checker.check(expectations, bundle)
            self.assertTrue(failures)
            self.assertTrue(any("missing" in failure or
                                "mismatch" in failure
                                for failure in failures))


if __name__ == "__main__":
    unittest.main()
