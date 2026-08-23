#!/usr/bin/env python3
"""Fail-closed source guard for the first product Wi-Fi function."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    renderer = (
        ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
    ).read_text(encoding="utf-8")
    catalog_h = (
        ROOT / "firmware/leshy1/src/apps/wifi/WifiNetworkCatalog.h"
    ).read_text(encoding="utf-8")
    catalog_cpp = (
        ROOT / "firmware/leshy1/src/apps/wifi/WifiNetworkCatalog.cpp"
    ).read_text(encoding="utf-8")
    strings = (
        ROOT / "firmware/leshy1/src/ui/UiStrings.def"
    ).read_text(encoding="utf-8")
    required_renderer = (
        "WifiProductView::Menu",
        "WifiProductView::Networks",
        "WifiProductView::NetworkDetail",
        "wifiNetworkCatalog.upsert(observation)",
        "renderWifiNetworksData();",
        "renderWifiNetworkRow(index, currentFirst);",
        "productSurveyIncrementalRefreshPending",
        "renderInteractiveScreen(false);",
        "wifiProductView != WifiProductView::NetworkDetail",
        "TouchTargetLayout::HomeRows",
        "wifi_networks_unique",
        "wifi_networks_strongest_first",
        "wifi_network_catalog_revision",
        "wifiNetworkCatalog.indexOfIdentity(wifiSelectionAnchor)",
        "renderRadioSignalCard(wifiNetworkDetail.rssiDbm)",
    )
    required_catalog = (
        "static constexpr std::size_t kCapacity = 32",
        "bool upsert",
        "sameIdentity",
        "visibleFieldsDiffer",
        "sortStrongestFirst",
        "entries_[position - 1U].rssiDbm < current.rssiDbm",
        "bool WifiNetworkCatalog::strongestFirst() const",
        "indexOfIdentity",
    )
    required_strings = (
        "WifiMenuNetworks",
        "WifiNetworksSearching",
        "WifiNetworkDetailTitle",
        "WifiNetworkBssidFormat",
        "RadioChannelFormat",
        "RadioSignalLabel",
    )
    failures = [
        f"renderer token missing: {token}"
        for token in required_renderer if token not in renderer
    ]
    failures.extend(
        f"catalog token missing: {token}"
        for token in required_catalog
        if token not in catalog_h and token not in catalog_cpp
    )
    failures.extend(
        f"string token missing: {token}"
        for token in required_strings if token not in strings
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Wi-Fi networks contract passed: unique strongest-first BSSID rows, four-row "
        "touch UI, data-only live redraw and dense frozen detail chrome"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
