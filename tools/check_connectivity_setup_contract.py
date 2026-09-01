#!/usr/bin/env python3
"""Static product gate for offline-first scoped USB/temporary Wi-Fi setup."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
CONTROLLER_H = ROOT / "firmware/leshy1/src/ui/ConnectivitySetupController.h"
CONTROLLER_CPP = ROOT / "firmware/leshy1/src/ui/ConnectivitySetupController.cpp"
CONNECTIVITY = ROOT / "firmware/leshy1/src/services/companion/CompanionConnectivity.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> int:
    entry = ENTRY.read_text(encoding="utf-8")
    controller = (CONTROLLER_H.read_text(encoding="utf-8") +
                  CONTROLLER_CPP.read_text(encoding="utf-8"))
    connectivity = CONNECTIVITY.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")

    for token in (
        "kConnectivityPage = 17",
        "kPowerPage, 5, kConnectivityPage, kDeviceLockPage,",
        "openTemporaryWifiFromConnectivity()",
        "connectivitySetupController.activate()",
        "connectivity_view",
        "connectivity_selection",
        "webCompanionOverlay = true",
    ):
        require(token in entry, f"missing product connectivity route: {token}")

    for token in (
        "ConnectivitySetupView::Menu",
        "ConnectivitySetupView::UsbGuide",
        "ConnectivitySetupView::WifiUnavailable",
        "TemporaryWifiRequested",
        "kActionCount = 2U",
    ):
        require(token in controller, f"missing bounded setup state: {token}")

    for forbidden in ("Preferences", "NVS", "File", "ssid", "passphrase"):
        require(forbidden not in controller,
                f"navigation controller owns secret/persistence API: {forbidden}")

    for token in (
        "ConnectivityUsbNote",
        "RECOMMENDED · NO PASSWORD",
        "ConnectivityWifiNote",
        "PHONE / BROWSER · ONE SESSION",
        "ConnectivityOfflineNote",
        "SCAN AND LIBRARY NEED NO NETWORK",
        "ConnectivityPrivacyNote",
        "SECRETS ARE NEVER EXPORTED",
        "NO CREDENTIAL WAS CREATED",
    ):
        require(token in strings, f"missing truthful user copy: {token}")

    for token in (
        "secureClear(ssid.data(), ssid.size())",
        "secureClear(passphrase.data(), passphrase.size())",
        "per-run SSID",
    ):
        require(token in connectivity,
                f"missing ephemeral credential boundary: {token}")

    direct_start = entry.find("bool openTemporaryWifiFromConnectivity()")
    next_function = entry.find("\nbool ", direct_start + 8)
    require(direct_start >= 0 and next_function > direct_start,
            "cannot isolate temporary Wi-Fi route")
    route = entry[direct_start:next_function]
    require("startWebCompanion()" not in route,
            "first connection selection must not start Wi-Fi")
    require("webCompanionCredentials" not in route,
            "first connection selection must not create/expose credentials")
    require("DeviceLockOperation::ProtectedUi" in route,
            "temporary Wi-Fi route lacks protected admission")

    print("Connectivity setup contract passed: task-first USB/temporary Wi-Fi "
          "route, second-confirmation AP boundary, ephemeral secret cleanup, "
          "and explicit offline Survey/Library guarantee")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
