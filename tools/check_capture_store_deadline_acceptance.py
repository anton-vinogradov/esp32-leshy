#!/usr/bin/env python3
"""Fail closed unless the retained exact 0.136 Capture Store proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-capture-store-deadline-0.136.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-capture-store-deadline-0.136"
VERSION = "0.136.0-capture-store-deadline"
SOURCE = "f6711822e2af834883b3981ec2636ac984034507"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "aaa24fd6cf3354834d18f36be5300c724c4c40fb9d2b6a9bb743e71a6e0391a0"
APP = "ebd08020a670a054b6024c6b86e1bd7870e8e0febb95b27c7955a8dbb09cfab4"
MAP = "acfae6cf5db93c971cc68fe3b453b200812f22f8f7f665a1cc368e1fb83113a2"
RUNNER = "b95f437d35ac51b7e4038a505525f346d0c66b0524944a0500752d855810b5b1"
RUN = "900dac02f0bdc91b188f0401207e8cf6999dc8ba86526eb7c776570450ca16e4"
INDEX = "f1440e1e5776a938195e987278bb66e53a00b5505911cf8e8f1f227c04539692"
FAILED_MEMORY = "6e3982e129397617af7483448ac67d373f738a592caeeffc761ea1c33bbf30d8"
FAILED_FLASH = "7854f418cbd2f454eb1ad0ee67542511a4a14e915004bf1f6aa6b29d75002a8b"
MOUNT_REGRESSION = "f48f767c2215fea78bd42af93cf92b49d7ad334b0d7c907ad39d2761716c3e68"
FRAME_PAGES = {
    "frame_latched": (
        "capture-store-deadline-latched.png", "safe_mode", "latched",
        "2eda0ea0c68c6810f11c7f7dc006532625792473548e862ace25268826502a16"),
    "frame_clear_pending": (
        "capture-store-deadline-clear-pending.png", "safe_mode", "clear_pending",
        "d3265689067a8fe31cb3393ce32fa2f747d96db6b9c46fb2a2c77c7322560f44"),
    "frame_final": (
        "home-final.png", "home", "armed",
        "f29853eff6af6f5440117e659100dd86de712cbb6e5dc0dfcca47a7da013bec4"),
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
            "0.136 Capture Store deadline evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    verified = summary.get("verified", {})
    coverage = summary.get("coverage", {})
    require(failures,
            summary.get("schema") ==
                "leshy.capture_store_deadline_acceptance.v1" and
            summary.get("status") == "pass_wifi_capture_store_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-136", "E-AUTO-097", "E-HIL-157", "E-SAFETY-005"],
            "summary identity mismatch")
    require(failures,
            candidate == {
                "schema": "leshy.capture_store_deadline.provenance.v1",
                "version": VERSION, "source_commit": SOURCE,
                "runner_commit": SOURCE, "firmware_sha256": FIRMWARE,
                "app_elf_sha256": APP, "map_sha256": MAP,
                "runner_sha256": RUNNER, "run_sha256": RUN,
                "firmware_bytes": 3059760, "linked_flash_bytes": 3059360,
                "static_ram_bytes": 207928},
            "candidate identity/resource mismatch")
    require(failures, summary.get("evidence") == {
        "files": 19, "indexed_files": 18, "tft_states": 3,
        "artifact_index_sha256": INDEX, "run_sha256": RUN,
        "failed_no_memory_run_sha256": FAILED_MEMORY,
        "failed_post_flash_run_sha256": FAILED_FLASH,
        "power_cycle_readonly_mount_sha256": MOUNT_REGRESSION,
    }, "evidence identity mismatch")
    require(failures,
            verified.get("before_storage_hardware") is True and
            verified.get("worker") == "wifi_capture_store" and
            verified.get("deadline_ms") == 8000 and
            verified.get("injection_ms") == 10000 and
            verified.get("exact_cid") == CID and
            verified.get("generation_before") == 98 and
            verified.get("generation_after_normal_save") == 99 and
            verified.get("generation_final") == 99 and
            verified.get("normal_heap_free_before_mount") == 93544 and
            verified.get("normal_heap_largest_before_mount") == 32756 and
            verified.get("normal_filesystem_mount_error") == 0 and
            verified.get("normal_worker_arm_count") == 1 and
            verified.get("normal_worker_heartbeat_count") == 9 and
            verified.get("normal_worker_trip_count") == 0 and
            verified.get("worker_arm_count") == 2 and
            verified.get("worker_heartbeat_count") == 10 and
            verified.get("worker_trip_count") == 1 and
            verified.get("observed_expiry_age_ms") == 8001 and
            verified.get("fault_storage_physical_write_calls") == 0 and
            verified.get("static_ram_reclaimed_bytes") == 25432 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified claim mismatch")
    require(failures,
            coverage.get("wifi_capture_store_worker") is True and
            coverage.get("normal_persistent_capture_commit") is True and
            coverage.get("pre_storage_fault_injection") is True and
            coverage.get("all_long_lived_workers") is False and
            coverage.get("physical_rail_kill") is False and
            coverage.get("raw_80211_payload_retained") is False and
            coverage.get("pcap_retained") is False,
            "coverage/limitations mismatch")

    verify_manifest(failures)
    require(failures,
            digest(BUNDLE / "artifacts.sha256") == INDEX and
            digest(BUNDLE / "run.json") == RUN and
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "runner.py") == RUNNER and
            digest(BUNDLE / "failed-no-memory-run.json") == FAILED_MEMORY and
            digest(BUNDLE / "failed-post-flash-run.json") == FAILED_FLASH and
            digest(BUNDLE / "power-cycle-readonly-mount.json") == MOUNT_REGRESSION,
            "retained candidate/diagnostic mismatch")
    runner_blob = git_blob(SOURCE, "tools/run_1x_capture_store_deadline_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() == RUNNER,
            "runner commit/source mismatch")

    run = load(BUNDLE / "run.json")
    records = run.get("records", {})
    require(failures,
            run.get("schema") == "leshy.capture_store_deadline_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": APP, "firmware_sha256": FIRMWARE,
                "flashed": True, "runner_sha256": RUNNER,
                "source_commit": SOURCE, "version": VERSION},
            "exact run identity mismatch")
    scope = run.get("scope", {})
    require(failures,
            scope.get("fault_injection_before_storage_hardware") is True and
            scope.get("fault_injection_physical_write_calls") == 0 and
            scope.get("normal_storage_write_authorized") is True and
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("pcap_retained_in_evidence") is False and
            scope.get("raw_80211_payload_retained_in_evidence") is False,
            "privacy/fault scope mismatch")

    normal = records.get("normal_saved", {})
    normal_safety = records.get("safety_after_normal", {})
    require(failures,
            normal.get("persist_state") == "saved" and
            normal.get("persist_status") == "saved" and
            normal.get("storage_written") is True and
            normal.get("persist_generation") == 99 and
            normal.get("frames_accepted") == 2 and
            normal.get("frames_dropped_capacity") == 0 and
            normal.get("frames_dropped_invalid") == 0 and
            normal.get("heap_free_before_mount") == 93544 and
            normal.get("heap_largest_before_mount") == 32756 and
            normal.get("filesystem_mount_error") == 0 and
            normal_safety.get("state") == "armed" and
            normal_safety.get("latched") is False and
            normal_safety.get("worker_arm_count") == 1 and
            normal_safety.get("worker_heartbeat_count") == 9 and
            normal_safety.get("worker_trip_count") == 0,
            "normal save/mount/deadline calibration mismatch")
    require(failures, records.get("injection") == {
        "before_storage_hardware": True, "deadline_ms": 8000,
        "injection_ms": 10000, "kind": "armed", "outputs_inactive": True,
        "physical_write_calls": 0, "requires_public_capture_save": True,
        "schema": "leshy.safety.capture_store_deadline_test.v1",
        "worker": "wifi_capture_store"},
        "pre-storage fault injection mismatch")
    saving = records.get("saving", {})
    require(failures,
            saving.get("persist_state") == "saving" and
            saving.get("storage_written") is False and
            saving.get("heap_free_before_mount") == 0 and
            saving.get("heap_largest_before_mount") == 0 and
            saving.get("filesystem_mount_error") == 0,
            "injection crossed the storage-hardware boundary")

    tripped = records.get("safety_tripped", {})
    cleanup = records.get("safety_cleanup", {})
    require(failures,
            safe_state(tripped, "latched", "worker_deadline", True, 11, 1) and
            tripped.get("worker_active") == "wifi_capture_store" and
            tripped.get("worker_armed") is True and
            tripped.get("worker_expired") is True and
            tripped.get("worker_last_expired") == "wifi_capture_store" and
            tripped.get("worker_deadline_ms") == 8000 and
            tripped.get("worker_age_ms") == 8001 and
            tripped.get("worker_arm_count") == 2 and
            tripped.get("worker_heartbeat_count") == 10 and
            tripped.get("worker_trip_count") == 1,
            "Capture Store deadline trip mismatch")
    require(failures,
            safe_state(cleanup, "latched", "worker_deadline", True, 11, 1) and
            cleanup.get("worker_active") == "none" and
            cleanup.get("worker_armed") is False,
            "post-trip cleanup mismatch")
    outputs = records.get("outputs_latched", {})
    require(failures,
            outputs.get("software_quiesce_complete") is True and
            outputs.get("buzzer_inactive") is True and
            outputs.get("nrf_ce_inactive") is True,
            "software output quiesce mismatch")

    after_restart = records.get("safety_after_restart", {})
    recovery_restart = records.get("recovery_after_restart", {})
    require(failures,
            safe_state(after_restart, "latched", "worker_deadline", True, 3, 1) and
            records.get("restart_ready", {}).get("reset_reason_code") == 3 and
            recovery_restart.get("status") == "safety_latched" and
            recovery_restart.get("physical_write_calls") == 0 and
            recovery_restart.get("owned_after") == 0 and
            records.get("restart_ready_marker_ms") == 949.068,
            "retained restart/blocked recovery mismatch")
    final = records.get("safety_final", {})
    recovery = records.get("recovery_final", {})
    ui_final = records.get("ui_final", {})
    require(failures,
            safe_state(final, "armed", "none", False, 3, 0) and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("generation") == 99 and
            recovery.get("catalog_admitted") is True and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("owned_after") == 0 and
            ui_final.get("page") == "home" and
            ui_final.get("library_generation") == 99 and
            ui_final.get("runtime_owner") == "none" and
            ui_final.get("lease_mask") == 0 and
            records.get("clear_ready_marker_ms") == 1574.404,
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

    failed_memory = load(BUNDLE / "failed-no-memory-run.json")
    failed_flash = load(BUNDLE / "failed-post-flash-run.json")
    mount = load(BUNDLE / "power-cycle-readonly-mount.json")
    require(failures,
            failed_memory.get("passed") is False and
            failed_memory.get("candidate", {}).get("source_commit") ==
                "69d7067e488b7662186a73fe2d4c0cf51ea84081" and
            failed_memory.get("records", {}).get("normal_saved", {}).get(
                "persist_status") == "mount_failed" and
            failed_memory.get("records", {}).get("home_after_normal", {}).get(
                "library_generation") == 98,
            "initial no-memory failure was not retained fail-closed")
    require(failures,
            failed_flash.get("passed") is False and
            failed_flash.get("gate_eligible") is False and
            failed_flash.get("failures") == [
                "TimeoutError: timed out synchronizing the firmware console"],
            "post-flash USB failure was not retained fail-closed")
    require(failures,
            mount.get("status") == "valid" and mount.get("cid_hex") == CID and
            mount.get("mounted") is True and
            mount.get("read_only_guaranteed") is True and
            mount.get("physical_write_calls") == 0 and
            mount.get("owned_after") == 0,
            "power-cycle read-only mount regression mismatch")

    platform_blob = git_blob(SOURCE, "firmware/leshy1/platformio.ini") or b""
    entry_blob = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp") or b""
    require(failures,
            VERSION.encode() in platform_blob and
            b"SupervisedWorker::WifiCaptureStore" in entry_blob and
            b"kWifiCaptureStoreDeadlineUs = 8000000ULL" in entry_blob and
            b"heap_caps_get_largest_free_block" in entry_blob and
            b"filesystem_mount_error" in entry_blob,
            "exact source safety/memory telemetry mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Capture Store deadline acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
