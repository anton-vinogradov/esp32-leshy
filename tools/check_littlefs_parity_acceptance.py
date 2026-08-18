#!/usr/bin/env python3
"""Fail closed unless exact 0.69 disposable LittleFS parity evidence passes."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-littlefs-parity-0.69.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-littlefs-parity-0.69"
RUNNER = ROOT / "tools/run_1x_littlefs_parity_hil.py"
RUNNER_TEST = ROOT / "tools/test_littlefs_parity_hil_runner.py"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
PARTITION_ADAPTER = (
    ROOT / "firmware/leshy1/src/platform/arduino/DisposableOtaLittleFs.cpp"
)
IO_ADAPTER = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoLittleFsSessionStoreIo.cpp"
)
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
        "schema": "leshy.storage.littlefs_parity_acceptance.v1",
        "status": "pass", "gate_eligible": False,
    }), "acceptance status mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-070", "E-AUTO-033", "E-HIL-093", "E-STORAGE-024"
    ], "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.69.0-littlefs-parity-measure",
        "firmware_sha256":
            "96e26161da3c696dedf4def4f2d9c14c02c00647e3aa11e823a1509eaadecd49",
        "factory_sha256":
            "04ca1d800b90d34caa8faa3acc91dcf1661e1a00de0007ec2fdce662a4ffe267",
        "app_elf_sha256":
            "1a8225efcf307b1c0082195a94573844509a12e6eda87ef6fbd15902617260d6",
        "map_sha256":
            "e85a45092d15f737906b3babed1f7501e5d148bfcb84ba044d893d077d43a466",
        "linked_flash_bytes": 1153228, "static_ram_bytes": 130216,
        "app_image_bytes": 1153632, "factory_image_bytes": 1219168,
        "rtc_noinit_bytes": 20, "host_tests_passed": True,
        "firmware_build_passed": True, "reproducible_rebuild": True,
    }, "exact candidate mismatch")
    for name, key, size_key in (
        ("firmware.bin", "firmware_sha256", "app_image_bytes"),
        ("firmware.factory.bin", "factory_sha256", "factory_image_bytes"),
        ("firmware.elf", "app_elf_sha256", None),
        ("firmware.map", "map_sha256", None),
    ):
        path = BUILD / name
        require(failures, path.is_file(), f"build artifact missing: {name}")
        if path.is_file():
            require(failures, digest(path) == candidate.get(key),
                    f"build hash mismatch: {name}")
            if size_key is not None:
                require(failures, path.stat().st_size == candidate.get(size_key),
                        f"build size mismatch: {name}")

    physical = evidence.get("physical", {})
    run_path = ROOT / physical.get("run_path", "")
    require(failures, run_path.is_file(), "retained run missing")
    if run_path.is_file():
        require(failures, digest(run_path) == physical.get("run_sha256"),
                "retained run hash mismatch")
    require(failures, RUNNER.is_file() and
            digest(RUNNER) == physical.get("runner_sha256"),
            "runner hash mismatch")
    run = json.loads(run_path.read_text(encoding="utf-8")) \
        if run_path.is_file() else {}
    require(failures, exact(run, {
        "schema": "leshy.storage.littlefs_parity_hil.run.v1",
        "passed": True, "gate_eligible": True, "failures": [],
        "run_id": physical.get("run_id"),
        "runner_source_sha256": physical.get("runner_sha256"),
        "expected_cid": physical.get("exact_cid"),
    }), "physical run did not pass")
    require(failures, exact(run.get("candidate", {}), {
        "firmware_sha256": candidate.get("firmware_sha256"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "version": candidate.get("version"), "flashed": True,
    }), "run candidate mismatch")

    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifact manifest missing")
    retained_names: set[str] = set()
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected_sha, relative = line.split("  ", 1)
            retained_names.add(relative)
            path = BUNDLE / relative
            require(failures, path.is_file(), f"artifact missing: {relative}")
            if path.is_file():
                require(failures, digest(path) == expected_sha,
                        f"artifact hash mismatch: {relative}")
    require(failures, retained_names == {
        "boot-after.ndjson", "boot-before.ndjson", "run.json"
    }, "retained artifact set mismatch")
    for private_name in (
        "firmware.bin", "ota1-private-backup.bin",
        "ota1-private-backup-second-read.bin",
        "ota1-private-restore-readback.bin",
        "partition-table-before.bin", "partition-table-after.bin",
    ):
        require(failures, not (BUNDLE / private_name).exists(),
                f"private/large artifact retained: {private_name}")

    target = run.get("disposable_target", {})
    require(failures, exact(target, {
        "kind": "inactive_ota1_littlefs", "offset": 0x410000,
        "size": 0x400000, "two_read_backup_verified": True,
        "before_sha256": physical.get("ota1_before_sha256"),
        "second_read_sha256": physical.get("ota1_before_sha256"),
        "backup_read_attempts": 1, "second_read_attempts": 1,
        "read_attempt_limit": 3, "restore_attempted": True,
        "restore_attempts": 1, "restore_attempt_limit": 3,
        "after_sha256": physical.get("ota1_after_sha256"),
        "restore_verified": True,
        "private_backup_deleted_after_verified_restore": True,
        "partition_table_before_sha256":
            physical.get("partition_table_before_sha256"),
        "partition_table_after_sha256":
            physical.get("partition_table_after_sha256"),
        "partition_table_before_read_attempts": 1,
        "partition_table_after_read_attempts": 1,
        "partition_table_unchanged": True,
    }), "disposable target backup/restore mismatch")

    parity = run.get("parity", {})
    require(failures, exact(parity, {
        "schema": "leshy.storage.littlefs.parity.v1", "kind": "result",
        "status": "valid", "explicitly_disposable": True,
        "target": "ota1", "target_address": 0x410000,
        "target_size": 0x400000, "running_address": 0x10000,
        "boot_address": 0x10000, "target_inactive": True,
        "fingerprint_matched": True,
        "host_backup_fingerprint_confirmed": True,
        "format_allowed": True, "format_performed": True,
        "mounted_writable": True, "remounted_read_only": True,
        "reopened_read_only": True, "permit_status": "permitted",
        "scratch_preexisting_after_format": False,
        "commit_samples_requested": 32, "commit_samples_completed": 32,
        "file_syncs": 96, "directory_syncs": 96,
        "file_sync_covers_directory": True, "fixture_observations": 64,
        "pre_remount_status": "valid", "pre_remount_generation": 32,
        "post_remount_status": "valid", "post_remount_generation": 32,
        "post_remount_observations": 64,
        "encoded_payload_bytes_per_second": 18586,
        "required_encoded_bytes_per_second": 2184,
        "storage_rate_target_met": True, "io_failure": "none",
        "io_errno": 0, "owned_during": 4, "owned_after": 0,
        "cleanup_complete": True, "product_partition_touched": False,
        "partition_table_modified": False, "nvs_touched": False,
        "sd_accessed": False, "radio_touched": False,
        "reset_injection": False, "physical_power_cut": False,
    }), "LittleFS parity contract mismatch")
    require(failures,
            parity.get("expected_fingerprint") ==
                physical.get("ota1_before_sha256") and
            parity.get("observed_fingerprint") ==
                physical.get("ota1_before_sha256") and
            parity.get("run_id") == physical.get("run_id"),
            "target identity/run binding mismatch")
    for field in (
        "commit_min_us", "commit_p50_us", "commit_p95_us",
        "commit_p99_us", "commit_max_us", "bytes_written", "free_before",
        "free_after", "heap_free_before", "heap_free_after", "heap_min_free",
    ):
        require(failures, parity.get(field) == physical.get(field),
                f"physical metric mismatch: {field}")

    for label in ("boot_before", "boot_after"):
        ready = run.get(label, {}).get("ready", {})
        recovery = run.get(label, {}).get("recovery", {})
        suffix = "before" if label.endswith("before") else "after"
        require(failures, exact(ready, {
            "version": candidate.get("version"),
            "app_elf_sha256": candidate.get("app_elf_sha256"),
            "buzzer_inactive": True, "legacy_sources": False,
        }), f"boot identity mismatch: {label}")
        require(failures, exact(recovery, {
            "status": "admitted", "generation": 68, "observations": 25,
            "expected_fingerprint": physical.get("exact_cid"),
            "observed_fingerprint": physical.get("exact_cid"),
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "catalog_admitted": True,
            "blocked_write_attempts": 0, "physical_write_calls": 0,
            "cleanup_complete": True, "owned_after": 0,
            "attempts": physical.get(f"boot_recovery_attempts_{suffix}"),
            "transient_retries":
                physical.get(f"boot_transient_retries_{suffix}"),
        }), f"product recovery mismatch: {label}")
    for cleanup in ("cleanup_before_restore", "cleanup_final"):
        state = run.get(cleanup, {})
        require(failures,
                state.get("complete") is True and
                state.get("final_state", {}).get("page") == "home" and
                state.get("final_state", {}).get("runtime_owner") == "none" and
                state.get("final_state", {}).get("lease_mask") == 0,
                f"cleanup mismatch: {cleanup}")

    partition_source = PARTITION_ADAPTER.read_text(encoding="utf-8")
    partition_source += PARTITION_ADAPTER.with_suffix(".h").read_text(
        encoding="utf-8"
    )
    for marker in (
        "kExpectedAddress = 0x410000", "kExpectedSize = 0x400000",
        'kPartitionLabel = "app1"', "ESP_PARTITION_SUBTYPE_APP_OTA_1",
        "esp_ota_get_running_partition", "esp_ota_get_boot_partition",
        'ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "spiffs"',
        "config.partition = target_", "config.partition_label = nullptr",
        "config.format_if_mount_failed = false",
        "esp_littlefs_format_partition(target_)",
    ):
        require(failures, marker in partition_source,
                f"partition safety marker missing: {marker}")
    io_source = IO_ADAPTER.read_text(encoding="utf-8")
    for marker in (
        'kScratchParent = "/leshy-hil"', "storage::kScratchRoot",
        "bytesWritten_ > byteLimit_", "O_WRONLY | O_CREAT | O_TRUNC",
        "::fsync", "fileBarrierComplete_", "writable_ = false",
    ):
        require(failures, marker in io_source,
                f"IO safety marker missing: {marker}")
    entry = ENTRY.read_text(encoding="utf-8")
    littlefs_start = entry.find("void emitLittleFsParity(")
    littlefs_body = entry[littlefs_start:
                          entry.find("void broadcast(", littlefs_start)]
    require(failures,
            littlefs_body.find("filesystem.hashTarget(") >= 0 and
            littlefs_body.find("filesystem.formatAndMountWritable()") >
                littlefs_body.find("filesystem.hashTarget("),
            "hash-before-format ordering missing")
    for forbidden in (
        "BoardSd", "productSurveyFilesystem", "saveProductFingerprint",
        "clearProductFingerprint", "esp_wifi_",
    ):
        require(failures, forbidden not in littlefs_body,
                f"unrelated subsystem reachable: {forbidden}")
    require(failures,
            'LESHY1_VERSION=\\"0.69.0-littlefs-parity-measure\\"' in
                PLATFORM.read_text(encoding="utf-8"),
            "0.69 version marker missing")
    try:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
        ast.parse(RUNNER_TEST.read_text(encoding="utf-8"))
    except SyntaxError as error:
        failures.append(f"runner syntax error: {error}")
    for doc in DOCS:
        source = doc.read_text(encoding="utf-8")
        require(failures, "0.69" in source and "E-HIL-093" in source,
                f"documentation marker missing: {doc.name}")

    scope = evidence.get("scope", {})
    require(failures, scope == {
        "st_hil_a07_normal_throughput_parity": "accepted",
        "littlefs_reset_boundary_matrix": "open",
        "physical_power_cut": "open", "s3": "in_progress",
        "remaining": ["physical_power_cut", "littlefs_reset_boundary_matrix",
                      "independent_demo_goldens", "reproducible_demo_s3"],
        "release_gate_eligible": False,
    }, "scope/promotion mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("LittleFS parity acceptance passed: disposable OTA1 restored, "
          "32/32 commits, RO remount 32/64, 18,586 B/s, product 68/25 intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
