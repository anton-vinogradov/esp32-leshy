#!/usr/bin/env python3
"""Fail closed unless the exact 0.74 passive-BLE checkpoint is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-passive-ble-0.74.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-passive-ble-0.74"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "ab7ff27ad4d0921bca55f499119e4c6f35f04ce6"


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


def verify_index(failures: list[str], index: Path) -> None:
    expected: dict[str, str] = {}
    require(failures, index.is_file(), "artifact index missing")
    if not index.is_file():
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


def verify_boot(failures: list[str], record: dict[str, Any],
                candidate: dict[str, Any], generation: int,
                observations: int) -> None:
    ready = record.get("ready", {})
    recovery = record.get("recovery", {})
    require(failures,
            ready.get("version") == candidate.get("version") and
            ready.get("app_elf_sha256") == candidate.get("app_elf_sha256"),
            "boot candidate identity mismatch")
    require(failures,
            ready.get("heap_total") == 234348 and
            ready.get("heap_free") == 169728 and
            ready.get("heap_min_free") == 150208,
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
    require(failures,
            isinstance(attempts, int) and 1 <= attempts <= 8 and
            recovery.get("transient_retries") == attempts - 1 and
            recovery.get("timeout_restarts") == 0,
            "boot retry accounting mismatch")
    require(failures,
            recovery.get("mounted_read_only") is True and
            recovery.get("read_only_guaranteed") is True and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("cleanup_complete") is True,
            "boot read-only/cleanup invariant mismatch")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.passive_ble_acceptance.v1" and
            evidence.get("status") == "pass_passive_ble_checkpoint" and
            evidence.get("passed") is True,
            "evidence is not an accepted passive-BLE checkpoint")
    require(failures,
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT,
            "board/profile/CID/source mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.74.0-passive-ble",
        "firmware_sha256": "806964a633fe0487bd487c4959ecf0bd898fd54f319bcac3c5b74e9666032bff",
        "factory_sha256": "4aee6025c566f582f953036f7fe918c5bb97e22482431da37f636e7a97036521",
        "app_elf_sha256": "80a02f090a612230c5e01cd7945e5bc28430ecd1bb4705cf28530ae66f37116e",
        "map_sha256": "d0713748c0db0dd5920699bb8dd05aae1e2d6b95549ce8d91995bfc6471b0001",
        "firmware_bytes": 1420304,
        "factory_bytes": 1485840,
        "linked_flash_bytes": 1419892,
        "linked_ram_bytes": 147360,
        "rtc_noinit_bytes": 60,
    }, "exact candidate metadata mismatch")

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
    verify_index(failures, index_path)
    for key, filename in (("firmware_sha256", "firmware.bin"),
                          ("factory_sha256", "firmware.factory.bin")):
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == candidate.get(key),
                f"retained {filename} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures,
                app_elf_sha256(BUNDLE / "firmware.bin") == candidate.get("app_elf_sha256"),
                "retained firmware app identity mismatch")

    runner_blob = git_blob(SOURCE_COMMIT, "tools/run_1x_passive_ble_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.passive_ble_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [],
                "physical run did not pass")
        require(failures,
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256"),
                "run ID/runner mismatch")
        require(failures, run.get("candidate") == {
            "version": candidate.get("version"),
            "firmware_sha256": candidate.get("firmware_sha256"),
            "app_elf_sha256": candidate.get("app_elf_sha256"),
            "flashed": True,
        }, "run candidate mismatch")
        verify_boot(failures, run.get("boot_before", {}), candidate, 76, 51)
        verify_boot(failures, run.get("boot_after", {}), candidate, 77, 40)

        running = run.get("running", {})
        require(failures,
                running.get("runtime_owner") == "survey" and
                running.get("lease_mask") == 15 and
                running.get("survey_product_wifi_scan_cycles") == 1 and
                running.get("survey_product_ble_scan_cycles") == 1 and
                running.get("survey_observations") == 40 and
                running.get("survey_forwarded") == 40 and
                running.get("survey_timeline_wifi_accepted") == 6 and
                running.get("survey_timeline_ble_accepted") == 34,
                "running dual-source accounting mismatch")
        require(failures,
                running.get("survey_source_wifi_state") == "available" and
                running.get("survey_source_ble_state") == "available" and
                running.get("survey_timeline_selected_mask") == 3 and
                running.get("survey_timeline_healthy") is True and
                running.get("survey_timeline_failure_status") == "none" and
                running.get("survey_timeline_queue_depth") == 0 and
                running.get("survey_timeline_queue_high_water") == 1 and
                running.get("survey_timeline_wifi_dropped") == 0 and
                running.get("survey_timeline_ble_dropped") == 0 and
                running.get("survey_timeline_overflow") == 0,
                "running timeline/degradation mismatch")

        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_product_status") == "committed" and
                committed.get("survey_generation") == 77 and
                committed.get("survey_observations") == 40 and
                committed.get("survey_timeline_archived_windows") == 6 and
                committed.get("survey_timeline_persisted_windows") == 6 and
                committed.get("survey_timeline_retained_windows") == 6 and
                committed.get("survey_timeline_evicted_windows") == 0 and
                committed.get("survey_timeline_queue_depth") == 0 and
                committed.get("survey_timeline_queue_high_water") == 2 and
                committed.get("survey_timeline_overflow") == 0 and
                committed.get("survey_product_store_bytes_written") == 2025,
                "terminal persistence/commit mismatch")

        artifact = run.get("library_export", {})
        session = artifact.get("session", {})
        timeline = session.get("timeline", {})
        windows = artifact.get("timeline_windows", [])
        require(failures,
                artifact.get("status") == "valid" and
                artifact.get("generation") == 77 and
                artifact.get("persistent") is True and
                artifact.get("radio_touched") is False and
                session.get("schema") == "leshy.session.summary.v2" and
                session.get("observations") == 40 and
                session.get("sources") == {"wifi": 6, "ble": 34} and
                timeline.get("selected_mask") == 3 and
                timeline.get("windows") == 6 and
                timeline.get("retained") == 6 and
                timeline.get("evicted") == 0 and
                timeline.get("overflow") == 0 and
                timeline.get("wifi", {}).get("accepted") == 6 and
                timeline.get("ble", {}).get("accepted") == 34 and
                len(windows) == 6,
                "cold Library dual-source export mismatch")
        if len(windows) == 6:
            require(failures,
                    sum(item.get("accepted", 0) for item in windows) == 40 and
                    sum(item.get("dropped", 0) for item in windows) == 0 and
                    {item.get("source") for item in windows} == {"wifi", "ble"} and
                    all(item.get("ended_us", 0) >= item.get("started_us", 1)
                        for item in windows),
                    "exported retained-window accounting mismatch")

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
            ("setup", "setup", "setup_png_sha256"),
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

    for key, value in evidence.get("accepted_contract", {}).items():
        require(failures, value is True, f"accepted contract missing: {key}")
    require(failures,
            evidence.get("evidence_ids") == [
                "E-BUILD-075", "E-AUTO-039", "E-HIL-099", "E-SURVEY-012"],
            "evidence ID mismatch")
    for relative in (
        "docs/v1/STATUS.md", "docs/v1/STATUS.ru.md",
        "docs/v1/TRACEABILITY.md", "docs/v1/TRACEABILITY.ru.md",
        "docs/v1/ARCHITECTURE.md", "docs/v1/ARCHITECTURE.ru.md",
        "docs/v1/RESOURCE_BUDGETS.md", "docs/v1/RESOURCE_BUDGETS.ru.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        require(failures,
                "0.74.0-passive-ble" in text and "E-HIL-099" in text and "S4" in text,
                f"documentation marker missing: {relative}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Passive-BLE checkpoint passed: exact 0.74, Wi-Fi 6 + BLE 34, "
          "generation 76->77, six persisted/exported windows, zero drops/overflow, "
          "invariant heap, exact CID, and final lease 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
