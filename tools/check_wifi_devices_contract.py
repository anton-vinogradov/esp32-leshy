#!/usr/bin/env python3
"""Fail-closed source guard for the Wi-Fi Devices product function."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    renderer = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text()
    catalog_h = (ROOT / "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.h").read_text()
    catalog_cpp = (ROOT / "firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.cpp").read_text()
    oui_h = (ROOT / "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.h").read_text()
    oui_cpp = (ROOT / "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.cpp").read_text()
    navigation = (ROOT / "firmware/leshy1/src/apps/wifi/WifiDeviceNavigationOrder.h").read_text()
    adapter_h = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h").read_text()
    adapter_cpp = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp").read_text()
    init_profile = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveInitConfig.h").read_text()
    adapter_contract = adapter_h + adapter_cpp + init_profile
    strings = (ROOT / "firmware/leshy1/src/ui/UiStrings.def").read_text()
    runner = (ROOT / "tools/run_1x_wifi_devices_hil.py").read_text()
    checker = (ROOT / "tools/check_wifi_devices_run.py").read_text()

    required_renderer = (
        "WifiProductView::Devices",
        "WifiProductView::DeviceDetail",
        "startWifiDevicesProduct()",
        "serviceWifiDevicesProduct()",
        "renderWifiDevicesData();",
        "renderWifiDeviceRow(index, currentFirst);",
        "wifiProductView == WifiProductView::Devices",
        "wifi_device_monitor_active",
        "wifi_devices_strongest_first",
        "wifi_device_clients_dropped",
        "wifiDeviceNavigationOrder.lock(wifiDeviceCatalog)",
        "wifiDeviceNavigationOrder.locked()",
        "nextWifiDeviceUiRefreshUs = nowUs + 250000ULL",
        "renderRadioSignalCard(",
        "renderRadioSignalCardDelta(",
        "WifiDeviceDetailVisual",
        "wifiDeviceDetailContentClears",
        "wifiDeviceRadarDeltaRepaints",
        "pushLiveMetaTextRow",
        "leshy.wifi.device_detail.v1",
        "wifiFrameCapture.lockDeviceChannel(",
        "wifiFrameCapture.unlockDeviceChannel(nowUs)",
        "wifiOuiDatabase.lookup(",
        "wifi_device_detail_wps_identity_known",
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
        "parseInformationElements",
        "parseWpsAttributes",
        "WifiDeviceGeneration::Wifi4",
        "WifiDeviceGeneration::Wifi5",
        "WifiDeviceGeneration::Wifi6",
        "locallyAdministered",
        "rssiTrendDb",
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
        "lockDeviceChannel",
        "deviceChannelLocked_",
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
        "RadioChannelFormat",
        "RadioSignalLabel",
        "WifiDevicePrivateAddress",
        "WifiDeviceMakerFormat",
        "WifiDeviceNetworkFormat",
        "WifiDeviceTrendCloser",
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
        for token in required_adapter if token not in adapter_contract
    )
    failures.extend(
        f"adapter contains active/TX path: {token}"
        for token in forbidden_adapter if token in adapter_cpp
    )
    failures.extend(
        f"string token missing: {token}"
        for token in required_strings if token not in strings
    )
    for token in ("kRecordSize = 32", "kNameSize = 29", "bool lookup("):
        if token not in oui_h + oui_cpp:
            failures.append(f"OUI database token missing: {token}")
    for token in ("std::uint32_t orderHash", "addresses_", "locked_"):
        if token not in navigation:
            failures.append(f"navigation token missing: {token}")
    asset = ROOT / "firmware/leshy1/assets/oui.bin"
    metadata_path = ROOT / "firmware/leshy1/assets/oui.json"
    if not asset.is_file() or not metadata_path.is_file():
        failures.append("release-pinned IEEE OUI asset or metadata is missing")
    else:
        metadata = json.loads(metadata_path.read_text())
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        if metadata.get("schema") != "leshy.wifi_oui_asset.v1":
            failures.append("OUI asset metadata schema mismatch")
        if metadata.get("asset_sha256") != digest:
            failures.append("OUI asset hash does not match metadata")
        if metadata.get("records", 0) < 10_000:
            failures.append("OUI asset is unexpectedly sparse")
        if metadata.get("asset_bytes") != asset.stat().st_size:
            failures.append("OUI asset byte count does not match metadata")
    if "type == 2U && toDistribution && !fromDistribution" not in catalog_cpp:
        failures.append("connected-client inference is not limited to To-DS data")
    if "subtype == 4U" not in catalog_cpp:
        failures.append("searching-client inference does not require probe request")
    for token in (
            'RUN_SCHEMA = "leshy.wifi_devices_hil.run.v4"',
            "TemporaryDeviceLockHil",
            '"device_lock_fixture": device_lock_fixture',
            '"product_device_lock_namespace_mutated": False',
            '"wifi_product_view": "device_detail"',
            '"wifi_device_channel_locked": True',
            '"wifi_device_detail_last_seen_us"',
            'DETAIL_SCHEMA = "leshy.wifi.device_detail.v1"',
            '"detail_oracle_first"',
            '"detail_oracle_second"',
            '"live_detail_atomic_rows": True',
            '"live_detail_no_full_repaint_after_entry": True',
            '"wifi-device-live-detail-first"',
            '"wifi-device-live-detail-second"',
            '"identity_changed_pixels"',
            '"live_changed_pixels"'):
        if token not in runner + checker:
            failures.append(f"integrated live-detail HIL token missing: {token}")
    for token in (
            "WifiProductView::DeviceRadar",
            "renderWifiDeviceRadar(",
            'return "device_radar"'):
        if token in renderer:
            failures.append(f"separate device-radar route remains: {token}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Wi-Fi devices contract passed: passive client fingerprint, embedded "
        "IEEE OUI lookup, identity-stable list, facts + channel-locked live "
        "radar in one detail screen, bounded redraw and no TX/config path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
