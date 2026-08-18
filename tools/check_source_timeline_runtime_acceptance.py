#!/usr/bin/env python3
"""Fail closed unless the exact 0.72 source-timeline runtime checkpoint is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-source-timeline-runtime-0.72.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-source-timeline-runtime-0.72"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "da2b33a4c3165806dde4b4f0b23955c941aaffdd"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def indexed_artifacts(failures: list[str], index: Path) -> None:
    expected: dict[str, str] = {}
    if not index.is_file():
        failures.append("artifact index missing")
        return
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
            continue
        expected[parts[1]] = parts[0]
    for relative, expected_hash in expected.items():
        path = BUNDLE / relative
        require(failures, path.is_file(), f"indexed artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected_hash,
                    f"indexed artifact hash mismatch: {relative}")
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual,
            "artifact index is not an exact bundle inventory")


def boot_failures(record: dict[str, Any], candidate: dict[str, Any],
                  generation: int, observations: int) -> list[str]:
    failures: list[str] = []
    ready = record.get("ready", {})
    recovery = record.get("recovery", {})
    require(failures,
            ready.get("version") == candidate.get("version") and
            ready.get("app_elf_sha256") == candidate.get("app_elf_sha256"),
            "boot candidate identity mismatch")
    require(failures,
            ready.get("buzzer_inactive") is True and
            ready.get("input_detected") is True,
            "boot input/output safety mismatch")
    require(failures,
            ready.get("heap_total") == 264624 and
            ready.get("heap_free") == 199952 and
            ready.get("heap_min_free") == 180156,
            "boot heap accounting mismatch")
    require(failures,
            recovery.get("status") == "admitted" and
            recovery.get("enrolled") is True and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("fingerprint_matched") is True,
            "boot exact-card admission mismatch")
    require(failures,
            recovery.get("generation") == generation and
            recovery.get("observations") == observations,
            "boot recovered generation mismatch")
    attempts = recovery.get("attempts")
    retries = recovery.get("transient_retries")
    require(failures,
            isinstance(attempts, int) and 1 <= attempts <= 8 and
            retries == attempts - 1 and recovery.get("timeout_restarts") == 0,
            "boot retry accounting mismatch")
    require(failures,
            recovery.get("mounted_read_only") is True and
            recovery.get("read_only_guaranteed") is True and
            recovery.get("blocked_write_attempts") == 0 and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("cleanup_complete") is True,
            "boot read-only/cleanup invariant mismatch")
    return failures


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.source_timeline_runtime_acceptance.v1" and
            evidence.get("status") == "pass_runtime_checkpoint" and
            evidence.get("passed") is True,
            "evidence is not an accepted runtime checkpoint")
    require(failures,
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID,
            "board/profile/CID mismatch")
    require(failures, evidence.get("source_commit") == SOURCE_COMMIT,
            "source commit mismatch")

    candidate = evidence.get("candidate", {})
    expected_candidate = {
        "version": "0.72.0-source-timeline-runtime",
        "firmware_sha256": "680a84ea43111c9ccaeb383dbce3b6bab6ec19b8a412f432ee75157b652cbed1",
        "factory_sha256": "422eec57a39085e99ef8cbc989d155f927ba0cbf86bc88b8aafaf0648eb1b522",
        "app_elf_sha256": "a09c8750e9fc60ef18a017c73c65fb69d690d34bf36c9d79e8553e52f71613ba",
        "map_sha256": "2a35327ed6c39c98b55002bdfb15a6b92d93e67ad77c08b5d41a5b2cd1d2fc39",
        "firmware_bytes": 1174864,
        "factory_bytes": 1240400,
        "linked_flash_bytes": 1174456,
        "linked_ram_bytes": 136880,
        "rtc_noinit_bytes": 60,
    }
    require(failures, candidate == expected_candidate,
            "exact candidate metadata mismatch")

    physical = evidence.get("physical", {})
    run_path = BUNDLE / "run.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures,
            physical.get("run_path") == str(run_path.relative_to(ROOT)) and
            run_path.is_file() and digest(run_path) == physical.get("run_sha256"),
            "physical run binding mismatch")
    require(failures,
            physical.get("artifact_index_path") == str(index_path.relative_to(ROOT)) and
            index_path.is_file() and
            digest(index_path) == physical.get("artifact_index_sha256"),
            "artifact-index binding mismatch")
    indexed_artifacts(failures, index_path)
    for key, filename in (("firmware_sha256", "firmware.bin"),
                          ("factory_sha256", "firmware.factory.bin")):
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == candidate.get(key),
                f"retained {filename} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures,
                app_elf_sha256(BUNDLE / "firmware.bin") ==
                candidate.get("app_elf_sha256"),
                "retained firmware app identity mismatch")

    source_files = {
        "firmware/leshy1/platformio.ini": "1fd7446da95d565a7546c54f0b9f8c6c09755b1a98a43d28b5e2fdaa9d8f7dab",
        "firmware/leshy1/src/services/survey/SourceTimeline.h": "37ea04aa8b79ed6976d87056fd000fffdba084842aff84f6d17f118a6532bbb6",
        "firmware/leshy1/src/services/survey/SourceTimeline.cpp": "d74e4cb41dea8ea7457379c4f1771cc17f7ff49428992d4d3fbf674f129fc690",
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp": "d3c85cca7035d5e1605b8145c8264e61cc643475f2ea6adf7e74a6e548f89c83",
        "firmware/leshy1/src/ui/UiStrings.def": "472be324cd48967e3a969171f66e9f525a9a796ab2bcc69022a1f8bd3852b47b",
        "tools/run_1x_source_timeline_hil.py": "6b208a2bd7632c20950e9fc3275691a19905954b613e3ba1804196c1a4f3c98b",
        "tools/test_source_timeline_hil_runner.py": "6559e30d80f5095204ca6a7a57adf438aece6090af5e958bb4af4248d1f09b82",
    }
    for relative, expected_hash in source_files.items():
        blob = git_blob(SOURCE_COMMIT, relative)
        require(failures, blob is not None, f"source blob missing: {relative}")
        if blob is not None:
            require(failures, hashlib.sha256(blob).hexdigest() == expected_hash,
                    f"source blob mismatch: {relative}")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.source_timeline_hil.run.v1" and
                run.get("passed") is True and run.get("failures") == [],
                "physical run did not pass")
        require(failures, run.get("run_id") == physical.get("run_id"),
                "run ID mismatch")
        require(failures,
                run.get("runner_source_sha256") == physical.get("runner_sha256"),
                "runner hash mismatch")
        run_candidate = run.get("candidate", {})
        require(failures,
                run_candidate == {
                    "version": candidate.get("version"),
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "flashed": True,
                }, "run candidate mismatch")
        failures.extend(boot_failures(run.get("boot_before", {}), candidate, 71, 33))
        failures.extend(boot_failures(run.get("boot_after", {}), candidate, 72, 34))

        running = run.get("running", {})
        require(failures,
                running.get("runtime_owner") == "survey" and
                running.get("lease_mask") == 15 and
                running.get("survey_product_status") == "running" and
                running.get("survey_product_scan_cycles") == 2,
                "running product state mismatch")
        require(failures,
                running.get("survey_observations") == 34 and
                running.get("survey_forwarded") == 34 and
                running.get("survey_scan_accepted") == 34 and
                running.get("survey_scan_dropped") == 0 and
                running.get("survey_dropped") == 0,
                "running observation accounting mismatch")
        require(failures,
                running.get("survey_timeline_state") == "running" and
                running.get("survey_timeline_healthy") is True and
                running.get("survey_timeline_selected_mask") == 1 and
                running.get("survey_timeline_wifi_state") in {"scheduled", "active"} and
                1 <= running.get("survey_timeline_wifi_duty_permille", 0) <= 1000 and
                running.get("survey_timeline_wifi_accepted") == 34 and
                running.get("survey_timeline_wifi_dropped") == 0 and
                running.get("survey_timeline_queue_depth") == 4 and
                running.get("survey_timeline_queue_high_water") == 4 and
                running.get("survey_timeline_overflow") == 0,
                "running timeline accounting mismatch")
        require(failures,
                running.get("survey_timeline_ble_state") == "unselected" and
                running.get("survey_timeline_ble_duty_permille") == 0 and
                running.get("survey_timeline_ble_accepted") == 0 and
                running.get("survey_timeline_ble_dropped") == 0,
                "unselected BLE accounting mismatch")

        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_product_status") == "committed" and
                committed.get("survey_generation") == 72 and
                committed.get("survey_observations") == 34 and
                committed.get("survey_timeline_state") == "stopped" and
                committed.get("survey_timeline_status") == "stopped" and
                committed.get("survey_timeline_wifi_state") == "stopped" and
                committed.get("survey_timeline_wifi_accepted") == 34 and
                committed.get("survey_timeline_wifi_dropped") == 0 and
                committed.get("survey_timeline_queue_depth") == 5 and
                committed.get("survey_timeline_queue_high_water") == 5 and
                committed.get("survey_timeline_overflow") == 0,
                "terminal timeline/commit mismatch")
        cleanup = run.get("cleanup", {})
        final = cleanup.get("final_state", {})
        require(failures,
                cleanup.get("complete") is True and
                final.get("page") == "home" and
                final.get("runtime_owner") == "none" and
                final.get("lease_mask") == 0,
                "final cleanup mismatch")
        captures = run.get("captures", {})
        for name, expected_hash in (
            ("running", physical.get("running_png_sha256")),
            ("committed", physical.get("committed_png_sha256")),
        ):
            png = BUNDLE / "frames" / f"{name}.png"
            require(failures,
                    png.is_file() and digest(png) == expected_hash and
                    captures.get(name, {}).get("png_sha256") == expected_hash and
                    png_dimensions(png) == (240, 320),
                    f"{name} TFT capture mismatch")

    accepted = evidence.get("accepted_contract", {})
    for key in (
        "source_plan_drives_selected_mask", "product_worker_emits_scan_boundaries",
        "monotonic_windows_accounted", "accepted_observations_match_forwarded",
        "drops_and_overflow_visible", "wifi_duty_visible_on_running_tft",
        "terminal_window_closed", "cold_recovery_preserves_observation_session",
        "exact_cid_preserved", "heap_invariant", "safe_cleanup",
    ):
        require(failures, accepted.get(key) is True,
                f"accepted runtime contract missing: {key}")
    for key in ("timeline_persisted", "timeline_exported", "passive_ble_active"):
        require(failures, accepted.get(key) is False,
                f"open scope is not represented honestly: {key}")
    require(failures,
            evidence.get("evidence_ids") == [
                "E-BUILD-073", "E-AUTO-037", "E-HIL-097", "E-SURVEY-010"],
            "evidence ID mismatch")

    for relative in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md",
        "docs/v1/TRACEABILITY.md", "docs/v1/TRACEABILITY.ru.md",
        "docs/v1/ARCHITECTURE.md", "docs/v1/ARCHITECTURE.ru.md",
        "docs/v1/RESOURCE_BUDGETS.md", "docs/v1/RESOURCE_BUDGETS.ru.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        require(failures,
                "0.72.0-source-timeline-runtime" in text and
                "E-HIL-097" in text and "S4" in text,
                f"documentation marker missing: {relative}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Source timeline runtime checkpoint passed: exact 0.72, 2 Wi-Fi cycles, "
          "34/34 observations, visible 74.1% duty, zero drops/overflow, cold recovery, "
          "and final lease 0; timeline persistence remains open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
