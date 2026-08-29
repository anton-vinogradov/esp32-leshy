#!/usr/bin/env python3
"""Fail closed when the CAP049 persistence HIL fixture can escape its scope."""

from __future__ import annotations

import re
from pathlib import Path

from check_wifi_authentication_synthetic_hil_contract import (
    audit_forbidden_apis,
    compact,
    cpp_function,
    mask_cpp_non_code,
)


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
FIXTURE_H = ROOT / (
    "firmware/leshy1/src/apps/auth/"
    "WifiAuthenticationPersistenceHilFixture.h"
)
FIXTURE_CPP = ROOT / (
    "firmware/leshy1/src/apps/auth/"
    "WifiAuthenticationPersistenceHilFixture.cpp"
)


def require_function(source: str, name: str, failures: list[str]) -> str:
    function = cpp_function(source, name)
    if function is None:
        failures.append(f"missing function definition: {name}")
        return ""
    return function


def require_all(label: str, source: str, markers: dict[str, str],
                failures: list[str]) -> None:
    source_c = compact(source)
    for meaning, marker in markers.items():
        if compact(marker) not in source_c:
            failures.append(f"{label} missing {meaning}")


def contract_failures(entry: str, fixture_h: str,
                      fixture_cpp: str) -> list[str]:
    failures: list[str] = []
    wrapper = require_function(
        entry, "emitWifiAuthenticationPersistenceHilFixture", failures)
    persist = require_function(
        entry, "requestWifiAuthenticationCapturePersist", failures)
    session_begin = require_function(entry, "emitHilSessionBegin", failures)
    session_end = require_function(entry, "emitHilSessionEnd", failures)
    state = require_function(
        entry, "emitWifiAuthenticationCaptureState", failures)
    ui_action = require_function(entry, "applyUiAction", failures)
    clear = require_function(
        entry, "clearWifiAuthenticationSyntheticHilState", failures)
    load = require_function(fixture_cpp, "loadOnce", failures)

    audit_forbidden_apis("fixture", fixture_cpp, failures)
    audit_forbidden_apis("wrapper", wrapper, failures)

    require_all("fixture header", fixture_h, {
        "public deterministic profile":
            'kProfile = "strict-m1-m2-raw-v1"',
        "bounded 120-second lifetime": "kLifetimeMs = 120000U",
        "locally administered AP": "0x02U, 0x4cU, 0x45U",
        "locally administered station": "0x02U, 0x48U, 0x49U",
    }, failures)
    require_all("fixture load", load, {
        "active HIL gate": "if (!context.hilActive)",
        "one-shot replay gate": "if (loaded_)",
        "authentication view gate": "!context.authenticationViewActive",
        "result gate": "!context.resultActive",
        "cleanup gate": "!context.cleanupComplete",
        "inactive capture gate": "!context.captureInactive",
        "foreground Wi-Fi RF ownership gate":
            "!context.foregroundWifiOwnsRf",
        "real capture begin": "capture->begin(plan, context.nowUs)",
        "real analysis":
            "analyzeWifiAuthenticationCapture(input, report)",
        "save-enabled controller": "controller->load(*report, true)",
    }, failures)
    require_all("command wrapper", wrapper, {
        "active HIL context": "hilSession.active()",
        "authentication result context":
            "wifiAuthenticationProductState == "
            "WifiAuthenticationProductState::Result",
        "production ingress cleanup":
            "wifiFrameCapture.cleanupComplete() && ingress.cleanupComplete",
        "idle store worker": "captureStoreTaskHandle == nullptr",
        "idle fixture capture":
            "wifiAuthenticationPersistenceHilCapture.stats().state == "
            "WifiFrameCaptureState::Idle",
        "foreground RF owner":
            "resourceBroker.ownerOf(Resource::EspRf) == "
            "AppRuntime::kForegroundOwner",
        "Wi-Fi foreground app":
            'std::strcmp(appRuntime.activeApp(), "wifi") == 0',
        "dedicated synthetic state":
            "&wifiAuthenticationPersistenceHilCapture, "
            "&wifiAuthenticationSyntheticHilReport, "
            "&wifiAuthenticationSyntheticHilController",
        "synthetic persistence origin":
            r'\"report_origin\":\"synthetic_hil_persistence\"',
        "no RF touch acknowledgement":
            r'\"rf_hardware_touched\":false',
        "no radio start acknowledgement": r'\"radio_started\":false',
        "no connection acknowledgement": r'\"connect_calls\":0',
        "no transmit acknowledgement": r'\"raw_tx_calls\":0',
        "no raw disclosure acknowledgement":
            r'\"raw_payload_disclosed\":false',
        "public identifiers acknowledgement":
            r'\"public_test_identifiers_only\":true',
    }, failures)
    wrapper_c = compact(wrapper)
    for unsafe_claim, meaning in (
        (r'\"rf_hardware_touched\":true', "RF touched claim"),
        (r'\"radio_started\":true', "radio started claim"),
        (r'\"connect_calls\":1', "connection call claim"),
        (r'\"raw_tx_calls\":1', "transmit call claim"),
        (r'\"raw_payload_disclosed\":true', "raw disclosure claim"),
    ):
        if compact(unsafe_claim) in wrapper_c:
            failures.append(f"command wrapper contains unsafe {meaning}")
    require_all("persistence request", persist, {
        "generic synthetic rejection":
            "(wifiAuthenticationSynthetic && "
            "!wifiAuthenticationPersistenceHil)",
        "exact fixture persistence allowance":
            "wifiAuthenticationPersistenceHil",
    }, failures)
    require_all("authentication state", state, {
        "exact persistence origin selection":
            "wifiAuthenticationPersistenceHil",
        "synthetic persistence field":
            r'\"synthetic_persistence_allowed\":%s',
        "synthetic export field":
            r'\"synthetic_export_allowed\":%s',
    }, failures)
    require_all("authentication save dialog", ui_action, {
        "authentication store kind before confirmation":
            "wifiCaptureStoreKind = "
            "WifiCaptureStoreKind::Authentication",
    }, failures)
    require_all("session begin", session_begin, {
        "fixture reset":
            "wifiAuthenticationPersistenceHilFixture.resetForSession()",
        "fixture state clear": "clearWifiAuthenticationSyntheticHilState()",
    }, failures)
    require_all("session end", session_end, {
        "storage busy rejection":
            "wifiAuthenticationPersistenceHil && "
            "captureStoreTaskHandle != nullptr",
        "fail-closed storage status": r'\"status\":\"storage_busy\"',
        "fixture reset":
            "wifiAuthenticationPersistenceHilFixture.resetForSession()",
    }, failures)
    require_all("fixture clear", clear, {
        "raw capture reset": "wifiAuthenticationPersistenceHilCapture.reset()",
        "authorization clear": "wifiAuthenticationPersistenceHil = false",
    }, failures)

    entry_c = compact(entry)
    required_entry = {
        "exact persistence command":
            '"wifi.authentication.hil-load-persistence-fixture once"',
        "dedicated persistence schema":
            "leshy.wifi.authentication.persistence_fixture.v1",
        "help listing":
            r'\"wifi.authentication.hil-load-persistence-fixture once\"',
    }
    for meaning, marker in required_entry.items():
        if compact(marker) not in entry_c:
            failures.append(f"entry missing {meaning}")

    # The public fixture must remain a two-frame, strict M1/M2 path.  This is
    # deliberately structural: changing the bytes is allowed only together
    # with the native semantic test and this review point.
    fixture_code = mask_cpp_non_code(fixture_cpp)
    for marker, meaning in (
        ("message1()", "message 1 construction"),
        ("message2()", "message 2 construction"),
        ("plan.maximumFrames = 2U", "two-frame bound"),
        ("input.framesReported = 2U", "reported frame count"),
        ("input.framesAccepted = 2U", "accepted frame count"),
    ):
        if compact(marker) not in compact(fixture_code):
            failures.append(f"fixture missing {meaning}")

    return failures


def main() -> int:
    failures = contract_failures(
        ENTRY.read_text(encoding="utf-8"),
        FIXTURE_H.read_text(encoding="utf-8"),
        FIXTURE_CPP.read_text(encoding="utf-8"),
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Wi-Fi authentication persistence HIL contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
