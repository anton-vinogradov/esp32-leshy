#!/usr/bin/env python3
"""Machine-check exact 0.56 UX-06 source, physical-key, and TFT evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_visual_system_acceptance import decode_png


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-accessibility-0.56.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-ui-accessibility-0.56"
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"
SHA256 = re.compile(r"[0-9a-f]{64}")

FILES = {
    "home_diagnostics_focus": "home-diagnostics-focus",
    "home_survey_focus": "home-survey-focus",
    "survey_setup": "survey-setup",
    "home_library_focus": "home-library-focus",
    "library_list": "library-list",
    "home_language_focus": "home-language-focus",
    "language_ru": "language-ru",
    "home_self_test_focus": "home-self-test-focus",
    "self_test_quick_focus": "self-test-quick-focus",
    "self_test_full_focus": "self-test-full-focus",
    "quick_result": "quick-result",
    "home_final": "home-final",
}

EXPECTED_STATE = {
    "home_diagnostics_focus": (0, "home", []),
    "home_survey_focus": (1, "home", ["down"]),
    "survey_setup": (2, "survey", ["right"]),
    "home_library_focus": (4, "home", ["left", "down"]),
    "library_list": (5, "library", ["right"]),
    "home_language_focus": (7, "home", ["left", "down"]),
    "language_ru": (8, "language", ["right"]),
    "home_self_test_focus": (10, "home", ["left", "down"]),
    "self_test_quick_focus": (11, "self_test", ["right"]),
    "self_test_full_focus": (12, "self_test", ["down"]),
    "quick_result": (14, "self_test", ["up", "select"]),
    "home_final": (16, "home", ["left", "left"]),
}


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    failures: list[str] = []
    evidence = load_json(EVIDENCE)
    require(failures, evidence.get("schema") == "leshy.ui_accessibility_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-058", "E-HIL-080", "E-UX-006"],
            "evidence IDs mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "UX-06 evidence must not claim stage/release eligibility")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.56.0-ui-accessibility-measure",
        "firmware_sha256": "38d9ac9cd746321a7cd182a9ba59d2081a8b0aec25e0af0b02d6e6ac877f3d81",
        "factory_sha256": "cdb5b3f88a4e8534571d67b911faaaac25760e51cce19baa08a024cd9159c7d4",
        "app_elf_sha256": "65c4731726aa9e443ed8030a2bfaa709978d87b5ae19820c7de55c4306e47c2a",
        "map_sha256": "0fb70d4330d50276a5acb0719a8fd93cebc342f3f77b1144dbda839ee07531b1",
        "linked_flash_bytes": 1105748,
        "static_ram_bytes": 128744,
        "app_image_bytes": 1105904,
        "factory_image_bytes": 1171440,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate block mismatch")
    require(failures, 'LESHY1_VERSION=\\"0.56.0-ui-accessibility-measure\\"' in
            PLATFORMIO.read_text(encoding="utf-8"), "current version mismatch")

    physical = evidence.get("physical_input", {})
    physical_path = ROOT / str(physical.get("retained_path", "missing"))
    require(failures, physical_path.is_file() and
            digest(physical_path) == physical.get("retained_sha256"),
            "physical keypad artifact binding mismatch")
    keypad = load_json(physical_path) if physical_path.is_file() else {}
    after = keypad.get("after", {})
    require(failures, keypad.get("status") == "pass" and
            after.get("presses") == {"select": 10, "up": 10, "down": 10,
                                      "left": 10, "right": 10} and
            after.get("press_events") == 50 and
            after.get("release_events") == 50 and
            after.get("dispatched_press_events") == 50 and
            after.get("read_errors") == 0 and
            after.get("ambiguous_presses") == 0 and
            after.get("queue_drops") == 0,
            "physical five-key acceptance mismatch")

    screens = evidence.get("screens", {})
    require(failures, set(screens) == set(FILES), "retained screen set mismatch")
    decoded: dict[str, list[list[tuple[int, int, int]]]] = {}
    for name, stem in FILES.items():
        hashes = screens.get(name, [])
        require(failures, isinstance(hashes, list) and len(hashes) == 3 and
                all(isinstance(value, str) and SHA256.fullmatch(value)
                    for value in hashes), f"{name}: invalid hash tuple")
        png = BUNDLE / f"{stem}.png"
        trace_path = BUNDLE / f"{stem}.png.json"
        require(failures, png.is_file() and trace_path.is_file(),
                f"{name}: retained files missing")
        if not png.is_file() or not trace_path.is_file() or len(hashes) != 3:
            continue
        require(failures, digest(png) == hashes[0], f"{name}: PNG hash mismatch")
        require(failures, digest(trace_path) == hashes[2],
                f"{name}: trace hash mismatch")
        trace = load_json(trace_path)
        require(failures, trace.get("rgb565_sha256") == hashes[1],
                f"{name}: RGB565 hash mismatch")
        expected_revision, expected_page, expected_actions = EXPECTED_STATE[name]
        state = trace.get("post_capture_state", {})
        require(failures, trace.get("actions") == expected_actions and
                state.get("revision") == expected_revision and
                state.get("page") == expected_page and
                state.get("language") == "ru",
                f"{name}: public Action/state trace mismatch")
        require(failures, trace.get("frame_begin", {}).get("revision") ==
                expected_revision == trace.get("frame_end", {}).get("revision"),
                f"{name}: capture revision mismatch")
        try:
            width, height, pixels = decode_png(png)
        except ValueError as error:
            failures.append(str(error))
        else:
            require(failures, (width, height) == (240, 320),
                    f"{name}: TFT dimensions mismatch")
            decoded[name] = pixels

    focus = (247, 199, 66)
    focused_rows = {
        "home_diagnostics_focus": 82,
        "home_survey_focus": 111,
        "home_library_focus": 140,
        "home_language_focus": 169,
        "home_self_test_focus": 201,
        "library_list": 94,
        "self_test_quick_focus": 94,
        "self_test_full_focus": 152,
    }
    for name, top in focused_rows.items():
        if name not in decoded:
            continue
        pixels = decoded[name]
        outline = sum(pixels[top][x] == focus for x in range(12, 228))
        marker = sum(pixel == focus for row in pixels[top:top + 42]
                     for pixel in row[12:22])
        require(failures, outline == 210, f"{name}: focus outline missing")
        require(failures, marker >= 67, f"{name}: geometric focus marker missing")

    runtime = evidence.get("runtime", {})
    records: dict[str, dict[str, Any]] = {}
    for field, filename in (("metrics", "metrics.json"), ("input", "input.json"),
                            ("safe_outputs", "safe-outputs.json"),
                            ("quick_report", "quick-report.json")):
        path = BUNDLE / filename
        require(failures, path.is_file() and
                digest(path) == runtime.get(f"{field}_sha256"),
                f"{field}: retained hash mismatch")
        records[field] = load_json(path) if path.is_file() else {}
    metrics = records["metrics"]
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            metrics.get("heap_total") == 272760 and
            metrics.get("heap_free") == 224280 and
            metrics.get("heap_min_free") == 188792,
            "runtime identity/heap mismatch")
    input_state = records["input"]
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and
            input_state.get("ambiguous_presses") == 0 and
            input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5,
            "current input health mismatch")
    safe = records["safe_outputs"]
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer safety mismatch")
    quick = records["quick_report"]
    side_effects = quick.get("side_effects", {})
    require(failures, quick.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            quick.get("status") == "pass" and quick.get("passed") == 8 and
            quick.get("failed") == 0 and quick.get("blocked") == 0 and
            quick.get("duration_us") == 66 and
            side_effects == {"radio_tx_commands": 0, "storage_write_commands": 0,
                             "buzzer_activations": 0} and
            quick.get("current_owner") == "none" and
            quick.get("current_lease_mask") == 0,
            "Quick regression mismatch")
    final_trace = load_json(BUNDLE / "home-final.png.json")
    final = final_trace.get("post_capture_state", {})
    require(failures, final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and final.get("page") == "home",
            "final cleanup mismatch")

    require(failures, evidence.get("scope") == {
        "ux_03": "accepted", "ux_04": "accepted", "ux_05": "accepted",
        "ux_06": "implemented_and_physically_evidenced", "ux_07": "partial",
        "demo_s2": "open", "release_gate_eligible": False,
    }, "scope overclaims S2/release")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI accessibility acceptance passed: five-key mapping, non-color focus, exact TFT actions, Quick 8/8, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
