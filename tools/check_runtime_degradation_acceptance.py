#!/usr/bin/env python3
"""Fail closed unless the exact 0.75 runtime-degradation checkpoint is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-runtime-degradation-0.75.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-runtime-degradation-0.75"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "aff0a1e6ec4babcc73335fd6821bb56b6323ab63"


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
            recovery.get("cleanup_complete") is True and
            recovery.get("owned_after") == 0,
            "boot read-only/cleanup invariant mismatch")


def verify_timeline(failures: list[str], artifact: dict[str, Any]) -> None:
    session = artifact.get("session", {})
    timeline = session.get("timeline", {})
    windows = artifact.get("timeline_windows", [])
    require(failures,
            artifact.get("status") == "valid" and
            artifact.get("generation") == 78 and
            artifact.get("persistent") is True and
            artifact.get("radio_touched") is False and
            artifact.get("simulated") is False and
            session.get("schema") == "leshy.session.summary.v2" and
            session.get("observations") == 28 and
            session.get("dropped") == 0 and
            session.get("sources") == {"wifi": 28, "ble": 0},
            "cold Library source export mismatch")
    require(failures,
            timeline.get("selected_mask") == 3 and
            timeline.get("windows") == 8 and
            timeline.get("retained") == 8 and
            timeline.get("evicted") == 0 and
            timeline.get("overflow") == 0 and
            timeline.get("wifi", {}).get("accepted") == 28 and
            timeline.get("wifi", {}).get("dropped") == 0 and
            timeline.get("wifi", {}).get("unavailable_us") == 0 and
            timeline.get("wifi", {}).get("fault_us") == 0 and
            timeline.get("ble", {}).get("accepted") == 0 and
            timeline.get("ble", {}).get("dropped") == 0 and
            timeline.get("ble", {}).get("unavailable_us") == 3625744 and
            timeline.get("ble", {}).get("fault_us") == 0 and
            len(windows) == 8,
            "durable degradation summary mismatch")
    if len(windows) != 8:
        return
    require(failures,
            sum(item.get("accepted", 0) for item in windows) == 28 and
            sum(item.get("dropped", 0) for item in windows) == 0,
            "timeline observation/drop totals mismatch")
    unavailable = [item for item in windows
                   if item.get("state") == "unavailable"]
    require(failures,
            len(unavailable) == 1 and
            unavailable[0].get("source") == "ble" and
            unavailable[0].get("reason") == "driver_unavailable" and
            unavailable[0].get("ended_us", 0) -
            unavailable[0].get("started_us", 0) == 3625744,
            "BLE unavailability window mismatch")
    for source in ("wifi", "ble"):
        source_windows = [item for item in windows if item.get("source") == source]
        for previous, current in zip(source_windows, source_windows[1:]):
            require(failures,
                    previous.get("ended_us") == current.get("started_us"),
                    f"{source} timeline continuity mismatch")
        summary = timeline.get(source, {})
        for state, key in (("scheduled", "scheduled_us"),
                           ("active", "active_us"),
                           ("unavailable", "unavailable_us"),
                           ("fault", "fault_us")):
            duration = sum(item.get("ended_us", 0) - item.get("started_us", 0)
                           for item in source_windows if item.get("state") == state)
            require(failures, duration == summary.get(key),
                    f"{source} {state} duration mismatch")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.runtime_degradation_acceptance.v1" and
            evidence.get("status") == "pass_runtime_degradation_checkpoint" and
            evidence.get("passed") is True,
            "evidence is not an accepted runtime-degradation checkpoint")
    require(failures,
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT,
            "board/profile/CID/source mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.75.0-runtime-degradation",
        "firmware_sha256": "d4f11ffb9971cd1345a943ef66e4083d47264d6052b1f5631dc74a7af76637ad",
        "factory_sha256": "5e9ab1321b3d46248bb957d1ddac18d1847ead2b89df253eba198026ee4a319b",
        "app_elf_sha256": "be56d6842e8024025642b6565480478bc5d103deb983c24208b3da55a8f3e162",
        "map_sha256": "e1a42a70968a479eb684046cc574cea45515ab7eeb384d756ad39bc202fd3f27",
        "firmware_bytes": 1422240,
        "factory_bytes": 1487776,
        "linked_flash_bytes": 1421832,
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

    runner_blob = git_blob(SOURCE_COMMIT, "tools/run_1x_runtime_degradation_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.runtime_degradation_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and
                run.get("expected_cid") == CID,
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
        verify_boot(failures, run.get("boot_before", {}), candidate, 77, 40)
        verify_boot(failures, run.get("boot_after", {}), candidate, 78, 28)

        injection = run.get("injection", {})
        require(failures,
                injection.get("schema") == "leshy.survey.runtime_unavailable_test.v1" and
                injection.get("status") == "armed" and
                injection.get("armed_mask") == 2 and
                injection.get("one_shot") is True and
                injection.get("ui_home") is True and
                injection.get("worker_idle") is True and
                injection.get("runtime_owner") == "none" and
                injection.get("lease_mask") == 0 and
                injection.get("hardware_touched") is False and
                injection.get("storage_mounted") is False and
                injection.get("storage_written") is False,
                "safe one-shot injection contract mismatch")

        degraded = run.get("degraded", {})
        require(failures,
                degraded.get("survey_product_status") == "running_degraded" and
                degraded.get("survey_product_selected_source_mask") == 3 and
                degraded.get("survey_product_active_source_mask") == 1 and
                degraded.get("survey_product_unavailable_source_mask") == 2 and
                degraded.get("survey_product_runtime_source_failure_injected") is True and
                degraded.get("survey_product_runtime_source_failure_injected_mask") == 2 and
                degraded.get("survey_product_runtime_source_injection_armed_mask") == 0 and
                degraded.get("survey_product_wifi_scan_cycles") == 2 and
                degraded.get("survey_product_ble_scan_cycles") == 0 and
                degraded.get("survey_observations") == 28 and
                degraded.get("survey_forwarded") == 28,
                "runtime continuation/degradation mismatch")
        require(failures,
                degraded.get("survey_timeline_ble_state") == "unavailable" and
                degraded.get("survey_timeline_healthy") is True and
                degraded.get("survey_timeline_archived_windows") == 6 and
                degraded.get("survey_timeline_queue_depth") == 0 and
                degraded.get("survey_timeline_queue_high_water") == 1 and
                degraded.get("survey_timeline_wifi_dropped") == 0 and
                degraded.get("survey_timeline_ble_dropped") == 0 and
                degraded.get("survey_timeline_overflow") == 0,
                "running timeline degradation mismatch")

        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_product_status") == "committed" and
                committed.get("survey_generation") == 78 and
                committed.get("survey_observations") == 28 and
                committed.get("survey_forwarded") == 28 and
                committed.get("survey_timeline_archived_windows") == 8 and
                committed.get("survey_timeline_persisted_windows") == 8 and
                committed.get("survey_timeline_retained_windows") == 8 and
                committed.get("survey_timeline_evicted_windows") == 0 and
                committed.get("survey_timeline_queue_depth") == 0 and
                committed.get("survey_timeline_queue_high_water") == 2 and
                committed.get("survey_timeline_overflow") == 0 and
                committed.get("survey_product_store_bytes_written") == 1898,
                "terminal persistence/commit mismatch")
        verify_timeline(failures, run.get("library_export", {}))

        captures = run.get("captures", {})
        capture_specs = {
            "setup": ("setup.png", "setup_png_sha256"),
            "degraded": ("degraded.png", "degraded_png_sha256"),
            "committed": ("committed.png", "committed_png_sha256"),
            "library_detail": ("library-detail.png", "library_detail_png_sha256"),
            "export": ("export.png", "export_png_sha256"),
        }
        require(failures, len(captures) == physical.get("screen_count") == 5,
                "capture count mismatch")
        for key, (filename, hash_key) in capture_specs.items():
            path = BUNDLE / "frames" / filename
            capture = captures.get(key, {})
            require(failures,
                    path.is_file() and png_dimensions(path) == (240, 320) and
                    digest(path) == physical.get(hash_key) == capture.get("png_sha256"),
                    f"{key} PNG mismatch")
        degraded_frame = captures.get("degraded", {}).get("state", {})
        require(failures,
                degraded_frame.get("survey_product_status") == "running_degraded" and
                degraded_frame.get("survey_timeline_ble_state") == "unavailable",
                "degraded frame is not bound to degraded state")

        final = run.get("final", {})
        cleanup = run.get("cleanup_after", {})
        require(failures,
                final.get("page") == "home" and
                final.get("runtime_owner") == physical.get("final_owner") == "none" and
                final.get("lease_mask") == physical.get("final_lease_mask") == 0 and
                cleanup.get("complete") is True and cleanup.get("errors") == [],
                "final cleanup/lease mismatch")

    contract = evidence.get("accepted_contract", {})
    require(failures, contract and all(value is True for value in contract.values()),
            "accepted contract is incomplete")
    require(failures, evidence.get("open_scope") == {
        "controlled_power_cut": True,
        "eight_hour_multisource_endurance": True,
        "release_promotion": True,
    }, "open scope is not explicit")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-076", "E-AUTO-040", "E-HIL-100", "E-SURVEY-013"
    ], "evidence IDs mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Runtime-degradation acceptance passed: exact 0.75 candidate, "
          "safe BLE loss, continued Wi-Fi, durable unavailable window, "
          "cold recovery, five TFT frames, zero drops, invariant heap and final lease 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
