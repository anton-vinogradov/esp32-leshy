#!/usr/bin/env python3
"""Fail-closed source guard for the Wi-Fi Devices product function."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    renderer = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text()
    catalog_h = (ROOT / "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.h").read_text()
    catalog_cpp = (ROOT / "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.cpp").read_text()
    adapter_h = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h").read_text()
    adapter_cpp = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp").read_text()
    strings = (ROOT / "firmware/leshy1/src/ui/UiStrings.def").read_text()

    required_renderer = (
        "WifiProductView::Devices",
        "WifiProductView::DeviceDetail",
        "startWifiDevicesProduct()",
        "serviceWifiDevicesProduct()",
        "renderWifiDevicesData();",
        "renderWifiDeviceRow(index, currentFirst);",
        "wifiProductView == WifiProductView::Devices",
        "wifi_device_monitor_active",
        "wifi_device_clients_dropped",
        "nextWifiDeviceUiRefreshUs = nowUs + 250000ULL",
    )
    required_catalog = (
        "static constexpr std::size_t kCapacity = 32",
        "decodeWifiClientFrame",
        "WifiDeviceState::Searching",
        "WifiDeviceState::Connecting",
        "WifiDeviceState::Connected",
        "oldestIndex",
        "sortStrongestFirst",
        "entries_[position - 1U].rssiDbm < current.rssiDbm",
        "bool WifiDeviceCatalog::strongestFirst() const",
        "indexOfAddress",
    )
    required_adapter = (
        "beginDeviceMonitor",
        "pollDevice",
        "kDeviceQueueCapacity = 64",
        "WIFI_PROMIS_FILTER_MASK_MGMT",
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
        "WifiDevicesListening",
        "WifiDeviceSearching",
        "WifiDeviceConnected",
        "WifiDeviceDetailTitle",
    )

    failures = [
        f"renderer token missing: {token}"
        for token in required_renderer if token not in renderer
    ]
    failures.extend(
        f"catalog token missing: {token}"
        for token in required_catalog if token not in catalog_h + catalog_cpp
    )
    failures.extend(
        f"adapter token missing: {token}"
        for token in required_adapter if token not in adapter_h + adapter_cpp
    )
    failures.extend(
        f"adapter contains active/TX path: {token}"
        for token in forbidden_adapter if token in adapter_cpp
    )
    failures.extend(
        f"string token missing: {token}"
        for token in required_strings if token not in strings
    )
    if "type == 2U && toDistribution && !fromDistribution" not in catalog_cpp:
        failures.append("connected-client inference is not limited to To-DS data")
    if "subtype == 4U" not in catalog_cpp:
        failures.append("searching-client inference does not require probe request")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Wi-Fi devices contract passed: passive client-only inference, bounded "
        "queue/strongest-first catalog, data-only redraw, frozen detail and no TX/config path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
