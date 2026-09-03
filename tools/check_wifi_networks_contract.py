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
    runner = (
        ROOT / "tools/run_1x_wifi_networks_hil.py"
    ).read_text(encoding="utf-8")
    run_checker = (
        ROOT / "tools/check_wifi_networks_run.py"
    ).read_text(encoding="utf-8")
    heap_policy = (
        ROOT / "tools/wifi_heap_plateau_policy.py"
    ).read_text(encoding="utf-8")
    heap_policy_test = (
        ROOT / "tools/test_wifi_heap_plateau_policy.py"
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
    for name, source in (("runner", runner), ("run checker", run_checker)):
        for token in (
            "MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES",
            "wifi_heap_plateau_failures(",
            "one_time_heap_initialization_ceiling_bytes",
        ):
            if token not in source:
                failures.append(f"{name} heap-policy token missing: {token}")
    for token in (
        'select_entry = action(device, "select")',
        '"action": "select", "changed": True',
        'right_entry = action(device, "right")',
        '"single_select_entry"',
        '"single_right_entry"',
    ):
        if token not in runner and token not in run_checker:
            failures.append(f"single-entry regression missing: {token}")
    for token in (
        "MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES = 8 * 1024",
        "if final_free != first_free:",
        "if final_total != first_total:",
        "Wi-Fi one-time heap initialization is unbounded",
    ):
        if token not in heap_policy:
            failures.append(f"heap policy token missing: {token}")
    for token in (
        "66_664, 59_320, 59_320, 142_284, 142_284",
        "MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES - 1",
        "test_rejects_post_warm_leak_and_total_change",
    ):
        if token not in heap_policy_test:
            failures.append(f"heap policy regression missing: {token}")
    if 'LESHY_UI_TEXT(AppWifi, Body, 196, "WI-FI", u8"WI-FI")' not in strings:
        failures.append(
            "Home must name the Wi-Fi section, not duplicate its Nearby "
            "Networks child task"
        )
    if (
        'LESHY_UI_TEXT(NoteWifiReady, Meta, 196, '
        '"NETWORKS · DEVICES · CHANNELS", '
        'u8"СЕТИ · УСТРОЙСТВА · КАНАЛЫ")'
    ) not in strings:
        failures.append(
            "Home Wi-Fi note must preview the section tree so its first "
            "Select cannot look ignored"
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
