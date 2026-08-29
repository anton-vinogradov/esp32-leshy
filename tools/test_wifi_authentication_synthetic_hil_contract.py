#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_wifi_authentication_synthetic_hil_contract.py"
SPEC = importlib.util.spec_from_file_location("synthetic_contract", CHECKER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WifiAuthenticationSyntheticHilContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entry = MODULE.ENTRY.read_text(encoding="utf-8")
        cls.fixture_h = MODULE.FIXTURE_H.read_text(encoding="utf-8")
        cls.fixture_cpp = MODULE.FIXTURE_CPP.read_text(encoding="utf-8")
        cls.presenter_h = MODULE.PRESENTER_H.read_text(encoding="utf-8")
        cls.presenter_cpp = MODULE.PRESENTER_CPP.read_text(encoding="utf-8")
        cls.hil_runner = MODULE.HIL_RUNNER.read_text(encoding="utf-8")
        cls.hil_run_checker = MODULE.HIL_RUN_CHECKER.read_text(
            encoding="utf-8")

    def failures(self, *, entry: str | None = None,
                 fixture_h: str | None = None,
                 fixture_cpp: str | None = None,
                 presenter_h: str | None = None,
                 presenter_cpp: str | None = None,
                 hil_runner: str | None = None,
                 hil_run_checker: str | None = None) -> list[str]:
        return MODULE.contract_failures(
            self.entry if entry is None else entry,
            self.fixture_h if fixture_h is None else fixture_h,
            self.fixture_cpp if fixture_cpp is None else fixture_cpp,
            self.presenter_h if presenter_h is None else presenter_h,
            self.presenter_cpp if presenter_cpp is None else presenter_cpp,
            self.hil_runner if hil_runner is None else hil_runner,
            self.hil_run_checker if hil_run_checker is None
            else hil_run_checker,
        )

    def replace_once(self, source: str, old: str, new: str) -> str:
        self.assertIn(old, source, f"mutation precondition missing: {old}")
        return source.replace(old, new, 1)

    def mutate_function(self, entry: str, function_name: str,
                        old: str, new: str) -> str:
        function = MODULE.cpp_function(entry, function_name)
        self.assertIsNotNone(function)
        assert function is not None
        mutated = self.replace_once(function, old, new)
        return self.replace_once(entry, function, mutated)

    def inject_function_code(self, entry: str, function_name: str,
                             statement: str) -> str:
        function = MODULE.cpp_function(entry, function_name)
        self.assertIsNotNone(function)
        assert function is not None
        mutated = function[:-1] + f"\n    {statement}\n}}"
        return self.replace_once(entry, function, mutated)

    def assert_failure(self, expected: str, **sources: str) -> None:
        failures = self.failures(**sources)
        self.assertTrue(
            any(expected in failure for failure in failures),
            f"expected {expected!r} in {failures!r}",
        )

    def test_current_contract_passes(self) -> None:
        self.assertEqual(self.failures(), [])

    def test_missing_hil_gate_fails_closed(self) -> None:
        mutated = self.mutate_function(
            self.entry,
            "emitWifiAuthenticationSyntheticHilReport",
            "        hilSession.active(),",
            "        true,",
        )
        self.assert_failure("active HIL gate", entry=mutated)

    def test_every_wrapper_safe_state_input_is_required(self) -> None:
        cases = (
            ("wifiProductView == WifiProductView::AuthenticationCapture,",
             "true,", "view"),
            ("wifiAuthenticationProductState ==\n"
             "            WifiAuthenticationProductState::Result,",
             "true,", "result"),
            ("wifiFrameCapture.cleanupComplete() && ingress.cleanupComplete",
             "true", "cleanup"),
            ("        !ingress.active,\n"
             "        resourceBroker.ownerOf(Resource::EspRf)",
             "        true,\n"
             "        resourceBroker.ownerOf(Resource::EspRf)",
             "capture inactive"),
            ("resourceBroker.ownerOf(Resource::EspRf) ==\n"
             "                AppRuntime::kForegroundOwner",
             "true", "RF ownership"),
            ("        wifiAuthenticationTarget.channel,",
             "        0U,", "target channel"),
        )
        for old, new, name in cases:
            with self.subTest(gate=name):
                mutated = self.mutate_function(
                    self.entry,
                    "emitWifiAuthenticationSyntheticHilReport",
                    old,
                    new,
                )
                self.assert_failure("exact synthetic safe-state context",
                                    entry=mutated)

    def test_every_fixture_gate_is_required(self) -> None:
        cases = (
            ("if (!context.hilActive)", "if (false)", "HIL"),
            ("if (loaded_)", "if (false)", "one-shot"),
            ("!context.authenticationViewActive",
             "false", "authentication view"),
            ("!context.resultActive", "false", "result"),
            ("!context.cleanupComplete", "false", "cleanup"),
            ("!context.captureInactive", "false", "capture inactive"),
            ("!context.foregroundWifiOwnsRf", "false", "RF ownership"),
        )
        for old, new, name in cases:
            with self.subTest(gate=name):
                mutated = self.replace_once(self.fixture_cpp, old, new)
                self.assertTrue(self.failures(fixture_cpp=mutated))

    def test_forbidden_apis_in_wrapper_are_rejected(self) -> None:
        cases = {
            "ESP Wi-Fi driver": "esp_wifi_start();",
            "connection": "client.connect();",
            "raw/transmit": "rawTx();",
            "filesystem object": "LittleFS.begin();",
        }
        for expected, statement in cases.items():
            with self.subTest(api=expected):
                mutated = self.inject_function_code(
                    self.entry,
                    "emitWifiAuthenticationSyntheticHilReport",
                    statement,
                )
                self.assert_failure(
                    f"wrapper touches forbidden API: {expected}",
                    entry=mutated,
                )

    def test_forbidden_apis_in_reachable_fixture_are_rejected(self) -> None:
        cases = {
            "ESP Wi-Fi driver": "void bad_rf() { esp_wifi_start(); }",
            "connection": "void bad_connect() { client.connect(); }",
            "raw/transmit": "void bad_tx() { sendPacket(); }",
            "filesystem object": "void bad_storage() { SD.begin(); }",
        }
        for expected, addition in cases.items():
            with self.subTest(api=expected):
                mutated = self.fixture_cpp + f"\n{addition}\n"
                self.assert_failure(
                    f"fixture touches forbidden API: {expected}",
                    fixture_cpp=mutated,
                )

    def test_forbidden_words_in_comments_and_literals_are_ignored(self) -> None:
        mutated = (
            self.fixture_cpp +
            '\n// esp_wifi_start(); LittleFS.begin(); rawTx();\n'
            'constexpr const char* kAuditWords = "connect() SD.begin()";\n'
        )
        self.assertEqual(self.failures(fixture_cpp=mutated), [])

    def test_separate_synthetic_globals_are_required(self) -> None:
        cases = {
            "report": (
                f"WifiAuthenticationCaptureReport "
                f"{MODULE.SYNTHETIC_REPORT}",
                "WifiAuthenticationCaptureReport removedSyntheticReport",
                "separate synthetic report global",
            ),
            "controller": (
                f"WifiAuthenticationCaptureController "
                f"{MODULE.SYNTHETIC_CONTROLLER}",
                "WifiAuthenticationCaptureController "
                "removedSyntheticController",
                "separate synthetic controller global",
            ),
        }
        for name, (old, new, expected) in cases.items():
            with self.subTest(global_name=name):
                mutated = self.replace_once(self.entry, old, new)
                self.assert_failure(expected, entry=mutated)

    def test_wrapper_must_not_load_fixture_into_production_state(self) -> None:
        function = MODULE.cpp_function(
            self.entry, "emitWifiAuthenticationSyntheticHilReport")
        self.assertIsNotNone(function)
        assert function is not None
        mutated_function = function.replace(
            f"&{MODULE.SYNTHETIC_REPORT}",
            f"&{MODULE.PRODUCTION_REPORT}",
            1,
        ).replace(
            f"&{MODULE.SYNTHETIC_CONTROLLER}",
            f"&{MODULE.PRODUCTION_CONTROLLER}",
            1,
        )
        self.assertNotEqual(function, mutated_function)
        mutated = self.replace_once(self.entry, function, mutated_function)
        failures = self.failures(entry=mutated)
        self.assertTrue(any("separate synthetic state" in failure
                            for failure in failures))
        self.assertTrue(any("wrapper uses production state" in failure
                            for failure in failures))

    def test_display_and_rf_touch_ack_are_truthful(self) -> None:
        cases = {
            "display field": (
                r'\"display_touched\":%s',
                r'\"display_touched\":false',
                "display touch ACK field",
            ),
            "display value": (
                'displayTouched ? "true" : "false"',
                '"true"',
                "conditional display touch value",
            ),
            "RF false": (
                r'\"rf_hardware_touched\":false',
                r'\"rf_hardware_touched\":true',
                "no RF hardware touch ACK",
            ),
            "persistence false": (
                r'\"persistence_allowed\":false',
                r'\"persistence_allowed\":true',
                "no synthetic persistence ACK",
            ),
            "export false": (
                r'\"export_allowed\":false',
                r'\"export_allowed\":true',
                "no synthetic export ACK",
            ),
        }
        for name, (old, new, expected) in cases.items():
            with self.subTest(marker=name):
                mutated = self.mutate_function(
                    self.entry,
                    "emitWifiAuthenticationSyntheticHilReport",
                    old,
                    new,
                )
                self.assert_failure(expected, entry=mutated)

    def test_ambiguous_hardware_touch_ack_is_rejected(self) -> None:
        mutated = self.mutate_function(
            self.entry,
            "emitWifiAuthenticationSyntheticHilReport",
            r'\"rf_hardware_touched\":false',
            r'\"rf_hardware_touched\":false,'
            r'\"hardware_touched\":false',
        )
        self.assert_failure("ambiguous hardware_touched", entry=mutated)

    def test_primary_safety_ack_markers_are_required(self) -> None:
        cases = (
            (r'\"one_shot\":true', r'\"one_shot\":false',
             "one-shot ACK"),
            (r'\"synthetic\":true', r'\"synthetic\":false',
             "synthetic ACK"),
            (r'\"report_origin\":\"synthetic_hil\"',
             r'\"report_origin\":\"ambient_rf\"',
             "synthetic report origin"),
            (r'\"radio_started\":false', r'\"radio_started\":true',
             "no radio start ACK"),
            (r'\"storage_mounted\":false',
             r'\"storage_mounted\":true', "no storage mount ACK"),
            (r'\"storage_written\":false',
             r'\"storage_written\":true', "no storage write ACK"),
            (r'\"connect_calls\":0', r'\"connect_calls\":1',
             "no connection ACK"),
            (r'\"raw_tx_calls\":0', r'\"raw_tx_calls\":1',
             "no raw TX ACK"),
            (r'\"response_complete\":true',
             r'\"response_complete\":false',
             "complete primary response ACK"),
        )
        for old, new, expected in cases:
            with self.subTest(marker=expected):
                mutated = self.mutate_function(
                    self.entry,
                    "emitWifiAuthenticationSyntheticHilReport",
                    old,
                    new,
                )
                self.assert_failure(expected, entry=mutated)

    def test_display_render_must_remain_on_loaded_path(self) -> None:
        for call in (
            "display.startWrite();",
            "renderWifiAuthenticationCapture(false);",
            "renderNavigationFooter();",
            "display.endWrite();",
        ):
            with self.subTest(call=call):
                mutated = self.mutate_function(
                    self.entry,
                    "emitWifiAuthenticationSyntheticHilReport",
                    call,
                    "",
                )
                self.assert_failure("balanced ordered TFT transaction",
                                    entry=mutated)

    def test_display_transaction_order_is_required(self) -> None:
        function = MODULE.cpp_function(
            self.entry, "emitWifiAuthenticationSyntheticHilReport")
        self.assertIsNotNone(function)
        assert function is not None
        mutated_function = function.replace(
            "renderWifiAuthenticationCapture(false);",
            "renderTemporaryPlaceholder();",
            1,
        ).replace(
            "renderNavigationFooter();",
            "renderWifiAuthenticationCapture(false);",
            1,
        ).replace(
            "renderTemporaryPlaceholder();",
            "renderNavigationFooter();",
            1,
        )
        mutated = self.replace_once(self.entry, function, mutated_function)
        self.assert_failure("balanced ordered TFT transaction",
                            entry=mutated)

    def test_snprintf_result_must_be_captured(self) -> None:
        function = MODULE.cpp_function(
            self.entry, "emitWifiAuthenticationSyntheticHilReport")
        self.assertIsNotNone(function)
        assert function is not None
        mutated_function, count = re.subn(
            r"const int [A-Za-z_]\w* = std::snprintf\(",
            "std::snprintf(",
            function,
            count=1,
        )
        self.assertEqual(count, 1)
        mutated = self.replace_once(self.entry, function, mutated_function)
        self.assert_failure("snprintf result is not uniquely checked",
                            entry=mutated)

    def test_snprintf_truncation_must_use_greater_equal(self) -> None:
        mutated = self.mutate_function(
            self.entry,
            "emitWifiAuthenticationSyntheticHilReport",
            ">= sizeof(line)",
            "> sizeof(line)",
        )
        self.assert_failure("snprintf error/truncation bounds check",
                            entry=mutated)

    def test_snprintf_truncation_requires_fail_closed_status(self) -> None:
        mutated = self.mutate_function(
            self.entry,
            "emitWifiAuthenticationSyntheticHilReport",
            "response_truncated",
            "ok",
        )
        self.assert_failure("response_truncated", entry=mutated)

    def test_synthetic_clear_resets_controller_report_and_mode(self) -> None:
        cases = {
            "controller": (
                f"{MODULE.SYNTHETIC_CONTROLLER}.reset();",
                "",
                "synthetic controller",
            ),
            "report": (
                f"{MODULE.SYNTHETIC_REPORT} = {{}};",
                "removedSyntheticReport = {};",
                "synthetic report",
            ),
            "mode": (
                "wifiAuthenticationSynthetic = false;",
                "wifiAuthenticationSynthetic = true;",
                "synthetic mode marker",
            ),
        }
        for name, (old, new, expected) in cases.items():
            with self.subTest(state=name):
                mutated = self.mutate_function(
                    self.entry, MODULE.SYNTHETIC_CLEAR, old, new)
                self.assert_failure(expected, entry=mutated)

    def test_session_and_product_cleanup_calls_are_required(self) -> None:
        cases = (
            ("emitHilSessionBegin", "session begin synthetic cleanup"),
            ("emitHilSessionEnd", "session end synthetic cleanup"),
            ("resetWifiAuthenticationCaptureProduct",
             "product reset synthetic cleanup"),
        )
        for function_name, expected in cases:
            with self.subTest(function=function_name):
                mutated = self.mutate_function(
                    self.entry,
                    function_name,
                    f"{MODULE.SYNTHETIC_CLEAR}();",
                    "",
                )
                self.assert_failure(expected, entry=mutated)

    def test_capture_exit_cleanup_is_required(self) -> None:
        mutated = self.mutate_function(
            self.entry,
            "leaveWifiAuthenticationCapture",
            "resetWifiAuthenticationCaptureProduct();",
            "",
        )
        self.assert_failure("capture exit", entry=mutated)

    def test_synthetic_exit_and_expiry_cleanup_are_required(self) -> None:
        mutated_exit = self.mutate_function(
            self.entry,
            "leaveWifiAuthenticationSyntheticHilView",
            f"{MODULE.SYNTHETIC_CLEAR}();",
            "",
        )
        self.assert_failure("synthetic capture exit",
                            entry=mutated_exit)
        mutated_expiry = self.mutate_function(
            self.entry,
            "serviceWifiAuthenticationSyntheticHilExpiry",
            "leaveWifiAuthenticationSyntheticHilView(false)",
            "false",
        )
        self.assert_failure("bounded exit cleanup", entry=mutated_expiry)

    def test_synthetic_paths_must_not_touch_production_state(self) -> None:
        cases = (
            (MODULE.SYNTHETIC_CLEAR, "wifiAuthenticationReport = {};",
             "synthetic cleanup mutates production state"),
            ("leaveWifiAuthenticationSyntheticHilView",
             "wifiAuthenticationController.reset();",
             "synthetic capture exit uses production state"),
        )
        for function_name, statement, expected in cases:
            with self.subTest(function=function_name):
                mutated = self.inject_function_code(
                    self.entry, function_name, statement)
                self.assert_failure(expected, entry=mutated)

    def test_presenter_security_telemetry_fields_are_required(self) -> None:
        fields = (
            ("presenter_synthetic", "presenter synthetic telemetry"),
            ("presenter_synthetic_label_visible",
             "presenter synthetic label telemetry"),
            ("presenter_title_semantic",
             "presenter title semantic telemetry"),
            ("presenter_headline_semantic",
             "presenter headline semantic telemetry"),
            ("presenter_note_semantic",
             "presenter note semantic telemetry"),
        )
        for field, expected in fields:
            with self.subTest(field=field):
                mutated = self.replace_once(
                    self.entry, f'\\"{field}\\"', f'\\"removed_{field}\\"')
                self.assert_failure(expected, entry=mutated)

    def test_production_continuity_telemetry_fields_are_required(self) -> None:
        fields = (
            ("production_report_fingerprint",
             "production report fingerprint telemetry"),
            ("production_report_fingerprint_scope",
             "session-scoped production report fingerprint"),
            ("production_controller_ready",
             "production controller ready telemetry"),
            ("production_controller_view",
             "production controller view telemetry"),
            ("production_controller_action_selection",
             "production controller action continuity telemetry"),
            ("production_controller_peer_selection",
             "production controller peer continuity telemetry"),
            ("production_controller_evidence_selection",
             "production controller evidence continuity telemetry"),
            ("production_controller_report_bound",
             "production controller/report binding telemetry"),
        )
        for field, expected in fields:
            with self.subTest(field=field):
                mutated = self.replace_once(
                    self.entry, f'\\"{field}\\"', f'\\"removed_{field}\\"')
                self.assert_failure(expected, entry=mutated)

    def test_production_fingerprint_is_session_salted_and_bounded(self) -> None:
        cases = (
            ("output == nullptr || capacity < 17U || !hilSession.active()",
             "output == nullptr", "production fingerprint output capacity gate"),
            ("const char* sessionId = hilSession.id();",
             "const char* sessionId = \"\";",
             "production fingerprint session salt"),
            ("std::uint64_t hash = 14695981039346656037ULL;",
             "std::uint64_t hash = 0U;",
             "production fingerprint 64-bit FNV offset"),
            ("&wifiAuthenticationReport", "&wifiAuthenticationSyntheticHilReport",
             "production fingerprint report bytes"),
            ("index < sizeof(wifiAuthenticationReport)", "index < 1U",
             "production fingerprint bounded report size"),
            ("hash *= 1099511628211ULL;", "",
             "production fingerprint 64-bit FNV mixing"),
            ('"%016llx"', '"%08lx"',
             "production fingerprint fixed lowercase hex"),
            ("return formatted == 16;", "return formatted >= 0;",
             "production fingerprint exact length check"),
        )
        for old, new, expected in cases:
            with self.subTest(invariant=expected):
                mutated = self.mutate_function(
                    self.entry,
                    "formatWifiAuthenticationProductionReportFingerprint",
                    old,
                    new,
                )
                self.assert_failure(expected, entry=mutated)

    def test_production_fingerprint_is_unavailable_outside_hil(self) -> None:
        cases = (
            ("productionReportFingerprintAvailable\n"
             "            ? productionReportFingerprint : \"unavailable\"",
             "productionReportFingerprint",
             "production report fingerprint unavailable outside HIL"),
            ("productionReportFingerprintAvailable ? \"hil_session\" : \"none\"",
             "\"hil_session\"",
             "production report fingerprint scope none outside HIL"),
        )
        for old, new, expected in cases:
            with self.subTest(invariant=expected):
                mutated = self.mutate_function(
                    self.entry, "emitWifiAuthenticationCaptureState",
                    old, new)
                self.assert_failure(expected, entry=mutated)

    def test_presenter_security_semantic_values_are_required(self) -> None:
        cases = (
            ('return "capture_result";', 'return "unknown";',
             "capture result presenter semantic"),
            ('return "full_handshake";', 'return "unknown";',
             "full handshake presenter semantic"),
            ('case UiTextId::SimulatedData: return "simulated_data";',
             'case UiTextId::SimulatedData: return "unknown";',
             "synthetic label presenter semantic"),
        )
        for old, new, expected in cases:
            with self.subTest(semantic=expected):
                mutated = self.replace_once(self.entry, old, new)
                self.assert_failure(expected, entry=mutated)

    def test_presenter_marker_and_visible_label_are_required(self) -> None:
        mutated_h = self.replace_once(
            self.presenter_h, "bool synthetic = false;", "")
        self.assert_failure("separate synthetic markers",
                            presenter_h=mutated_h)
        mutated_cpp = self.replace_once(
            self.presenter_cpp,
            "model.note = UiTextId::SimulatedData;",
            "",
        )
        self.assert_failure("visibly labelled", presenter_cpp=mutated_cpp)
        mutated_propagation = self.replace_once(
            self.presenter_cpp,
            "model.synthetic = input.synthetic;",
            "model.synthetic = false;",
        )
        self.assert_failure("propagate synthetic marker",
                            presenter_cpp=mutated_propagation)

    def test_direct_terminal_back_branch_is_required(self) -> None:
        for marker, expected in (
                ('"leshy.wifi.authentication.synthetic_back_cleanup.v1"',
                 "direct terminal Back retained proof"),
                ('menu_after_back = action(device, "back")',
                 "direct terminal Back action"),
                ('hil_session_cycle["begin"] = begin_hil_session(',
                 "one-shot HIL session cycle")):
            with self.subTest(marker=marker):
                mutated = self.replace_once(self.hil_runner, marker, "removed")
                self.assert_failure(expected, hil_runner=mutated)
        mutated_checker = self.replace_once(
            self.hil_run_checker,
            "def verify_synthetic_terminal_back_cleanup(",
            "def removed_synthetic_terminal_back_cleanup(")
        self.assert_failure(
            "direct terminal Back fail-closed checker",
            hil_run_checker=mutated_checker)

    def test_storage_scope_cannot_overclaim_measurement(self) -> None:
        mutated = self.hil_runner.replace(
            '"product_storage_writes_measured": False',
            '"product_storage_writes_measured": True')
        self.assert_failure(
            "honest unmeasured product-storage scope", hil_runner=mutated)
        mutated = self.hil_runner.replace(
            '"static_no_storage_api_contract_required": True',
            '"static_no_storage_api_contract_required": False')
        self.assert_failure("static no-storage API contract scope",
                            hil_runner=mutated)
        overclaimed = self.hil_runner + \
            '\nsynthetic_side_effects_independently_proven = True\n'
        self.assert_failure("retains overclaim", hil_runner=overclaimed)


if __name__ == "__main__":
    unittest.main()
