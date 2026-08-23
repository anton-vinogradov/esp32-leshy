#!/usr/bin/env python3
"""Verify retained board-01 Bluetooth device-intelligence evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-ble-device-intelligence-0.122"
SUMMARY = ROOT / "tests/hil/evidence/board-01-ble-device-intelligence-0.122.json"
VERSION = "0.122.2-ble-device-intelligence"
FAILED_VERSION = "0.122.1-ble-device-intelligence"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "bdc6258c8498b285a17888e81feea8b4ed2de02d"
FAILED_SOURCE_COMMIT = "55045b8cabf063d3c33cc95313d2ced072acec4f"
FIRMWARE_SHA256 = "d8e62726c4ffa9857cb36b4fc5e757e9d27431b7971375cf1ab6bdbf103effad"
FAILED_FIRMWARE_SHA256 = "31b812d22b371c8f88dc6b87d4a779259f1dac9480510fe90f1ed6b3e8699d96"
FACTORY_SHA256 = "fcdd63229cbbf320a353847ae47e34a231d37edc9d6a9dc6b2a43c215b39e680"
ELF_SHA256 = "a59047cd8f52b4cac9f1a3ffa1a413c9e9e430382e180585f7cba6613378f088"
FAILED_ELF_SHA256 = "3b5979e652cc17ee415900b95036d8efeae6e7e8da76700cc5c8c76a4c03f6d3"
MAP_SHA256 = "679b0aeca6bb13714e92d035e7a27e2aaff7f55de11e3b4bf52201991ea29786"
EVIDENCE_IDS = {"E-BUILD-122", "E-AUTO-086", "E-HIL-146", "E-UX-041"}
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    indexed_present: set[Path] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        artifact = root / relative
        if not artifact.is_file():
            require(relative.endswith(OPAQUE_SUFFIXES),
                    f"tracked artifact missing: {relative}")
            continue
        require(digest(artifact) == expected,
                f"artifact hash mismatch: {relative}")
        indexed_present.add(Path(relative))
    present = {
        path.relative_to(root) for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed_present == present, "artifact index coverage mismatch")


def verify_source(provenance: dict[str, Any]) -> None:
    source = BUNDLE / "source"
    files = {
        "renderer": source / "ArduinoEntry.cpp",
        "observation": source / "Observation.h",
        "passive_h": source / "BlePassiveContract.h",
        "passive_cpp": source / "BlePassiveContract.cpp",
        "adapter": source / "BoardBlePassiveScanner.cpp",
        "adapter_h": source / "BoardBlePassiveScanner.h",
        "catalog_h": source / "BleDeviceCatalog.h",
        "catalog_cpp": source / "BleDeviceCatalog.cpp",
        "navigation": source / "BleDeviceNavigationOrder.h",
        "intelligence_h": source / "BleDeviceIntelligence.h",
        "intelligence_cpp": source / "BleDeviceIntelligence.cpp",
        "company_h": source / "BleCompanyDatabase.h",
        "company_cpp": source / "BleCompanyDatabase.cpp",
        "company_metadata": source / "bluetooth_companies.json",
        "strings": source / "UiStrings.def",
        "platform": source / "platformio.ini",
        "native_tests": source / "clean_target_tests.cpp",
        "contract": source / "check_ble_nearby_contract.py",
        "generator": source / "make_ble_company_asset.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")

    renderer = files["renderer"].read_text(encoding="utf-8")
    adapter = files["adapter"].read_text(encoding="utf-8")
    catalog = files["catalog_cpp"].read_text(encoding="utf-8")
    navigation = files["navigation"].read_text(encoding="utf-8")
    company = files["company_cpp"].read_text(encoding="utf-8")
    for token in (
            "renderBleDeviceRadar(live, signal)",
            "bleCompanyDatabase.lookup(",
            "emitBleDeviceDetailState(",
            "ble_device_detail",
    ):
        require(token in renderer, f"renderer contract missing: {token}")
    for token in ("setActiveScan(false)", "setDuplicateFilter(true)",
                  "kMaximumScanAttempts = 2U", "result.transientRetries"):
        require(token in adapter, f"passive/retry contract missing: {token}")
    for token in ("setActiveScan(true)", "startAdvertising", "BLEAdvertising"):
        require(token not in adapter, f"active/TX adapter path found: {token}")
    require("sortStrongestFirst" in catalog and
            "entries_[position - 1U].rssiDbm < current.rssiDbm" in catalog,
            "strongest-first catalog source missing")
    require("class BleDeviceNavigationOrder final" in navigation and
            "catalog.indexOfIdentity(identity)" in navigation,
            "identity-stable navigation source missing")
    require("BleCompanyDatabase::lookup" in company and
            "while (low < high)" in company,
            "offline company database source missing")


def verify_negative_run(summary: dict[str, Any], provenance: dict[str, Any]) -> None:
    negative_dir = BUNDLE / "negative"
    run_file = negative_dir / "run.json"
    manifest = negative_dir / "artifacts.sha256"
    negative = load(run_file)
    candidate = negative.get("candidate", {})
    final = negative.get("cleanup_after", {}).get("final_state", {})
    retained = summary.get("retained_failure", {})
    require(negative.get("schema") == "leshy.ble_nearby_hil.run.v2" and
            negative.get("passed") is False and
            negative.get("gate_eligible") is False and
            len(negative.get("failures", [])) == 1,
            "retained negative run status mismatch")
    require(candidate.get("version") == FAILED_VERSION and
            candidate.get("source_commit") == FAILED_SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FAILED_FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == FAILED_ELF_SHA256 and
            candidate.get("flashed") is True and
            candidate.get("flash_mode") == "fresh",
            "retained negative candidate mismatch")
    require(negative.get("expected_cid") == CID and
            negative.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "negative run did not fail closed")
    require(retained.get("status") == "failed" and
            retained.get("gate_eligible") is False and
            retained.get("failure_stage") == "before_first_valid_ble_scan" and
            retained.get("failure_count") == 1 and
            retained.get("final_cleanup_complete") is True and
            retained.get("final_lease_mask") == 0 and
            retained.get("run_sha256") == digest(run_file) ==
                provenance.get("negative_run_sha256") and
            retained.get("artifact_index_sha256") == digest(manifest) ==
                provenance.get("negative_artifact_index_sha256"),
            "negative-run summary/provenance mismatch")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.ble_device_intelligence.acceptance.v1" and
            summary.get("status") == "pass_ble_device_intelligence",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest) and
            summary.get("evidence", {}).get("files") == 48 and
            summary.get("evidence", {}).get("tft_states") == 5,
            "evidence inventory mismatch")
    require(provenance.get("schema") ==
            "leshy.ble_device_intelligence_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == SOURCE_COMMIT,
            "candidate provenance mismatch")
    require(provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("app_image_bytes") == 3050096 and
            provenance.get("factory_image_bytes") == 3115632 and
            provenance.get("static_ram_bytes") == 228688 and
            provenance.get("linked_flash_bytes") == 3049684 and
            provenance.get("tft_states") == 5,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)
    verify_negative_run(summary, provenance)

    run_dir = BUNDLE / "run"
    run = load(run_dir / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.ble_nearby_hil.run.v2" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID,
            "positive run status mismatch")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == ELF_SHA256 and
            candidate.get("flashed") is True and
            candidate.get("flash_mode") == "fresh",
            "exact fresh-flash binding mismatch")
    require(digest(run_dir / "run.json") == provenance.get("run_sha256"),
            "positive run hash mismatch")
    runner = BUNDLE / "tools/run_1x_ble_nearby_hil.py"
    checker = BUNDLE / "tools/check_ble_nearby_run.py"
    source_guard = BUNDLE / "tools/check_ble_nearby_contract.py"
    require(digest(runner) == provenance.get("runner_sha256") ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance.get("checker_sha256"),
            "checker hash mismatch")
    require(digest(source_guard) == provenance.get("source_guard_sha256"),
            "source-guard hash mismatch")
    firmware = run_dir / "firmware.bin"
    if firmware.is_file():
        checked = subprocess.run(
            [sys.executable, str(checker), "--run", str(run_dir),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        require(checked.returncode == 0,
                f"independent retained run check failed: {checked.stdout}")

    verified = summary.get("verified", {})
    require(verified == {
        "active_probe_allowed": False,
        "active_scan": False,
        "advertisement_payload_bytes": 17,
        "buzzer_inactive": True,
        "company_database_records": 4012,
        "detail_chrome_changed_pixels": 0,
        "detail_static_changed_pixels": 0,
        "driver_scan_drops": 0,
        "final_lease_mask": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "fresh_flash_pass": True,
        "heap_free_bytes": 82248,
        "heap_min_free_bytes": 9760,
        "heap_total_bytes": 152764,
        "identity_stable": True,
        "live_chrome_changed_pixels": 0,
        "live_content_changed_pixels": 111,
        "manual_button_presses": 0,
        "passive_receive_only": True,
        "persistent_generation_unchanged": True,
        "physical_sd_write_calls": 0,
        "radar_changed_pixels": 3234,
        "scan_attempts_first": 1,
        "scan_attempts_second": 2,
        "scan_transient_retries_first": 0,
        "scan_transient_retries_second": 0,
        "service": "",
        "signal_samples_first": 2,
        "signal_samples_second": 3,
        "tracker": "none",
        "two_complete_ble_lifecycles": True,
        "unique_devices_first": 31,
        "unique_devices_second": 32,
        "vendor_known": True,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Bluetooth device-intelligence acceptance passed: 4,012 company "
        "records, passive facts, strongest-first list, identity-stable live "
        "radar, retained fail-closed precursor and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
