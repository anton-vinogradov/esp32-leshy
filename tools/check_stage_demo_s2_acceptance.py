#!/usr/bin/env python3
"""Machine-check retained exact-candidate DEMO-S2 evidence."""

from __future__ import annotations

import hashlib
import json
import sys
import zlib
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import masked_frame


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-stage-demo-s2-0.58.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-stage-demo-s2-0.58"
SUITE = ROOT / "tests/hil/stage-demo-s2.v1.json"


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
    require(failures, evidence.get("schema") == "leshy.stage_demo_s2_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("status") == "pass_s2_stage_gate" and
            evidence.get("stage_gate_eligible") is True and
            evidence.get("release_gate_eligible") is False,
            "stage/release eligibility mismatch")
    require(failures, evidence.get("evidence_ids") ==
            ["E-BUILD-060", "E-AUTO-022", "E-HIL-082", "E-GATE-002"],
            "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.58.0-stage-demo-s2-measure",
        "source_commit": "d696c9bcd0af5564453e8702e8a63f28a09b30ba",
        "source_worktree_clean_before_evidence_copy": True,
        "firmware_sha256": "b4d854f4735e2fb83f202169951107a7a8c9a7f97beb07d0af7c1cf3e45dc50a",
        "factory_sha256": "fd5ec12e2f67eddfdf1fdeec38578c9219f18b51429cced76162f90817a8b553",
        "app_elf_sha256": "ec12011c7134e08aa857e6209e846b29d41428a1dcad98840c69c09d80e85d4f",
        "map_sha256": "91d2e6cc1ea9d019a823297be3fb841f2736d28d558dd3a00d0ed7e302a3945a",
        "linked_flash_bytes": 1107612,
        "static_ram_bytes": 128744,
        "app_image_bytes": 1107760,
        "factory_image_bytes": 1173296,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate block mismatch")

    retained = evidence.get("retained", {})
    retained_files = {
        "run_sha256": BUNDLE / "run.json",
        "artifact_index_sha256": BUNDLE / "artifacts.sha256",
        "runner_result_sha256": BUNDLE / "runner-result.json",
        "candidate_manifest_sha256": BUNDLE / "candidate-manifest.json",
        "serial_sha256": BUNDLE / "serial.ndjson",
        "golden_recording_run_sha256": BUNDLE / "golden-recording-run.json",
        "golden_recording_runner_result_sha256":
            BUNDLE / "golden-recording-runner-result.json",
    }
    for field, path in retained_files.items():
        require(failures, path.is_file() and digest(path) == retained.get(field),
                f"{field}: retained hash mismatch")
    require(failures, SUITE.is_file() and digest(SUITE) == retained.get("suite_sha256"),
            "suite hash mismatch")

    index_path = BUNDLE / "artifacts.sha256"
    indexed: set[str] = set()
    if index_path.is_file():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("  ", 1)
            if len(parts) != 2:
                failures.append("artifact index contains malformed line")
                continue
            expected, relative = parts
            path = (BUNDLE / relative).resolve()
            try:
                path.relative_to(BUNDLE.resolve())
            except ValueError:
                failures.append(f"artifact escapes bundle: {relative}")
                continue
            require(failures, path.is_file() and digest(path) == expected,
                    f"artifact hash mismatch: {relative}")
            indexed.add(relative)
    require(failures, "candidate/firmware.bin" in indexed and
            "run.json" in indexed and "serial.ndjson" in indexed and
            len([value for value in indexed if value.endswith(".rgb565")]) == 9,
            "artifact index is incomplete")

    firmware = BUNDLE / "candidate/firmware.bin"
    require(failures, firmware.is_file() and firmware.stat().st_size == 1107760 and
            digest(firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            "bundled exact candidate mismatch")
    manifest = load_json(BUNDLE / "candidate-manifest.json")
    require(failures, manifest.get("firmware_sha256") == candidate.get("firmware_sha256") and
            manifest.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            manifest.get("firmware_bytes") == 1107760 and
            manifest.get("flashed_by_runner") is True and
            manifest.get("suite_id") == "stage-demo-s2" and
            manifest.get("suite_revision") == 1,
            "candidate manifest mismatch")

    runner = load_json(BUNDLE / "runner-result.json")
    require(failures, runner.get("passed") is True and
            runner.get("gate_eligible") is False and
            runner.get("trust_status") == "unsigned_local_result" and
            runner.get("bundle_sha256") == digest(index_path),
            "local runner-result trust/bundle mismatch")
    recording = load_json(BUNDLE / "golden-recording-run.json")
    recorded_visuals = [step.get("capture", {}).get("visual", {}).get("status")
                        for step in recording.get("trace", []) if step.get("capture")]
    require(failures, recording.get("passed") is True and
            recording.get("gate_eligible") is False and
            recording.get("goldens_recorded") is True and
            recorded_visuals == ["recorded"] * 9,
            "separate non-gate golden recording mismatch")

    run = load_json(BUNDLE / "run.json")
    require(failures, run.get("passed") is True and run.get("failures") == [] and
            run.get("gate_eligible") is True and
            run.get("goldens_recorded") is False and
            run.get("candidate_flashed") is True and
            run.get("suite_id") == "stage-demo-s2" and
            run.get("suite_revision") == 1 and
            run.get("candidate_sha256") == candidate.get("firmware_sha256") and
            run.get("candidate_app_elf_sha256") == candidate.get("app_elf_sha256"),
            "gate run identity/result mismatch")
    trace = run.get("trace", [])
    require(failures, isinstance(trace, list) and len(trace) == 29 and
            all(step.get("assertion_failures") == [] for step in trace),
            "29-step Action/query trace mismatch")
    by_id = {step.get("id"): step for step in trace}

    boot = run.get("boot", {})
    ready = boot.get("ready", {})
    require(failures, ready.get("version") == candidate.get("version") and
            ready.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            ready.get("legacy_sources") is False and
            ready.get("buzzer_inactive") is True and
            ready.get("input_detected") is True and
            0 < boot.get("ready_marker_ms", 9999) <= 2000,
            "cold-boot identity/readiness mismatch")
    session = run.get("hil_session", {})
    require(failures, session.get("begin", {}).get("active") is True and
            session.get("begin", {}).get("session_id") == run.get("run_id") and
            session.get("end", {}).get("active") is False and
            session.get("end", {}).get("session_id") == run.get("run_id") and
            session.get("end", {}).get("ui_revision") == 26,
            "bounded HIL session mismatch")

    input_state = by_id.get("input-ready", {}).get("record", {})
    require(failures, input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and
            input_state.get("ambiguous_presses") == 0 and
            input_state.get("queue_drops") == 0 and
            input_state.get("maximum_sample_gap_ms", 999) <= 5,
            "input frontend health mismatch")
    quick = by_id.get("quick-report", {}).get("record", {})
    expected_checks = [
        "quick.build.identity", "quick.board.profile", "quick.runtime.heap",
        "quick.display.ready", "quick.input.frontend", "quick.input.queue",
        "quick.output.buzzer", "quick.resource.scope",
    ]
    require(failures, quick.get("plan_version") == 2 and
            quick.get("mode") == "quick" and quick.get("status") == "pass" and
            quick.get("passed") == 8 and quick.get("failed") == 0 and
            quick.get("blocked") == 0 and 1 <= quick.get("duration_us", 0) <= 10000 and
            [item.get("id") for item in quick.get("checks", [])] == expected_checks and
            all(item.get("status") == "pass" for item in quick.get("checks", [])) and
            quick.get("side_effects") == {
                "radio_tx_commands": 0, "storage_write_commands": 0,
                "buzzer_activations": 0},
            "Quick plan/report mismatch")

    require(failures,
            by_id.get("full-dialog-confirm", {}).get("state", {}).get(
                "self_test_visual_state") == "dialog_confirm" and
            by_id.get("full-unavailable-reason", {}).get("state", {}).get(
                "self_test_visual_state") == "unavailable",
            "explicit unavailable/dialog state identity mismatch")

    suite = load_json(SUITE)
    capture_specs: dict[str, dict[str, Any]] = {}
    for scenario in suite.get("scenarios", []):
        for step in scenario.get("steps", []):
            capture = step.get("capture")
            if capture:
                capture_specs[str(capture.get("name", step["id"]))] = capture
    captures = [step for step in trace if step.get("capture")]
    require(failures, len(captures) == 9 and set(capture_specs) ==
            {step.get("capture", {}).get("name") for step in captures},
            "nine-capture set mismatch")
    for step in captures:
        capture = step["capture"]
        name = capture.get("name")
        spec = capture_specs.get(name, {})
        raw = BUNDLE / f"frames/{name}.rgb565"
        png = BUNDLE / f"frames/{name}.png"
        golden = (SUITE.parent / str(spec.get("golden", "missing"))).resolve()
        require(failures, capture.get("visual", {}).get("status") == "matched" and
                capture.get("visual", {}).get("mismatch_pixels") == 0,
                f"{name}: visual match mismatch")
        require(failures, raw.is_file() and raw.stat().st_size == 153600 and
                digest(raw) == capture.get("rgb565_sha256") and
                png.is_file() and digest(png) == capture.get("png_sha256") and
                golden.is_file(), f"{name}: retained frame/golden mismatch")
        if raw.is_file() and golden.is_file():
            actual = raw.read_bytes()
            expected = zlib.decompress(golden.read_bytes())
            masks = spec.get("masks", []) if spec.get("mode") == "masked_exact" else []
            require(failures,
                    masked_frame(actual, 240, 320, masks) ==
                    masked_frame(expected, 240, 320, masks),
                    f"{name}: independent golden comparison failed")

    metrics = run.get("metrics", {})
    require(failures, metrics.get("version") == candidate.get("version") and
            metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            metrics.get("heap_total") == 272760 and
            metrics.get("heap_free") == 224280 and
            metrics.get("heap_min_free") == 188792,
            "final identity/heap mismatch")
    safe = run.get("safe_outputs", {})
    require(failures, safe.get("buzzer_pin") == 2 and
            safe.get("buzzer_level") == "low" and
            safe.get("buzzer_inactive") is True,
            "final buzzer safety mismatch")
    final = run.get("final_state", {})
    require(failures, final.get("page") == "home" and
            final.get("selection") == 4 and final.get("selected_id") == "self-test" and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0 and
            final.get("survey_dropped") == 0 and
            final.get("survey_queue_depth") == 0,
            "final Home/resource cleanup mismatch")
    require(failures, evidence.get("scope") == {
        "s1": "done", "s2": "done", "s3": "active",
        "full_self_test_capability_coverage": "blocked_until_s3_s7",
        "release_gate_eligible": False,
    }, "stage scope mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("DEMO-S2 acceptance passed: exact committed candidate, 29 steps, nine zero-mismatch TFT states, Quick 8/8, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
