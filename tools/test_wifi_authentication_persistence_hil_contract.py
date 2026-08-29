#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_wifi_authentication_persistence_hil_contract.py"
SPEC = importlib.util.spec_from_file_location("persistence_contract", CHECKER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WifiAuthenticationPersistenceHilContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entry = MODULE.ENTRY.read_text(encoding="utf-8")
        cls.fixture_h = MODULE.FIXTURE_H.read_text(encoding="utf-8")
        cls.fixture_cpp = MODULE.FIXTURE_CPP.read_text(encoding="utf-8")

    def failures(self, *, entry: str | None = None,
                 fixture_h: str | None = None,
                 fixture_cpp: str | None = None) -> list[str]:
        return MODULE.contract_failures(
            self.entry if entry is None else entry,
            self.fixture_h if fixture_h is None else fixture_h,
            self.fixture_cpp if fixture_cpp is None else fixture_cpp,
        )

    def mutate_once(self, source: str, old: str, new: str) -> str:
        self.assertIn(old, source)
        return source.replace(old, new, 1)

    def test_current_contract_passes(self) -> None:
        self.assertEqual(self.failures(), [])

    def test_each_fixture_safety_gate_is_required(self) -> None:
        for marker in (
            "if (!context.hilActive)",
            "if (loaded_)",
            "!context.authenticationViewActive",
            "!context.resultActive",
            "!context.cleanupComplete",
            "!context.captureInactive",
            "!context.foregroundWifiOwnsRf",
        ):
            with self.subTest(marker=marker):
                mutated = self.mutate_once(self.fixture_cpp, marker, "false")
                self.assertTrue(self.failures(fixture_cpp=mutated))

    def test_fixture_cannot_touch_radio_or_storage(self) -> None:
        for call in (
            "esp_wifi_start();", "client.connect();", "rawTx();",
            "SD.begin();",
        ):
            with self.subTest(call=call):
                mutated = self.fixture_cpp + f"\nvoid forbidden() {{{call}}}\n"
                self.assertTrue(self.failures(fixture_cpp=mutated))

    def test_generic_synthetic_report_cannot_be_saved(self) -> None:
        mutated = self.mutate_once(
            self.entry,
            "(wifiAuthenticationSynthetic && "
            "!wifiAuthenticationPersistenceHil)",
            "false",
        )
        self.assertTrue(self.failures(entry=mutated))

    def test_save_dialog_declares_authentication_store_kind(self) -> None:
        action = MODULE.cpp_function(self.entry, "applyUiAction")
        self.assertIsNotNone(action)
        assert action is not None
        changed = self.mutate_once(
            action,
            "wifiCaptureStoreKind =\n"
            "                            WifiCaptureStoreKind::Authentication;",
            "wifiCaptureStoreKind = WifiCaptureStoreKind::Generic;",
        )
        mutated = self.mutate_once(self.entry, action, changed)
        self.assertTrue(self.failures(entry=mutated))

    def test_command_ack_must_not_claim_rf_or_tx(self) -> None:
        for old, new in (
            (r'\"rf_hardware_touched\":false',
             r'\"rf_hardware_touched\":true'),
            (r'\"radio_started\":false', r'\"radio_started\":true'),
            (r'\"connect_calls\":0', r'\"connect_calls\":1'),
            (r'\"raw_tx_calls\":0', r'\"raw_tx_calls\":1'),
        ):
            with self.subTest(field=old):
                function = MODULE.cpp_function(
                    self.entry,
                    "emitWifiAuthenticationPersistenceHilFixture",
                )
                self.assertIsNotNone(function)
                assert function is not None
                changed = self.mutate_once(function, old, new)
                mutated = self.mutate_once(self.entry, function, changed)
                self.assertTrue(self.failures(entry=mutated))


if __name__ == "__main__":
    unittest.main()
