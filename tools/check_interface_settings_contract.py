#!/usr/bin/env python3
"""Fail closed unless the S5 interface-settings implementation is truthful."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    paths = {
        "header": ROOT / "firmware/leshy1/src/ui/InterfaceSettingsController.h",
        "source": ROOT / "firmware/leshy1/src/ui/InterfaceSettingsController.cpp",
        "theme": ROOT / "firmware/leshy1/src/ui/VisualTheme.h",
        "renderer": ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
        "strings": ROOT / "firmware/leshy1/src/ui/UiStrings.def",
        "version": ROOT / "firmware/leshy1/platformio.ini",
        "delta": ROOT / "tests/hil/delta-scopes/interface-settings-0.145.json",
    }
    failures: list[str] = []
    for name, path in paths.items():
        if not path.is_file():
            failures.append(f"missing {name}: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    header = paths["header"].read_text(encoding="utf-8")
    source = paths["source"].read_text(encoding="utf-8")
    theme = paths["theme"].read_text(encoding="utf-8")
    renderer = paths["renderer"].read_text(encoding="utf-8")
    strings = paths["strings"].read_text(encoding="utf-8")
    version = paths["version"].read_text(encoding="utf-8")

    required_header = (
        "enum class InterfaceTheme", "enum class InterfaceSetting",
        "kItemCount = 5", "kBrightnessCount = 5",
        "static bool soundAvailable() { return false; }",
    )
    required_source = (
        "255, 176, 112, 64, 24", "100, 69, 44, 25, 9",
        "brightnessIndex < kBrightnessCount ? brightnessIndex : 0",
        "theme == InterfaceTheme::HighContrast",
    )
    required_renderer = (
        'kUiBrightnessKey = "bright.v1"', 'kUiThemeKey = "theme.v1"',
        "renderSettingsPage", "Components::homeRow(index - firstVisible)",
        "saveUiBrightnessIndex", "saveUiTheme",
        "interfaceSettingsController.brightnessDuty()",
        'lastRuntimeEvent = "sound_locked_hw_t09"',
        '\\"sound_available\\":false',
    )
    for token in required_header:
        if token not in header:
            failures.append(f"controller header missing: {token}")
    for token in required_source:
        if token not in source:
            failures.append(f"controller source missing: {token}")
    for token in ("applyTheme(InterfaceTheme theme)",
                  "Palette::Canvas = rgb565(0, 0, 0)"):
        if token not in theme:
            failures.append(f"semantic theme missing: {token}")
    for token in required_renderer:
        if token not in renderer:
            failures.append(f"renderer missing: {token}")
    for identifier in ("SettingsLanguage", "SettingsBrightness",
                       "SettingsTheme", "SettingsAntennaLeds", "SettingsSound",
                       "SettingsSoundLocked"):
        if f"LESHY_UI_TEXT({identifier}," not in strings:
            failures.append(f"EN/RU string missing: {identifier}")
    current_version = re.search(
        r'LESHY1_VERSION=\\"(\d+)\.(\d+)\.[^\\"]+\\"', version)
    if (current_version is None or
            (int(current_version.group(1)), int(current_version.group(2))) < (0, 145)):
        failures.append("current product predates accepted 0.145 interface settings")
    if re.search(r"ledcWrite\s*\(\s*BoardProfile::kBuzzerPin", renderer):
        failures.append("Settings must not energize the unverified buzzer path")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("interface-settings contract passed: persisted language/brightness/theme/antenna LEDs, sound fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
