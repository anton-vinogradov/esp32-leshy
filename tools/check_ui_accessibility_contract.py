#!/usr/bin/env python3
"""Fail closed when the UX-06 button/non-color accessibility contract drifts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "firmware/leshy1/src/ui/Pcf8574ButtonInput.cpp"
CONTROLLER = ROOT / "firmware/leshy1/src/ui/UiController.cpp"
COMPONENTS = ROOT / "firmware/leshy1/src/ui/UiComponents.h"
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
TESTS = ROOT / "tests/native/clean_target_tests.cpp"
KEYPAD = ROOT / "tests/hil/evidence/board-01-keypad-0.43.json"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    for path in (INPUT, CONTROLLER, COMPONENTS, RENDERER, STRINGS, TESTS,
                 KEYPAD):
        require(failures, path.is_file(), f"missing UX-06 contract input: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    input_source = INPUT.read_text(encoding="utf-8")
    expected_physical = {
        "Select": "(1U << 6U)",
        "Up": "(1U << 7U)",
        "Down": "(1U << 5U)",
        "Left": "(1U << 3U)",
        "Right": "(1U << 4U)",
    }
    for action, pin in expected_physical.items():
        require(failures, pin in input_source and f"UiAction::{action}" in input_source,
                f"physical mapping missing: {action}/{pin}")
    require(failures, "ambiguousPresses" in input_source,
            "multi-key ambiguity must remain fail closed")

    controller = CONTROLLER.read_text(encoding="utf-8")
    for action in ("Up", "Down", "Left", "Right", "Select", "Back"):
        require(failures, f"UiAction::{action}" in controller,
                f"normalized action missing: {action}")
    require(failures, "UiAction::Back || action == UiAction::Left" in controller,
            "permanent physical Left/diagnostic Back return path missing")

    components = COMPONENTS.read_text(encoding="utf-8")
    for token in ("focusMarker", "non-color focus marker", "contains("):
        require(failures, token in components,
                f"focus geometry contract missing: {token}")
    renderer = RENDERER.read_text(encoding="utf-8")
    for token in ("void renderFocusCue", "display.drawRoundRect",
                  "display.fillTriangle", "Components::focusMarker"):
        require(failures, token in renderer, f"non-color focus cue missing: {token}")
    require(failures, renderer.count("renderFocusCue(") >= 4,
            "focus cue must cover menus, Survey rows, and Library rows")

    strings = STRINGS.read_text(encoding="utf-8")
    explicit_state_ids = (
        "NoteSurveyUnavailable", "NoteLibraryUnavailable", "SurveyRunning",
        "SurveyCommitted", "SurveyError", "PriorLibraryPreserved",
        "PersistedYes", "PersistedNo", "SelfTestPass", "SelfTestFail",
        "SelfTestBlocked", "ResultBlocked", "NavBack", "NavSelect",
        "NavEnter", "NavCancel", "NavDetails", "NavApply",
    )
    for identifier in explicit_state_ids:
        require(failures, f"LESHY_UI_TEXT({identifier}," in strings,
                f"explicit non-color state label missing: {identifier}")
    for marker in ("NavigationKey::Left", "NavigationKey::UpDown",
                   "NavigationKey::RightAndSelect", "renderNavigationFooter"):
        require(failures, marker in renderer,
                f"spatial navigation footer contract missing: {marker}")
    require(failures, "item->enabled ? Tone::Positive : Tone::Muted" in renderer and
            "tr(homeNote(*item))" in renderer,
            "disabled Home item must retain a textual reason")

    tests = TESTS.read_text(encoding="utf-8")
    require(failures, "contains(row, Components::focusMarker(row))" in tests,
            "native focus-marker geometry test missing")
    keypad = json.loads(KEYPAD.read_text(encoding="utf-8"))
    after = keypad.get("after", {})
    require(failures, keypad.get("status") == "pass" and
            after.get("presses") == {name.lower(): 10 for name in expected_physical} and
            after.get("press_events") == 50 and after.get("release_events") == 50 and
            after.get("dispatched_press_events") == 50,
            "retained five-key physical mapping evidence mismatch")
    require(failures, after.get("read_errors") == 0 and
            after.get("ambiguous_presses") == 0 and
            after.get("queue_drops") == 0 and
            after.get("maximum_sample_gap_ms", 999) <= 5,
            "retained physical input health mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI accessibility contract passed: five physical keys, full normalized actions, geometric focus, explicit states")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
