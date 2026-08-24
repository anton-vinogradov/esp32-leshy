#!/usr/bin/env python3
"""Fail closed unless the retained exact 0.138 IR Store proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-infrared-store-deadline-0.138.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-infrared-store-deadline-0.138"
VERSION = "0.138.0-safety-restart-noos"
SOURCE = "0f52520a6323e3e9b68a4a2f26dcd242bdcd71f6"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "97e5c9830ff11883a11c0e823e07408d3d6b11be8e442cd7edc3794be6019e08"
APP = "d453ac8a9af5017a494262e3bac958f7256736084f3e154aa4421b21c68e62c1"
MAP = "661f9132ac836753435db65d314172d133518cbc96c793a213da393a2d6ba9fa"
RUNNER = "ae02d35b7d4431ef93a1f72369fa035fd83d2d79e28907d1f7f03f6007786d9e"
RUN = "69ed73f5777d360583710898677f9b6ad0a360417bc72696195ff8430fd11e43"
INDEX = "0f6931727f27ab5a27a881be540c617fac6f27bafb8b24e35ac5a9fac2073d7d"
REGRESSION = "6f37d4d4ecfc8cea1fcb78b67996f5c10660616c60f4ae0969c01f602418010c"
FAILED_RUN = "a942214e622ddcb8667be75978e7c4e03c65a6928d69ad7e3aef2f9f9b8f9f52"
FAILED_BOOT = "0ddb668bbb0024056a1d8e05dae865a8e496228eecb05db5ed17978ddc312597"
FIXTURE_FIRMWARE = "ad34877f7a2f4b1c6d9c9cf9c489990daafcdd00105c913897057876fd462039"
FIXTURE_APP = "c94fef07d1ee608b0141ecaf8b8f990e4f68d0f4c6f70d14badf1c98338edf94"
FIXTURE_PROFILE = "729ac286ef505203bd6db06ee4129b1df977b5833e11797d6571d8bf04eaa74d"
FRAME_PAGES = {
    "frame_latched": (
        "infrared-store-deadline-latched.png", "safe_mode", "latched",
        "2eda0ea0c68c6810f11c7f7dc006532625792473548e862ace25268826502a16"),
    "frame_clear_pending": (
        "infrared-store-deadline-clear-pending.png", "safe_mode",
        "clear_pending",
        "d3265689067a8fe31cb3393ce32fa2f747d96db6b9c46fb2a2c77c7322560f44"),
    "frame_final": (
        "home-final.png", "home", "armed",
        "ea7829a7e6258e32efd2a567037ae39cb79061409623225e8ebf3461c4158130"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


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
    if (len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or
            data[12:16] != b"IHDR"):
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
        artifact = BUNDLE / relative
        require(failures, artifact.is_file(),
                f"retained artifact missing: {relative}")
        if artifact.is_file():
            require(failures, digest(artifact) == expected,
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


def decoded_nec(record: dict[str, Any]) -> bool:
    return (
        record.get("schema") == "leshy.capture.infrared_raw.v1" and
        record.get("state") == "complete" and
        record.get("protocol") == "nec" and
        record.get("raw_code") == 3409243920 and
        record.get("address") == 16 and record.get("command") == 52 and
        record.get("pulses") == 67 and record.get("transitions") == 68 and
        record.get("decode_integrity_valid") is True and
        record.get("truncated") is False
    )


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.138 IR Store deadline evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    fixture_candidate = summary.get("fixture_candidate", {})
    verified = summary.get("verified", {})
    coverage = summary.get("coverage", {})
    require(failures,
            summary.get("schema") ==
                "leshy.infrared_store_deadline_acceptance.v1" and
            summary.get("status") ==
                "pass_infrared_capture_store_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("fixture") == "board-02" and
            summary.get("evidence_ids") == [
                "E-BUILD-138", "E-AUTO-099", "E-HIL-159", "E-SAFETY-006"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("run_sha256") == RUN and
            candidate.get("firmware_bytes") == 3061920 and
            candidate.get("factory_bytes") == 3127456 and
            candidate.get("linked_flash_bytes") == 3061508 and
            candidate.get("static_ram_bytes") == 207960,
            "candidate identity/resource mismatch")
    require(failures,
            fixture_candidate == {
                "version": "0.2.5-shared-pin-safe",
                "fixture_id": "00009070690D15E0",
                "firmware_sha256": FIXTURE_FIRMWARE,
                "app_elf_sha256": FIXTURE_APP,
                "profile_sha256": FIXTURE_PROFILE,
            }, "fixture identity mismatch")
    require(failures,
            summary.get("evidence") == {
                "files": 21, "indexed_files": 20, "tft_states": 3,
                "artifact_index_sha256": INDEX, "run_sha256": RUN,
                "regression_run_sha256": REGRESSION,
                "failed_esp_restart_run_sha256": FAILED_RUN,
                "failed_esp_restart_transcript_sha256": FAILED_BOOT,
            }, "evidence identity mismatch")
    require(failures,
            verified.get("automatic_clear") is False and
            verified.get("automatic_screenshots") is True and
            verified.get("automatic_fresh_flash_exit") is True and
            verified.get("before_storage_hardware") is True and
            verified.get("deadline_ms") == 8000 and
            verified.get("injection_ms") == 10000 and
            verified.get("exact_cid") == CID and
            verified.get("generation_before") == 106 and
            verified.get("generation_after_normal_save") == 107 and
            verified.get("generation_final") == 107 and
            verified.get("normal_heap_free_before_mount") == 94136 and
            verified.get("normal_heap_largest_before_mount") == 51188 and
            verified.get("normal_filesystem_mount_error") == 0 and
            verified.get("normal_worker_arm_count") == 1 and
            verified.get("normal_worker_heartbeat_count") == 10 and
            verified.get("normal_worker_trip_count") == 0 and
            verified.get("worker") == "infrared_capture_store" and
            verified.get("worker_arm_count") == 2 and
            verified.get("worker_heartbeat_count") == 11 and
            verified.get("worker_trip_count") == 1 and
            verified.get("observed_expiry_age_ms") == 8001 and
            verified.get("fault_storage_physical_write_calls") == 0 and
            verified.get("product_ir_transmit_calls") == 0 and
            verified.get("fixture_emissions") == 2 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0 and
            verified.get("regression_passed") is True and
            verified.get("esp_restart_failure_retained") is True and
            verified.get("manual_button_presses_in_gate") == 0,
            "verified claim mismatch")
    require(failures,
            coverage.get("infrared_capture_store_worker") is True and
            coverage.get("normal_ir_decode_and_persistent_commit") is True and
            coverage.get("pre_storage_fault_injection") is True and
            coverage.get("bounded_two_board_fixture") is True and
            coverage.get("native_usb_flash_exit") is True and
            coverage.get("all_long_lived_workers") is False and
            coverage.get("subghz_capture_store_worker") is False and
            coverage.get("physical_rail_kill") is False and
            coverage.get("general_ir_protocol_coverage") is False and
            coverage.get("product_ir_replay") is False,
            "coverage/limitations mismatch")

    verify_manifest(failures)
    require(failures,
            digest(BUNDLE / "artifacts.sha256") == INDEX and
            digest(BUNDLE / "run.json") == RUN and
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "runner.py") == RUNNER and
            digest(BUNDLE / "fixture.bin") == FIXTURE_FIRMWARE and
            app_elf_sha256(BUNDLE / "fixture.bin") == FIXTURE_APP and
            digest(BUNDLE / "fixture-profile.json") == FIXTURE_PROFILE and
            digest(BUNDLE / "regression-run.json") == REGRESSION and
            digest(BUNDLE / "failed-esp-restart-run.json") == FAILED_RUN and
            digest(BUNDLE / "failed-esp-restart-latched.ndjson") == FAILED_BOOT,
            "retained candidate/fixture/diagnostic mismatch")
    runner_blob = git_blob(SOURCE, "tools/run_1x_infrared_store_deadline_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() == RUNNER,
            "runner commit/source mismatch")

    run = load(BUNDLE / "run.json")
    records = run.get("records", {})
    require(failures,
            run.get("schema") == "leshy.infrared_store_deadline_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": APP, "firmware_sha256": FIRMWARE,
                "flashed": True, "runner_sha256": RUNNER,
                "source_commit": SOURCE, "version": VERSION} and
            run.get("fixture") == {
                "app_elf_sha256": FIXTURE_APP,
                "firmware_sha256": FIXTURE_FIRMWARE,
                "fixture_id": "00009070690D15E0", "flashed": True,
                "profile_sha256": FIXTURE_PROFILE,
                "version": "0.2.5-shared-pin-safe"},
            "exact run identity mismatch")
    scope = run.get("scope", {})
    require(failures,
            scope.get("fault_injection_before_storage_hardware") is True and
            scope.get("fault_injection_physical_write_calls") == 0 and
            scope.get("normal_storage_write_authorized") is True and
            scope.get("product_ir_transmit_calls") == 0 and
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("two_bounded_fixture_emissions") is True,
            "fault/emission scope mismatch")
    require(failures,
            run.get("restart_raw") == {
                "bytes": 7102,
                "sha256": "025657c0616e42212d7a4612ed729fd3f6496870ce5e30bee985ded841262604"} and
            run.get("clear_raw") == {
                "bytes": 7512,
                "sha256": "286661401eaf5dcd9c77152fefd00f11f046bd805bfceb9dae8ba79b54edfd9d"},
            "restart transcript identity mismatch")

    require(failures,
            len(run.get("trace", [])) == 26 and
            run["trace"][3].get("selected_id") == "capture" and
            run["trace"][5].get("page") == "capture" and
            run["trace"][11].get("page") == "home" and
            run["trace"][19].get("selected_id") == "capture" and
            run["trace"][25].get("lease_mask") == 15,
            "public IR Capture path mismatch")
    normal = records.get("normal_saved", {})
    require(failures,
            decoded_nec(normal) and normal.get("persist_state") == "saved" and
            normal.get("persist_status") == "saved" and
            normal.get("storage_written") is True and
            normal.get("persist_generation") == 107 and
            normal.get("heap_free_before_mount") == 94136 and
            normal.get("heap_largest_before_mount") == 51188 and
            normal.get("filesystem_mount_error") == 0,
            "normal NEC save/mount mismatch")
    normal_safety = records.get("safety_after_normal", {})
    require(failures,
            normal_safety.get("state") == "armed" and
            normal_safety.get("latched") is False and
            normal_safety.get("runtime_owner") == "capture" and
            normal_safety.get("lease_mask") == 11 and
            normal_safety.get("worker_arm_count") == 1 and
            normal_safety.get("worker_heartbeat_count") == 10 and
            normal_safety.get("worker_trip_count") == 0,
            "normal deadline calibration mismatch")
    require(failures, records.get("injection") == {
        "before_storage_hardware": True, "deadline_ms": 8000,
        "injection_ms": 10000, "kind": "armed", "outputs_inactive": True,
        "physical_write_calls": 0, "requires_public_capture_save": True,
        "schema": "leshy.safety.pulse_capture_store_deadline_test.v1",
        "source": "infrared",
        "worker": "infrared_capture_store"},
        "pre-storage fault injection mismatch")
    saving = records.get("saving", {})
    require(failures,
            decoded_nec(saving) and saving.get("persist_state") == "saving" and
            saving.get("storage_written") is False and
            saving.get("heap_free_before_mount") == 0 and
            saving.get("heap_largest_before_mount") == 0 and
            saving.get("filesystem_mount_error") == 0,
            "injection crossed storage-hardware boundary")

    tripped = records.get("safety_tripped", {})
    cleanup = records.get("safety_cleanup", {})
    require(failures,
            safe_state(tripped, "latched", "worker_deadline", True, 11, 1) and
            tripped.get("worker_active") == "infrared_capture_store" and
            tripped.get("worker_armed") is True and
            tripped.get("worker_expired") is True and
            tripped.get("worker_last_expired") == "infrared_capture_store" and
            tripped.get("worker_deadline_ms") == 8000 and
            tripped.get("worker_age_ms") == 8001 and
            tripped.get("worker_arm_count") == 2 and
            tripped.get("worker_heartbeat_count") == 11 and
            tripped.get("worker_trip_count") == 1,
            "IR Capture Store deadline trip mismatch")
    require(failures,
            safe_state(cleanup, "latched", "worker_deadline", True, 11, 1) and
            cleanup.get("worker_active") == "none" and
            cleanup.get("worker_armed") is False and
            records.get("outputs_latched", {}).get(
                "software_quiesce_complete") is True,
            "post-trip cleanup/output quiesce mismatch")

    restart = records.get("safety_after_restart", {})
    final = records.get("safety_final", {})
    recovery_restart = records.get("recovery_after_restart", {})
    recovery_final = records.get("recovery_final", {})
    ui_final = records.get("ui_final", {})
    require(failures,
            safe_state(restart, "latched", "worker_deadline", True, 3, 1) and
            records.get("restart_ready", {}).get("reset_reason_code") == 3 and
            records.get("restart_ready_marker_ms") == 947.445 and
            records.get("restart_usb_disconnects") == 0 and
            records.get("restart_usb_open_attempts") == 1 and
            recovery_restart.get("status") == "safety_latched" and
            recovery_restart.get("physical_write_calls") == 0 and
            recovery_restart.get("owned_after") == 0,
            "retained no-OS restart/blocked recovery mismatch")
    require(failures,
            safe_state(final, "armed", "none", False, 3, 0) and
            records.get("clear_ready_marker_ms") == 1594.198 and
            records.get("clear_usb_disconnects") == 0 and
            records.get("clear_usb_open_attempts") == 1 and
            recovery_final.get("expected_fingerprint") == CID and
            recovery_final.get("observed_fingerprint") == CID and
            recovery_final.get("generation") == 107 and
            recovery_final.get("catalog_admitted") is True and
            recovery_final.get("physical_write_calls") == 0 and
            recovery_final.get("owned_after") == 0 and
            ui_final.get("page") == "home" and
            ui_final.get("library_generation") == 107 and
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

    fixture_results = (
        records.get("fixture_normal_nec", {}),
        records.get("fixture_injected_nec", {}),
    )
    require(failures, all(
        value.get("state") == "complete" and
        value.get("signal") == "infrared_nec" and
        value.get("vector_id") == "nec-10-34" and
        0 < value.get("last_duration_us", 0) <= 100000 and
        value.get("output_inactive") is True and
        value.get("buzzer_inactive") is True and
        value.get("nrf_ce_inactive") is True
        for value in fixture_results),
        "bounded fixture emission mismatch")
    fixture_cleanup = records.get("fixture_cleanup", {})
    require(failures,
            fixture_cleanup.get("armed") is False and
            fixture_cleanup.get("ir_tx_inactive") is True and
            fixture_cleanup.get("nrf_carrier_active") is False and
            fixture_cleanup.get("nrf_powered_down") is True and
            fixture_cleanup.get("output_inactive") is True,
            "fixture final cleanup mismatch")

    regression = load(BUNDLE / "regression-run.json")
    failed_run = load(BUNDLE / "failed-esp-restart-run.json")
    failed_boot = (BUNDLE / "failed-esp-restart-latched.ndjson").read_bytes()
    require(failures,
            regression.get("passed") is True and
            regression.get("gate_eligible") is False and
            regression.get("failures") == [] and
            regression.get("candidate", {}).get("version") == VERSION and
            regression.get("candidate", {}).get("flashed") is False,
            "short exact-image regression mismatch")
    require(failures,
            failed_run.get("passed") is False and
            failed_run.get("gate_eligible") is False and
            failed_run.get("candidate", {}).get("version") ==
                "0.137.0-pulse-store-deadline" and
            failed_run.get("restart_raw") == {
                "bytes": 259, "sha256": FAILED_BOOT} and
            any("synchronizing the firmware console" in item
                for item in failed_run.get("failures", [])) and
            b"RTC_SW_CPU_RST" in failed_boot and
            b'"schema":"leshy.boot.v1","kind":"ready"' not in failed_boot,
            "ordinary esp_restart failure was not retained fail-closed")

    platform_blob = git_blob(SOURCE, "firmware/leshy1/platformio.ini") or b""
    entry_blob = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp") or b""
    flash_blob = git_blob(SOURCE, "tools/run_1x_prerelease_hil.py") or b""
    require(failures,
            VERSION.encode() in platform_blob and
            b"SupervisedWorker::InfraredCaptureStore" in entry_blob and
            b"kPulseCaptureStoreDeadlineUs = 8000000ULL" in entry_blob and
            entry_blob.count(b"esp_restart_noos();") >= 2 and
            b'"--after", "no-reset"' in flash_blob and
            b'"--after", "watchdog-reset"' in flash_blob and
            b'"--before", "no-reset"' in flash_blob,
            "exact source restart/deploy contract mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(
        "infrared store deadline acceptance passed: exact fresh-flash pair, "
        "2 bounded NEC emissions, normal save, 8 s pre-storage trip, retained "
        "no-OS restart, explicit clear, CID/catalog recovery and final lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
