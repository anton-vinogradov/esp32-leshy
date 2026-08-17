#!/usr/bin/env python3
"""Machine-check retained board-01 UX-05 EN/RU evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from check_visual_system_acceptance import decode_png


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-language-0.55.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained(failures: list[str], relative: object, expected: object) -> Path | None:
    require(failures, isinstance(relative, str) and bool(relative), "retained path missing")
    require(failures, isinstance(expected, str) and SHA256.fullmatch(expected or "") is not None,
            f"invalid retained hash: {relative}")
    if not isinstance(relative, str):
        return None
    path = ROOT / relative
    require(failures, path.is_file(), f"missing retained file: {relative}")
    if path.is_file() and isinstance(expected, str):
        require(failures, digest(path) == expected, f"retained hash mismatch: {relative}")
    return path if path.is_file() else None


def main() -> int:
    failures: list[str] = []
    if not EVIDENCE.is_file():
        print(f"FAIL: missing {EVIDENCE}", file=sys.stderr)
        return 1
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures, evidence.get("schema") == "leshy.ui_language_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-057", "E-HIL-079", "E-UX-005"],
            "evidence IDs mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "UX-05 evidence must not claim the S2/release gate")

    expected_candidate = {
        "version": "0.55.0-ui-language-measure",
        "firmware_sha256": "c9709ae952c210c277bbd820c80a32dfcb308dd6b813c9c8ca4398d3b814fd1f",
        "factory_sha256": "3e79f7d37c6c1e753c5e2ee0ac2a4df2fc25972237111092f1fe6c8bb0883f8b",
        "app_elf_sha256": "16e247eecb4f499039d7eb2e710b2921fb9a3de3af08478ff307178f6442e515",
        "map_sha256": "bc5df588aa45616fbf7072aca888382a032fb756966755284ac817d8eccc9c16",
        "linked_flash_bytes": 1104448,
        "static_ram_bytes": 128744,
        "app_image_bytes": 1104592,
        "factory_image_bytes": 1170128,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }
    candidate = evidence.get("candidate", {})
    require(failures, candidate == expected_candidate, "candidate block mismatch")

    font = evidence.get("font", {})
    require(failures, font.get("license") == "SIL Open Font License 1.1" and
            font.get("ttf_sha256") ==
            "4102edda03059163771869d258df54ac8563c408fa6e9ef75b2ddc85eabea6f4" and
            font.get("runtime_heap_allocations") == 0,
            "font provenance/runtime contract mismatch")
    catalog = evidence.get("catalog", {})
    require(failures, catalog.get("languages") == ["en", "ru"] and
            catalog.get("entries") == 111 and catalog.get("measured_variants") == 222 and
            catalog.get("all_fit_declared_pixel_budget") is True,
            "catalog coverage/fit mismatch")
    navigation = evidence.get("navigation", {})
    require(failures, navigation == {
        "home_items": 5,
        "language_page": 4,
        "self_test_page": 5,
        "self_test_is_final": True,
        "language_applies_immediately": True,
        "language_persisted_in_nvs": True,
        "russian_restored_after_exact_candidate_flash_reset": True,
    }, "navigation/persistence contract mismatch")

    expected_screens = {
        "home_ru_persisted", "diagnostics_ru", "survey_setup_ru", "library_ru",
        "language_ru", "self_test_ru", "quick_result_ru", "home_en",
        "language_en", "home_final_ru",
    }
    screens = evidence.get("screens", {})
    require(failures, set(screens) == expected_screens, "screen set mismatch")
    decoded = {}
    for name, record in screens.items():
        png_path = retained(failures, record.get("path"), record.get("png_sha256"))
        trace_path = retained(failures, record.get("trace_path"), record.get("trace_sha256"))
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
            state = trace.get("post_capture_state", {})
            require(failures, state.get("page") == record.get("page") and
                    state.get("language") == record.get("language"),
                    f"{name}: state binding mismatch")
            require(failures, trace.get("rgb565_sha256") == record.get("rgb565_sha256") and
                    trace.get("png_sha256") == record.get("png_sha256"),
                    f"{name}: frame hash binding mismatch")
            require(failures, trace.get("frame_begin", {}).get("width") == 240 and
                    trace.get("frame_begin", {}).get("height") == 320,
                    f"{name}: capture metadata mismatch")

    if expected_screens.issubset(decoded):
        require(failures, decoded["home_en"] != decoded["home_ru_persisted"],
                "EN and RU Home frames must be visually distinct")
        require(failures, decoded["language_en"] != decoded["language_ru"],
                "EN and RU Language frames must be visually distinct")
        divider = (57, 73, 66)
        for name, pixels in decoded.items():
            require(failures, all(pixels[236][x] == divider for x in range(12, 228)),
                    f"{name}: footer divider missing or overwritten")
        require(failures, len({record["png_sha256"] for record in screens.values()}) == 10,
                "retained acceptance frames must be distinct")

    persisted_trace = json.loads(
        (ROOT / screens.get("home_ru_persisted", {}).get("trace_path", "missing")).read_text()
    ) if screens.get("home_ru_persisted") else {}
    require(failures, persisted_trace.get("frame_begin", {}).get("revision") == 0 and
            persisted_trace.get("post_capture_state", {}).get("language") == "ru",
            "Russian was not restored at exact-candidate boot")

    runtime = evidence.get("runtime", {})
    records = {}
    for key in ("metrics", "quick_report", "input", "safe_outputs", "switch_en", "switch_ru"):
        path = retained(failures, runtime.get(f"{key}_path"), runtime.get(f"{key}_sha256"))
        records[key] = json.loads(path.read_text()) if path is not None else {}
    metrics = records["metrics"]
    report = records["quick_report"]
    input_state = records["input"]
    safe = records["safe_outputs"]
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            metrics.get("heap_total") == 272760 and metrics.get("heap_free") == 224280 and
            metrics.get("heap_min_free") == 188792,
            "runtime identity/heap mismatch")
    require(failures, report.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            report.get("status") == "pass" and report.get("passed") == 8 and
            report.get("failed") == 0 and report.get("blocked") == 0 and
            report.get("read_only") is True and report.get("current_owner") == "none" and
            report.get("current_lease_mask") == 0,
            "Quick regression/cleanup mismatch")
    require(failures, report.get("side_effects") == {
        "buzzer_activations": 0, "radio_tx_commands": 0, "storage_write_commands": 0,
    }, "Quick side effects mismatch")
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5,
            "input health mismatch")
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer safety mismatch")
    require(failures, records["switch_en"].get("language") == "en" and
            records["switch_ru"].get("language") == "ru" and
            records["switch_ru"].get("runtime_owner") == "none" and
            records["switch_ru"].get("lease_mask") == 0,
            "language switching/final lease mismatch")

    require(failures, evidence.get("scope") == {
        "ux_03": "accepted", "ux_04": "accepted",
        "ux_05": "implemented_and_physically_evidenced", "ux_06": "open",
        "ux_07": "partial", "demo_s2": "open", "release_gate_eligible": False,
    }, "scope overclaims the stage")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI language acceptance passed: EN/RU fit, persistence, exact TFT HIL, Quick 8/8, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
