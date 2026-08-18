#!/usr/bin/env python3
"""Fail closed unless the exact 0.73 durable timeline checkpoint is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-source-timeline-persistence-0.73.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-source-timeline-persistence-0.73"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "bfe798ffdb81180eadb51167c8f00aa8630e1b70"


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
            ready.get("heap_total") == 256320 and
            ready.get("heap_free") == 191648 and
            ready.get("heap_min_free") == 171852,
            "boot heap accounting mismatch")
    require(failures,
            ready.get("buzzer_inactive") is True and
            ready.get("input_detected") is True,
            "boot input/output safety mismatch")
    require(failures,
            recovery.get("status") == "admitted" and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("fingerprint_matched") is True and
            recovery.get("generation") == generation and
            recovery.get("observations") == observations,
            "boot recovery identity/generation mismatch")
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
            evidence.get("schema") == "leshy.source_timeline_persistence_acceptance.v1" and
            evidence.get("status") == "pass_persistence_checkpoint" and
            evidence.get("passed") is True,
            "evidence is not an accepted persistence checkpoint")
    require(failures,
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT,
            "board/profile/CID/source mismatch")

    candidate = evidence.get("candidate", {})
    expected_candidate = {
        "version": "0.73.0-source-timeline-persistence",
        "firmware_sha256": "3bf32bf3edcf8fad79fe45e89b216fe440e12b0192bd14942b0ac017ea0c3ffa",
        "factory_sha256": "680a2815294cfc19426bb5a3d9358149980fbd6225d12b1c570a1c115b319c91",
        "app_elf_sha256": "11dc9ae42a726546757f1dcd20dbb22783c2502b9034260d793d658e70188fe7",
        "map_sha256": "0ad8b322d1ba8209424ba7a954874bdf7cc51b8d3c1dfa646345de6850116323",
        "firmware_bytes": 1184208,
        "factory_bytes": 1249744,
        "linked_flash_bytes": 1184052,
        "linked_ram_bytes": 145184,
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
            index_path.is_file() and digest(index_path) == physical.get("artifact_index_sha256"),
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
        "firmware/leshy1/platformio.ini": "c0b682f24a6edf1db6bc0c412b389e5ab9ceca686ef3efd663056f46115af509",
        "firmware/leshy1/src/services/survey/SourceTimeline.h": "37ea04aa8b79ed6976d87056fd000fffdba084842aff84f6d17f118a6532bbb6",
        "firmware/leshy1/src/services/survey/SourceTimeline.cpp": "d74e4cb41dea8ea7457379c4f1771cc17f7ff49428992d4d3fbf674f129fc690",
        "firmware/leshy1/src/services/survey/SurveySession.h": "de6c759dc9a11b38ecceb5df6c06f25a4c130355d25fe718092bb7286c86c376",
        "firmware/leshy1/src/services/survey/SurveySession.cpp": "f9c7cbc363719aa0e014658134b6ad21890ceefbfac11e5940e9effe5d34659d",
        "firmware/leshy1/src/storage/SessionCodec.h": "8fe2a162f66f5f27dcae8cd8e01d6fd3e9d40a3dbf1a14243364ac01c717b36b",
        "firmware/leshy1/src/storage/SessionCodec.cpp": "1dd9243b4031cdec16bf23a942022936212f729238c79900b6d1a12031674892",
        "firmware/leshy1/src/apps/library/LibraryController.cpp": "5c0e727d49d006355f4a4326f78eddba72286f1d5a9354bf1e661476a273bea4",
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp": "9b3b482a003b741401b4a39797281a85476845f324bf4173f849e9f0a404e2a9",
        "firmware/leshy1/src/ui/UiStrings.def": "2a1b57a21df867898c729f3bd9ac4b52100507174fe0b78513dd62f21707b907",
        "tests/native/clean_target_tests.cpp": "0262c5b0816985c392bf53fc7da511ee504e35f06330e33f47b4ab6c394bdff0",
        "tools/run_1x_source_timeline_persistence_hil.py": "c8898ece7baaf1fb85421e3e7f1bde4b0b65860581380cde632ffa308fac1c18",
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
                run.get("schema") == "leshy.source_timeline_persistence_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [],
                "physical run did not pass")
        require(failures,
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256"),
                "run ID/runner mismatch")
        require(failures,
                run.get("candidate") == {
                    "version": candidate.get("version"),
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "flashed": True,
                }, "run candidate mismatch")
        failures.extend(boot_failures(run.get("boot_before", {}), candidate, 73, 30))
        failures.extend(boot_failures(run.get("boot_after", {}), candidate, 74, 21))

        running = run.get("running", {})
        require(failures,
                running.get("runtime_owner") == "survey" and
                running.get("lease_mask") == 15 and
                running.get("survey_product_scan_cycles") == 2 and
                running.get("survey_observations") == 21 and
                running.get("survey_forwarded") == 21 and
                running.get("survey_timeline_wifi_accepted") == 21,
                "running product/observation mismatch")
        require(failures,
                running.get("survey_timeline_state") == "running" and
                running.get("survey_timeline_archive_status") == "appended" and
                running.get("survey_timeline_archived_windows") == 4 and
                running.get("survey_timeline_queue_depth") == 0 and
                running.get("survey_timeline_queue_high_water") == 1 and
                running.get("survey_timeline_wifi_duty_permille") == 740 and
                running.get("survey_timeline_wifi_dropped") == 0 and
                running.get("survey_timeline_overflow") == 0,
                "running durable timeline mismatch")

        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_product_status") == "committed" and
                committed.get("survey_generation") == 74 and
                committed.get("survey_observations") == 21 and
                committed.get("survey_timeline_archive_status") == "finalized" and
                committed.get("survey_timeline_archived_windows") == 5 and
                committed.get("survey_timeline_persisted") is True and
                committed.get("survey_timeline_persisted_windows") == 5 and
                committed.get("survey_timeline_retained_windows") == 5 and
                committed.get("survey_timeline_evicted_windows") == 0 and
                committed.get("survey_timeline_queue_depth") == 0 and
                committed.get("survey_timeline_overflow") == 0,
                "terminal persistence/commit mismatch")

        artifact = run.get("library_export", {})
        session = artifact.get("session", {})
        timeline = session.get("timeline", {})
        windows = artifact.get("timeline_windows", [])
        require(failures,
                artifact.get("status") == "valid" and
                artifact.get("generation") == 74 and
                artifact.get("persistent") is True and
                artifact.get("radio_touched") is False and
                session.get("schema") == "leshy.session.summary.v2" and
                session.get("observations") == 21 and
                timeline.get("selected_mask") == 1 and
                timeline.get("windows") == 5 and
                timeline.get("retained") == 5 and
                timeline.get("evicted") == 0 and
                timeline.get("overflow") == 0 and
                timeline.get("wifi", {}).get("accepted") == 21 and
                timeline.get("wifi", {}).get("dropped") == 0 and
                len(windows) == 5,
                "cold Library summary/window export mismatch")
        if len(windows) == 5:
            require(failures,
                    sum(item.get("accepted", 0) for item in windows) == 21 and
                    sum(item.get("dropped", 0) for item in windows) == 0 and
                    all(item.get("source") == "wifi" for item in windows) and
                    all(item.get("ended_us", 0) >= item.get("started_us", 1)
                        for item in windows),
                    "exported retained-window accounting mismatch")
        wifi = timeline.get("wifi", {})
        duration = sum(wifi.get(field, 0) for field in (
            "scheduled_us", "active_us", "unavailable_us", "fault_us"
        ))
        require(failures,
                duration == timeline.get("stopped_us", 0) -
                    timeline.get("started_us", 0),
                "exported lifetime duration mismatch")

        for cleanup_name in ("cleanup_before", "cleanup_after"):
            cleanup = run.get(cleanup_name, {})
            final = cleanup.get("final_state", {})
            require(failures,
                    cleanup.get("complete") is True and
                    final.get("page") == "home" and
                    final.get("runtime_owner") == "none" and
                    final.get("lease_mask") == 0,
                    f"{cleanup_name} mismatch")
        captures = run.get("captures", {})
        for name, filename, key in (
            ("running", "running", "running_png_sha256"),
            ("committed", "committed", "committed_png_sha256"),
            ("library_detail", "library-detail", "library_detail_png_sha256"),
            ("export", "export", "export_png_sha256"),
        ):
            png = BUNDLE / "frames" / f"{filename}.png"
            expected_hash = physical.get(key)
            require(failures,
                    png.is_file() and digest(png) == expected_hash and
                    captures.get(name, {}).get("png_sha256") == expected_hash and
                    png_dimensions(png) == (240, 320),
                    f"{name} TFT capture mismatch")

    accepted = evidence.get("accepted_contract", {})
    for key in (
        "legacy_schema_v1_reopened", "schema_v2_manifest_segment_bound",
        "timeline_record_crc_bound", "runtime_fifo_drained_incrementally",
        "bounded_history_and_evictions_explicit",
        "aggregate_duration_and_counts_exact",
        "accepted_observations_match_forwarded",
        "drops_and_overflow_zero_and_visible",
        "cold_recovery_preserves_timeline",
        "library_detail_shows_persisted_history",
        "library_export_contains_summary_v2", "exact_cid_preserved",
        "heap_invariant", "safe_cleanup",
    ):
        require(failures, accepted.get(key) is True,
                f"accepted persistence contract missing: {key}")
    require(failures, accepted.get("passive_ble_active") is False,
            "open BLE scope is not represented honestly")
    require(failures,
            evidence.get("evidence_ids") == [
                "E-BUILD-074", "E-AUTO-038", "E-HIL-098", "E-SURVEY-011"],
            "evidence ID mismatch")

    for relative in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md",
        "docs/v1/TRACEABILITY.md", "docs/v1/TRACEABILITY.ru.md",
        "docs/v1/ARCHITECTURE.md", "docs/v1/ARCHITECTURE.ru.md",
        "docs/v1/RESOURCE_BUDGETS.md", "docs/v1/RESOURCE_BUDGETS.ru.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        require(failures,
                "0.73.0-source-timeline-persistence" in text and
                "E-HIL-098" in text and "S4" in text,
                f"documentation marker missing: {relative}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Source timeline persistence checkpoint passed: exact 0.73, FIFO 0/1, "
          "generation 73->74, 21/21 observations, five persisted/exported windows, "
          "cold recovery, invariant heap, and final lease 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
