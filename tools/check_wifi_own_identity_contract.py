#!/usr/bin/env python3
"""Static product gate for Leshy-owned Wi-Fi identity privacy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_H = ROOT / "firmware/leshy1/src/services/privacy/WifiOwnIdentityPolicy.h"
POLICY_CPP = ROOT / "firmware/leshy1/src/services/privacy/WifiOwnIdentityPolicy.cpp"
PLATFORM_H = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoWifiOwnIdentity.h"
PLATFORM_CPP = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoWifiOwnIdentity.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
SCANNER = ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveScanner.cpp"
CAPTURE = ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
WEB = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoCompanionWebService.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> int:
    policy = POLICY_H.read_text(encoding="utf-8") + POLICY_CPP.read_text(
        encoding="utf-8")
    platform = PLATFORM_H.read_text(encoding="utf-8") + PLATFORM_CPP.read_text(
        encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    scanner = SCANNER.read_text(encoding="utf-8")
    capture = CAPTURE.read_text(encoding="utf-8")
    web = WEB.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")

    for token in (
        "PrivatePerSession",
        "Hardware",
        "Station = 0U",
        "AccessPoint = 1U",
        "(result.address[0] & 0xfcU) | 0x02U",
        "differsFromHardware",
    ):
        require(token in policy, f"missing bounded identity policy: {token}")

    for token in (
        "esp_fill_random",
        "esp_wifi_get_mac",
        "esp_wifi_set_mac",
        "clearAddress(hardware)",
        "clearAddress(generated.address)",
        "rawAddressRetained = false",
    ):
        require(token in platform, f"missing platform privacy boundary: {token}")
    for forbidden in ("Serial.print", "printf(", "Preferences", "File"):
        require(forbidden not in platform,
                f"identity platform exports or persists raw address: {forbidden}")

    for token in (
        "kWifiOwnIdentityModeKey = \"wifiid.v1\"",
        "loadWifiOwnIdentityMode()",
        "saveWifiOwnIdentityMode(requested)",
        "wifi.identity.state",
        "leshy.wifi.own_identity.v1",
        "\\\"raw_address_retained\\\":false",
        "ConnectivitySetupView::Privacy",
    ):
        require(token in entry, f"missing user/configuration route: {token}")

    require(scanner.count("wifiOwnIdentity().apply(WIFI_IF_STA)") == 1,
            "passive scanner must apply one session identity")
    require(capture.count("wifiOwnIdentity().apply(WIFI_IF_STA)") == 3,
            "all three passive capture lifecycles need session identity")
    require(web.count("wifiOwnIdentity().apply(WIFI_IF_AP)") == 1,
            "temporary AP must apply one session identity")
    for source, name in ((scanner, "scanner"), (capture, "capture"),
                         (web, "temporary AP")):
        require(source.find("wifiOwnIdentity().apply") <
                source.find("esp_wifi_start()"),
                f"{name} applies identity only after radio start")

    for token in (
        "THIS DEVICE ONLY",
        "OTHER DEVICES UNCHANGED",
        "RAM ONLY · RECOMMENDED",
        "NO EMULATION · NO EXPORT",
    ):
        require(token in strings, f"missing truthful user copy: {token}")

    print("Wi-Fi own-identity contract passed: per-session local-admin STA/AP "
          "identity, hardware opt-out, RAM-only raw address, truthful scope, "
          "and pre-radio lifecycle hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
