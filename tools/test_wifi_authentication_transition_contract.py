#!/usr/bin/env python3
"""Adversarial tests for the CAP-049 transition contract checker."""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_wifi_authentication_transition_contract.py"
SPEC = importlib.util.spec_from_file_location("transition_contract", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class WifiAuthenticationTransitionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entry = CHECKER.ARDUINO_ENTRY.read_text(encoding="utf-8")
        cls.capture_header = CHECKER.CAPTURE_HEADER.read_text(encoding="utf-8")
        cls.capture_source = CHECKER.CAPTURE_SOURCE.read_text(encoding="utf-8")
        cls.scanner_source = CHECKER.SCANNER_SOURCE.read_text(encoding="utf-8")
        cls.profile = CHECKER.INIT_PROFILE.read_text(encoding="utf-8")
        cls.runner = CHECKER.RUNNER.read_text(encoding="utf-8")

    def failures(self, **changes: str) -> list[str]:
        return CHECKER.check_sources(
            changes.get("entry", self.entry),
            changes.get("capture_header", self.capture_header),
            changes.get("capture_source", self.capture_source),
            changes.get("scanner_source", self.scanner_source),
            changes.get("profile", self.profile),
            changes.get("runner", self.runner),
        )

    def test_repository_contract_passes(self) -> None:
        self.assertEqual([], self.failures())

    def test_sdk_default_config_bypass_is_rejected(self) -> None:
        scanner = self.scanner_source.replace(
            "makeBoardWifiPassiveOnlyInitConfig()",
            "WIFI_INIT_CONFIG_DEFAULT()", 1)
        failures = self.failures(scanner_source=scanner)
        self.assertTrue(any("SDK defaults" in item for item in failures))

    def test_oversized_passive_buffer_profile_is_rejected(self) -> None:
        profile = self.profile.replace(
            "kDynamicRxBuffers = 8", "kDynamicRxBuffers = 80", 1)
        self.assertNotEqual(profile, self.profile)
        failures = self.failures(profile=profile)
        self.assertTrue(any("kDynamicRxBuffers=8;" in item
                            for item in failures))

    def test_missing_retained_adapter_diagnostic_is_rejected(self) -> None:
        entry = self.entry.replace("adapter_failure_stage", "failure_stage", 1)
        failures = self.failures(entry=entry)
        self.assertTrue(any("adapter_failure_stage" in item
                            for item in failures))

    def test_hold_without_active_hil_session_is_rejected(self) -> None:
        block = CHECKER.braced_block(
            CHECKER.compact(self.entry),
            "voidemitWifiAuthenticationHilHold(")
        self.assertIn("hilSession.active()", block)
        entry = self.entry.replace("hilSession.active()", "true")
        failures = self.failures(entry=entry)
        self.assertTrue(any("outside an active session" in item
                            for item in failures))

    def test_unbounded_hold_is_rejected(self) -> None:
        entry, replacements = re.subn(
            r"(kWifiAuthentication[A-Za-z0-9_]*Hold[A-Za-z0-9_]*"
            r"TimeoutMs\s*=\s*)\d+U",
            r"\g<1>6001U", self.entry, count=1)
        self.assertEqual(1, replacements)
        failures = self.failures(entry=entry)
        self.assertTrue(any("exceeds" in item for item in failures))

    def test_rearming_an_active_hold_is_rejected(self) -> None:
        entry = self.entry.replace(
            "if (safeState && !replayed)", "if (safeState)", 1)
        self.assertNotEqual(entry, self.entry)
        failures = self.failures(entry=entry)
        self.assertTrue(any("extend" in item for item in failures))

    def test_hold_leaking_into_rf_adapter_is_rejected(self) -> None:
        capture_source = self.capture_source + "\nbool surveyTerminalHold = true;\n"
        failures = self.failures(capture_source=capture_source)
        self.assertTrue(any("RF adapter" in item for item in failures))

    def test_missing_hil_end_clear_is_rejected(self) -> None:
        end = self.entry.find("void emitHilSessionEnd(")
        self.assertGreaterEqual(end, 0)
        close = self.entry.find("\n}\n", end)
        self.assertGreater(close, end)
        block = self.entry[end:close]
        changed = re.sub(
            r"clearWifiAuthentication[A-Za-z0-9_]*Hold[A-Za-z0-9_]*\(\);",
            "/* missing transition-hold clear */", block)
        self.assertNotEqual(block, changed)
        entry = self.entry[:end] + changed + self.entry[close:]
        failures = self.failures(entry=entry)
        self.assertTrue(any("hil.end" in item for item in failures))

    def test_missing_timeout_clear_is_rejected(self) -> None:
        old = (
            "if (nowUs >= wifiAuthenticationSurveyTerminalHoldDeadlineUs) {\n"
            "        clearWifiAuthenticationSurveyTerminalHold();\n"
            "    }")
        new = (
            "if (nowUs >= wifiAuthenticationSurveyTerminalHoldDeadlineUs) {\n"
            "        /* stale hold */\n"
            "    }")
        entry = self.entry.replace(old, new, 1)
        self.assertNotEqual(entry, self.entry)
        failures = self.failures(entry=entry)
        self.assertTrue(any("timeout" in item for item in failures))

    def test_stable_waiting_query_before_back_is_rejected(self) -> None:
        marker = 'cancel_back_ui = action(device, "left")'
        self.assertIn(marker, self.runner)
        runner = self.runner.replace(
            marker,
            'require_exact(auth_state(device), {"state": '
            '"waiting_for_survey_stop"}, "stale")\n                ' + marker,
            1)
        failures = self.failures(runner=runner)
        self.assertTrue(any("stable transitional" in item
                            for item in failures))

    def test_stable_waiting_query_before_running_is_rejected(self) -> None:
        marker = "auth_running = wait_auth_state("
        self.assertIn(marker, self.runner)
        runner = self.runner.replace(
            marker,
            'require_exact(auth_requested, {"state": '
            '"waiting_for_survey_stop"}, "stale")\n                    ' +
            marker,
            1)
        failures = self.failures(runner=runner)
        self.assertTrue(any("stable waiting" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
