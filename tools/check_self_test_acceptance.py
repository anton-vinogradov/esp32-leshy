#!/usr/bin/env python3
"""Fail-closed verifier for retained board-01 Self-Test 0.53 evidence."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "tests/hil/evidence/board-01-self-test-0.53.json"
EVIDENCE_ROOT = EVIDENCE_PATH.parent
SOURCE = ROOT / "firmware/leshy1/src/apps/self_test/SelfTestController.cpp"
HEADER = ROOT / "firmware/leshy1/src/apps/self_test/SelfTestController.h"
CATALOG = ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.cpp"
CATALOG_HEADER = ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.h"
UI = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
UI_CONTROLLER = ROOT / "firmware/leshy1/src/ui/UiController.cpp"
SHA256 = re.compile(r"[0-9a-f]{64}")
QUICK_IDS = [
    "quick.build.identity",
    "quick.board.profile",
    "quick.runtime.heap",
    "quick.display.ready",
    "quick.input.frontend",
    "quick.input.queue",
    "quick.output.buzzer",
    "quick.resource.scope",
]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def retained_path(failures: list[str], relative: Any) -> Path | None:
    if not isinstance(relative, str):
        failures.append("retained path is not a string")
        return None
    path = (EVIDENCE_ROOT / relative).resolve()
    try:
        path.relative_to(EVIDENCE_ROOT.resolve())
    except ValueError:
        failures.append(f"retained path escapes evidence root: {relative}")
        return None
    require(failures, path.is_file(), f"retained file missing: {relative}")
    return path if path.is_file() else None


def verify_file(failures: list[str], relative: Any, expected: Any) -> Path | None:
    path = retained_path(failures, relative)
    require(failures, isinstance(expected, str) and SHA256.fullmatch(expected) is not None,
            f"invalid SHA-256 for {relative}")
    if path is not None and isinstance(expected, str):
        require(failures, digest(path) == expected, f"hash mismatch: {relative}")
    return path


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def main() -> int:
    failures: list[str] = []
    evidence = load(EVIDENCE_PATH)
    require(failures, evidence.get("schema") == "leshy.self_test_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_id") == "E-HIL-077",
            "evidence ID mismatch")

    candidate = evidence.get("candidate", {})
    expected_candidate = {
        "version": "0.53.0-self-test-quick-measure",
        "firmware_sha256": "25d1f6208b3005b3e13df7e7344837d70526dc83c5b111a077afc4682cc010bb",
        "factory_sha256": "e42c30c7cc902703a7d74cfd2e29c760b36c83f0357d9bc4e04b23aab026ff1f",
        "elf_sha256": "06a5e9d406d5d2459c8ab73941248d7279cc177e28381176f0189e8088701e38",
        "linked_flash_bytes": 1067800,
        "static_ram_bytes": 128720,
        "app_image_bytes": 1068208,
        "factory_image_bytes": 1133744,
        "rtc_noinit_bytes": 20,
    }
    require(failures, candidate == expected_candidate, "candidate block mismatch")

    quick = evidence.get("quick", {})
    quick_path = verify_file(failures, quick.get("report_path"), quick.get("report_sha256"))
    quick_report = load(quick_path) if quick_path is not None else {}
    require(failures, quick_report.get("schema") == "leshy.self_test.report.v1",
            "Quick report schema mismatch")
    require(failures, quick_report.get("plan_version") == 1,
            "Quick plan version mismatch")
    require(failures, quick_report.get("mode") == "quick" and
            quick_report.get("status") == "pass", "Quick must pass")
    require(failures, [item.get("id") for item in quick_report.get("checks", [])] == QUICK_IDS,
            "Quick check IDs/order mismatch")
    require(failures, all(item.get("status") == "pass"
                          for item in quick_report.get("checks", [])),
            "every Quick check must pass")
    require(failures, quick_report.get("passed") == 8 and
            quick_report.get("failed") == 0 and quick_report.get("blocked") == 0,
            "Quick counts mismatch")
    require(failures, quick_report.get("app_elf_sha256") == candidate.get("elf_sha256"),
            "Quick report is not bound to candidate ELF")
    require(failures, quick_report.get("read_only") is True and
            set(quick_report.get("side_effects", {}).values()) == {0},
            "Quick side-effect contract mismatch")
    require(failures, quick_report.get("current_owner") == "none" and
            quick_report.get("current_lease_mask") == 0,
            "Quick final cleanup mismatch")
    facts = quick_report.get("facts", {})
    require(failures, facts.get("heap_minimum", 0) >= facts.get("heap_floor", 1),
            "Quick heap floor failed")
    require(failures, facts.get("input_queue_drops") == 0 and
            facts.get("buzzer_inactive") is True and
            facts.get("resource_scope_clean") is True,
            "Quick safety facts mismatch")

    full = evidence.get("full_guided", {})
    full_path = verify_file(failures, full.get("report_path"), full.get("report_sha256"))
    full_report = load(full_path) if full_path is not None else {}
    full_checks = full_report.get("checks", [])
    require(failures, full_report.get("mode") == "full_guided" and
            full_report.get("status") == "blocked", "Full must fail closed as blocked")
    require(failures, [item.get("id") for item in full_checks[:-1]] == QUICK_IDS,
            "Full must reuse Quick check IDs")
    require(failures, len(full_checks) == 9 and
            full_checks[-1] == {"id": "full.capability.coverage", "status": "blocked"},
            "Full coverage blocker mismatch")
    require(failures, full_report.get("passed") == 8 and
            full_report.get("failed") == 0 and full_report.get("blocked") == 1,
            "Full counts mismatch")

    runtime = evidence.get("runtime", {})
    metrics_path = verify_file(failures, runtime.get("metrics_path"),
                               runtime.get("metrics_sha256"))
    input_path = verify_file(failures, runtime.get("input_path"),
                             runtime.get("input_sha256"))
    safe_path = verify_file(failures, runtime.get("safe_outputs_path"),
                            runtime.get("safe_outputs_sha256"))
    metrics = load(metrics_path) if metrics_path is not None else {}
    input_state = load(input_path) if input_path is not None else {}
    safe = load(safe_path) if safe_path is not None else {}
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("elf_sha256"),
            "runtime identity mismatch")
    require(failures, metrics.get("heap_free") == 224332 and
            metrics.get("heap_min_free") == 188872,
            "runtime heap mismatch")
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and
            input_state.get("ambiguous_presses") == 0 and
            input_state.get("queue_depth") == 0 and
            input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms") <= 5,
            "input final state mismatch")
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer final state mismatch")

    expected_screens = {"modes", "quick_result", "full_preflight",
                        "full_blocked", "home_cleanup"}
    screens = evidence.get("screens", {})
    require(failures, set(screens) == expected_screens, "screen set mismatch")
    for name in sorted(expected_screens):
        record = screens.get(name, {})
        path = verify_file(failures, record.get("path"), record.get("png_sha256"))
        require(failures, isinstance(record.get("rgb565_sha256"), str) and
                SHA256.fullmatch(record.get("rgb565_sha256", "")) is not None,
                f"{name}: invalid RGB565 SHA-256")
        if path is not None:
            require(failures, png_dimensions(path) == (240, 320),
                    f"{name}: dimensions mismatch")

    rejected = evidence.get("rejected_attempt", {})
    raw_path = verify_file(failures, rejected.get("raw_path"), rejected.get("raw_sha256"))
    require(failures, rejected.get("status") == "fail_closed", "panic not fail-closed")
    if raw_path is not None:
        require(failures, b"Guru Meditation Error" in raw_path.read_bytes(),
                "panic raw marker missing")

    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    catalog = CATALOG.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    for check_id in QUICK_IDS + ["full.capability.coverage"]:
        require(failures, f'"{check_id}"' in source, f"source check missing: {check_id}")
    for forbidden in ("WiFi", "SD.", "digitalWrite", "tone(", "SPI.begin"):
        require(failures, forbidden not in source, f"Self-Test starts forbidden path: {forbidden}")
    require(failures, "kCapacity = 5" in CATALOG_HEADER.read_text(encoding="utf-8") and
            '"self-test", "SELF-TEST"' in catalog and
            catalog.index('"self-test", "SELF-TEST"') > catalog.index('"language", "LANGUAGE"'),
            "Self-Test is not the final catalog item")
    require(failures, 'case 5: return "self_test"' in
            UI_CONTROLLER.read_text(encoding="utf-8"), "Self-Test page mapping missing")
    require(failures, "char diagnosticJson[3072]" in ui and
            "char line[3072]" not in ui,
            "diagnostic JSON must reuse static bounded workspace")
    # The exact candidate block binds the historical 0.53 evidence. Current
    # source may advance while this accepted Self-Test evidence stays replayable.
    require(failures, evidence.get("scope") == {
        "quick_s2_slice_accepted": True,
        "full_guided_complete": False,
        "s2_gate_complete": False,
        "release_gate_eligible": False,
    }, "scope must remain honest")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("self-test acceptance passed: Quick 8/8, Full blocked honestly, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
