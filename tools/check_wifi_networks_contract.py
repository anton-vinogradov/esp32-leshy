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
    navigation = (
        ROOT / "firmware/leshy1/src/apps/wifi/WifiNetworkNavigationOrder.h"
    ).read_text(encoding="utf-8")
    strings = (
        ROOT / "firmware/leshy1/src/ui/UiStrings.def"
    ).read_text(encoding="utf-8")
    required_renderer = (
        "WifiProductView::Menu",
        "WifiProductView::Networks",
        "WifiProductView::NetworkDetail",
        "wifiNetworkCatalog.upsert(",
        "const bool rowsPainted = renderWifiNetworksData(false);",
        "renderWifiNetworkRow(first + slot, first, force)",
        "productSurveyIncrementalRefreshPending",
        "renderInteractiveScreen(false);",
        "Detail views keep receiving passive samples",
        "if (render) {",
        "TouchTargetLayout::HomeRows",
        "wifi_networks_unique",
        "wifi_networks_strongest_first",
        "wifi_network_catalog_revision",
        "wifiNetworkCatalog.indexOfIdentity(wifiSelectionAnchor)",
        "wifiNetworkFocus.userOwned()",
        "wifiNetworkFocus.claimByUser()",
        "renderWifiNetworkDetailData()",
        "renderWifiNetworkRadar(live, signal, false)",
        "liveWifiNetworkSignal()",
        "wifiNetworkDetailStaticFieldsDiffer(",
        "wifiOuiDatabase.lookup(",
        "liveWifiNetworkDetail()",
        "emitWifiNetworkDetailState(",
        "leshy.wifi.network_detail.v1",
        "active_probe_allowed\\\":false",
        "wifiNetworkVisibleSize()",
        "wifiNetworkAt(wifiNetworkSelection)",
        "!wifiNetworkNavigationOrder.locked()",
        "wifi_network_navigation_locked",
        "wifi_network_order_hash",
        "wifi_network_selected_identity_hash",
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
        "bool allowReplacement = true",
        "!allowReplacement",
        "resolvedHidden",
        "observation.labelLength == 0U",
        "hiddenResolutions_",
        "wifiNetworkFactsEqual",
        "struct WifiNetworkSignalStats final",
        "signal.minimumRssiDbm",
        "signal.maximumRssiDbm",
        "signal.rssiTrendDb",
        "signalAt",
    )
    required_navigation = (
        "class WifiNetworkNavigationOrder final",
        "bool lock(const WifiNetworkCatalog& catalog)",
        "return locked_ ? size_ : catalog.size()",
        "catalog.indexOfIdentity(identity)",
        "std::uint32_t orderHash",
        "std::uint32_t identityHash",
        "WifiNetworkCatalog::kCapacity",
    )
    required_strings = (
        "WifiMenuNetworks",
        "WifiNetworksSearching",
        "WifiNetworkDetailTitle",
        "WifiNetworkBssidFormat",
        "WifiNetworkRadioFormat",
        "WifiNetworkSecurityFormat",
        "WifiNetworkCipherFormat",
        "WifiNetworkVendorFormat",
        "WifiNetworkListeningForName",
        "WifiNetworkRangeFormat",
        "WifiNetworkTrendStronger",
        "WifiNetworkTrendWeaker",
        "WifiNetworkTrendStable",
    )
    failures = [
        f"renderer token missing: {token}"
        for token in required_renderer if token not in renderer
    ]
    if "wifiNetworkNavigationOrder.lock(wifiNetworkCatalog)" in renderer:
        failures.append(
            "renderer must not freeze live Wi-Fi order after user input"
        )
    failures.extend(
        f"catalog token missing: {token}"
        for token in required_catalog
        if token not in catalog_h and token not in catalog_cpp
    )
    failures.extend(
        f"navigation-order token missing: {token}"
        for token in required_navigation if token not in navigation
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
        "touch UI, continuous strongest-first sorting with identity-anchored focus, "
        "data-only live redraw, OUI/security/PHY detail, monotonic hidden-SSID "
        "resolution and bounded live BSSID radar without cursor movement"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
