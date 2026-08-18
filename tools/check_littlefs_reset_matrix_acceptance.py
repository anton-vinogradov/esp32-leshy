#!/usr/bin/env python3
"""Fail closed unless exact 0.70 LittleFS reset-matrix evidence passes."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-littlefs-reset-matrix-0.70.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-littlefs-reset-matrix-0.70"
RUNNER = ROOT / "tools/run_1x_littlefs_reset_matrix_hil.py"
RUNNER_TEST = ROOT / "tools/test_littlefs_reset_matrix_hil_runner.py"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
IO_ADAPTER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoLittleFsSessionStoreIo.cpp"
PLATFORM = ROOT / "firmware/leshy1/platformio.ini"
BUILD = ROOT / "firmware/leshy1/.pio/build/esp32-div-v2-clean"
DOCS = (
    ROOT / "docs/v1/STATUS.md",
    ROOT / "docs/v1/STATUS.ru.md",
    ROOT / "docs/v1/STORAGE_HIL.md",
    ROOT / "docs/v1/STORAGE_HIL.ru.md",
    ROOT / "docs/v1/RESOURCE_BUDGETS.md",
    ROOT / "docs/v1/RESOURCE_BUDGETS.ru.md",
    ROOT / "docs/v1/TRACEABILITY.md",
    ROOT / "docs/v1/TRACEABILITY.ru.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def exact(record: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in expected.items())


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "acceptance evidence missing")
    require(failures, BUNDLE.is_dir(), "retained evidence bundle missing")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures, exact(evidence, {
        "schema": "leshy.storage.littlefs_reset_matrix_acceptance.v1",
        "status": "pass", "gate_eligible": False,
    }), "acceptance status mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-071", "E-AUTO-034", "E-HIL-094", "E-STORAGE-025"
    ], "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.70.0-littlefs-reset-matrix",
        "firmware_sha256":
            "83dfc22bab7462a47cd329d6d7720dc8705bb9738ba08eb9fdc50e4df8f2468a",
        "factory_sha256":
            "8b808a78b4258625e96a5eee11be921982cedd0035f2a7d03ab45b1af4f770c6",
        "app_elf_sha256":
            "5ce796743f0282cc2d2f458e80ce405cf04acca9ac0c9c068f5e11605bd85efe",
        "map_sha256":
            "efdb876b37a9feb32390eed8aacad01a8e3d0dcaf2aae23e2a2784c56ac9975b",
        "linked_flash_bytes": 1165916, "static_ram_bytes": 134888,
        "app_image_bytes": 1166320, "factory_image_bytes": 1231856,
        "rtc_noinit_bytes": 60, "host_tests_passed": True,
        "firmware_build_passed": True, "reproducible_rebuild": True,
    }, "exact candidate mismatch")
    version_match = re.search(
        r'LESHY1_VERSION=\\"(\d+)\.(\d+)\.[^\\"]+\\"',
        PLATFORM.read_text(encoding="utf-8"),
    )
    require(failures, version_match is not None and
            (int(version_match.group(1)), int(version_match.group(2))) >= (0, 70),
            "current baseline predates accepted 0.70 reset matrix")
    if version_match is not None and (
            int(version_match.group(1)), int(version_match.group(2))) == (0, 70):
        for name, hash_key, size_key in (
            ("firmware.bin", "firmware_sha256", "app_image_bytes"),
            ("firmware.factory.bin", "factory_sha256", "factory_image_bytes"),
            ("firmware.elf", "app_elf_sha256", None),
            ("firmware.map", "map_sha256", None),
        ):
            artifact = BUILD / name
            require(failures, artifact.is_file(), f"build artifact missing: {name}")
            if artifact.is_file():
                require(failures, digest(artifact) == candidate.get(hash_key),
                        f"build hash mismatch: {name}")
                if size_key is not None:
                    require(failures, artifact.stat().st_size == candidate.get(size_key),
                            f"build size mismatch: {name}")

    physical = evidence.get("physical", {})
    run_path = ROOT / physical.get("run_path", "")
    require(failures, run_path.is_file(), "retained run missing")
    require(failures, RUNNER.is_file() and
            digest(RUNNER) == physical.get("runner_sha256"),
            "runner hash mismatch")
    if run_path.is_file():
        require(failures, digest(run_path) == physical.get("run_sha256"),
                "retained run hash mismatch")
    run = json.loads(run_path.read_text(encoding="utf-8")) \
        if run_path.is_file() else {}
    require(failures, exact(run, {
        "schema": "leshy.storage.littlefs_reset_matrix_hil.run.v1",
        "status": "pass", "passed": True, "gate_eligible": True,
        "failures": [], "run_id": physical.get("run_id"),
        "runner_source_sha256": physical.get("runner_sha256"),
        "expected_cid": physical.get("exact_cid"),
        "boundaries_requested": [1, 2, 3, 4, 5, 6],
        "boundaries_completed": 6,
    }), "physical run did not pass the ordered gate")
    require(failures, exact(run.get("candidate", {}), {
        "version": candidate.get("version"),
        "firmware_sha256": candidate.get("firmware_sha256"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "flashed": True,
    }), "run candidate mismatch")

    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifact manifest missing")
    retained: set[str] = set()
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected_sha, relative = line.split("  ", 1)
            retained.add(relative)
            artifact = BUNDLE / relative
            require(failures, artifact.is_file(), f"artifact missing: {relative}")
            if artifact.is_file():
                require(failures, digest(artifact) == expected_sha,
                        f"artifact hash mismatch: {relative}")
    require(failures, retained == {
        "boot-after.ndjson", "boot-before.ndjson", "run.json"
    }, "retained artifact set mismatch")
    for private_name in (
        "firmware.bin", "ota1-private-backup.bin",
        "ota1-private-backup-second-read.bin",
        "ota1-private-restore-readback.bin", "partition-table-before.bin",
        "partition-table-after.bin", "ota1-current-private-read.bin",
    ):
        require(failures, not (BUNDLE / private_name).exists(),
                f"private/large artifact retained: {private_name}")

    target = run.get("disposable_target", {})
    require(failures, exact(target, {
        "kind": "inactive_ota1_littlefs", "offset": 0x410000,
        "size": 0x400000, "two_read_backup_verified": True,
        "before_sha256": physical.get("ota1_before_sha256"),
        "second_read_sha256": physical.get("ota1_before_sha256"),
        "restore_attempted": True, "restore_write_attempts": 1,
        "restore_write_attempt_limit": 1, "restore_read_attempts": 1,
        "restore_read_attempt_limit": 6,
        "after_sha256": physical.get("ota1_after_sha256"),
        "restore_verified": True,
        "private_backup_deleted_after_verified_restore": True,
        "partition_table_before_sha256":
            physical.get("partition_table_before_sha256"),
        "partition_table_after_sha256":
            physical.get("partition_table_after_sha256"),
        "partition_table_unchanged": True,
    }), "disposable target backup/restore mismatch")

    expected_names = physical.get("boundary_names")
    expected_generations = physical.get("recovered_generations")
    runs = run.get("runs", [])
    require(failures, len(runs) == 6, "six boundary results required")
    fingerprints: set[str] = set()
    for index, boundary_run in enumerate(runs):
        boundary = index + 1
        armed = boundary_run.get("armed", {})
        recovery = boundary_run.get("recovery", {})
        fingerprint = boundary_run.get("target_fingerprint_before")
        fingerprints.add(fingerprint)
        require(failures, exact(boundary_run, {
            "boundary": boundary, "valid": True, "failures": [],
        }), f"boundary {boundary} wrapper mismatch")
        require(failures, exact(armed, {
            "status": "ready", "boundary": boundary,
            "boundary_name": expected_names[index],
            "expected_fingerprint": fingerprint,
            "observed_fingerprint": fingerprint,
            "fingerprint_matched": True, "target": "ota1",
            "target_address": 0x410000, "target_size": 0x400000,
            "target_inactive": True, "initial_generation": 1,
            "initial_observations": 3, "continuity_armed": True,
            "format_performed": True, "writes_bounded_to_scratch": True,
            "product_partition_touched": False, "nvs_touched": False,
            "sd_accessed": False, "radio_touched": False,
            "reset_injection": True, "physical_power_cut": False,
        }), f"boundary {boundary} arm mismatch")
        require(failures, exact(recovery, {
            "mode": "recovery", "status": "valid", "boundary": boundary,
            "boundary_name": expected_names[index], "software_reset": True,
            "continuity_valid": True, "target_inactive": True,
            "read_permit_status": "permitted", "mounted_read_only": True,
            "opened_read_only": True, "session_store_io_writable": False,
            "recovered_generation": expected_generations[index],
            "reopened_observations": 3, "generation_allowed": True,
            "prior_unchanged": True,
            "prior_segment_crc32c": physical.get("prior_segment_crc32c"),
            "prior_manifest_crc32c": physical.get("prior_manifest_crc32c"),
            "bytes_written": 0, "file_syncs": 0, "directory_syncs": 0,
            "owned_after": 0, "cleanup_complete": True,
            "mount_on_boot": False, "format_allowed": False,
            "existing_paths_deleted": False,
            "product_partition_touched": False, "nvs_touched": False,
            "sd_accessed": False, "radio_touched": False,
            "reset_injection": True, "physical_power_cut": False,
        }), f"boundary {boundary} recovery mismatch")
    require(failures, len(fingerprints) == 6,
            "each boundary must bind the current full-target fingerprint")

    for label, suffix in (("boot_before", "before"), ("boot_after", "after")):
        ready = run.get(label, {}).get("ready", {})
        recovery = run.get(label, {}).get("recovery", {})
        require(failures, exact(ready, {
            "version": candidate.get("version"),
            "app_elf_sha256": candidate.get("app_elf_sha256"),
            "buzzer_inactive": True, "legacy_sources": False,
            "heap_total": physical.get(f"heap_total_{suffix}"),
            "heap_free": physical.get(f"heap_free_{suffix}"),
            "heap_min_free": physical.get(f"heap_min_{suffix}"),
        }), f"boot identity/heap mismatch: {label}")
        require(failures, exact(recovery, {
            "status": "admitted", "generation": 68, "observations": 25,
            "expected_fingerprint": physical.get("exact_cid"),
            "observed_fingerprint": physical.get("exact_cid"),
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "catalog_admitted": True,
            "physical_write_calls": 0, "cleanup_complete": True,
            "owned_after": 0,
            "attempts": physical.get(f"boot_recovery_attempts_{suffix}"),
            "transient_retries":
                physical.get(f"boot_transient_retries_{suffix}"),
        }), f"product recovery mismatch: {label}")
    cleanup = run.get("cleanup_final", {})
    require(failures, cleanup.get("complete") is True and
            cleanup.get("final_state", {}).get("page") == "home" and
            cleanup.get("final_state", {}).get("runtime_owner") == "none" and
            cleanup.get("final_state", {}).get("lease_mask") == 0,
            "final cleanup mismatch")

    entry = ENTRY.read_text(encoding="utf-8")
    arm_start = entry.find("void emitLittleFsResetArm(")
    recover_start = entry.find("void emitLittleFsResetRecovery(")
    arm_body = entry[arm_start:recover_start]
    recover_body = entry[recover_start:entry.find("void emit", recover_start + 10)]
    for marker in (
        "filesystem.hashTarget(", "filesystem.formatAndMountWritable()",
        "armLittleFsResetContinuity(", "SessionStoreBoundaryIo",
        "restartAtLittleFsSessionStoreBoundary",
    ):
        require(failures, marker in arm_body, f"arm safety marker missing: {marker}")
    require(failures, arm_body.find("filesystem.hashTarget(") <
            arm_body.find("filesystem.formatAndMountWritable()"),
            "full-target hash must precede format")
    for marker in (
        "ESP_RST_SW", "littleFsResetContinuityValid(",
        "filesystem.mountReadOnly()", "openExistingReadOnly(permit)",
        "bytesWritten == 0", "fileSyncs == 0",
        "directorySyncs == 0",
    ):
        require(failures, marker in recover_body,
                f"recovery safety marker missing: {marker}")
    for forbidden in (
        "BoardSd", "productSurveyFilesystem", "saveProductFingerprint",
        "clearProductFingerprint", "esp_wifi_",
    ):
        require(failures, forbidden not in arm_body + recover_body,
                f"unrelated subsystem reachable: {forbidden}")
    io_source = IO_ADAPTER.read_text(encoding="utf-8")
    require(failures, "const storage::ReadPermit& permit)" in
            io_source and "writable_ = false" in io_source,
            "read-permit LittleFS IO path missing")
    try:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
        ast.parse(RUNNER_TEST.read_text(encoding="utf-8"))
    except SyntaxError as error:
        failures.append(f"runner syntax error: {error}")
    runner_source = RUNNER.read_text(encoding="utf-8")
    require(failures, 'stats["write_attempts"] = 1' in runner_source and
            "restore_flash_single_write(" in runner_source,
            "single-write restore guard missing")

    for doc in DOCS:
        source = doc.read_text(encoding="utf-8")
        require(failures, "0.70" in source and "E-HIL-094" in source,
                f"documentation marker missing: {doc.name}")
    require(failures, evidence.get("storage_contract") == {
        "target": "inactive_ota1", "target_address": 0x410000,
        "target_size": 0x400000, "two_read_backup_verified": True,
        "six_ordered_boundaries_verified": True,
        "software_reset_continuity_verified": True,
        "read_only_recovery": True, "recovery_bytes_written": 0,
        "recovery_file_syncs": 0, "recovery_directory_syncs": 0,
        "restore_single_write": True, "restore_verified": True,
        "private_backup_deleted_after_verified_restore": True,
        "partition_table_unchanged": True,
        "product_partition_touched": False, "nvs_touched": False,
        "sd_accessed": False, "radio_touched": False,
        "format_implicit": False, "cleanup_complete": True,
        "final_lease_mask": 0,
    }, "storage contract mismatch")
    require(failures, evidence.get("scope") == {
        "st_hil_a07_littlefs_software_reset_matrix": "accepted",
        "physical_power_cut": "deferred_to_demo_s4", "s3": "in_progress",
        "remaining_s3": ["independent_demo_goldens", "reproducible_demo_s3"],
        "release_gate_eligible": False,
    }, "scope/promotion mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("LittleFS reset-matrix acceptance passed: 6/6 software resets, "
          "generations 1/1/1/1/1/2, zero recovery writes, exact restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
