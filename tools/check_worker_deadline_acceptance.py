#!/usr/bin/env python3
"""Fail closed unless the retained exact 0.133 worker-deadline proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-worker-deadline-0.133.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-worker-deadline-0.133"
VERSION = "0.133.0-worker-deadline-supervision"
SOURCE = "da9e0bd47177af27a871467dd5bff322488a5f5e"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "40212538f5e3fe1518ab08eddfdb6ae42e0f1d32521a0f41f0382723cc232525"
APP = "52a0e00f095693d492ce320c9c3b1473e578f75c57fae49d4a12574555adc76c"
MAP = "8a80f84e44c10158beaf1403b79adad9ee9bebc4e1b03d757ff5144310a1bc12"
RUNNER = "42e51864726e3f3cc137279bd861eff45fb0aba115b94a491767f14162913394"
RUN = "3b4bb2219dea177120774c266b2285ab8315281b30083cc483818e6ce4be7a21"
INDEX = "5f2646fab482175bd8c8668886bc9430d70c13963fc6911a78b16d9cff8b81e9"
FRAME_PAGES = {
    "frame_latched": (
        "worker-deadline-latched.png", "safe_mode", "latched",
        "2eda0ea0c68c6810f11c7f7dc006532625792473548e862ace25268826502a16"),
    "frame_clear_pending": (
        "worker-deadline-clear-pending.png", "safe_mode", "clear_pending",
        "d3265689067a8fe31cb3393ce32fa2f747d96db6b9c46fb2a2c77c7322560f44"),
    "frame_final": (
        "home-final.png", "home", "armed",
        "c8e2c503bfec998b19280d4add522d09df66f1ea7d8410395bd194a143f40067"),
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


def safe_state(record: dict[str, Any], state: str, reason: str,
               latched: bool, reset_reason: int, count: int) -> bool:
    return (
        record.get("schema") == "leshy.safety.v1" and
        record.get("state") == state and record.get("reason") == reason and
        record.get("latched") is latched and
        record.get("automatic_clear") is False and
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
            "0.133 worker-deadline evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    coverage = summary.get("coverage", {})
    require(failures,
            summary.get("schema") == "leshy.worker_deadline_acceptance.v1" and
            summary.get("status") ==
                "pass_product_survey_wifi_worker_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-133", "E-AUTO-094", "E-HIL-154", "E-SAFETY-002"],
            "summary identity mismatch")
    require(failures,
            candidate.get("schema") == "leshy.worker_deadline.provenance.v1" and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("run_sha256") == RUN and
            candidate.get("firmware_bytes") == 3066528 and
            candidate.get("linked_flash_bytes") == 3066128 and
            candidate.get("static_ram_bytes") == 233360,
            "candidate identity/resource mismatch")
    require(failures,
            evidence == {
                "files": 16, "indexed_files": 15, "tft_states": 3,
                "artifact_index_sha256": INDEX, "run_sha256": RUN},
            "evidence identity mismatch")
    require(failures, verified == {
        "automatic_clear": False,
        "automatic_screenshots": True,
        "buzzer_inactive": True,
        "catalog_generation": 98,
        "catalog_observations": 0,
        "clear_reset_reason_code": 3,
        "deadline_ms": 6000,
        "emergency_quiesce_count": 1,
        "exact_cid": CID,
        "final_lease_mask": 0,
        "final_owner": "none",
        "injection_ms": 8000,
        "latched_restart_reset_reason_code": 3,
        "manual_button_presses": 0,
        "nrf_ce_inactive": True,
        "observed_expiry_age_ms": 6001,
        "physical_rail_kill_available": False,
        "public_product_path": "wifi_nearby_networks",
        "selected_source_mask": 1,
        "software_only": True,
        "storage_physical_write_calls": 0,
        "trip_count": 1,
        "worker": "product_survey",
        "worker_arm_count": 1,
        "worker_heartbeat_count": 2,
        "worker_trip_count": 1,
    }, "verified claim mismatch")
    require(failures, coverage == {
        "all_long_lived_workers": False,
        "ble_product_survey_physical_injection": False,
        "future_transmit_leases": False,
        "physical_rail_kill": False,
        "product_survey_preparation_phase": False,
        "product_survey_wifi_worker": True,
        "software_controlled_outputs_quiesced": True,
        "software_restart_latch_retention": True,
        "worker_heartbeat_supervision": True,
    }, "coverage/limitations mismatch")

    verify_manifest(failures)
    require(failures,
            digest(BUNDLE / "artifacts.sha256") == INDEX and
            digest(BUNDLE / "run.json") == RUN and
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "runner.py") == RUNNER,
            "retained candidate/runner mismatch")
    runner_blob = git_blob(SOURCE, "tools/run_1x_worker_deadline_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() == RUNNER,
            "runner commit/source mismatch")

    run = load(BUNDLE / "run.json")
    records = run.get("records", {})
    require(failures,
            run.get("schema") == "leshy.worker_deadline_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": APP, "firmware_sha256": FIRMWARE,
                "flashed": True, "runner_sha256": RUNNER,
                "source_commit": SOURCE, "version": VERSION},
            "exact run identity mismatch")
    require(failures,
            run.get("restart_raw") == {
                "bytes": 6913,
                "sha256": "52de2cae2ce4edf31bfab253448cb73b7a9e422bd61c775c3f658d803f709a82"} and
            run.get("clear_raw") == {
                "bytes": 7418,
                "sha256": "80db2951fba03905d404d5003b637f7c0067bd5fde63e84eeeac92df6bee9ef1"},
            "restart transcript identity mismatch")

    trace = run.get("trace", [])
    require(failures, len(trace) == 2 and
            trace[0].get("page") == "survey" and
            trace[0].get("wifi_product_view") == "menu" and
            trace[0].get("selected_id") == "wifi" and
            trace[0].get("runtime_owner") == "wifi" and
            trace[0].get("lease_mask") == 15 and
            trace[1].get("wifi_product_view") == "networks" and
            trace[1].get("survey_product_selected_source_mask") == 1 and
            trace[1].get("survey_product_status") == "preparing",
            "public Wi-Fi Product Survey path mismatch")
    require(failures, records.get("injection") == {
        "deadline_ms": 6000, "injection_ms": 8000, "kind": "armed",
        "outputs_inactive": True, "physical_write_calls": 0,
        "requires_public_survey_start": True,
        "schema": "leshy.safety.worker_deadline_test.v1",
        "worker": "product_survey"}, "fault injection mismatch")

    tripped = records.get("safety_tripped", {})
    cleanup = records.get("safety_cleanup", {})
    require(failures,
            safe_state(tripped, "latched", "worker_deadline", True, 11, 1) and
            tripped.get("armed") is False and
            tripped.get("worker_active") == "product_survey" and
            tripped.get("worker_armed") is True and
            tripped.get("worker_expired") is True and
            tripped.get("worker_deadline_ms") == 6000 and
            tripped.get("worker_age_ms") == 6001 and
            tripped.get("worker_arm_count") == 1 and
            tripped.get("worker_heartbeat_count") == 2 and
            tripped.get("worker_trip_count") == 1,
            "worker deadline trip mismatch")
    require(failures,
            safe_state(cleanup, "latched", "worker_deadline", True, 11, 1) and
            cleanup.get("armed") is False and
            cleanup.get("worker_active") == "none" and
            cleanup.get("worker_armed") is False and
            cleanup.get("worker_expired") is True,
            "post-cancel cleanup mismatch")
    outputs = records.get("outputs_latched", {})
    require(failures,
            outputs.get("software_quiesce_complete") is True and
            outputs.get("buzzer_inactive") is True and
            outputs.get("nrf_ce_inactive") is True and
            outputs.get("physical_rail_kill_available") is False and
            outputs.get("cc1101_hard_kill_available") is False,
            "software output quiesce mismatch")

    after_restart = records.get("safety_after_restart", {})
    recovery_restart = records.get("recovery_after_restart", {})
    require(failures,
            safe_state(after_restart, "latched", "worker_deadline", True, 3, 1) and
            after_restart.get("armed") is True and
            records.get("restart_ready", {}).get("reset_reason_code") == 3 and
            records.get("restart_request", {}).get("latch_preserved") is True and
            records.get("restart_request", {}).get("physical_write_calls") == 0 and
            recovery_restart.get("status") == "safety_latched" and
            recovery_restart.get("cleanup_complete") is True and
            recovery_restart.get("physical_write_calls") == 0 and
            recovery_restart.get("owned_after") == 0,
            "retained restart/blocked recovery mismatch")
    require(failures,
            records.get("ui_latched", {}).get("safety_state") == "latched" and
            records.get("ui_clear_pending", {}).get("safety_state") ==
                "clear_pending" and
            records.get("ui_latched", {}).get("page") ==
                records.get("ui_clear_pending", {}).get("page") == "safe_mode",
            "explicit two-action clear state mismatch")

    final = records.get("safety_final", {})
    recovery = records.get("recovery_final", {})
    ui_final = records.get("ui_final", {})
    require(failures,
            safe_state(final, "armed", "none", False, 3, 0) and
            final.get("armed") is True and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("generation") == 98 and
            recovery.get("observations") == 0 and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("owned_after") == 0 and
            ui_final.get("page") == "home" and
            ui_final.get("runtime_owner") == "none" and
            ui_final.get("lease_mask") == 0,
            "final Home/CID/catalog/lease mismatch")

    for key, (filename, page, state, expected_png) in FRAME_PAGES.items():
        frame = records.get(key, {})
        png = BUNDLE / "frames" / filename
        require(failures,
                png_size(png) == (240, 320) and digest(png) == expected_png and
                frame.get("png_sha256") == expected_png and
                frame.get("state", {}).get("page") == page and
                frame.get("state", {}).get("safety_state") == state,
                f"TFT evidence mismatch: {key}")

    platform_blob = git_blob(SOURCE, "firmware/leshy1/platformio.ini") or b""
    core_blob = git_blob(
        SOURCE,
        "firmware/leshy1/src/kernel/safety/WorkerDeadlineSupervisor.cpp") or b""
    entry_blob = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp") or b""
    require(failures,
            VERSION.encode() in platform_blob and
            b"state_.expired = true" in core_blob and
            b"serviceWorkerDeadlineSupervisor();" in entry_blob and
            b"latchSafetyStopInTask(SafetyReason::WorkerDeadline);" in entry_blob,
            "source-bound deadline integration mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "schema": summary["schema"], "status": summary["status"],
        "source": SOURCE, "cid": CID, "worker": "product_survey",
        "path": "wifi_nearby_networks", "deadline_ms": 6000,
        "observed_age_ms": 6001, "trip_count": 1,
        "final_owner": "none", "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
