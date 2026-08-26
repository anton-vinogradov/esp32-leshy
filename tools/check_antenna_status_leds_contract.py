#!/usr/bin/env python3
"""Fail closed unless antenna status LEDs retain the proven 0.x contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    paths = {
        "profile": ROOT / "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h",
        "model_header": ROOT / "firmware/leshy1/src/ui/AntennaStatusController.h",
        "model_source": ROOT / "firmware/leshy1/src/ui/AntennaStatusController.cpp",
        "adapter_header": ROOT / "firmware/leshy1/src/platform/arduino/BoardAntennaStatusLeds.h",
        "adapter_source": ROOT / "firmware/leshy1/src/platform/arduino/BoardAntennaStatusLeds.cpp",
        "entry": ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
        "strings": ROOT / "firmware/leshy1/src/ui/UiStrings.def",
        "version": ROOT / "firmware/leshy1/platformio.ini",
        "runner": ROOT / "tools/run_1x_antenna_status_leds_hil.py",
        "delta": ROOT / "tests/hil/delta-scopes/antenna-status-leds-0.171.json",
    }
    failures: list[str] = []
    for name, path in paths.items():
        if not path.is_file():
            failures.append(f"missing {name}: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    texts = {name: path.read_text(encoding="utf-8")
             for name, path in paths.items()}
    requirements = {
        "profile": ("kStatusLedPin = 1", "kStatusLedCount = 4"),
        "model_header": (
            "kCc1101Mask = 0x01U", "kBrightnessCount = 6",
            "kDefaultBrightnessIndex = 1", "zeroBasedSlot + 1U",
            "(slotMask & 0x07U) << 1U",
        ),
        "model_source": (
            "{0, 2, 3, 5, 8, 12}",
            "receiveMask = static_cast<std::uint8_t>(receiveMask & ~faultMask)",
        ),
        "adapter_header": ("Adafruit_NeoPixel", "NEO_GRB + NEO_KHZ800"),
        "adapter_source": (
            "pixels_.setBrightness", "pixels_.Color(255, 0, 0)",
            "pixels_.Color(0, 255, 0)", "pixels_.show()",
        ),
        "entry": (
            'kStatusLedBrightnessKey = "led.v1"',
            'kLegacyStatusLedBrightnessKey = "led_br"',
            "loadStatusLedBrightnessIndex", "saveStatusLedBrightnessIndex",
            "serviceAntennaStatusLeds", "activeSlotMask",
            "antenna_led_brightness_raw", "antenna_led_receive_mask",
            "antenna_led_fault_mask",
        ),
        "strings": (
            "LESHY_UI_TEXT(SettingsAntennaLeds,",
            "LESHY_UI_TEXT(SettingsAntennaLedsOff,",
            "LESHY_UI_TEXT(SettingsAntennaLeds2,",
            "LESHY_UI_TEXT(SettingsAntennaLeds12,",
        ),
        "version": ("Adafruit NeoPixel@1.12.3",),
        "runner": (
            "BRIGHTNESS_RAW = (0, 2, 3, 5, 8, 12)",
            'parser.add_argument("--restore-raw"',
            'parser.add_argument("--restore-only"',
            "antenna_led_receive_mask=(nrf_slots & 0x07) << 1",
            "antenna_led_receive_mask=1", "cardputer_ports_opened",
        ),
        "delta": (
            '"id": "antenna-status-leds-0.171"',
            '"one changed-candidate flash on original board-01 only"',
        ),
    }
    for name, tokens in requirements.items():
        for token in tokens:
            if token not in texts[name]:
                failures.append(f"{name} missing: {token}")

    for forbidden in ("delay(", "millis("):
        if forbidden in texts["adapter_source"]:
            failures.append(
                f"physical LED adapter must be state-change-only: {forbidden}")
    current_version = re.search(
        r'LESHY1_VERSION=\\"(\d+)\.(\d+)\.[^\\"]+\\"',
        texts["version"])
    if current_version is None or (
            int(current_version.group(1)), int(current_version.group(2))) < (0, 171):
        failures.append("current product predates antenna-status LED support")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("antenna-status LEDs passed: CC/N1/N2/N3 mapping, 0.x brightness ladder, RX/fault colors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
