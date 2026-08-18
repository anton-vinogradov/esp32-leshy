#!/usr/bin/env python3
"""Fail closed unless the exact 0.88 physical touch proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-touch-input-0.88.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-touch-input-0.88"
COMMIT = "c96590e728bfa9fd0be3b68c1668eca27ff9ba2e"
APP = "9af4a20f603c57722e3c11b8fb44b8c1ba65ca03516bd1be41784c439c1d4e30"
FIRMWARE = "479e8aff67678e2833f6a8c43ef48f4a3bc62ffb6091a974ab37eae26432ae92"
FACTORY = "4dfc89a3dfe42c2844868559eb93f7784b85825a10d9ff58a32a0e36ac551479"
RUNNER = "a57fad1ce7901502c17505be3fef0781e486aa04f59893d562b1cf881938f442"
CALIBRATION = [533, 2996, 531, 3117, 6]
SCREENS = {
    "home_three_targets": "home-three-targets",
    "library_from_touch": "library-from-touch",
    "self_test_from_touch": "self-test-from-touch",
    "quick_touch_pass": "quick-touch-pass",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_index(failures: list[str]) -> None:
    index = BUNDLE / "artifacts.sha256"
    expected: dict[str, str] = {}
    for number, line in enumerate(
            index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
        else:
            expected[parts[1]] = parts[0]
    actual = {
        path.name for path in BUNDLE.iterdir()
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual,
            "artifact index does not cover the exact bundle")
    for name, expected_hash in expected.items():
        path = BUNDLE / name
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"artifact mismatch: {name}")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file() and BUNDLE.is_dir(),
            "0.88 touch evidence is missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    candidate = evidence.get("candidate", {})
    retained = evidence.get("evidence", {})
    verified = evidence.get("verified", {})
    regression = evidence.get("regression", {})
    require(failures,
            evidence.get("schema") == "leshy.touch_input_acceptance.v1" and
            evidence.get("status") == "pass_physical_touch_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.88.0-touch-input" and
            candidate.get("source_commit") == COMMIT,
            "acceptance identity mismatch")
    require(failures,
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("firmware_bytes") == 1497456 and
            candidate.get("factory_bytes") == 1562992 and
            candidate.get("static_ram_bytes") == 149936 and
            candidate.get("linked_flash_bytes") == 1497056,
            "candidate hash/size mismatch")

    require(failures,
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "firmware.elf") == APP and
            digest(BUNDLE / "runner.py") == RUNNER and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP,
            "retained candidate binding mismatch")
    require(failures,
            digest(BUNDLE / "run.original.json") ==
                retained.get("original_run_sha256") ==
                "d93c6458b7f7fb57c847d0a1174b2901f65bcdc8d647b0f3ec0dd6aeb9da2ab7" and
            digest(BUNDLE / "run.json") ==
                retained.get("canonical_run_sha256") ==
                "55ecad0fa0ef48798ef27fbfeee6b402fac2b7258a4afc635e7a2a69ebe0f303" and
            digest(BUNDLE / "artifacts.sha256") ==
                retained.get("artifact_index_sha256") ==
                "5b52f4440201ac801910ee7eb883e955a9dff48982f732232432ef17cb2b93bc" and
            retained.get("files") == 22 and retained.get("tft_states") == 4,
            "retained run/index binding mismatch")
    verify_index(failures)

    source = git_blob(
        "firmware/leshy1/src/platform/arduino/BoardTouchInput.h")
    entry = git_blob(
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    targets = git_blob("firmware/leshy1/src/ui/TouchTargets.cpp")
    runner = git_blob("tools/run_1x_touch_hil.py")
    require(failures, source is not None and
            b"kPressureThreshold = 80" in source and
            b"kDefaultCalibration[5]" in source and
            b"kReleaseDebounceMs" not in source,
            "touch adapter source contract mismatch")
    require(failures, entry is not None and
            b"boardTouchInput.begin(display, millis())" in entry and
            b"dispatchTouchPoint" in entry and
            b'touch_back_enabled\\":false' in entry,
            "touch integration source contract mismatch")
    require(failures, targets is not None and
            b"TouchTargetLayout::HomeRows" in targets and
            b"Components::choiceRow" in targets,
            "shared hit-target source contract mismatch")
    require(failures, runner is not None and
            hashlib.sha256(runner).hexdigest() == RUNNER,
            "runner source binding mismatch")

    run = load(BUNDLE / "run.json")
    original = load(BUNDLE / "run.original.json")
    require(failures,
            run.get("schema") == "leshy.touch_hil.v1" and
            run.get("status") == "pass" and
            run.get("physical_touch_required") is True and
            run.get("physical_touch_observed") is True and
            run.get("candidate", {}).get("version") ==
                "0.88.0-touch-input" and
            run.get("candidate", {}).get("app_elf_sha256") == APP and
            original.get("candidate") == run.get("candidate"),
            "physical run identity mismatch")
    require(failures,
            run.get("heap_invariant") is True and
            run.get("final_owner") == "none" and
            run.get("final_lease_mask") == 0 and
            run.get("quick") == {"passed": 9, "plan_version": 8},
            "run cleanup/Quick mismatch")

    for key, record in run.get("records", {}).items():
        path = ROOT / record.get("path", "missing")
        require(failures, path.parent == BUNDLE and path.is_file() and
                digest(path) == record.get("sha256"),
                f"record binding mismatch: {key}")

    require(failures, set(run.get("screens", {})) == set(SCREENS),
            "exact four TFT states are required")
    for key, record in run.get("screens", {}).items():
        basename = SCREENS.get(key, "missing")
        png = BUNDLE / f"{basename}.png"
        trace = BUNDLE / f"{basename}.json"
        data = png.read_bytes() if png.is_file() else b""
        dimensions = struct.unpack(">II", data[16:24]) \
            if len(data) >= 24 else None
        require(failures,
                dimensions == (240, 320) and trace.is_file() and
                digest(png) == record.get("png_sha256") and
                digest(trace) == record.get("trace_sha256"),
                f"TFT binding mismatch: {key}")

    physical = load(BUNDLE / "touch-physical.json")
    physical_ui = load(BUNDLE / "touch-physical-ui.json")
    require(failures,
            physical.get("calibration_source") == "leshy1" and
            physical.get("calibration") == CALIBRATION and
            physical.get("pressure_threshold") == 80 and
            physical.get("press_events") == 1 and
            physical.get("handled_presses") == 1 and
            physical.get("synthetic_presses") == 0 and
            physical.get("last_changed") is True and
            12 <= physical.get("last_x", -1) < 228 and
            82 <= physical.get("last_y", -1) < 128,
            "physical touch event mismatch")
    require(failures,
            physical_ui.get("page") == "diagnostics" and
            physical_ui.get("runtime_owner") == "diagnostics" and
            physical_ui.get("lease_mask") == 1 and
            physical_ui.get("revision") == 1,
            "physical target dispatch mismatch")

    final_touch = load(BUNDLE / "touch-final.json")
    require(failures,
            final_touch.get("calibration") == CALIBRATION and
            final_touch.get("handled_presses") == 4 and
            final_touch.get("missed_presses") == 2 and
            final_touch.get("synthetic_presses") == 5 and
            final_touch.get("press_events") == 1 and
            final_touch.get("release_events") == 1 and
            final_touch.get("rejected_coordinates") == 0 and
            final_touch.get("footer_interactive") is False and
            final_touch.get("touch_back_enabled") is False,
            "final touch/chrome contract mismatch")

    quick = load(BUNDLE / "quick.json")
    checks = {item.get("id"): item.get("status")
              for item in quick.get("checks", [])}
    require(failures,
            [quick.get("status"), quick.get("plan_version"),
             quick.get("passed"), quick.get("failed"),
             quick.get("blocked")] == ["pass", 8, 9, 0, 0] and
            checks.get("quick.input.touch") == "pass",
            "Quick touch check mismatch")
    before = load(BUNDLE / "metrics-before.json")
    after = load(BUNDLE / "metrics-after.json")
    require(failures,
            before == after and before.get("app_elf_sha256") == APP and
            before.get("heap_free") == 167028 and
            before.get("heap_min_free") == 147632 and
            before.get("buzzer_inactive") is True,
            "heap/safe-output invariance mismatch")

    require(failures,
            regression.get("failed_pressure_threshold") == 350 and
            regression.get("physical_wait_seconds") == 180 and
            regression.get("samples_without_touch_event") == 15055 and
            regression.get("touched_samples") == 0 and
            regression.get("calibration_crc_valid") is True and
            regression.get("calibration") == CALIBRATION,
            "failed threshold regression is not retained honestly")
    require(failures, verified.get("physical_touch", {}).get("point") == [76, 91] and
            verified.get("geometry", {}).get("footer_interactive") is False and
            verified.get("geometry", {}).get("touch_back_enabled") is False and
            evidence.get("limits") == {
                "touch_corrective_complete": True,
                "controlled_power_cut_complete": False,
                "one_hour_endurance_complete": False,
                "demo_s4_complete": False,
                "release_gate_eligible": False,
            }, "summary/remaining-limits mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.88 calibrated physical touch proof is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
