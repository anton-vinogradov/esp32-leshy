#!/usr/bin/env python3
"""Machine-check the exact 0.54 UX-04 component and board evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_visual_system_acceptance import decode_png


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-components-0.54.json"
COMPONENTS = ROOT / "firmware/leshy1/src/ui/UiComponents.h"
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
TESTS = ROOT / "tests/native/clean_target_tests.cpp"
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"
SHA256 = re.compile(r"[0-9a-f]{64}")


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained(failures: list[str], relative: Any, expected: Any) -> Path | None:
    require(failures, isinstance(relative, str), "retained path is not a string")
    require(failures, isinstance(expected, str) and SHA256.fullmatch(expected) is not None,
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
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures, evidence.get("schema") == "leshy.ui_components_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-056", "E-HIL-078", "E-UX-004"], "evidence IDs mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "component evidence must not claim the S2/release gate")

    candidate = evidence.get("candidate", {})
    expected_candidate = {
        "version": "0.54.0-ui-components-measure",
        "firmware_sha256": "479935d596da0a772dc69988a56e1bf96d7d4c3c78813afb99d3454636ea7f77",
        "factory_sha256": "5e54832d143d54caf8c33a10edbc81027db9669456c2a56df46650ccc9b3e650",
        "app_elf_sha256": "d9366104fb6ce8da3b7324ea8b4771fe2a019bcbeac0e6ce0a8f7e18d08d787f",
        "map_sha256": "b6909f447c383f789c320776bd29b7c3ffc301f27ea24770e8fcbde92524b069",
        "linked_flash_bytes": 1068048,
        "static_ram_bytes": 128720,
        "app_image_bytes": 1068192,
        "factory_image_bytes": 1133728,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }
    require(failures, candidate == expected_candidate, "candidate block mismatch")
    require(failures, 'LESHY1_VERSION=\\"0.54.0-ui-components-measure\\"' in
            PLATFORMIO.read_text(encoding="utf-8"), "current version mismatch")

    contract = evidence.get("component_contract", {})
    expected_components = ["header", "title", "home_row", "choice_row",
                           "metric_row", "footer_divider", "input_status",
                           "footer_hint"]
    require(failures, contract.get("components") == expected_components,
            "component inventory mismatch")
    require(failures, contract.get("compile_time_bounds") is True and
            contract.get("compile_time_overlap_guards") is True,
            "component bounds/overlap contract missing")
    component_source = COMPONENTS.read_text(encoding="utf-8")
    for token in ("struct Rect", "enum class Tone", "struct Components",
                  "homeRow", "choiceRow", "metricRow", "footerDivider",
                  "inputStatus", "footerHint", "insideScreen", "overlaps",
                  "static_assert"):
        require(failures, token in component_source, f"component source missing: {token}")
    renderer = RENDERER.read_text(encoding="utf-8")
    require(failures, '#include "ui/UiComponents.h"' in renderer,
            "renderer does not consume component contract")
    require(failures, renderer.count("renderMenuRow(") >= 3,
            "menu row primitive is not reused across Home and Self-Test")
    require(failures, renderer.count("renderMetric(") >= 9,
            "metric primitive is not reused across preflight and result")
    for token in ("Components::header()", "Components::title()",
                  "Components::homeRow", "Components::choiceRow",
                  "Components::metricRow", "Components::footerDivider()",
                  "Components::inputStatus()", "Components::footerHint()"):
        require(failures, token in renderer, f"renderer missing contract use: {token}")
    require(failures, "testUiComponentGeometryContract" in
            TESTS.read_text(encoding="utf-8"), "native component geometry test missing")

    screens = evidence.get("screens", {})
    require(failures, set(screens) ==
            {"home", "self_test_modes", "quick_result", "home_cleanup"},
            "screen set mismatch")
    decoded: dict[str, list[list[tuple[int, int, int]]]] = {}
    for name, record in screens.items():
        png_path = retained(failures, record.get("path"), record.get("png_sha256"))
        trace_path = retained(failures, record.get("trace_path"),
                              record.get("trace_sha256"))
        require(failures, isinstance(record.get("rgb565_sha256"), str) and
                SHA256.fullmatch(record.get("rgb565_sha256", "")) is not None,
                f"{name}: RGB565 hash missing")
        if png_path is not None:
            try:
                width, height, pixels = decode_png(png_path)
            except ValueError as error:
                failures.append(str(error))
            else:
                require(failures, (width, height) == (240, 320),
                        f"{name}: TFT dimensions mismatch")
                decoded[name] = pixels
        if trace_path is not None:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            require(failures, trace.get("frame_begin", {}).get("width") == 240 and
                    trace.get("frame_begin", {}).get("height") == 320,
                    f"{name}: capture metadata mismatch")
            require(failures, trace.get("rgb565_sha256") == record.get("rgb565_sha256"),
                    f"{name}: RGB565 trace binding mismatch")

    if {"home", "self_test_modes", "quick_result"}.issubset(decoded):
        home = decoded["home"]
        modes = decoded["self_test_modes"]
        quick = decoded["quick_result"]
        require(failures, home[:42] == modes[:42] == quick[:42],
                "shared brand header is not byte-identical across screen families")
        focus = (24, 77, 49)
        require(failures, home[100][100] == focus and modes[110][100] == focus,
                "shared focused menu surface mismatch")
        divider = (57, 73, 66)
        for name, pixels in (("home", home), ("modes", modes), ("quick", quick)):
            require(failures, all(pixels[236][x] == divider for x in range(12, 228)),
                    f"{name}: shared footer divider missing")
        require(failures, len({digest(ROOT / record["path"])
                               for record in screens.values()}) == 4,
                "retained frames must be distinct")

    runtime = evidence.get("runtime", {})
    quick_path = retained(failures, runtime.get("quick_report_path"),
                          runtime.get("quick_report_sha256"))
    metrics_path = retained(failures, runtime.get("metrics_path"),
                            runtime.get("metrics_sha256"))
    input_path = retained(failures, runtime.get("input_path"),
                          runtime.get("input_sha256"))
    safe_path = retained(failures, runtime.get("safe_outputs_path"),
                         runtime.get("safe_outputs_sha256"))
    quick_report = json.loads(quick_path.read_text()) if quick_path else {}
    metrics = json.loads(metrics_path.read_text()) if metrics_path else {}
    input_state = json.loads(input_path.read_text()) if input_path else {}
    safe = json.loads(safe_path.read_text()) if safe_path else {}
    require(failures, quick_report.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            quick_report.get("status") == "pass" and quick_report.get("passed") == 8 and
            quick_report.get("failed") == 0 and quick_report.get("blocked") == 0,
            "Quick regression mismatch")
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            metrics.get("heap_free") == 224332 and metrics.get("heap_min_free") == 188872,
            "runtime identity/heap mismatch")
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5,
            "input regression mismatch")
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer safety regression mismatch")
    cleanup_trace_path = ROOT / screens.get("home_cleanup", {}).get("trace_path", "missing")
    cleanup = json.loads(cleanup_trace_path.read_text()) if cleanup_trace_path.is_file() else {}
    final = cleanup.get("post_capture_state", {})
    require(failures, final.get("page") == "home" and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0,
            "final Home cleanup mismatch")

    require(failures, evidence.get("scope") == {
        "ux_03": "accepted",
        "ux_04": "implemented_and_physically_evidenced",
        "ux_05": "open",
        "ux_06": "open",
        "ux_07": "partial",
        "demo_s2": "open",
        "release_gate_eligible": False,
    }, "scope overclaims the stage")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI component acceptance passed: shared Home/Self-Test primitives, exact TFT HIL, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
