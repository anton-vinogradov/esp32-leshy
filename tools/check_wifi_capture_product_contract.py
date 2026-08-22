#!/usr/bin/env python3
"""Fail-closed source guard for the Wi-Fi packet recorder product route."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    entry = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
    ).read_text()
    capture_h = (
        ROOT / "firmware/leshy1/src/apps/capture/WifiFrameCapture.h"
    ).read_text()
    adapter_cpp = (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
    ).read_text()
    strings = (
        ROOT / "firmware/leshy1/src/ui/UiStrings.def"
    ).read_text()

    required_entry = (
        "WifiProductView::Capture",
        'case WifiProductView::Capture: return "capture";',
        "openWifiCaptureProduct()",
        "closeWifiCaptureProduct()",
        "wifiProductSelection == 3",
        "return index <= 3U;",
        "UiTextId::WifiCaptureTitle",
        "renderWifiCaptureLiveData()",
        "wifiCaptureRenderedFrames != stats.framesAccepted",
        "wifiCaptureRenderedChannel != channel",
        "wifiCaptureRenderedDrops != dropped",
        "Components::metricRow(0)",
        "Components::metricRow(1)",
        "Components::metricRow(3)",
        "nextCaptureUiRefreshUs = nowUs + 500000ULL;",
        "display.startWrite();\n        renderWifiCaptureLiveData();\n"
        "        display.endWrite();",
        "if (wifiProductView == WifiProductView::Capture) return;",
        "capturePersistState = CapturePersistState::Confirm;",
        "requestWifiFrameCapturePersist()",
        "kProductWifiFrameCapturePlan",
    )
    required_capture = (
        "durationMs = 10000",
        "channelDwellMs = 120",
        "maximumFrames = 16",
        "snapLength = 256",
    )
    required_adapter = (
        "WIFI_PROMIS_FILTER_MASK_MGMT",
        "WIFI_PROMIS_FILTER_MASK_CTRL",
        "WIFI_PROMIS_FILTER_MASK_DATA",
        "esp_wifi_set_promiscuous(true)",
        "esp_wifi_set_promiscuous(false)",
        "init.nvs_enable = 0",
        "WIFI_STORAGE_RAM",
    )
    forbidden_adapter = (
        "esp_wifi_connect(",
        "esp_wifi_set_config(",
        "esp_wifi_80211_tx(",
        "WIFI_MODE_AP",
    )
    required_strings = (
        "WifiCaptureTitle",
        'u8"WI-FI / ПАКЕТЫ"',
        "CaptureWifiPurpose",
        "CaptureDurationUser",
        "CaptureAutoChannelsUser",
        "CaptureIdentifiersWarning",
    )

    failures = [
        f"product route token missing: {token}"
        for token in required_entry if token not in entry
    ]
    failures.extend(
        f"bounded capture token missing: {token}"
        for token in required_capture if token not in capture_h
    )
    failures.extend(
        f"passive adapter token missing: {token}"
        for token in required_adapter if token not in adapter_cpp
    )
    failures.extend(
        f"adapter contains active/TX path: {token}"
        for token in forbidden_adapter if token in adapter_cpp
    )
    failures.extend(
        f"user copy token missing: {token}"
        for token in required_strings if token not in strings
    )

    service_start = entry.find("void serviceWifiFrameCapture()")
    service_end = entry.find("bool startInfraredCapture()", service_start)
    service = entry[service_start:service_end]
    if service_start < 0 or service_end < 0:
        failures.append("capture service function not found")
    else:
        periodic_start = service.find("else if ((productRoute || captureRoute)")
        periodic = service[periodic_start:]
        if periodic_start < 0:
            failures.append("bounded live-refresh branch missing")
        if "renderInteractiveScreen" in periodic:
            failures.append("periodic live branch performs a full-screen redraw")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Wi-Fi capture product contract passed: direct passive bounded PCAP "
        "workflow, explicit privacy confirmation, retained Wi-Fi ownership "
        "and changed-metric-only live refresh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
