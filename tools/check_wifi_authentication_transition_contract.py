#!/usr/bin/env python3
"""Static fail-closed contract for the survey -> authentication transition.

This checker deliberately binds the physical adapter, HIL-only transition
hold, diagnostics, and host runner together.  The hold is test orchestration;
it must never become part of a radio adapter or a production RF decision.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARDUINO_ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
CAPTURE_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h"
)
CAPTURE_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
)
SCANNER_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveScanner.cpp"
)
INIT_PROFILE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveInitConfig.h"
)
RUNNER = ROOT / "tools/run_1x_wifi_authentication_capture_hil.py"


def compact(value: str) -> str:
    value = re.sub(r"/\*.*?\*/|//[^\n]*", "", value, flags=re.DOTALL)
    return re.sub(r"\s+", "", value)


def braced_block(value: str, marker: str) -> str:
    start = value.find(marker)
    if start < 0:
        return ""
    opening = value.find("{", start + len(marker))
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start:index + 1]
    return ""


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check_sources(
    arduino_entry: str,
    capture_header: str,
    capture_source: str,
    scanner_source: str,
    init_profile: str,
    runner: str,
) -> list[str]:
    failures: list[str] = []
    entry = compact(arduino_entry)
    capture_h = compact(capture_header)
    capture = compact(capture_source)
    scanner = compact(scanner_source)
    profile = compact(init_profile)
    runner_compact = re.sub(r"\s+", "", runner)

    # Scanner and every passive capture mode must use one bounded RX-only
    # ESP-IDF configuration.  Reintroducing WIFI_INIT_CONFIG_DEFAULT in either
    # adapter is a memory regression on the no-PSRAM board profile.
    for marker in (
        "structBoardWifiPassiveInitProfile",
        "kStaticRxBuffers=4;",
        "kDynamicRxBuffers=8;",
        "kStaticTxBuffers=0;",
        "kDynamicTxBuffers=4;",
        "kManagementShortBuffers=6;",
        "makeBoardWifiPassiveOnlyInitConfig()",
        "init.ampdu_rx_enable=0",
        "init.ampdu_tx_enable=0",
        "init.amsdu_tx_enable=0",
        "init.rx_ba_win=0",
        "init.nvs_enable=0",
    ):
        require(failures, marker in profile,
                f"passive Wi-Fi init profile lost bounded field: {marker}")
    for name, source, minimum_calls in (
        ("scanner", scanner, 1),
        ("capture", capture, 3),
    ):
        require(
            failures,
            source.count("makeBoardWifiPassiveOnlyInitConfig()") >= minimum_calls,
            f"{name} does not use the shared passive Wi-Fi init profile",
        )
        require(
            failures,
            "WIFI_INIT_CONFIG_DEFAULT()" not in source,
            f"{name} bypasses bounded passive Wi-Fi init with SDK defaults",
        )

    # A start failure must be actionable from retained evidence without a raw
    # serial log.  Values must come from the adapter, not synthetic constants.
    emit_state = braced_block(
        entry, "voidemitWifiAuthenticationCaptureState(Stream&reply)")
    for field in (
        "adapter_driver_error",
        "adapter_failure_stage",
        "adapter_heap_free_before_init",
        "adapter_heap_largest_before_init",
        "survey_terminal_hold_armed",
    ):
        require(failures, f'\\\"{field}\\\"' in emit_state,
                f"authentication diagnostic omits exact field: {field}")
    for marker in (
        "wifiFrameCapture.beginDriverError()",
        "wifiFrameCapture.beginFailureStage()",
        "boardWifiPassiveBeginFailureStageName(",
        "wifiFrameCapture.heapFreeBeforeInit",
        "wifiFrameCapture.heapLargestBeforeInit",
    ):
        require(failures, marker in emit_state,
                f"authentication diagnostic is not bound to adapter: {marker}")
    for marker in (
        "lastError()const",
        "beginDriverError()const",
        "beginFailureStage()const",
        "heapFreeBeforeInit",
        "heapLargestBeforeInit",
    ):
        require(failures, marker in capture_h,
                f"capture adapter does not expose retained failure fact: {marker}")

    # The deterministic hold is admitted only inside an exact HIL session. It
    # is one-shot, monotonic and bounded, clears on successful hil.end, and is
    # forbidden from the RF adapters themselves.
    require(
        failures,
        "wifi.authentication.hil-hold-survey-stoponce" in entry,
        "missing exact one-shot authentication HIL hold command",
    )
    require(
        failures,
        "leshy.wifi.authentication.hil_hold.v1" in entry and
        '\\"kind\\":\\"armed\\"' in entry and
        '\\"status\\":\\"armed\\"' in entry,
        "HIL hold acknowledgement schema/kind/status is not exact",
    )
    hold_arm = braced_block(entry, "voidemitWifiAuthenticationHilHold(")
    require(failures, bool(hold_arm),
            "missing isolated authentication HIL hold arm function")
    require(failures, "hilSession.active()" in hold_arm,
            "authentication HIL hold can arm outside an active session")
    require(
        failures,
        "constboolreplayed=safeState&&"
        "wifiAuthenticationSurveyTerminalHoldArmed" in hold_arm and
        "if(safeState&&!replayed){" in hold_arm and
        "armWifiAuthenticationSurveyTerminalHoldDeadline()" in hold_arm and
        '\\"replayed\\":%s' in hold_arm,
        "authentication HIL hold replay can extend its existing deadline",
    )
    require(
        failures,
        not any(marker in hold_arm for marker in (
            "esp_wifi_", "beginAuthenticationCapture", "resourceBroker",
            "BoardSafeOutputs", "holdRadioTransmitPathsInactive",
        )),
        "authentication HIL hold arm function alters an RF/safety path",
    )

    timeout = re.search(
        r"kWifiAuthentication[A-Za-z0-9_]*Hold[A-Za-z0-9_]*"
        r"TimeoutMs=(\d+)U", entry)
    require(failures, timeout is not None,
            "authentication HIL hold has no explicit millisecond bound")
    if timeout is not None:
        timeout_ms = int(timeout.group(1))
        require(failures, 1 <= timeout_ms <= 5000,
                "authentication HIL hold exceeds the 5 s test-only bound")
    require(
        failures,
        "armWifiAuthenticationSurveyTerminalHoldDeadline()" in hold_arm and
        "esp_timer_get_time()" in entry,
        "authentication HIL hold is not armed from monotonic time",
    )

    hil_end = braced_block(entry, "voidemitHilSessionEnd(Stream&reply,")
    require(failures, "HilSessionStatus::Ended" in hil_end,
            "cannot locate successful hil.end path")
    require(
        failures,
        "clearWifiAuthentication" in hil_end and "Hold" in hil_end,
        "successful hil.end does not clear authentication transition hold",
    )
    hold_expiry = braced_block(
        entry, "voidexpireWifiAuthenticationSurveyTerminalHold()")
    survey_service = braced_block(entry, "voidserviceProductSurveyWorker()")
    require(
        failures,
        "clearWifiAuthenticationSurveyTerminalHold()" in hold_expiry,
        "authentication HIL hold is not cleared on timeout",
    )
    require(
        failures,
        "clearWifiAuthenticationSurveyTerminalHold()" in survey_service and
        "wifiAuthenticationSurveyTerminalHoldArmed" in survey_service and
        "WifiAuthenticationProductState::WaitingForSurveyStop" in
        survey_service,
        "authentication HIL hold is not one-shot at the survey terminal",
    )
    for name, source in (("capture", capture), ("scanner", scanner)):
        require(
            failures,
            "hil-hold" not in source and "SurveyTerminalHold" not in source and
            "surveyTerminalHold" not in source,
            f"test-only authentication hold leaked into {name} RF adapter",
        )

    # The UI action acknowledgement is the proof that Waiting was entered.
    # Waiting is transitional: a subsequent read-only query may legitimately
    # see Running/Failed, so the runner must send Back immediately in the held
    # edge and wait for Running directly in the normal edge.
    require(
        failures,
        'b"wifi.authentication.hil-hold-survey-stoponce"' in runner_compact,
        "runner does not arm the exact one-shot transition hold",
    )
    for marker in (
        '"leshy.wifi.authentication.hil_hold.v1"',
        '"kind":"armed"',
        '"status":"armed"',
        '"replayed":False',
        '"runtime_event":"authentication_waiting_for_survey_stop"',
    ):
        require(failures, marker in runner_compact,
                f"runner does not retain exact waiting acknowledgement: {marker}")

    cancel_start = runner.find("cancel_requested_ui = action(device, \"right\")")
    cancel_back = runner.find("cancel_back_ui = action(device, \"left\")",
                              max(cancel_start, 0))
    cancel_window = (runner[cancel_start:cancel_back]
                     if cancel_start >= 0 and cancel_back > cancel_start else "")
    require(failures, bool(cancel_window),
            "cannot locate held Back-during-wait runner window")
    require(
        failures,
        '"state": "waiting_for_survey_stop"' not in cancel_window,
        "runner still asserts a stable transitional auth query before Back",
    )

    normal_start = runner.find("auth_requested_ui = action(device, \"right\")")
    normal_wait = runner.find("auth_running = wait_auth_state(",
                              max(normal_start, 0))
    normal_window = (runner[normal_start:normal_wait]
                     if normal_start >= 0 and normal_wait > normal_start else "")
    require(failures, bool(normal_window),
            "cannot locate normal waiting-to-running runner window")
    require(
        failures,
        '"state": "waiting_for_survey_stop"' not in normal_window,
        "runner still demands a stable waiting query before Running",
    )

    return failures


def main() -> int:
    try:
        failures = check_sources(
            ARDUINO_ENTRY.read_text(encoding="utf-8"),
            CAPTURE_HEADER.read_text(encoding="utf-8"),
            CAPTURE_SOURCE.read_text(encoding="utf-8"),
            SCANNER_SOURCE.read_text(encoding="utf-8"),
            INIT_PROFILE.read_text(encoding="utf-8"),
            RUNNER.read_text(encoding="utf-8"),
        )
    except OSError as error:
        print(f"wifi authentication transition contract failed: {error}",
              file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print(f"wifi authentication transition contract failed: {failure}",
                  file=sys.stderr)
        return 1
    print("wifi authentication transition contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
