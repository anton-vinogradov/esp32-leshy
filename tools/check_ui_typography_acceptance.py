#!/usr/bin/env python3
"""Machine-check exact 0.63 Roboto Condensed source and real-TFT evidence."""

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
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-typography-0.63.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-ui-typography-0.63"
TTF = ROOT / "firmware/leshy1/assets/fonts/roboto-condensed/RobotoCondensed-wght.ttf"
LICENSE = ROOT / "firmware/leshy1/assets/fonts/roboto-condensed/OFL.txt"
FONT = ROOT / "firmware/leshy1/src/ui/fonts/RobotoCondensedGfx.h"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
GENERATOR = ROOT / "tools/generate_ui_gfx_font.py"
RUNNER = ROOT / "tools/run_1x_ui_typography_hil.py"
SHA256 = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def retained(failures: list[str], relative: Any, expected: Any) -> Path | None:
    require(failures, isinstance(relative, str) and bool(relative),
            "retained path missing")
    require(failures, isinstance(expected, str) and SHA256.fullmatch(expected or "") is not None,
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
        require(failures, digest(path) == expected, f"retained hash mismatch: {relative}")
    return path if path.is_file() else None


def main() -> int:
    failures: list[str] = []
    for path in (EVIDENCE, BUNDLE / "run.json", TTF, LICENSE, FONT,
                 STRINGS, GENERATOR, RUNNER):
        require(failures, path.is_file(), f"required file missing: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures, evidence.get("schema") == "leshy.ui_typography_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-064", "E-AUTO-027", "E-HIL-087", "E-UX-008"],
            "evidence ID set mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "typography evidence must not promote a stage/release gate")

    expected_candidate = {
        "version": "0.63.0-roboto-condensed-ui-measure",
        "firmware_sha256": "e72aa955fd6eba2c3a78652d693ce9cc4c354a469f8ac42d0735250c59245abc",
        "factory_sha256": "b698b7f638254c2ef87eaa17c9eb6ace30ea6e5d38aaf8efac0a5e95aa03dbde",
        "app_elf_sha256": "3171e472c40c49484922c9c1b0ca82b60f2a3b71deedeaf8008604d8751eb01a",
        "map_sha256": "a9f32ceb3d586d965eef6d93ec70be376b8f12fc4b12fa4a12cc0b24f3084d50",
        "linked_flash_bytes": 1111932,
        "static_ram_bytes": 128816,
        "app_image_bytes": 1112336,
        "factory_image_bytes": 1177872,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }
    candidate = evidence.get("candidate", {})
    require(failures, candidate == expected_candidate, "candidate block mismatch")

    font = evidence.get("font", {})
    require(failures, font == {
        "family": "Roboto Condensed",
        "weight": 500,
        "weight_name": "Medium",
        "body_px": 16,
        "meta_px": 12,
        "license": "SIL Open Font License 1.1",
        "source_ttf_sha256":
            "dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0",
        "generated_header_sha256":
            "44d7e1e0130960fd0fe7a7c6cffdbfb6c587e85490209dabada833c5a0609c14",
        "body_bitmap_bytes": 2153,
        "meta_bitmap_bytes": 1275,
        "catalog_entries": 127,
        "measured_variants": 254,
        "shortened_variants": 8,
        "fit_failures": 0,
        "runtime_heap_allocations": 0,
    }, "font contract mismatch")
    require(failures, digest(TTF) == font.get("source_ttf_sha256"),
            "Roboto Condensed source hash mismatch")
    require(failures, digest(FONT) == font.get("generated_header_sha256"),
            "generated font hash mismatch")
    require(failures, "SIL OPEN FONT LICENSE Version 1.1" in
            LICENSE.read_text(encoding="utf-8"), "Roboto Condensed OFL missing")
    generated = FONT.read_text(encoding="utf-8")
    for marker in (
        "Roboto Condensed Medium (weight 500)",
        "kRobotoCondensedBodyBitmapBytes = 2153",
        "kRobotoCondensedMetaBitmapBytes = 1275",
        "Source SHA-256: dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0",
    ):
        require(failures, marker in generated, f"generated font marker missing: {marker}")
    generator = GENERATOR.read_text(encoding="utf-8")
    for marker in ('WEIGHT_NAME = "Medium"', "font.set_variation_by_name(WEIGHT_NAME)",
                   '("RobotoCondensedBody", 16)', '("RobotoCondensedMeta", 12)'):
        require(failures, marker in generator, f"generator marker missing: {marker}")
    try:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
    except SyntaxError as error:
        failures.append(f"typography runner syntax error: {error}")

    ui_strings = STRINGS.read_text(encoding="utf-8")
    expected_shortened = (
        'u8"ДИАЛОГ / ПОДТВЕРДИТЬ"',
        'u8"САМОТЕСТ / НЕДОСТУПЕН"',
        '"READ ONLY | REPORT OVER USB"',
        'u8"SD | ВОССТАНОВЛЕНО | RF ВЫКЛ"',
        'u8"старт | назад: отмена | RF выкл"',
        'u8"скан | назад: отмена | только RX"',
        'u8"детали | вправо: стоп | RF выкл"',
        'u8"сохранено | назад | только RX"',
    )
    for marker in expected_shortened:
        require(failures, marker in ui_strings, f"shortened fit copy missing: {marker}")

    physical = evidence.get("physical", {})
    run_path = retained(failures, physical.get("run_path"), physical.get("run_sha256"))
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path else {}
    require(failures, run.get("schema") == "leshy.ui_typography_hil.v1" and
            run.get("status") == "pass" and run.get("passed") is True,
            "retained physical run did not pass")
    run_candidate = run.get("candidate", {})
    for key in ("version", "firmware_sha256", "factory_sha256", "app_elf_sha256",
                "map_sha256", "firmware_bytes", "factory_bytes"):
        summary_key = {"firmware_bytes": "app_image_bytes",
                       "factory_bytes": "factory_image_bytes"}.get(key, key)
        require(failures, run_candidate.get(key) == candidate.get(summary_key),
                f"run candidate mismatch: {key}")
    require(failures, run_candidate.get("runner_sha256") == digest(RUNNER),
            "retained runner hash mismatch")
    require(failures, run.get("font") == {
        "family": "Roboto Condensed", "weight": 500, "weight_name": "Medium",
        "body_px": 16, "meta_px": 12,
        "source_ttf_sha256": font.get("source_ttf_sha256"),
    }, "run font identity mismatch")
    require(failures, run.get("catalog_entries") == 127 and
            run.get("measured_variants") == 254 and run.get("fit_failures") == 0,
            "run catalog/fit mismatch")

    expected_screens = {
        "home_ru", "diagnostics_ru", "survey_setup_ru", "library_list_ru",
        "library_detail_ru", "language_ru", "self_test_modes_ru", "quick_result_ru",
        "full_preflight_ru", "visual_dialog_confirm_ru", "visual_unavailable_ru",
        "visual_degraded_ru", "visual_error_ru", "visual_running_ru", "full_blocked_ru",
        "home_en", "language_en", "home_final_ru",
    }
    screens = run.get("screens", {})
    require(failures, set(screens) == expected_screens and run.get("screen_count") == 18,
            "exact 18-screen TFT set mismatch")
    frame_names: dict[str, set[str]] = {}
    for name, record in screens.items():
        png_path = retained(failures, record.get("png_path"), record.get("png_sha256"))
        trace_path = retained(failures, record.get("trace_path"), record.get("trace_sha256"))
        if png_path is not None:
            try:
                width, height, pixels = decode_png(png_path)
            except ValueError as error:
                failures.append(str(error))
            else:
                require(failures, (width, height) == (240, 320),
                        f"{name}: TFT geometry mismatch")
                divider = (57, 73, 66)
                require(failures, all(pixels[236][x] == divider for x in range(12, 228)),
                        f"{name}: footer divider missing or overwritten")
        if trace_path is not None:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            require(failures, trace.get("png_sha256") == record.get("png_sha256") and
                    trace.get("rgb565_sha256") == record.get("rgb565_sha256"),
                    f"{name}: trace/frame binding mismatch")
            require(failures, trace.get("frame_begin", {}).get("width") == 240 and
                    trace.get("frame_begin", {}).get("height") == 320 and
                    trace.get("frame_begin", {}).get("bytes") == 153600,
                    f"{name}: frame metadata mismatch")
        frame_names.setdefault(record.get("png_sha256", ""), set()).add(name)

    duplicates = {frozenset(names) for names in frame_names.values() if len(names) > 1}
    require(failures, duplicates == {frozenset({"home_ru", "home_final_ru"})},
            "unexpected framebuffer duplication or final RU Home mismatch")
    require(failures, screens.get("home_ru", {}).get("png_sha256") !=
            screens.get("home_en", {}).get("png_sha256"), "EN/RU Home did not differ")
    require(failures, screens.get("language_ru", {}).get("png_sha256") !=
            screens.get("language_en", {}).get("png_sha256"), "EN/RU Language did not differ")
    visuals = {record.get("post_capture_state", {}).get("self_test_visual_state")
               for name, record in screens.items() if name.startswith("visual_")}
    require(failures, visuals == {"dialog_confirm", "unavailable", "degraded", "error", "running"},
            "Full guided visual-state coverage mismatch")
    require(failures, screens.get("library_detail_ru", {}).get("post_capture_state", {}).get(
                "library_view") == "detail", "persistent Library detail was not captured")

    records = run.get("records", {})
    loaded: dict[str, dict[str, Any]] = {}
    for name, record in records.items():
        path = retained(failures, record.get("path"), record.get("sha256"))
        loaded[name] = json.loads(path.read_text()) if path else {}
        require(failures, loaded[name] == record.get("value"),
                f"{name}: retained record/value mismatch")
    quick = loaded.get("quick_report", {})
    full = loaded.get("full_report", {})
    side_effects = {"buzzer_activations": 0, "radio_tx_commands": 0,
                    "storage_write_commands": 0}
    require(failures, (quick.get("status"), quick.get("passed"), quick.get("failed"),
                       quick.get("blocked"), quick.get("read_only")) ==
            ("pass", 8, 0, 0, True) and quick.get("side_effects") == side_effects,
            "Quick Self-Test regression mismatch")
    require(failures, (full.get("status"), full.get("passed"), full.get("failed"),
                       full.get("blocked"), full.get("read_only")) ==
            ("blocked", 9, 0, 1, True) and full.get("side_effects") == side_effects,
            "Full guided regression mismatch")
    before = loaded.get("metrics_before", {})
    after = loaded.get("metrics_after", {})
    require(failures, before.get("version") == candidate.get("version") and
            before.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            after.get("app_elf_sha256") == candidate.get("app_elf_sha256"),
            "runtime identity mismatch")
    require(failures, (before.get("heap_total"), before.get("heap_free"),
                       before.get("heap_min_free")) == (272688, 208912, 188720) and
            (after.get("heap_total"), after.get("heap_free"), after.get("heap_min_free")) ==
            (272688, 208912, 188720), "heap invariance mismatch")
    input_state = loaded.get("input", {})
    safe = loaded.get("safe_outputs", {})
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5,
            "input health mismatch")
    require(failures, safe.get("buzzer_inactive") is True and safe.get("buzzer_level") == "low",
            "buzzer safety mismatch")
    final = screens.get("home_final_ru", {}).get("post_capture_state", {})
    require(failures, final.get("page") == "home" and final.get("language") == "ru" and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0,
            "final Home/language/lease mismatch")

    expected_physical = {
        "screen_count": 18, "languages": ["ru", "en"],
        "visual_states": ["dialog_confirm", "unavailable", "degraded", "error", "running"],
        "quick_passed": 8, "quick_failed": 0, "quick_blocked": 0,
        "full_passed": 9, "full_failed": 0, "full_blocked": 1,
        "heap_total": 272688, "heap_free_before": 208912, "heap_free_after": 208912,
        "heap_min_before": 188720, "heap_min_after": 188720,
        "input_read_errors": 0, "input_queue_drops": 0, "maximum_sample_gap_ms": 5,
        "buzzer_inactive": True, "radio_tx_commands": 0, "storage_write_commands": 0,
        "buzzer_activations": 0, "final_language": "ru", "final_owner": "none",
        "final_lease_mask": 0,
    }
    for key, expected in expected_physical.items():
        require(failures, physical.get(key) == expected,
                f"physical summary mismatch: {key}")

    docs = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md", "docs/v1/UX_UI_BASELINE.md",
        "docs/v1/UX_UI_BASELINE.ru.md", "docs/v1/RESOURCE_BUDGETS.md",
        "docs/v1/RESOURCE_BUDGETS.ru.md", "docs/v1/TRACEABILITY.md",
        "docs/v1/TRACEABILITY.ru.md"))
    for marker in ("0.63", "Roboto Condensed", "E-BUILD-064", "E-AUTO-027",
                   "E-HIL-087", "E-UX-008"):
        require(failures, marker in docs, f"source-of-truth docs marker missing: {marker}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI typography acceptance passed: Roboto Condensed Medium 16/12, "
          "254/254 fit, 18 exact TFT states, zero heap drift, final lease 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
