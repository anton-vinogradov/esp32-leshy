#!/usr/bin/env python3
"""Fail-closed source audit for the authentication synthetic HIL fixture."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
FIXTURE_H = ROOT / (
    "firmware/leshy1/src/apps/auth/"
    "WifiAuthenticationSyntheticHilFixture.h"
)
FIXTURE_CPP = ROOT / (
    "firmware/leshy1/src/apps/auth/"
    "WifiAuthenticationSyntheticHilFixture.cpp"
)
PRESENTER_H = ROOT / (
    "firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.h"
)
PRESENTER_CPP = ROOT / (
    "firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.cpp"
)
HIL_RUNNER = ROOT / "tools/run_1x_wifi_authentication_capture_hil.py"
HIL_RUN_CHECKER = ROOT / "tools/check_wifi_authentication_capture_hil_run.py"

SYNTHETIC_REPORT = "wifiAuthenticationSyntheticHilReport"
SYNTHETIC_CONTROLLER = "wifiAuthenticationSyntheticHilController"
PRODUCTION_REPORT = "wifiAuthenticationReport"
PRODUCTION_CONTROLLER = "wifiAuthenticationController"
SYNTHETIC_CLEAR = "clearWifiAuthenticationSyntheticHilState"


def compact(source: str) -> str:
    return "".join(source.split())


def mask_cpp_non_code(source: str) -> str:
    """Mask comments and literals while preserving source offsets."""
    masked = list(source)
    index = 0
    state = "code"
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if current == "/" and following == "/":
                masked[index] = masked[index + 1] = " "
                state = "line_comment"
                index += 2
                continue
            if current == "/" and following == "*":
                masked[index] = masked[index + 1] = " "
                state = "block_comment"
                index += 2
                continue
            if current == '"':
                masked[index] = " "
                state = "string"
            elif current == "'":
                masked[index] = " "
                state = "character"
            index += 1
            continue
        if state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                masked[index] = " "
            index += 1
            continue
        if state == "block_comment":
            if current == "*" and following == "/":
                masked[index] = masked[index + 1] = " "
                state = "code"
                index += 2
            else:
                if current != "\n":
                    masked[index] = " "
                index += 1
            continue
        if current == "\\":
            masked[index] = " "
            if index + 1 < len(source):
                if source[index + 1] != "\n":
                    masked[index + 1] = " "
                index += 2
            else:
                index += 1
            continue
        masked[index] = " "
        if (state == "string" and current == '"') or (
            state == "character" and current == "'"
        ):
            state = "code"
        index += 1
    return "".join(masked)


def cpp_function(source: str, name: str,
                 masked: str | None = None) -> str | None:
    """Return a named C++ definition, balancing braces outside literals."""
    if masked is None:
        masked = mask_cpp_non_code(source)
    definition = re.search(
        rf"\b{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{", masked
    )
    if definition is None:
        return None
    opening = masked.find("{", definition.start(), definition.end())
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return source[definition.start():index + 1]
    return None


def cpp_control_block(source: str, condition: str) -> str | None:
    """Return the braced body for the first matching control condition."""
    masked = mask_cpp_non_code(source)
    statement = re.search(condition + r"\s*\{", masked)
    if statement is None:
        return None
    opening = masked.find("{", statement.start(), statement.end())
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
    return None


def require_function(entry: str, entry_masked: str, name: str,
                     failures: list[str]) -> str:
    function = cpp_function(entry, name, entry_masked)
    if function is None:
        failures.append(f"missing function definition: {name}")
        return ""
    return function


def audit_forbidden_apis(label: str, source: str,
                         failures: list[str]) -> None:
    code = mask_cpp_non_code(source)
    forbidden = {
        "ESP Wi-Fi driver": r"\besp_wifi_[A-Za-z0-9_]*\s*\(",
        "Arduino Wi-Fi": r"\bWiFi\s*(?:\.|::)",
        "BLE/Bluetooth": r"\b(?:BLEDevice|NimBLE[A-Za-z0-9_]*|Bluetooth)\b",
        "capture/RF start": (
            r"\b(?:beginWifiAuthenticationCapture|"
            r"beginAuthenticationCapture)\s*\("
        ),
        "capture adapter start": (
            r"\bwifiFrameCapture\s*\.\s*(?:begin|start|open)\s*\("
        ),
        "connection": r"\bconnect\s*\(",
        "raw/transmit": (
            r"\b(?:rawTx|transmit|sendPacket|esp_now_send)\s*\("
        ),
        "filesystem object": (
            r"\b(?:LittleFS|SPIFFS|SD|SD_MMC)\s*(?:\.|::)"
        ),
        "storage write/mount": (
            r"\b(?:mount|writeFile|appendFile|fopen|fwrite)\s*\("
        ),
    }
    for api, pattern in forbidden.items():
        if re.search(pattern, code):
            failures.append(f"{label} touches forbidden API: {api}")


def contract_failures(
    entry: str,
    fixture_h: str,
    fixture_cpp: str,
    presenter_h: str,
    presenter_cpp: str,
    hil_runner: str,
    hil_run_checker: str,
) -> list[str]:
    failures: list[str] = []
    entry_c = compact(entry)
    header_c = compact(fixture_h)
    fixture_c = compact(fixture_cpp)
    presenter_h_c = compact(presenter_h)
    presenter_c = compact(presenter_cpp)
    entry_masked = mask_cpp_non_code(entry)

    wrapper = require_function(
        entry, entry_masked,
        "emitWifiAuthenticationSyntheticHilReport", failures)
    session_begin = require_function(
        entry, entry_masked, "emitHilSessionBegin", failures)
    session_end = require_function(
        entry, entry_masked, "emitHilSessionEnd", failures)
    product_reset = require_function(
        entry, entry_masked, "resetWifiAuthenticationCaptureProduct",
        failures)
    product_leave = require_function(
        entry, entry_masked, "leaveWifiAuthenticationCapture", failures)
    synthetic_leave = require_function(
        entry, entry_masked, "leaveWifiAuthenticationSyntheticHilView",
        failures)
    synthetic_expiry = require_function(
        entry, entry_masked, "serviceWifiAuthenticationSyntheticHilExpiry",
        failures)
    production_fingerprint = require_function(
        entry, entry_masked,
        "formatWifiAuthenticationProductionReportFingerprint", failures)
    synthetic_clear = require_function(
        entry, entry_masked, SYNTHETIC_CLEAR, failures)
    wrapper_c = compact(wrapper)
    loaded_block = cpp_control_block(
        wrapper, r"\bif\s*\(\s*loaded\s*\)") or ""
    loaded_block_c = compact(mask_cpp_non_code(loaded_block))
    wrapper_code = mask_cpp_non_code(wrapper)
    snprintf_assignments = re.findall(
        r"\b(?:const\s+)?int\s+([A-Za-z_]\w*)\s*=\s*std::snprintf\s*\(",
        wrapper_code,
    )
    snprintf_calls = len(re.findall(
        r"\bstd::snprintf\s*\(", wrapper_code))
    if len(snprintf_assignments) == 1:
        primary_ack_c = wrapper_c.split(
            f"if({snprintf_assignments[0]}<0", 1)[0]
    else:
        primary_ack_c = ""

    required_entry = {
        "exact synthetic command":
            '"wifi.authentication.hil-load-synthetic-reportonce"',
        "dedicated synthetic schema":
            "leshy.wifi.authentication.synthetic_fixture.v1",
        "state synthetic marker":
            r'\"synthetic\":%s,\"report_origin\":\"%s\"',
        "controller view telemetry": r'\"controller_view\":\"%s\"',
        "controller action telemetry":
            r'\"controller_selected_action\":\"%s\"',
        "controller peer telemetry":
            r'\"controller_selected_peer_mask\":%u',
        "controller evidence telemetry":
            r'\"controller_selected_evidence_source_frame\":%u',
        "presenter synthetic telemetry":
            r'\"presenter_synthetic\":%s',
        "presenter synthetic label telemetry":
            r'\"presenter_synthetic_label_visible\":%s',
        "presenter title semantic telemetry":
            r'\"presenter_title_semantic\":\"%s\"',
        "presenter headline semantic telemetry":
            r'\"presenter_headline_semantic\":\"%s\"',
        "presenter note semantic telemetry":
            r'\"presenter_note_semantic\":\"%s\"',
        "production report fingerprint telemetry":
            r'\"production_report_fingerprint\":\"%s\"',
        "session-scoped production report fingerprint":
            r'\"production_report_fingerprint_scope\":\"%s\"',
        "production report fingerprint unavailable outside HIL":
            'productionReportFingerprintAvailable?'
            'productionReportFingerprint:"unavailable"',
        "production report fingerprint scope none outside HIL":
            'productionReportFingerprintAvailable?"hil_session":"none"',
        "production controller ready telemetry":
            r'\"production_controller_ready\":%s',
        "production controller view telemetry":
            r'\"production_controller_view\":\"%s\"',
        "production controller action continuity telemetry":
            r'\"production_controller_action_selection\":%u',
        "production controller peer continuity telemetry":
            r'\"production_controller_peer_selection\":%u',
        "production controller evidence continuity telemetry":
            r'\"production_controller_evidence_selection\":%u',
        "production controller/report binding telemetry":
            r'\"production_controller_report_bound\":%s',
        "capture result presenter semantic":
            'caseUiTextId::CaptureResult:return"capture_result";',
        "full handshake presenter semantic":
            'caseUiTextId::WifiAuthFullHandshakeHeadline:'
            'return"full_handshake";',
        "synthetic label presenter semantic":
            'caseUiTextId::SimulatedData:return"simulated_data";',
        "repeat telemetry": r'\"repeat_request_generation\":%lu',
    }
    for label, marker in required_entry.items():
        if marker not in entry_c:
            failures.append(f"missing {label}")

    required_wrapper = {
        "exact synthetic safe-state context":
            "constWifiAuthenticationSyntheticHilContextcontext{"
            "hilSession.active(),"
            "wifiProductView==WifiProductView::AuthenticationCapture,"
            "wifiAuthenticationProductState=="
            "WifiAuthenticationProductState::Result,"
            "wifiFrameCapture.cleanupComplete()&&"
            "ingress.cleanupComplete&&!ingress.active,"
            "!ingress.active,"
            "resourceBroker.ownerOf(Resource::EspRf)=="
            "AppRuntime::kForegroundOwner&&"
            'std::strcmp(appRuntime.activeApp(),"wifi")==0,'
            "wifiAuthenticationTarget.channel,millis(),};",
        "active HIL gate":
            "constWifiAuthenticationSyntheticHilContextcontext{"
            "hilSession.active(),",
        "authentication view gate":
            "wifiProductView==WifiProductView::AuthenticationCapture",
        "terminal result gate":
            "wifiAuthenticationProductState=="
            "WifiAuthenticationProductState::Result",
        "capture cleanup gate": "wifiFrameCapture.cleanupComplete()",
        "adapter cleanup gate": "ingress.cleanupComplete",
        "capture inactive gate": "!ingress.active",
        "foreground Wi-Fi ownership gate":
            'std::strcmp(appRuntime.activeApp(),"wifi")==0',
        "content render on successful load":
            "if(loaded){wifiAuthenticationSynthetic=true;",
    }
    for label, marker in required_wrapper.items():
        if marker not in wrapper_c:
            failures.append(f"missing {label}")
    required_primary_ack = {
        "one-shot ACK": r'\"one_shot\":true',
        "synthetic ACK": r'\"synthetic\":true',
        "synthetic report origin":
            r'\"report_origin\":\"synthetic_hil\"',
        "display touch ACK field": r'\"display_touched\":%s',
        "no RF hardware touch ACK": r'\"rf_hardware_touched\":false',
        "no radio start ACK": r'\"radio_started\":false',
        "no synthetic persistence ACK":
            r'\"persistence_allowed\":false',
        "no synthetic export ACK": r'\"export_allowed\":false',
        "no storage mount ACK": r'\"storage_mounted\":false',
        "no storage write ACK": r'\"storage_written\":false',
        "no connection ACK": r'\"connect_calls\":0',
        "no raw TX ACK": r'\"raw_tx_calls\":0',
        "complete primary response ACK": r'\"response_complete\":true',
        "conditional display touch value":
            'displayTouched?"true":"false"',
    }
    for label, marker in required_primary_ack.items():
        if marker not in primary_ack_c:
            failures.append(f"missing {label}")
    draw_transaction = (
        "display.startWrite()",
        "renderWifiAuthenticationCapture(false)",
        "renderNavigationFooter()",
        "display.endWrite()",
    )
    draw_positions = [loaded_block_c.find(marker)
                      for marker in draw_transaction]
    if (any(position < 0 for position in draw_positions) or
            draw_positions != sorted(draw_positions) or
            any(loaded_block_c.count(marker) != 1
                for marker in draw_transaction)):
        failures.append(
            "successful synthetic draw lacks one balanced ordered TFT "
            "transaction")
    if r'\"hardware_touched\"' in wrapper_c:
        failures.append("ambiguous hardware_touched ACK remains in wrapper")

    entry_code_c = compact(entry_masked)
    separate_globals = {
        "separate synthetic report global":
            f"WifiAuthenticationCaptureReport{SYNTHETIC_REPORT}{{}};",
        "separate synthetic controller global":
            f"WifiAuthenticationCaptureController{SYNTHETIC_CONTROLLER}{{}};",
        "production report global":
            f"WifiAuthenticationCaptureReport{PRODUCTION_REPORT}{{}};",
        "production controller global":
            f"WifiAuthenticationCaptureController{PRODUCTION_CONTROLLER}{{}};",
    }
    for label, marker in separate_globals.items():
        if marker not in entry_code_c:
            failures.append(f"missing {label}")
    expected_fixture_load = (
        "wifiAuthenticationSyntheticHilFixture.loadOnce(context,"
        f"&{SYNTHETIC_REPORT},&{SYNTHETIC_CONTROLLER})"
    )
    if expected_fixture_load not in wrapper_c:
        failures.append("fixture is not loaded into separate synthetic state")
    for production_name in (PRODUCTION_REPORT, PRODUCTION_CONTROLLER):
        if re.search(rf"\b{production_name}\b", wrapper_code):
            failures.append(
                f"wrapper uses production state: {production_name}")

    audit_forbidden_apis("wrapper", wrapper, failures)
    audit_forbidden_apis("fixture", fixture_cpp, failures)

    if len(snprintf_assignments) != 1 or snprintf_calls != 1:
        failures.append("wrapper snprintf result is not uniquely checked")
    else:
        result = snprintf_assignments[0]
        result_check = (
            f"if({result}<0||static_cast<std::size_t>({result})"
            ">=sizeof(line))"
        )
        if result_check not in wrapper_c:
            failures.append("wrapper lacks snprintf error/truncation bounds check")
        if wrapper_c.count("response_truncated") < 2:
            failures.append("wrapper lacks fail-closed response_truncated status")
        error_at = wrapper_c.find(result_check)
        reply_at = wrapper_c.find("reply.println(line)")
        if error_at < 0 or reply_at < 0 or error_at > reply_at:
            failures.append("wrapper emits snprintf buffer before bounds check")

    clear_c = compact(mask_cpp_non_code(synthetic_clear))
    if f"{SYNTHETIC_CONTROLLER}.reset()" not in clear_c:
        failures.append("synthetic cleanup does not reset synthetic controller")
    report_cleared = (
        f"{SYNTHETIC_REPORT}={{}}" in clear_c or
        (
            f"std::memset(&{SYNTHETIC_REPORT},0," in clear_c and
            f"sizeof({SYNTHETIC_REPORT})" in clear_c
        )
    )
    if not report_cleared:
        failures.append("synthetic cleanup does not clear synthetic report")
    if "wifiAuthenticationSynthetic=false" not in clear_c:
        failures.append("synthetic cleanup does not clear synthetic mode marker")
    for production_name in (PRODUCTION_REPORT, PRODUCTION_CONTROLLER):
        if re.search(rf"\b{production_name}\b", mask_cpp_non_code(
                synthetic_clear)):
            failures.append(
                f"synthetic cleanup mutates production state: {production_name}")
    fingerprint_c = compact(mask_cpp_non_code(production_fingerprint))
    fingerprint_requirements = {
        "production fingerprint output capacity gate":
            "output==nullptr||capacity<17U||!hilSession.active()",
        "production fingerprint session salt":
            "constchar*sessionId=hilSession.id()",
        "production fingerprint 64-bit FNV offset":
            "std::uint64_thash=14695981039346656037ULL",
        "production fingerprint report bytes":
            "reinterpret_cast<conststd::uint8_t*>(&wifiAuthenticationReport)",
        "production fingerprint bounded report size":
            "index<sizeof(wifiAuthenticationReport)",
        "production fingerprint fixed lowercase hex":
            "output,capacity,,static_cast<unsignedlonglong>(hash)",
        "production fingerprint exact length check": "returnformatted==16",
    }
    for label, marker in fingerprint_requirements.items():
        if marker not in fingerprint_c:
            failures.append(f"missing {label}")
    if '"%016llx"' not in production_fingerprint:
        failures.append("missing production fingerprint fixed lowercase hex")
    if fingerprint_c.count("hash*=1099511628211ULL") != 2:
        failures.append("missing production fingerprint 64-bit FNV mixing")

    cleanup_sites = {
        "session begin synthetic cleanup": session_begin,
        "session end synthetic cleanup": session_end,
        "product reset synthetic cleanup": product_reset,
    }
    for label, function in cleanup_sites.items():
        if f"{SYNTHETIC_CLEAR}()" not in compact(
                mask_cpp_non_code(function)):
            failures.append(f"missing {label}")
    if "resetWifiAuthenticationCaptureProduct()" not in compact(
            mask_cpp_non_code(product_leave)):
        failures.append("capture exit does not run product/synthetic cleanup")
    synthetic_leave_c = compact(mask_cpp_non_code(synthetic_leave))
    if f"{SYNTHETIC_CLEAR}()" not in synthetic_leave_c:
        failures.append("synthetic capture exit does not clear synthetic state")
    for production_name in (PRODUCTION_REPORT, PRODUCTION_CONTROLLER):
        if re.search(rf"\b{production_name}\b", mask_cpp_non_code(
                synthetic_leave)):
            failures.append(
                f"synthetic capture exit uses production state: {production_name}")
    if "leaveWifiAuthenticationSyntheticHilView(false)" not in compact(
            mask_cpp_non_code(synthetic_expiry)):
        failures.append("synthetic fixture expiry does not use bounded exit cleanup")

    required_fixture = {
        "HIL inactive rejection": "if(!context.hilActive)",
        "one-shot rejection": "if(loaded_)",
        "exact safe-state conjunction":
            "!context.authenticationViewActive||!context.resultActive||"
            "!context.cleanupComplete||!context.captureInactive||"
            "!context.foregroundWifiOwnsRf",
        "two peer fixture": "report->peerCount=2U",
        "six evidence rows": "report->evidenceCount=6U",
        "independent PMKID": "report->pmkidCount=1U",
        "full handshake": "complete.messageMask=0x0fU",
        "partial handshake": "partial.messageMask=0x03U",
        # Synthetic evidence must remain inspectable but cannot expose the
        # product persistence action.
        "controller validation": "controller->load(*report,false)",
    }
    for label, marker in required_fixture.items():
        if marker not in fixture_c:
            failures.append(f"missing {label}")

    if presenter_h_c.count("boolsynthetic=false") < 2:
        failures.append("presenter input/model lacks separate synthetic markers")
    if "model.note=UiTextId::SimulatedData" not in presenter_c:
        failures.append("synthetic UI is not visibly labelled")
    if "if(input.synthetic)" not in presenter_c:
        failures.append("presenter does not branch explicitly on synthetic")
    if "model.synthetic=input.synthetic" not in presenter_c:
        failures.append("presenter does not propagate synthetic marker")
    if "kReportIdentity" not in header_c:
        failures.append("fixture lacks immutable report identity")

    runner_requirements = {
        "direct terminal Back retained proof":
            '"leshy.wifi.authentication.synthetic_back_cleanup.v1"',
        "direct terminal Back action":
            'menu_after_back = action(device, "back")',
        "one-shot HIL session cycle for Back branch":
            'hil_session_cycle["begin"] = begin_hil_session(',
        "boot-recovery continuity scope":
            '"boot_recovery_continuity":',
        "honest unmeasured product-storage scope":
            '"product_storage_writes_measured": False',
        "static no-storage API contract scope":
            '"static_no_storage_api_contract_required": True',
    }
    for label, marker in runner_requirements.items():
        if marker not in hil_runner:
            failures.append(f"missing {label}")
    checker_requirements = {
        "direct terminal Back fail-closed checker":
            "def verify_synthetic_terminal_back_cleanup(",
        "Back scope rejects measured product storage":
            'proof.get("product_storage_writes_measured") is False',
        "scope checker requires boot-recovery continuity":
            'scope.get("synthetic_boot_recovery_continuity_proven") is True',
    }
    for label, marker in checker_requirements.items():
        if marker not in hil_run_checker:
            failures.append(f"missing {label}")
    for overclaim in (
            "synthetic_side_effects_independently_proven",
            '"independently_proven":'):
        if overclaim in hil_runner or overclaim in hil_run_checker:
            failures.append(f"synthetic HIL retains overclaim: {overclaim}")
    return failures


def main() -> int:
    failures = contract_failures(
        ENTRY.read_text(encoding="utf-8"),
        FIXTURE_H.read_text(encoding="utf-8"),
        FIXTURE_CPP.read_text(encoding="utf-8"),
        PRESENTER_H.read_text(encoding="utf-8"),
        PRESENTER_CPP.read_text(encoding="utf-8"),
        HIL_RUNNER.read_text(encoding="utf-8"),
        HIL_RUN_CHECKER.read_text(encoding="utf-8"),
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Wi-Fi authentication synthetic HIL contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
