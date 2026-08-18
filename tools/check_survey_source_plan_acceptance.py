#!/usr/bin/env python3
"""Fail closed unless the exact 0.71 S4 source-plan evidence is complete."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-survey-source-plan-0.71.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-survey-source-plan-0.71"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def indexed_artifacts(failures: list[str], index: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not index.is_file():
        failures.append("artifact index missing")
        return result
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
            continue
        result[parts[1]] = parts[0]
    for relative, expected in result.items():
        path = BUNDLE / relative
        require(failures, path.is_file(), f"indexed artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"indexed artifact hash mismatch: {relative}")
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(result) == actual,
            "artifact index is not an exact bundle inventory")
    return result


def git_blob(commit: str, path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.survey_source_plan_acceptance.v1",
            "evidence schema mismatch")
    require(failures, evidence.get("status") == "pass_s4_user_slice" and
            evidence.get("passed") is True, "evidence is not accepted")
    require(failures, evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16",
            "board/profile mismatch")
    require(failures,
            evidence.get("observed_cid") ==
            "FE343253440000002000000055019CB7", "CID mismatch")

    candidate = evidence.get("candidate", {})
    expected_candidate = {
        "version": "0.71.0-survey-source-plan",
        "firmware_sha256":
            "5636f3b48aa06a1aa488c75f1368d12f37e8cedfd5e2daed4595af4669e821e6",
        "factory_sha256":
            "dea1d2ce8386a98b7d8ec6b2680008089d14093dcabedb17d37ae53c5dd5692a",
        "app_elf_sha256":
            "e35896c4a4e289ef5f221c4edbbe6ab7303c7983316668fe5a8ba3c95a6c5057",
        "map_sha256":
            "82ea3089d5c55be9104c830cfe255d3bc1aedf8380b3962abb17f488380056b2",
        "firmware_bytes": 1169424,
        "factory_bytes": 1234960,
        "linked_flash_bytes": 1169012,
        "linked_ram_bytes": 134928,
    }
    require(failures, candidate == expected_candidate,
            "exact candidate metadata mismatch")

    physical = evidence.get("physical", {})
    index = BUNDLE / "artifacts.sha256"
    require(failures, digest(index) == physical.get("artifact_index_sha256"),
            "artifact-index binding mismatch")
    indexed_artifacts(failures, index)
    run_path = ROOT / str(physical.get("run_path", "missing"))
    require(failures, run_path == BUNDLE / "run.json" and run_path.is_file(),
            "physical run path mismatch")
    if run_path.is_file():
        require(failures, digest(run_path) == physical.get("run_sha256"),
                "physical run hash mismatch")

    retained = {
        "firmware_sha256": BUNDLE / "firmware.bin",
        "factory_sha256": BUNDLE / "firmware.factory.bin",
    }
    for key, path in retained.items():
        require(failures, path.is_file() and digest(path) == candidate.get(key),
                f"retained {key} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures,
                app_elf_sha256(BUNDLE / "firmware.bin") ==
                candidate.get("app_elf_sha256"),
                "retained firmware app identity mismatch")

    source_commit = str(evidence.get("source_commit", ""))
    require(failures,
            source_commit == "b0901f9e19346ba1f8e970e932270681c6c287ed",
            "source commit mismatch")
    source_paths = (
        "firmware/leshy1/platformio.ini",
        "firmware/leshy1/src/apps/survey/SurveySourceController.cpp",
        "firmware/leshy1/src/apps/survey/SurveySourceController.h",
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
        "firmware/leshy1/src/ui/UiStrings.def",
        "tests/native/clean_target_tests.cpp",
        "tools/run_1x_survey_source_plan_hil.py",
    )
    for relative in source_paths:
        blob = git_blob(source_commit, relative)
        require(failures, blob is not None, f"source blob missing: {relative}")
        if blob is not None:
            require(failures, blob == (ROOT / relative).read_bytes(),
                    f"source drift after physical run: {relative}")
    require(failures,
            digest(ROOT / "tools/run_1x_survey_source_plan_hil.py") ==
            physical.get("runner_sha256"), "runner hash mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.survey_source_plan_hil.v1" and
                run.get("status") == "pass" and run.get("passed") is True,
                "physical run did not pass")
        run_candidate = run.get("candidate", {})
        for key in ("version", "firmware_sha256", "factory_sha256",
                    "app_elf_sha256", "map_sha256", "firmware_bytes",
                    "factory_bytes"):
            require(failures, run_candidate.get(key) == candidate.get(key),
                    f"run candidate mismatch: {key}")
        require(failures,
                run_candidate.get("runner_sha256") ==
                physical.get("runner_sha256"), "run runner mismatch")
        require(failures,
                len(run.get("screens", {})) == physical.get("screen_count") == 5,
                "screen count mismatch")
        require(failures,
                len(run.get("transitions", {})) ==
                physical.get("transition_count") == 11,
                "transition count mismatch")
        require(failures,
                run.get("maximum_incremental_render_us") ==
                physical.get("maximum_incremental_render_us") == 31818 and
                31818 <= physical.get("maximum_allowed_incremental_render_us", 0),
                "incremental render budget mismatch")

        transitions = run.get("transitions", {})
        require(failures,
                transitions.get("open_plan", {}).get(
                    "survey_source_selected_mask") == 1 and
                transitions.get("open_plan", {}).get(
                    "survey_source_wifi_state") == "available" and
                transitions.get("open_plan", {}).get(
                    "survey_source_ble_state") == "unavailable",
                "initial source projection mismatch")
        require(failures,
                transitions.get("disable_wifi", {}).get(
                    "survey_source_selected_mask") == 0 and
                transitions.get("disable_wifi", {}).get(
                    "survey_source_can_start") is False,
                "Wi-Fi disable did not empty the plan")
        require(failures,
                transitions.get("reject_unavailable_ble", {}).get("changed") is False and
                transitions.get("reject_unavailable_ble", {}).get(
                    "runtime_event") == "source_unavailable",
                "unavailable BLE did not fail closed")
        require(failures,
                transitions.get("block_empty_start", {}).get("changed") is False and
                transitions.get("block_empty_start", {}).get(
                    "runtime_event") == "start_blocked" and
                transitions.get("block_empty_start", {}).get(
                    "survey_workflow_state") == "setup",
                "empty Start was not blocked")
        require(failures,
                transitions.get("restore_wifi", {}).get(
                    "survey_source_selected_mask") == 1 and
                transitions.get("restore_wifi", {}).get(
                    "survey_source_can_start") is True,
                "source selection did not restore Start")
        require(failures,
                transitions.get("leave_plan", {}).get("runtime_owner") == "none" and
                transitions.get("leave_plan", {}).get("lease_mask") == 0 and
                run.get("final_owner") == "none" and
                run.get("final_lease_mask") == 0,
                "final resource cleanup mismatch")
        contract = run.get("contract", {})
        require(failures,
                contract.get("radio_started") is False and
                contract.get("storage_opened") is False and
                contract.get("hidden_fallback") is False,
                "source-plan gate exceeded its side-effect scope")
        before = run.get("records", {}).get("metrics_before", {}).get("value", {})
        after = run.get("records", {}).get("metrics_after", {}).get("value", {})
        require(failures,
                before.get("version") == candidate.get("version") and
                before.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                before.get("heap_free") == after.get("heap_free") == 202160 and
                before.get("heap_min_free") == after.get("heap_min_free") == 182108,
                "identity/heap invariance mismatch")
        input_state = run.get("records", {}).get("input", {}).get("value", {})
        safe = run.get("records", {}).get("safe_outputs", {}).get("value", {})
        require(failures,
                input_state.get("status") == "ready" and
                input_state.get("queue_drops") == 0 and
                input_state.get("read_errors") == 0,
                "input health mismatch")
        require(failures,
                safe.get("buzzer_inactive") is True and
                safe.get("buzzer_level") == "low",
                "safe-output invariant mismatch")

    accepted = evidence.get("accepted_contract", {})
    for key in (
        "setup_is_interactive", "available_sources_user_selectable",
        "wifi_default_selected", "ble_visible_unavailable",
        "unavailable_source_activation_rejected", "empty_plan_start_blocked",
        "selection_restore_reenables_start", "five_tft_states_visually_reviewed",
        "heap_invariant", "safe_cleanup",
    ):
        require(failures, accepted.get(key) is True,
                f"accepted contract missing: {key}")
    require(failures,
            accepted.get("hidden_fallback") is False and
            accepted.get("radio_started") is False and
            accepted.get("storage_opened") is False,
            "accepted side-effect scope mismatch")
    require(failures,
            evidence.get("evidence_ids") == [
                "E-BUILD-072", "E-AUTO-036", "E-HIL-096", "E-SURVEY-009"],
            "evidence IDs mismatch")

    for relative in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md",
        "docs/v1/TRACEABILITY.md", "docs/v1/TRACEABILITY.ru.md",
        "docs/v1/ARCHITECTURE.md", "docs/v1/ARCHITECTURE.ru.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        require(failures, "0.71.0-survey-source-plan" in text and
                "E-HIL-096" in text and "S4" in text,
                f"documentation marker missing: {relative}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Survey source-plan acceptance passed: exact 0.71, Wi-Fi selectable, "
          "BLE unavailable honestly, empty Start blocked, five TFT states, "
          "31.818 ms max incremental render, zero final leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
