#!/usr/bin/env python3
"""Machine-check exact 0.57 guided Self-Test and real-TFT state evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_visual_system_acceptance import decode_png


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-ui-states-0.57.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-ui-states-0.57"
SHA256 = re.compile(r"[0-9a-f]{64}")

FILES = {
    "mode_menu": "00-self-test-modes",
    "preflight": "01-preflight",
    "dialog": "02-dialog",
    "unavailable": "03-unavailable",
    "degraded": "04-degraded",
    "error": "05-error",
    "running": "06-running",
    "result": "07-result",
    "home_cleanup": "08-home-cleanup",
}

EXPECTED_STATE = {
    "mode_menu": (5, "self_test", "mode_menu", "quick",
                  ["down", "down", "down", "down", "right"]),
    "preflight": (7, "self_test", "preflight", "full_guided", ["down", "select"]),
    "dialog": (8, "self_test", "visual_check", "full_guided", ["select"]),
    "unavailable": (9, "self_test", "visual_check", "full_guided", ["select"]),
    "degraded": (10, "self_test", "visual_check", "full_guided", ["select"]),
    "error": (11, "self_test", "visual_check", "full_guided", ["select"]),
    "running": (12, "self_test", "visual_check", "full_guided", ["select"]),
    "result": (13, "self_test", "result", "full_guided", ["select"]),
    "home_cleanup": (15, "home", "mode_menu", "full_guided", ["left", "left"]),
}

STATE_TONES = {
    "dialog": (247, 199, 66),
    "unavailable": (107, 117, 107),
    "degraded": (247, 166, 66),
    "error": (247, 93, 90),
    "running": (82, 219, 140),
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
    require(failures, evidence.get("schema") == "leshy.ui_states_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-059", "E-HIL-081", "E-UX-007"],
            "evidence IDs mismatch")
    require(failures, evidence.get("gate_eligible") is False,
            "UX-07 evidence must not claim stage/release eligibility")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.57.0-ui-state-evidence-measure",
        "firmware_sha256": "9385244167e5234bd21e2872567d6dbb99ce94a45092f052ce001f969d8a0d86",
        "factory_sha256": "3ff89d1002c61bab98854b0c2164a64ac0ec81eca1e7961221043dc04e7e83ad",
        "app_elf_sha256": "e8c7515dc4c5b66f7913639bb3d19d6fdd54e49cf28cf532ea0dfb69e817051a",
        "map_sha256": "3c9cd118c1f2d499a10b9f6d0e0555719d629388fcd5d6ec3132b6e0ba2cd891",
        "linked_flash_bytes": 1107448,
        "static_ram_bytes": 128744,
        "app_image_bytes": 1107600,
        "factory_image_bytes": 1173136,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate block mismatch")

    screens = evidence.get("screens", {})
    require(failures, set(screens) == set(FILES), "retained screen set mismatch")
    decoded: dict[str, list[list[tuple[int, int, int]]]] = {}
    state_rgb: list[str] = []
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
        revision, page, view, mode, actions = EXPECTED_STATE[name]
        state = trace.get("post_capture_state", {})
        require(failures, trace.get("actions") == actions and
                state.get("revision") == revision and state.get("page") == page and
                state.get("self_test_view") == view and
                state.get("self_test_mode") == mode and state.get("language") == "ru",
                f"{name}: Action/state trace mismatch")
        require(failures, trace.get("frame_begin", {}).get("revision") == revision ==
                trace.get("frame_end", {}).get("revision"),
                f"{name}: capture revision mismatch")
        try:
            width, height, pixels = decode_png(png)
        except ValueError as error:
            failures.append(str(error))
        else:
            require(failures, (width, height) == (240, 320),
                    f"{name}: TFT dimensions mismatch")
            decoded[name] = pixels
        if name in STATE_TONES:
            state_rgb.append(str(hashes[1]))

    require(failures, len(state_rgb) == 5 and len(set(state_rgb)) == 5,
            "guided state frames must all be distinct")
    for name, tone in STATE_TONES.items():
        if name not in decoded:
            continue
        pixels = decoded[name]
        card_tone = sum(pixel == tone for row in pixels[92:204] for pixel in row[12:228])
        square_tone = sum(pixel == tone for row in pixels[107:125] for pixel in row[24:42])
        require(failures, card_tone >= 500, f"{name}: explicit tone/text/card missing")
        require(failures, square_tone == 68,
                f"{name}: non-color square outline mismatch")

    runtime = evidence.get("runtime", {})
    records: dict[str, dict[str, Any]] = {}
    runtime_files = {
        "metrics": ("metrics.json", "metrics_sha256"),
        "input": ("input.json", "input_sha256"),
        "safe": ("safe-outputs.json", "safe_outputs_sha256"),
        "active_report": ("full-report-active.json", "active_report_sha256"),
        "final_ui": ("final-ui-state.json", "final_ui_state_sha256"),
        "final_report": ("full-report-final.json", "final_report_sha256"),
        "final_input": ("final-input.json", "final_input_sha256"),
        "final_safe": ("final-safe-outputs.json", "final_safe_outputs_sha256"),
    }
    for field, (filename, hash_field) in runtime_files.items():
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == runtime.get(hash_field),
                f"{field}: retained hash mismatch")
        records[field] = load_json(path) if path.is_file() else {}

    metrics = records["metrics"]
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            metrics.get("heap_total") == 272760 and
            metrics.get("heap_free") == 224280 and
            metrics.get("heap_min_free") == 188792,
            "runtime identity/heap mismatch")
    for field in ("input", "final_input"):
        input_state = records[field]
        require(failures, input_state.get("status") == "ready" and
                input_state.get("read_errors") == 0 and
                input_state.get("ambiguous_presses") == 0 and
                input_state.get("queue_drops") == 0 and
                input_state.get("maximum_sample_gap_ms", 999) <= 5,
                f"{field}: input health mismatch")
    for field in ("safe", "final_safe"):
        safe = records[field]
        require(failures, safe.get("buzzer_inactive") is True and
                safe.get("buzzer_level") == "low", f"{field}: buzzer safety mismatch")

    expected_checks = [
        ("quick.build.identity", "pass"),
        ("quick.board.profile", "pass"),
        ("quick.runtime.heap", "pass"),
        ("quick.display.ready", "pass"),
        ("quick.input.frontend", "pass"),
        ("quick.input.queue", "pass"),
        ("quick.output.buzzer", "pass"),
        ("quick.resource.scope", "pass"),
        ("full.ui.common_states", "pass"),
        ("full.capability.coverage", "blocked"),
    ]
    for field, owner, lease in (("active_report", "self-test", 1),
                                ("final_report", "none", 0)):
        report = records[field]
        checks = [(item.get("id"), item.get("status"))
                  for item in report.get("checks", [])]
        require(failures, report.get("plan_version") == 2 and
                report.get("firmware_version") == candidate.get("version") and
                report.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                report.get("mode") == "full_guided" and
                report.get("status") == "blocked" and
                report.get("passed") == 9 and report.get("failed") == 0 and
                report.get("blocked") == 1 and checks == expected_checks and
                report.get("side_effects") == {
                    "radio_tx_commands": 0, "storage_write_commands": 0,
                    "buzzer_activations": 0} and
                report.get("current_owner") == owner and
                report.get("current_lease_mask") == lease,
                f"{field}: Full/Guided report mismatch")

    result_state = load_json(BUNDLE / "07-result.png.json").get("post_capture_state", {})
    require(failures, result_state.get("self_test_checks") == 10 and
            result_state.get("self_test_passed") == 9 and
            result_state.get("self_test_failed") == 0 and
            result_state.get("self_test_blocked") == 1,
            "result screen/report mismatch")
    final = records["final_ui"]
    require(failures, final.get("page") == "home" and
            final.get("selected_id") == "self-test" and final.get("selection") == 4 and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0,
            "final Home/cleanup mismatch")

    require(failures, evidence.get("self_test_contract") == {
        "home_position": "last", "automatic_at_boot": False,
        "modes": ["quick", "full_guided"],
        "user_and_release_share_engine": True,
        "full_current_status": "blocked_until_capability_coverage",
        "radio_tx_commands": 0, "storage_write_commands": 0,
        "buzzer_activations": 0,
    }, "Self-Test product contract mismatch")
    require(failures, evidence.get("scope") == {
        "ux_03": "accepted", "ux_04": "accepted", "ux_05": "accepted",
        "ux_06": "accepted", "ux_07": "implemented_and_physically_evidenced",
        "demo_s2": "open", "release_gate_eligible": False,
    }, "scope overclaims S2/release")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("UI state acceptance passed: last-item Self-Test, five guided states, Full 9/10 blocked honestly, zero side effects and final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
