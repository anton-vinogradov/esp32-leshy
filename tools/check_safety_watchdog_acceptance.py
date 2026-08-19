#!/usr/bin/env python3
"""Fail closed unless the retained 0.103 safety-watchdog proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-safety-watchdog-0.103.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-safety-watchdog-0.103"
VERSION = "0.103.0-safety-supervisor"
SOURCE = "28630901cf84fb6df11956d2ddbb3d75924886fa"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "569a72e3bfae79e353a03e65865c4c58a3c498e3411d6fb1a7905bbf2e0183d5"
APP = "145c35089f0496c7b50540e9d94f81d45048716cf7a0532ab1fd3dcb3374310a"
FACTORY = "d8b49f4b5ee84c18fa18b01814f7ab0f2fc35aa76bd77147de699492ed06766f"
MAP = "637037076c88ceabb0dde657303ce3a55a2528317c32fee7038fc9fd35f625af"
RUNNER = "f368a6eae604f318cdfb799a9a85398093ece8637501d4f2e4e194c1653540d8"
RUN = "47aa60d3af0101b75d806d50d858c177ae31e367acc2a9012a824259b76bdc58"
FRAME_PAGES = {
    "frame_latched": ("safety-latched.png", "safe_mode", "latched"),
    "frame_clear_pending": (
        "safety-clear-pending.png", "safe_mode", "clear_pending"),
    "frame_final": ("home-final.png", "home", "armed"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, relative: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24] if path.is_file() else b""
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def verify_manifest(failures: list[str]) -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifact index missing")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append("malformed artifact index line")
            continue
        expected, relative = parts
        indexed.add(relative)
        path = BUNDLE / relative
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, indexed == actual, "artifact index coverage mismatch")


def state_matches(record: dict[str, Any], state: str, reason: str,
                  latched: bool, reset_reason: int, count: int) -> bool:
    return (
        record.get("state") == state and record.get("reason") == reason and
        record.get("armed") is True and record.get("latched") is latched and
        record.get("clear_pending") is False and
        record.get("trip_count") == count and
        record.get("emergency_quiesce_count") == count and
        record.get("reset_reason_code") == reset_reason and
        record.get("buzzer_inactive") is True and
        record.get("nrf_ce_inactive") is True and
        record.get("runtime_owner") == "none" and
        record.get("lease_mask") == 0
    )


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.103 safety evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.safety_watchdog_acceptance.v1" and
            summary.get("status") == "pass_main_loop_watchdog_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-104", "E-AUTO-068", "E-HIL-128", "E-SAFETY-001"],
            "summary identity mismatch")
    require(failures,
            candidate.get("schema") ==
                "leshy.safety_watchdog.provenance.v1" and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("run_sha256") == RUN and
            candidate.get("firmware_bytes") == 1535072 and
            candidate.get("factory_bytes") == 1600608 and
            candidate.get("linked_flash_bytes") == 1534668 and
            candidate.get("static_ram_bytes") == 171496 and
            candidate.get("iram_used_bytes") ==
                candidate.get("iram_total_bytes") == 16384 and
            candidate.get("rtc_noinit_bytes") == 108,
            "candidate identity/resource mismatch")
    require(failures,
            evidence.get("files") == 19 and evidence.get("tft_states") == 3 and
            evidence.get("artifact_index_sha256") ==
                digest(BUNDLE / "artifacts.sha256") and
            evidence.get("provenance_sha256") ==
                digest(BUNDLE / "provenance.json") and
            evidence.get("run_sha256") == digest(BUNDLE / "run.json") == RUN,
            "evidence identity mismatch")
    require(failures, verified == {
        "automatic_clear": False,
        "automatic_screenshots": True,
        "buzzer_inactive": True,
        "catalog_generation": 95,
        "catalog_observations": 0,
        "cc1101_hard_kill_available": False,
        "clear_reset_reason_code": 3,
        "emergency_quiesce_count": 1,
        "exact_cid": CID,
        "final_lease_mask": 0,
        "final_owner": "none",
        "latched_restart_reset_reason_code": 3,
        "manual_button_presses": 0,
        "nrf_ce_inactive": True,
        "physical_rail_kill_available": False,
        "software_only": True,
        "storage_physical_write_calls": 0,
        "thermal_sensor_available": False,
        "trip_count": 1,
        "watchdog_observed_reset_ms": 5810.775,
        "watchdog_reset_reason_code": 6,
        "watchdog_timeout_ms": 5000,
    }, "verified claim mismatch")
    require(failures, summary.get("coverage") == {
        "cc1101_independent_hard_kill": False,
        "full_power_cycle_latch_retention": False,
        "main_loop_watchdog": True,
        "physical_rail_kill": False,
        "physical_rf_stop_instrumented": False,
        "software_controlled_outputs_quiesced": True,
        "software_restart_latch_retention": True,
        "thermal_voltage_current_fault_detection": False,
        "worker_heartbeat_supervision": False,
    }, "coverage/limitations mismatch")

    verify_manifest(failures)
    provenance = load(BUNDLE / "provenance.json")
    require(failures, provenance == candidate, "provenance/summary mismatch")
    require(failures,
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "runner.py") == RUNNER,
            "retained candidate/runner mismatch")
    runner_blob = git_blob(SOURCE, "tools/run_1x_safety_watchdog_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() == RUNNER,
            "runner commit/source mismatch")

    run = load(BUNDLE / "run.json")
    records = run.get("records", {})
    require(failures,
            run.get("schema") == "leshy.safety_watchdog_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": APP, "firmware_sha256": FIRMWARE,
                "flashed": True, "runner_sha256": RUNNER,
                "source_commit": SOURCE, "version": VERSION,
            }, "exact run identity mismatch")
    require(failures,
            run.get("watchdog_raw") == {
                "bytes": 6982,
                "sha256": "724070fe4215d7435f0ee237a6d54246d0f7d0aac6d350e9d91af1a328324d4f"} and
            run.get("restart_raw") == {
                "bytes": 6481,
                "sha256": "acaac7f8a64006bbc90eb4e786d5f2e00bed4339e6cea2c977f102346758dfdd"} and
            run.get("clear_raw") == {
                "bytes": 6968,
                "sha256": "3a8bba129ad5500aaa4c26f3bb87ded44bc499b5383d218ec47541f1cddce8e3"},
            "reset transcript identity mismatch")
    require(failures,
            state_matches(records.get("safety_latched", {}),
                          "latched", "runtime_watchdog", True, 6, 1) and
            state_matches(records.get("safety_after_latched_restart", {}),
                          "latched", "runtime_watchdog", True, 3, 1),
            "retained safety latch mismatch")
    require(failures,
            state_matches(records.get("safety_final", {}),
                          "armed", "none", False, 3, 0),
            "final armed state mismatch")
    require(failures,
            records.get("watchdog_ready", {}).get("reset_reason_code") == 6 and
            records.get("watchdog_ready_marker_ms") == 5810.775 and
            records.get("latched_restart_ready", {}).get(
                "reset_reason_code") == 3 and
            records.get("latched_restart_ready_marker_ms") == 701.819 and
            records.get("clear_ready", {}).get("reset_reason_code") == 3 and
            records.get("clear_ready_marker_ms") == 1316.289,
            "watchdog/restart timing mismatch")
    require(failures,
            records.get("injection", {}).get("outputs_inactive") is True and
            records.get("injection", {}).get(
                "filesystem_write_attempted") is False and
            records.get("latched_restart_request", {}).get(
                "latch_preserved") is True and
            records.get("latched_restart_request", {}).get(
                "outputs_inactive") is True and
            records.get("latched_restart_request", {}).get(
                "physical_write_calls") == 0,
            "injection/restart precondition mismatch")
    for key in ("recovery_latched", "recovery_after_latched_restart"):
        recovery = records.get(key, {})
        require(failures,
                recovery.get("status") == "safety_latched" and
                recovery.get("cleanup_complete") is True and
                recovery.get("physical_write_calls") == 0 and
                recovery.get("owned_after") == 0,
                f"{key} fail-closed recovery mismatch")
    before = records.get("boot_before", {}).get("recovery", {})
    final = records.get("recovery_final", {})
    require(failures,
            before.get("expected_fingerprint") ==
                before.get("observed_fingerprint") == CID and
            final.get("expected_fingerprint") ==
                final.get("observed_fingerprint") == CID and
            before.get("generation") == final.get("generation") == 95 and
            before.get("observations") == final.get("observations") == 0 and
            before.get("physical_write_calls") ==
                final.get("physical_write_calls") == 0,
            "catalog/CID continuity mismatch")
    for key, (name, page, safety_state) in FRAME_PAGES.items():
        capture = records.get(key, {})
        png = BUNDLE / "frames" / name
        require(failures,
                capture.get("frame_begin", {}).get("width") == 240 and
                capture.get("frame_begin", {}).get("height") == 320 and
                capture.get("state", {}).get("page") == page and
                capture.get("state", {}).get("safety_state") == safety_state and
                capture.get("state", {}).get("runtime_owner") == "none" and
                capture.get("state", {}).get("lease_mask") == 0 and
                png_size(png) == (240, 320) and
                digest(png) == capture.get("png_sha256"),
                f"{key} TFT capture mismatch")

    source_platform = git_blob(SOURCE, "firmware/leshy1/platformio.ini")
    source_core = git_blob(
        SOURCE, "firmware/leshy1/src/kernel/safety/SafetySupervisor.cpp")
    source_entry = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    require(failures, source_platform is not None and
            b'LESHY1_VERSION=\\"0.103.0-safety-supervisor\\"' in source_platform,
            "source version binding mismatch")
    require(failures, source_core is not None and all(
        token in source_core for token in (
            b"validateSafetyRetainedRecord", b"latchConfirmedInverse",
            b"requestClear", b"confirmClear")),
            "retained safety core source mismatch")
    require(failures, source_entry is not None and all(
        token in source_entry for token in (
            b"esp_task_wdt_isr_user_handler", b"quiesceEmergencyGpioFromIsr",
            b"safety.restart-test confirm", b"clearSafetyStopAndRestart")),
            "watchdog/Safe Mode source mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION,
        "watchdog_reset_reason_code": 6,
        "watchdog_observed_reset_ms": 5810.775,
        "latched_restart_reset_reason_code": 3,
        "trip_count": 1, "quiesce_count": 1,
        "tft_states": 3, "final_lease_mask": 0,
        "worker_heartbeat_supervision": False,
        "physical_rail_kill": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
