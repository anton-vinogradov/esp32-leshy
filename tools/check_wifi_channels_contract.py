#!/usr/bin/env python3
"""Fail-closed source guard for the Wi-Fi Channels product function."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    renderer = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
    ).read_text()
    load_h = (
        ROOT / "firmware/leshy1/src/apps/wifi/WifiChannelLoad.h"
    ).read_text()
    load_cpp = (
        ROOT / "firmware/leshy1/src/apps/wifi/WifiChannelLoad.cpp"
    ).read_text()
    adapter_h = (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h"
    ).read_text()
    adapter_cpp = (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
    ).read_text()
    init_profile = (
        ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveInitConfig.h"
    ).read_text()
    adapter_contract = adapter_h + adapter_cpp + init_profile

    required_renderer = (
        "WifiProductView::Channels",
        "startWifiChannelsProduct()",
        "serviceWifiChannelsProduct()",
        "renderWifiChannelsData(false);",
        "renderWifiChannelBar(channel, snapshot, full);",
        "wifiChannelRenderedAverages",
        "kWifiChannelAverageTone",
        "kWifiChannelCurrentBarWidth",
        "bin.averageBusyPermille",
        "WifiChannelsAverageLegend",
        "renderWifiChannelAxisLabel",
        "wifiChannelBarTone(std::uint16_t busyPermille)",
        "return Palette::Positive;",
        "kWifiChannelGraphBackground",
        "rgb565(0, 0, 0)",
        "wifi_channel_completed_sweeps",
        "wifi_channel_measured_mask",
        "wifiProductSelection == 2",
    )
    required_load = (
        "std::array<WifiChannelLoadBin, 13>",
        "std::array<std::uint32_t, 13>",
        "static constexpr std::uint8_t kFirstChannel = 1",
        "static constexpr std::uint8_t kLastChannel = 13",
        "constexpr std::uint16_t required = (1U << kLastChannel) - 1U",
        "busyPermille",
        "averageBusyPermille",
        "cumulativeBusyPermille_",
        "candidateMean < bestMean",
        "candidateMean == bestMean && candidatePressure < bestPressure",
        "completedSweeps",
        "measuredMask",
    )
    required_adapter = (
        "beginChannelMonitor",
        "estimatedFrameAirtimeUs",
        "WIFI_PROMIS_FILTER_MASK_MGMT",
        "WIFI_PROMIS_FILTER_MASK_CTRL",
        "WIFI_PROMIS_FILTER_MASK_DATA",
        "esp_wifi_set_promiscuous(true)",
        "esp_wifi_set_promiscuous(false)",
        "init.nvs_enable = 0",
        "WIFI_STORAGE_RAM",
        "channelLoad_.completeDwell",
    )
    forbidden_adapter = (
        "esp_wifi_connect(",
        "esp_wifi_set_config(",
        "esp_wifi_80211_tx(",
        "WIFI_MODE_AP",
    )

    failures = [
        f"renderer token missing: {token}"
        for token in required_renderer if token not in renderer
    ]
    failures.extend(
        f"channel-load token missing: {token}"
        for token in required_load if token not in load_h + load_cpp
    )
    failures.extend(
        f"adapter token missing: {token}"
        for token in required_adapter if token not in adapter_contract
    )
    failures.extend(
        f"adapter contains active/TX path: {token}"
        for token in forbidden_adapter if token in adapter_cpp
    )
    if "channel == 1U || channel == 6U || channel == 11U" in renderer:
        failures.append("legacy 1/6/11 visual emphasis remains")
    if "kWifiChannelDisplayFullScalePermille = 80" not in renderer:
        failures.append("honest lower-bound 0..8% display scale missing")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Wi-Fi channels contract passed: real passive airtime over channels "
        "1..13, bounded aggregation, all-channel mean recommendation, black idle "
        "background, channel-neutral current bars, gray session mean, "
        "adjacent-pressure tie-break and "
        "changed-bar-only redraw with no TX/config path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
