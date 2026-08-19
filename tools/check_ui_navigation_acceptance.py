#!/usr/bin/env python3
"""Fail closed unless the 0.67 non-blocking physical-key evidence is complete."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_visual_system_acceptance import decode_png


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-navigation-0.67.json"
RUNNER = ROOT / "tools/run_1x_ui_navigation_hil.py"
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
COMPONENTS = ROOT / "firmware/leshy1/src/ui/UiComponents.h"
THEME = ROOT / "firmware/leshy1/src/ui/VisualTheme.h"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
PRODUCT_RUNNER = ROOT / "tools/run_1x_product_survey_hil.py"
SHA256 = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def retained(failures: list[str], relative: Any, expected: Any) -> Path | None:
    require(failures, isinstance(relative, str) and bool(relative),
            "retained path missing")
    require(failures, isinstance(expected, str) and
            SHA256.fullmatch(expected or "") is not None,
            f"invalid retained hash: {relative}")
    if not isinstance(relative, str):
        return None
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        failures.append(f"retained path escapes repository: {relative}")
        return None
    require(failures, path.is_file(), f"retained file missing: {relative}")
    if path.is_file() and isinstance(expected, str):
        require(failures, digest(path) == expected,
                f"retained hash mismatch: {relative}")
    return path if path.is_file() else None


def main() -> int:
    failures: list[str] = []
    for path in (EVIDENCE, RUNNER, RENDERER, COMPONENTS, THEME, STRINGS,
                 PRODUCT_RUNNER):
        require(failures, path.is_file(), f"required file missing: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures, evidence.get("schema") ==
            "leshy.ui_navigation_acceptance.v1" and
            evidence.get("status") == "pass",
            "navigation evidence schema/status mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-068", "E-AUTO-031", "E-HIL-091", "E-UX-012"],
            "navigation evidence ID set mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "navigation evidence must not promote a stage/release gate")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.67.0-nonblocking-keypath-measure",
        "firmware_sha256":
            "9af801bcabb139c6edcc86ed74b08faa7b98d30de16584fe14ce7a970367e926",
        "factory_sha256":
            "74b248da84dc846638cb7066834be5880d8d6d934e9b067410bceaac9dae523e",
        "app_elf_sha256":
            "c1f89b2292c4c0320093c36eeb630d992dd48066228ab850144ae237a9193123",
        "map_sha256":
            "bc55597172bbecb6e909a95da70bb36e2990aab1b134543990d4c946a8e7ba9a",
        "linked_flash_bytes": 1112568,
        "static_ram_bytes": 128896,
        "app_image_bytes": 1112976,
        "factory_image_bytes": 1178512,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate block mismatch")
    require(failures, evidence.get("navigation") == {
        "left": "back", "right_or_ok": "enter", "up_down": "select",
        "footer_height_px": 26, "spatial_cells": 3,
        "label_font": "Roboto Condensed Medium 12",
        "key_legend_font": "Roboto Condensed Medium 12",
        "programmatic_direction_icons": True,
        "technical_status_removed_from_footer": True,
        "survey_right_enters_detail": True,
        "survey_stop_or_save_inside_detail": True,
        "library_right_or_ok_enters_detail": True,
    }, "navigation contract mismatch")
    require(failures, evidence.get("rendering") == {
        "full_screen_fill_removed": True,
        "full_transition_clears_content_below_header": True,
        "selection_repaints_only_changed_rows": True,
        "selection_skips_footer_repaint": True,
        "one_queued_press_per_repaint": True,
        "press_frames_are_never_coalesced": True,
        "hot_path_serial_writes": 0,
        "incremental_transition_count": 8,
        "full_transition_count": 12,
        "incremental_render_us": [15543, 15282, 13972, 22963, 22961,
                                  15463, 23057, 23058],
        "maximum_incremental_render_us": 23058,
        "maximum_allowed_incremental_render_us": 40000,
    }, "incremental rendering summary mismatch")

    regression = evidence.get("regression", {})
    incident_path = retained(failures, regression.get("failed_incident_path"),
                             regression.get("failed_incident_sha256"))
    incident = json.loads(incident_path.read_text(encoding="utf-8")) \
        if incident_path else {}
    require(failures,
            incident.get("schema") == "leshy.ui_input_incident.v1" and
            incident.get("status") == "failed" and
            incident.get("measured_after_observation", {}).get(
                "queue_high_water") == 5 and
            incident.get("disposition", {}).get("accepted_as_ux_fix") is False,
            "0.66 user-lag incident is missing or not fail-closed")
    require(failures, regression.get("failed_queue_high_water") == 5 and
            regression.get("passing_queue_high_water") == 1 and
            regression.get("user_confirmed_responsive") is True,
            "physical user regression summary mismatch")

    physical = evidence.get("physical", {})
    run_path = retained(failures, physical.get("run_path"),
                        physical.get("run_sha256"))
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path else {}
    require(failures, run.get("schema") == "leshy.ui_navigation_hil.v1" and
            run.get("status") == "pass" and run.get("passed") is True,
            "physical navigation run did not pass")
    run_candidate = run.get("candidate", {})
    for run_key, evidence_key in (
        ("version", "version"), ("firmware_sha256", "firmware_sha256"),
        ("factory_sha256", "factory_sha256"),
        ("app_elf_sha256", "app_elf_sha256"), ("map_sha256", "map_sha256"),
        ("firmware_bytes", "app_image_bytes"),
        ("factory_bytes", "factory_image_bytes"),
    ):
        require(failures, run_candidate.get(run_key) ==
                candidate.get(evidence_key), f"run candidate mismatch: {run_key}")
    require(failures, run_candidate.get("runner_sha256") == digest(RUNNER),
            "navigation runner source hash mismatch")
    require(failures, run.get("contract") == {
        "left": "back", "right_or_ok": "enter", "up_down": "select",
        "context_actions_live_inside_destination": True,
        "technical_status_removed_from_footer": True,
        "footer_height_px": 26,
        "selection_repaints_only_changed_rows": True,
        "full_screen_clear_on_selection": False,
    }, "physical navigation contract mismatch")

    expected_screens = {
        "home_ru", "diagnostics_ru", "survey_setup_ru", "library_list_ru",
        "library_detail_ru", "language_ru", "self_test_modes_ru", "home_en",
        "home_final_ru",
    }
    screens = run.get("screens", {})
    require(failures, set(screens) == expected_screens and
            run.get("screen_count") == 9,
            "exact nine-screen navigation set mismatch")
    active_cells = {
        "home_ru": {1, 2}, "diagnostics_ru": {0},
        "survey_setup_ru": {0, 2}, "library_list_ru": {0, 1, 2},
        "library_detail_ru": {0, 2}, "language_ru": {0, 1, 2},
        "self_test_modes_ru": {0, 1, 2}, "home_en": {1, 2},
        "home_final_ru": {1, 2},
    }
    frame_names: dict[str, set[str]] = {}
    for name, record in screens.items():
        png_path = retained(failures, record.get("png_path"),
                            record.get("png_sha256"))
        trace_path = retained(failures, record.get("trace_path"),
                              record.get("trace_sha256"))
        if png_path is not None:
            try:
                width, height, pixels = decode_png(png_path)
            except ValueError as error:
                failures.append(str(error))
            else:
                require(failures, (width, height) == (240, 320),
                        f"{name}: TFT geometry mismatch")
                divider = (57, 73, 66)
                require(failures,
                        all(pixels[236][x] == divider for x in range(12, 228)),
                        f"{name}: footer divider missing")
                surface = (8, 20, 16)
                for index, x in enumerate((12, 85, 158)):
                    count = sum(
                        pixels[y][column] == surface
                        for y in range(294, 320)
                        for column in range(x, x + 70)
                    )
                    if index in active_cells[name]:
                        require(failures, count > 1400,
                                f"{name}: navigation cell {index} missing")
                    else:
                        require(failures, count == 0,
                                f"{name}: inactive navigation cell {index} painted")
        if trace_path is not None:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            require(failures, trace.get("png_sha256") ==
                    record.get("png_sha256") and
                    trace.get("rgb565_sha256") == record.get("rgb565_sha256"),
                    f"{name}: trace/frame binding mismatch")
        frame_names.setdefault(record.get("png_sha256", ""), set()).add(name)
    duplicates = {frozenset(names) for names in frame_names.values()
                  if len(names) > 1}
    require(failures, duplicates == {frozenset({"home_ru", "home_final_ru"})},
            "unexpected framebuffer duplication or final RU Home mismatch")

    expected_transitions = {
        "right_enters": ("right", "diagnostics", 0, True),
        "left_returns": ("left", "home", 0, True),
        "select_enters": ("select", "diagnostics", 0, True),
        "back_returns": ("back", "home", 0, True),
        "up_at_first_is_bounded": ("up", "home", 0, False),
        "down_selects_survey": ("down", "home", 1, True),
        "right_enters_survey": ("right", "survey", 1, True),
        "left_returns_from_survey": ("left", "home", 1, True),
        "down_selects_library": ("down", "home", 2, True),
        "right_enters_library": ("right", "library", 2, True),
        "right_enters_library_detail": ("right", "library", 2, True),
        "left_returns_library_list": ("left", "library", 2, True),
        "select_enters_library_detail": ("select", "library", 2, True),
        "down_selects_language": ("down", "home", 3, True),
        "right_enters_language": ("right", "language", 3, True),
        "language_up_incremental": ("up", "language", 3, True),
        "language_down_incremental": ("down", "language", 3, True),
        "down_selects_self_test": ("down", "home", 4, True),
        "right_enters_self_test": ("right", "self_test", 4, True),
        "self_test_down_incremental": ("down", "self_test", 4, True),
        "self_test_up_incremental": ("up", "self_test", 4, True),
    }
    transitions = run.get("transitions", {})
    require(failures, set(transitions) == set(expected_transitions) and
            run.get("transition_count") == 21,
            "exact transition set mismatch")
    for name, expected in expected_transitions.items():
        state = transitions.get(name, {})
        actual = (state.get("action"), state.get("page"),
                  state.get("selection"), state.get("changed"))
        require(failures, actual == expected, f"{name}: transition mismatch")
    for name in ("right_enters_library_detail", "select_enters_library_detail"):
        require(failures, transitions.get(name, {}).get("library_view") == "detail",
                f"{name}: nested detail was not entered")
    require(failures,
            transitions.get("left_returns_library_list", {}).get("library_view") ==
            "list", "nested Left did not return to Library list")
    incremental_names = (
        "down_selects_survey", "down_selects_library",
        "down_selects_language", "language_up_incremental",
        "language_down_incremental", "down_selects_self_test",
        "self_test_down_incremental", "self_test_up_incremental",
    )
    incremental_us = []
    for name in incremental_names:
        state = transitions.get(name, {})
        render_us = state.get("render_us")
        require(failures, state.get("render_mode") == "incremental" and
                isinstance(render_us, int) and 0 < render_us <= 40000,
                f"{name}: bounded incremental render missing")
        if isinstance(render_us, int):
            incremental_us.append(render_us)
    rendering = run.get("rendering", {})
    require(failures, rendering.get("incremental_transition_count") == 8 and
            rendering.get("full_transition_count") == 12 and
            rendering.get("incremental_render_us") == incremental_us and
            rendering.get("maximum_incremental_render_us") == 23058 and
            rendering.get("maximum_allowed_incremental_render_us") == 40000,
            "measured rendering block mismatch")

    loaded: dict[str, dict[str, Any]] = {}
    for name, record in run.get("records", {}).items():
        path = retained(failures, record.get("path"), record.get("sha256"))
        loaded[name] = json.loads(path.read_text(encoding="utf-8")) if path else {}
        require(failures, loaded[name] == record.get("value"),
                f"{name}: retained record/value mismatch")
    before = loaded.get("metrics_before", {})
    after = loaded.get("metrics_after", {})
    require(failures, (before.get("heap_total"), before.get("heap_free"),
                       before.get("heap_min_free")) ==
            (272608, 208320, 188140) and
            (after.get("heap_total"), after.get("heap_free"),
             after.get("heap_min_free")) == (272608, 208320, 188140),
            "heap invariance mismatch")
    input_state = loaded.get("input", {})
    safe = loaded.get("safe_outputs", {})
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and
            input_state.get("ambiguous_presses") == 0 and
            input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5 and
            input_state.get("press_events") == 75 and
            input_state.get("release_events") == 75 and
            input_state.get("dispatched_press_events") == 75 and
            input_state.get("queue_high_water") == 1 and
            input_state.get("maximum_queue_latency_us") == 1256 and
            input_state.get("hot_path_serial_writes") == 0,
            "input health mismatch")
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer safety mismatch")
    final = screens.get("home_final_ru", {}).get("post_capture_state", {})
    require(failures, final.get("page") == "home" and
            final.get("language") == "ru" and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0,
            "final Home/language/lease mismatch")

    renderer = RENDERER.read_text(encoding="utf-8")
    components = COMPONENTS.read_text(encoding="utf-8")
    theme = THEME.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    product_runner = PRODUCT_RUNNER.read_text(encoding="utf-8")
    for marker in ("NavigationKey::Left", "NavigationKey::UpDown",
                   "NavigationKey::RightAndSelect", "renderNavigationFooter",
                   "UiTextId::NavBack", "UiTextId::NavSelect",
                   "UiTextId::NavEnter", "kNavigationInset = 6",
                   "kNavigationGap = 4", "navigationKeyWidth(",
                   "bounds.y + (bounds.height - textHeight) / 2"):
        require(failures, marker in renderer,
                f"renderer navigation marker missing: {marker}")
    require(failures, "bounds.y + 11" not in
            renderer[renderer.find("void renderNavigationCell"):
                     renderer.find("void renderNavigationFooter")],
            "navigation footer still stacks the label below its key")
    for marker in ("NavigationGap = 0", "NavigationWidth = 80",
                   "navigationCell(std::uint8_t index)"):
        require(failures, marker in components,
                f"navigation geometry marker missing: {marker}")
    require(failures, "HintY = 294" in theme and "HintHeight = 26" in theme,
            "26 px compact footer theme contract missing")
    for marker in ("renderSelectionDelta()", "renderHomeRow(",
                   "renderLanguageRow(", "renderSelfTestModeRow(",
                   "renderSurveyListRow(", "renderLibraryListRow(",
                   "renderInteractiveScreen(!lastUiActionUsedIncrementalRender)"):
        require(failures, marker in renderer,
                f"incremental renderer marker missing: {marker}")
    loop_body = renderer[renderer.find("void loop() {"):]
    require(failures,
            loop_body.count("xQueueReceive(physicalInputEvents") == 1 and
            "while (physicalInputEvents" not in loop_body and
            "lastPhysicalInputQueueUs" in loop_body and
            "lastPhysicalInputEndToEndUs" in loop_body,
            "0.x-style one-event/one-repaint dispatch contract missing")
    input_dispatch = loop_body[loop_body.find("PhysicalInputEvent inputEvent;"):
                               loop_body.find("delay(2);")]
    require(failures, "broadcast(" not in input_dispatch and
            "println(" not in input_dispatch and
            '\\"hot_path_serial_writes\\":0' in renderer,
            "physical input hot path still performs blocking serial output")
    render_start = renderer.find("void renderInteractiveScreen(bool clearContent)")
    render_end = renderer.find("void emitUiState(", render_start)
    render_body = renderer[render_start:render_end]
    full_render_start = render_body.find("if (!incremental) {")
    full_render_end = render_body.find("\n    }\n    display.endWrite();",
                                       full_render_start)
    full_render_body = render_body[full_render_start:full_render_end]
    require(failures, render_start >= 0 and render_end > render_start and
            full_render_start >= 0 and full_render_end > full_render_start and
            "renderInput(lastInputRaw)" not in render_body and
            "renderNavigationFooter();" in full_render_body and
            "renderHeaderStatus();" in renderer,
            "incremental selection or full render violates clean chrome")
    require(failures, "fillScreen(" not in renderer,
            "interactive renderer reintroduced full-screen fill")
    for identifier in ("NavOk", "NavBack", "NavCancel", "NavSelect",
                       "NavEnter", "NavStart", "NavDetails", "NavStop",
                       "NavSave", "NavExport", "NavApply", "NavNext",
                       "NavModes", "NavHome", "NavList"):
        require(failures, f"LESHY_UI_TEXT({identifier}," in strings,
                f"localized navigation label missing: {identifier}")
    for obsolete in ("FooterRoot", "FooterSurveyRunReal", "FooterLanguage",
                     "blocked item has reason", "есть причины"):
        require(failures, obsolete not in strings,
                f"obsolete prose footer remains: {obsolete}")
    require(failures,
            "action == UiAction::Select ||\n                       action == UiAction::Right" in
            renderer and "changed = surveyController.openSelected();" in renderer,
            "Survey Right/OK inward behavior missing")
    require(failures, 'right_detail_ack = action(device, "right")' in
            product_runner and 'stop_ack = action(device, "select")' in
            product_runner, "product HIL runner did not follow spatial navigation")
    try:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
        ast.parse(PRODUCT_RUNNER.read_text(encoding="utf-8"))
    except SyntaxError as error:
        failures.append(f"navigation runner syntax error: {error}")

    expected_physical = {
        "screen_count": 9, "transition_count": 21,
        "languages": ["ru", "en"], "right_and_select_entry_proven": True,
        "left_and_back_return_proven": True,
        "nested_library_entry_proven": True,
        "nested_incremental_selection_proven": True,
        "physical_press_events": 75, "physical_release_events": 75,
        "physical_dispatched_press_events": 75,
        "physical_queue_high_water": 1,
        "physical_maximum_queue_latency_us": 1256,
        "physical_last_repaint_us": 15429,
        "physical_last_end_to_end_us": 16703,
        "physical_maximum_end_to_end_us": 102741,
        "hot_path_serial_writes": 0,
        "heap_total": 272608,
        "heap_free_before": 208320, "heap_free_after": 208320,
        "heap_min_before": 188140, "heap_min_after": 188140,
        "input_read_errors": 0, "input_ambiguous_presses": 0,
        "input_queue_drops": 0, "maximum_sample_gap_ms": 5,
        "buzzer_inactive": True, "final_language": "ru",
        "final_owner": "none", "final_lease_mask": 0,
    }
    for key, expected in expected_physical.items():
        require(failures, physical.get(key) == expected,
                f"physical summary mismatch: {key}")

    docs = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md",
        "docs/v1/UX_UI_BASELINE.md", "docs/v1/UX_UI_BASELINE.ru.md",
        "docs/v1/UX_ACCESSIBILITY.md", "docs/v1/UX_ACCESSIBILITY.ru.md",
        "docs/v1/UI_AUTOMATION.md", "docs/v1/UI_AUTOMATION.ru.md",
        "docs/v1/RESOURCE_BUDGETS.md", "docs/v1/RESOURCE_BUDGETS.ru.md",
        "docs/v1/TRACEABILITY.md", "docs/v1/TRACEABILITY.ru.md",
    ))
    for marker in ("0.67", "serial backpressure", "serial backpressure",
                   "E-BUILD-068", "E-AUTO-031", "E-HIL-091", "E-UX-012"):
        require(failures, marker in docs,
                f"source-of-truth docs marker missing: {marker}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI navigation acceptance passed: 75 physical presses, non-blocking "
          "hot path, queue high-water 1, <=1.256 ms queue latency")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
