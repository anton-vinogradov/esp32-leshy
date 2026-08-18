#!/usr/bin/env python3
"""Fail closed unless the exact 0.76 observation-browser checkpoint is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-observation-browser-0.76.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-observation-browser-0.76"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "bea9261f7882243c3d3bbc864f3517a2e3d4c3fa"


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
            ready.get("heap_total") == 234340 and
            ready.get("heap_free") == 169720 and
            ready.get("heap_min_free") == 150200,
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


def verify_browser(failures: list[str], browser: dict[str, Any]) -> None:
    specs = {
        "all_focused": ("all", "list", 45),
        "filter_menu": ("all", "filter", 45),
        "wifi_focused": ("wifi", "list", 8),
        "wifi_list": ("wifi", "list", 8),
        "wifi_detail": ("wifi", "detail", 8),
        "ble_focused": ("ble", "list", 37),
        "ble_list": ("ble", "list", 37),
        "ble_detail": ("ble", "detail", 37),
    }
    for key, (filter_name, view, visible) in specs.items():
        state = browser.get(key, {})
        require(failures,
                state.get("schema") == "leshy.survey.browser.v1" and
                state.get("filter") == filter_name and
                state.get("view") == view and
                state.get("total") == 45 and
                state.get("visible") == visible and
                state.get("read_only_query") is True and
                state.get("radio_touched") is False and
                state.get("storage_touched") is False,
                f"{key} browser state mismatch")
    for source, expected_rssi in (("wifi", -72), ("ble", -92)):
        detail = browser.get(f"{source}_detail", {})
        samples = detail.get("history_samples")
        retained = detail.get("history_retained")
        require(failures,
                detail.get("selected") is True and
                detail.get("selected_radio") == source and
                detail.get("history_valid") is True and
                isinstance(samples, int) and isinstance(retained, int) and
                samples >= retained and 1 <= retained <= 12 and
                detail.get("history_min_rssi_dbm") == expected_rssi and
                detail.get("history_max_rssi_dbm") == expected_rssi and
                detail.get("history_latest_rssi_dbm") == expected_rssi,
                f"{source} detail/history mismatch")


def verify_export(failures: list[str], artifact: dict[str, Any]) -> None:
    session = artifact.get("session", {})
    timeline = session.get("timeline", {})
    windows = artifact.get("timeline_windows", [])
    require(failures,
            artifact.get("status") == "valid" and
            artifact.get("generation") == 81 and
            artifact.get("persistent") is True and
            artifact.get("radio_touched") is False and
            artifact.get("simulated") is False and
            session.get("schema") == "leshy.session.summary.v2" and
            session.get("observations") == 45 and
            session.get("dropped") == 0 and
            session.get("sources") == {"wifi": 8, "ble": 37},
            "cold Library export mismatch")
    require(failures,
            timeline.get("selected_mask") == 3 and
            timeline.get("windows") == 6 and
            timeline.get("retained") == 6 and
            timeline.get("evicted") == 0 and
            timeline.get("overflow") == 0 and
            timeline.get("wifi", {}).get("accepted") == 8 and
            timeline.get("wifi", {}).get("dropped") == 0 and
            timeline.get("ble", {}).get("accepted") == 37 and
            timeline.get("ble", {}).get("dropped") == 0 and
            len(windows) == 6,
            "durable timeline summary mismatch")
    if len(windows) != 6:
        return
    require(failures,
            sum(item.get("accepted", 0) for item in windows) == 45 and
            sum(item.get("dropped", 0) for item in windows) == 0,
            "timeline observation/drop totals mismatch")
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
            evidence.get("schema") == "leshy.observation_browser_acceptance.v1" and
            evidence.get("status") == "pass_observation_browser_checkpoint" and
            evidence.get("passed") is True,
            "evidence is not an accepted observation-browser checkpoint")
    require(failures,
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT,
            "board/profile/CID/source mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.76.0-observation-browser",
        "firmware_sha256": "89358bc5d7fd0e084a40fce2a8dc98ec2a47ac4bacbae9639376336d0b8ba19d",
        "factory_sha256": "76615971a3a179f8b412b32364c4d0baaa4fdf81953b771c64806c2c816c22b2",
        "app_elf_sha256": "f86cf116f3ad5de6d17023833807799e60076ae726936f3f487f28761b314dd2",
        "map_sha256": "e5d0ce70a05b15d43a7e5df16c978f7ea6284ffd4bb75e7e1272c57415eff519",
        "firmware_bytes": 1426656,
        "factory_bytes": 1492192,
        "linked_flash_bytes": 1426252,
        "linked_ram_bytes": 147368,
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

    runner_blob = git_blob(SOURCE_COMMIT, "tools/run_1x_observation_browser_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.observation_browser_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID,
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
        verify_boot(failures, run.get("post_flash", {}), candidate, 80, 49)
        verify_boot(failures, run.get("boot_before", {}), candidate, 80, 49)
        verify_boot(failures, run.get("boot_after", {}), candidate, 81, 45)

        running = run.get("running", {})
        require(failures,
                running.get("survey_product_status") == "running" and
                running.get("survey_product_source_active") is True and
                running.get("survey_product_wifi_scan_cycles") == 1 and
                running.get("survey_product_ble_scan_cycles") == 1 and
                running.get("survey_scan_accepted") == 8 and
                running.get("survey_ble_scan_accepted") == 37 and
                running.get("survey_observations") == 45 and
                running.get("survey_forwarded") == 45 and
                running.get("survey_dropped") == 0 and
                running.get("survey_queue_depth") == 0 and
                running.get("survey_queue_high_water") == 8 and
                running.get("survey_timeline_evicted_windows") == 0 and
                running.get("survey_timeline_overflow") == 0,
                "complete dual-source cycle mismatch")

        paused = run.get("paused", {})
        require(failures,
                paused.get("survey_product_status") == "paused" and
                paused.get("survey_product_source_active") is False and
                paused.get("survey_product_backend_open") is True and
                paused.get("survey_product_scan_active") is False and
                paused.get("survey_timeline_state") == "stopped" and
                paused.get("survey_timeline_archive_status") == "finalized" and
                paused.get("survey_timeline_archived_windows") == 6 and
                paused.get("survey_observations") == 45 and
                paused.get("survey_dropped") == 0 and
                paused.get("lease_mask") == 15,
                "snapshot pause/finalization mismatch")
        verify_browser(failures, run.get("browser", {}))

        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_product_status") == "committed" and
                committed.get("survey_generation") == 81 and
                committed.get("survey_observations") == 45 and
                committed.get("survey_forwarded") == 45 and
                committed.get("survey_dropped") == 0 and
                committed.get("survey_timeline_persisted_windows") == 6 and
                committed.get("survey_timeline_retained_windows") == 6 and
                committed.get("survey_timeline_evicted_windows") == 0 and
                committed.get("survey_timeline_overflow") == 0 and
                committed.get("survey_product_store_bytes_written") == 2187,
                "paused snapshot persistence mismatch")
        verify_export(failures, run.get("library_export", {}))

        captures = run.get("captures", {})
        capture_specs = {
            "setup": ("setup.png", "setup_png_sha256"),
            "all_list": ("all-list.png", "all_list_png_sha256"),
            "filter_menu": ("filter-menu.png", "filter_menu_png_sha256"),
            "wifi_list": ("wifi-list.png", "wifi_list_png_sha256"),
            "wifi_detail": ("wifi-detail.png", "wifi_detail_png_sha256"),
            "ble_list": ("ble-list.png", "ble_list_png_sha256"),
            "ble_detail": ("ble-detail.png", "ble_detail_png_sha256"),
            "committed": ("committed.png", "committed_png_sha256"),
            "library_detail": ("library-detail.png", "library_detail_png_sha256"),
        }
        require(failures, len(captures) == physical.get("screen_count") == 9,
                "capture count mismatch")
        for key, (filename, hash_key) in capture_specs.items():
            path = BUNDLE / "frames" / filename
            capture = captures.get(key, {})
            require(failures,
                    path.is_file() and png_dimensions(path) == (240, 320) and
                    digest(path) == physical.get(hash_key) == capture.get("png_sha256"),
                    f"{key} PNG mismatch")

        final = run.get("final", {})
        cleanup = run.get("cleanup_after", {})
        require(failures,
                final.get("page") == "home" and
                final.get("runtime_owner") == physical.get("final_owner") == "none" and
                final.get("lease_mask") == physical.get("final_lease_mask") == 0 and
                final.get("library_generation") == 81 and
                final.get("library_entries") == 1 and
                cleanup.get("complete") is True and cleanup.get("errors") == [],
                "final cleanup/lease mismatch")

    contract = evidence.get("accepted_contract", {})
    require(failures, contract and all(value is True for value in contract.values()),
            "accepted contract is incomplete")
    require(failures, evidence.get("open_scope") == {
        "capture_metadata": True,
        "compatible_csv_pcap_export": True,
        "conditional_nrf24_cc1101_gps_contracts": True,
        "applicable_full_guided_self_test": True,
        "controlled_power_cut": True,
        "eight_hour_multisource_endurance": True,
        "release_promotion": True,
    }, "open scope is not explicit")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-077", "E-AUTO-041", "E-HIL-101", "E-SURVEY-014"
    ], "evidence IDs mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Observation-browser acceptance passed: exact 0.76 candidate, "
          "All/Wi-Fi/BLE filters, bounded RSSI detail, frozen RF-off snapshot, "
          "45/45 cold-recovered observations, nine TFT frames, zero drops and final lease 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
