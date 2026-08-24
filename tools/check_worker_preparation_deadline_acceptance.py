#!/usr/bin/env python3
"""Fail closed unless the retained exact 0.135 preparation proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-worker-preparation-deadline-0.135.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-worker-preparation-deadline-0.135"
VERSION = "0.135.0-survey-preparation-deadline"
SOURCE = "58cd94429568a1caf2685cae01625b4444d796c8"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "27d75987767c1b5acb54b5a02fafb819de87c0cbeb51ff35ac017bf7bf32e9f7"
APP = "749dac30b5d87002df9d8a71668ab57e33a603eaae8d66ce2bc0dd975ff83541"
MAP = "0b38a6f9d1f4d2753d140847466934b9e5b86c76c74b1c28fa5d696aa8ebc801"
RUNNER = "0e38316cdad0487334de37e843f072d7a05c67055a4644aae54e17c2e5216d4e"
RUN = "10294b1d7529543f7fbd3171dc8bc177c586cc5cc6d2383c6f54c42253915eef"
INDEX = "ed8f154bff98a6dfae5f655939a9b7697c9a5bab9c25ef11ad5fb0b4bfcb1c49"
FRAME_PAGES = {
    "frame_latched": (
        "worker-deadline-latched.png", "safe_mode", "latched",
        "2eda0ea0c68c6810f11c7f7dc006532625792473548e862ace25268826502a16"),
    "frame_clear_pending": (
        "worker-deadline-clear-pending.png", "safe_mode", "clear_pending",
        "d3265689067a8fe31cb3393ce32fa2f747d96db6b9c46fb2a2c77c7322560f44"),
    "frame_final": (
        "home-final.png", "home", "armed",
        "9b6bc25fd962ed9f95617c821c4459bf7bf9cd1bb01fca02b33452e27dc2dcae"),
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
            "0.135 preparation-deadline evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    verified = summary.get("verified", {})
    coverage = summary.get("coverage", {})
    require(failures,
            summary.get("schema") ==
                "leshy.worker_preparation_deadline_acceptance.v1" and
            summary.get("status") ==
                "pass_product_survey_preparation_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-135", "E-AUTO-096", "E-HIL-156", "E-SAFETY-004"],
            "summary identity mismatch")
    require(failures,
            candidate == {
                "schema": "leshy.worker_preparation_deadline.provenance.v1",
                "version": VERSION, "source_commit": SOURCE,
                "runner_commit": SOURCE, "firmware_sha256": FIRMWARE,
                "app_elf_sha256": APP, "map_sha256": MAP,
                "runner_sha256": RUNNER, "run_sha256": RUN,
                "firmware_bytes": 3068064, "linked_flash_bytes": 3067656,
                "static_ram_bytes": 233360},
            "candidate identity/resource mismatch")
    require(failures, summary.get("evidence") == {
        "files": 16, "indexed_files": 15, "tft_states": 3,
        "artifact_index_sha256": INDEX, "run_sha256": RUN,
    }, "evidence identity mismatch")
    require(failures,
            verified.get("before_hardware_preparation") is True and
            verified.get("worker") == "product_survey_preparation" and
            verified.get("deadline_ms") == 8000 and
            verified.get("injection_ms") == 10000 and
            verified.get("normal_ble_accepted") == 30 and
            verified.get("normal_ble_attempts") == 1 and
            verified.get("normal_ble_cycles") == 1 and
            verified.get("normal_ble_dropped") == 0 and
            verified.get("normal_ble_transient_retries") == 0 and
            verified.get("normal_worker_arm_count") == 2 and
            verified.get("normal_worker_heartbeat_count") == 16 and
            verified.get("worker_arm_count") == 3 and
            verified.get("worker_heartbeat_count") == 18 and
            verified.get("worker_trip_count") == 1 and
            verified.get("observed_expiry_age_ms") == 8001 and
            verified.get("exact_cid") == CID and
            verified.get("catalog_generation") == 98 and
            verified.get("catalog_observations") == 0 and
            verified.get("storage_physical_write_calls") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified claim mismatch")
    require(failures,
            coverage.get("product_survey_preparation_phase") is True and
            coverage.get("product_survey_admission_phase") is True and
            coverage.get("all_long_lived_workers") is False and
            coverage.get("physical_rail_kill") is False,
            "coverage/limitations mismatch")

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
            run.get("failures") == [] and
            run.get("injection_stage") == "preparation" and
            run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": APP, "firmware_sha256": FIRMWARE,
                "flashed": True, "runner_sha256": RUNNER,
                "source_commit": SOURCE, "version": VERSION},
            "exact run identity mismatch")
    require(failures,
            run.get("restart_raw") == {
                "bytes": 6963,
                "sha256": "48f59a3859e9e19d50ad68427522ac3a6d0b90614c94d8741ca1c24253b60520"} and
            run.get("clear_raw") == {
                "bytes": 9409,
                "sha256": "9f6cb604bdeb120dc8440df049eb972e18c10ae079b858c22ed0682a2149e0ef"},
            "restart transcript identity mismatch")

    trace = run.get("trace", [])
    require(failures, len(trace) == 4 and
            trace[0].get("page") == "home" and
            trace[0].get("selected_id") == "ble" and
            trace[1].get("ble_product_view") == "devices" and
            trace[1].get("survey_product_selected_source_mask") == 2 and
            trace[2].get("survey_product_status") == "cancelling" and
            trace[3].get("survey_product_status") == "preparing",
            "public BLE Product Survey path mismatch")
    normal = records.get("normal_ble_cycle", {})
    normal_safety = records.get("safety_after_normal_ble", {})
    normal_cleanup = records.get("safety_after_normal_cleanup", {})
    require(failures,
            normal.get("survey_product_ble_scan_cycles") == 1 and
            normal.get("survey_ble_scan_attempts") == 1 and
            normal.get("survey_ble_scan_transient_retries") == 0 and
            normal.get("survey_ble_scan_reported") == 30 and
            normal.get("survey_ble_scan_accepted") == 30 and
            normal.get("survey_ble_scan_dropped") == 0 and
            normal_safety.get("state") == "armed" and
            normal_safety.get("latched") is False and
            normal_safety.get("runtime_owner") == "ble" and
            normal_safety.get("lease_mask") == 15 and
            normal_safety.get("worker_active") == "product_survey" and
            normal_safety.get("worker_arm_count") == 2 and
            normal_safety.get("worker_heartbeat_count") == 16 and
            normal_safety.get("worker_trip_count") == 0 and
            normal_cleanup.get("runtime_owner") == "none" and
            normal_cleanup.get("lease_mask") == 0 and
            normal_cleanup.get("worker_active") == "none" and
            normal_cleanup.get("worker_armed") is False,
            "normal BLE preparation/worker calibration mismatch")
    require(failures, records.get("injection") == {
        "before_hardware_preparation": True,
        "deadline_ms": 8000, "injection_ms": 10000, "kind": "armed",
        "outputs_inactive": True, "physical_write_calls": 0,
        "requires_public_survey_start": True,
        "schema": "leshy.safety.worker_preparation_deadline_test.v1",
        "worker": "product_survey_preparation"},
        "preparation fault injection mismatch")

    tripped = records.get("safety_tripped", {})
    cleanup = records.get("safety_cleanup", {})
    require(failures,
            safe_state(tripped, "latched", "worker_deadline", True, 11, 1) and
            tripped.get("armed") is False and
            tripped.get("worker_active") == "product_survey_preparation" and
            tripped.get("worker_armed") is True and
            tripped.get("worker_expired") is True and
            tripped.get("worker_last_expired") ==
                "product_survey_preparation" and
            tripped.get("worker_deadline_ms") == 8000 and
            tripped.get("worker_age_ms") == 8001 and
            tripped.get("worker_arm_count") == 3 and
            tripped.get("worker_heartbeat_count") == 18 and
            tripped.get("worker_trip_count") == 1,
            "preparation deadline trip mismatch")
    require(failures,
            safe_state(cleanup, "latched", "worker_deadline", True, 11, 1) and
            cleanup.get("worker_active") == "none" and
            cleanup.get("worker_armed") is False and
            cleanup.get("worker_expired") is True and
            cleanup.get("worker_last_expired") ==
                "product_survey_preparation",
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
            "explicit two-action clear mismatch")

    final = records.get("safety_final", {})
    recovery = records.get("recovery_final", {})
    ui_final = records.get("ui_final", {})
    require(failures,
            safe_state(final, "armed", "none", False, 3, 0) and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("generation") == 98 and
            recovery.get("observations") == 0 and
            recovery.get("attempts") == 5 and
            recovery.get("transient_retries") == 4 and
            recovery.get("timeout_restarts") == 0 and
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
    entry_blob = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp") or b""
    require(failures,
            VERSION.encode() in platform_blob and
            b"SupervisedWorker::ProductSurveyPreparation" in entry_blob and
            b"kProductSurveyPreparationDeadlineUs = 8000000ULL" in entry_blob and
            b"kProductSurveyPreparationDeadlineInjectionMs = 10000" in entry_blob and
            b"armProductSurveyPreparationDeadline(preparationStartedUs)" in entry_blob and
            entry_blob.count(b"heartbeatProductSurveyPreparation();") >= 8 and
            b"safety.worker-preparation-deadline-test confirm" in entry_blob,
            "source-bound preparation deadline mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "schema": summary["schema"], "status": summary["status"],
        "source": SOURCE, "cid": CID,
        "worker": "product_survey_preparation",
        "normal_ble_accepted": 30, "deadline_ms": 8000,
        "observed_age_ms": 8001, "trip_count": 1,
        "final_owner": "none", "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
