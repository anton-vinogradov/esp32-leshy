#!/usr/bin/env python3
"""Constrain the new ordinary-product AP adapter, not a blanket Wi-Fi exemption."""
from pathlib import Path
import re
from check_live_render_contract import function_body
ROOT = Path(__file__).resolve().parent.parent

def check(adapter, entry):
    failures = []
    allowed = {"esp_wifi_init", "esp_wifi_set_storage", "esp_wifi_set_mode",
               "esp_wifi_get_mac", "esp_wifi_set_config", "esp_wifi_start",
               "esp_wifi_set_max_tx_power", "esp_wifi_get_max_tx_power",
               "esp_wifi_stop", "esp_wifi_deinit"}
    calls = set(re.findall(r"\b(esp_wifi_\w+)\s*\(", adapter))
    if calls != allowed: failures.append("AP SDK surface changed")
    for marker in ("init.nvs_enable = 0", "WIFI_STORAGE_RAM", "WIFI_MODE_AP",
                   "WIFI_AUTH_WPA2_PSK", "WIFI_CIPHER_TYPE_CCMP",
                   "WifiTestNetwork::kChannel", 'wifiOwnIdentity().apply(WIFI_IF_AP)',
                   "esp_fill_random", '"LESHY-TEST-%02X%02X"',
                   "esp_wifi_set_max_tx_power(8)", "power_ != 8",
                   "password[i] = 0", "cleanupComplete_ = complete",
                   "pinMode(0, INPUT_PULLUP)", "digitalRead(0) == LOW"):
        if marker not in adapter: failures.append("missing AP bound: " + marker)
    for pattern in (r"\besp_netif_\w+\s*\(", r"\bWiFi\.", r"\bSD\.",
                    r"\b(?:fopen|socket|esp_http_server)\s*\("):
        if re.search(pattern, adapter): failures.append("unapproved AP side effect")
    try:
        start = function_body(entry, "bool startWifiTestNetwork()")
        service = function_body(entry, "bool serviceWifiTestNetwork()")
        stop = function_body(entry, "void stopWifiTestNetwork(")
        render = function_body(entry, "void renderWifiTestNetwork(")
        query = function_body(entry, "void emitWifiTestNetworkState(")
    except ValueError:
        return failures + ["missing product bridge"]
    for marker in ("SelfTestView::WifiNetwork", "runtimeSafetyWatchdogReady",
                   "safetySupervisor.armed()", "DeviceLockOperation::ProtectedUi",
                   "resourceBroker.ownerOf(Resource::EspRf)", "kNoOwner",
                   "resourceBroker.acquire", "digitalRead(0) != LOW"):
        if marker not in start: failures.append("missing admission: " + marker)
    for marker in ("wifiTestNetwork.due(millis())", "digitalRead(0) == LOW",
                   "safetySupervisor.latched()", "uiController.page() != 6"):
        if marker not in service: failures.append("missing runtime stop: " + marker)
    if stop.index("if (!stopped)") > stop.index("resourceBroker.release"):
        failures.append("lease released before confirmed cleanup")
    if "ESP.restart()" not in stop: failures.append("cleanup failure not fail-closed")
    if "wifiTestTextCache.changed" not in render or "pushLiveMetaTextRow" not in render:
        failures.append("shared retained paint missing")
    if "display.fillRect" in render: failures.append("full clear in live paint")
    if ".begin(" in query or ".stop(" in query: failures.append("state query mutates radio")
    if "displayPassword" in query or "password" in query.lower():
        failures.append("state query leaks AP credential")
    if entry.count("boardWifiTestNetwork.displayPassword()") != 1:
        failures.append("AP credential must have only the local TFT consumer")
    for marker in ("boardWifiTestNetwork.displayPassword()",
                   "wifiTestTextCache.changed(4, credentialState",
                   "wifiTestTextCache.publish(4, credentialState",
                   "UiTextId::WifiTestPasswordIdle", "secret[i] = 0"):
        if marker not in render: failures.append("missing ephemeral TFT credential bound: " + marker)
    return failures

def check_repository():
    base = ROOT / "firmware/leshy1/src/platform/arduino"
    failures = check((base / "BoardWifiTestNetwork.cpp").read_text(),
                     (base / "ArduinoEntry.cpp").read_text())
    if 'return started_ ? password_.data() : "";' not in (base / "BoardWifiTestNetwork.h").read_text():
        failures.append("credential visible while AP inactive")
    return failures

if __name__ == "__main__":
    failures = check_repository()
    if failures: raise SystemExit("\n".join(failures))
    print("Wi-Fi product AP contract: exact SDK surface, normal menu, admission, stop and retained paint passed")
