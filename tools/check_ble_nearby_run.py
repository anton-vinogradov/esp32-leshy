#!/usr/bin/env python3
"""Independent fail-closed verifier for a Bluetooth Nearby HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ble_nearby_entry_gate import ble_entry_stability_evidence_failure
from ble_nearby_run_policy import (
    boot_recovery_continuity,
    bounded_pipeline_accounting_valid,
    display_signal_signature,
    storage_measurement_scope_valid,
)
from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.ble_nearby_hil.run.v2"
SCREENS = {
    "ble_devices_first": "ble-devices-first",
    "ble_devices_second": "ble-devices-second",
    "ble_detail_first": "ble-detail-first",
    "ble_detail_second": "ble-detail-second",
    "home_after": "ble-home-after",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def fact_signature(state: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(state.get(field) for field in (
        "identity_hash", "label_known", "vendor_known", "vendor",
        "company_known", "company_id", "device_kind", "subtype", "tracker",
        "address_type", "advertisement_type", "legacy", "scannable",
        "connectable", "tx_power_known", "tx_power_dbm",
        "appearance_known", "appearance", "service", "known_service_mask",
        "service_uuid_hash",
        "service_uuid_count", "service_data_count",
        "manufacturer_data_length", "payload_length"))


def verify_manifest(failures: list[str], root: Path) -> None:
    manifest = root / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifacts.sha256 missing")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"invalid manifest line: {line!r}")
            continue
        expected, relative = parts
        target = root / relative
        indexed.add(relative)
        require(failures, target.is_file(), f"indexed artifact missing: {relative}")
        if target.is_file():
            require(failures, digest(target) == expected,
                    f"artifact hash mismatch: {relative}")
    actual = {
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, indexed == actual, "manifest coverage mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    failures: list[str] = []
    run_file = root / "run.json"
    require(failures, run_file.is_file(), "run.json missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    run: dict[str, Any] = json.loads(run_file.read_text(encoding="utf-8"))
    require(failures, run.get("schema") == SCHEMA, "run schema mismatch")
    require(failures, run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "run is not a clean pass")
    candidate = run.get("candidate", {})
    firmware = root / "firmware.bin"
    require(failures, candidate.get("version") == args.expected_version,
            "candidate version mismatch")
    require(failures, candidate.get("source_commit") == args.source_commit,
            "candidate source commit mismatch")
    require(failures, candidate.get("flashed") is True and
            candidate.get("flash_mode") in ("fresh", "reuse_exact"),
            "physical exact-flash binding missing")
    require(failures, run.get("expected_cid") == args.expected_cid,
            "CID mismatch")
    require(failures, firmware.is_file(), "candidate firmware missing")
    if firmware.is_file():
        require(failures, candidate.get("firmware_sha256") == digest(firmware),
                "firmware hash mismatch")
        require(failures,
                candidate.get("app_elf_sha256") == app_elf_sha256(firmware),
                "embedded app identity mismatch")

    first = run.get("live_first", {})
    second = run.get("live_second", {})
    entry_stability = run.get("entry_stability", {})
    require(failures,
            isinstance(entry_stability, dict) and
            ble_entry_stability_evidence_failure(entry_stability) is None,
            "delayed BLE entry lifecycle was not stable")
    require(failures,
            first.get("ble_product_view") == "devices" and
            first.get("survey_product_status") == "running" and
            first.get("survey_product_active_source_mask") == 2 and
            first.get("ble_devices_strongest_first") is True and
            isinstance(first.get("ble_devices_unique"), int) and
            first.get("ble_devices_unique", 0) >= 1 and
            first.get("survey_ble_scan_status") == "valid" and
            first.get("survey_ble_scan_accepted") ==
                first.get("survey_ble_scan_read") and
            first.get("survey_ble_scan_dropped") == 0 and
            bounded_pipeline_accounting_valid(first) and
            isinstance(
                first.get("survey_product_store_bytes_written"), int) and
            not isinstance(
                first.get("survey_product_store_bytes_written"), bool) and
            first.get("survey_product_store_bytes_written") >= 0,
            "first live BLE scan mismatch")
    require(failures,
            first.get("ble_begin_stage") in ("ready", "reused_ready") and
            first.get("ble_begin_error") == 0 and
            first.get("ble_begin_heap_free_before", 0) > 0 and
            first.get("ble_begin_heap_free_after", 0) > 0 and
            first.get("ble_begin_heap_largest_before", 0) > 0 and
            first.get("ble_begin_heap_largest_after", 0) > 0,
            "BLE begin stage/error/heap evidence missing")
    require(failures,
            second.get("survey_product_ble_scan_cycles", 0) >
                first.get("survey_product_ble_scan_cycles", 0) and
            second.get("ble_devices_strongest_first") is True and
            second.get("ble_device_catalog_revision", 0) >
                first.get("ble_device_catalog_revision", 0) and
            second.get("survey_ble_scan_dropped") == 0 and
            bounded_pipeline_accounting_valid(second),
            "live BLE catalog did not advance")
    for label, state in (("first", first), ("second", second)):
        cycles = state.get("survey_product_ble_scan_cycles")
        attempts = state.get("survey_ble_scan_attempts")
        retries = state.get("survey_ble_scan_transient_retries")
        require(failures,
                isinstance(cycles, int) and isinstance(attempts, int) and
                isinstance(retries, int) and
                cycles <= attempts <= cycles * 2 and
                retries == attempts - cycles,
                f"{label} bounded BLE retry accounting mismatch")
    list_changes = run.get("list_pixel_changes", {})
    list_render_first = run.get("list_render_first", {})
    list_render_second = run.get("list_render_second", {})
    row_repaint_delta = list_render_second.get("list_row_repaints", -1) - \
        list_render_first.get("list_row_repaints", -1)
    content_changed = list_changes.get("content_changed_pixels", -1)
    bounded_rows = (content_changed == 0 and row_repaint_delta == 0) or \
        (content_changed > 0 and 1 <= row_repaint_delta <= 4)
    require(failures,
            list_changes.get("chrome_changed_pixels") == 0 and
            bounded_rows and
            list_render_second.get("list_content_clears") ==
                list_render_first.get("list_content_clears"),
            "BLE list final pixels/counters show a full or unbounded repaint")
    detail_changes = run.get("detail_pixel_changes", {})
    require(failures,
            detail_changes.get("radar_changed_pixels", 0) > 0 and
            detail_changes.get("static_changed_pixels") == 0 and
            detail_changes.get("chrome_changed_pixels") == 0,
            "BLE live redraw escaped the integrated radar")
    detail_first = run.get("detail_oracle_first", {})
    detail_second = run.get("detail_oracle_second", {})
    require(failures,
            detail_first.get("active") is True and
            detail_first.get("passive") is True and
            detail_first.get("active_probe_allowed") is False and
            detail_first.get("facts_known") is True and
            detail_first.get("company_database_available") is True and
            detail_first.get("company_database_records") == 4012 and
            detail_first.get("payload_length", 0) > 0 and
            detail_first.get("signal_samples", 0) >= 1,
            "BLE passive advertisement intelligence missing")
    require(failures,
            detail_second.get("identity_hash") ==
                detail_first.get("identity_hash") and
            fact_signature(detail_second) == fact_signature(detail_first) and
            display_signal_signature(detail_second) !=
                display_signal_signature(detail_first),
            "BLE detail was not identity-stable with a live signal update")
    require(failures,
            detail_second.get("detail_content_clears") ==
                detail_first.get("detail_content_clears") and
            detail_second.get("radar_full_repaints") ==
                detail_first.get("radar_full_repaints") and
            detail_second.get("radar_delta_repaints", -1) >
                detail_first.get("radar_delta_repaints", -1),
            "BLE detail repaint counters show a full content clear")

    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    scope = run.get("scope", {})
    require(failures,
            first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free") and
            scope.get("two_complete_ble_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "BLE heap plateau changed")
    require(failures,
            scope.get("manual_button_presses") == 0 and
            scope.get("delayed_entry_stability_gate") is True and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_ble_only") is True and
            scope.get("active_scan") is False and
            scope.get("detail_live_radar_only") is True and
            scope.get("intermediate_clear_counters_checked") is True and
            scope.get("advertisement_facts_visible") is True and
            scope.get("offline_company_database") is True and
            storage_measurement_scope_valid(scope),
            "automation/passive/measurement scope mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures,
            boot_recovery_continuity(before, after) and
            scope.get("boot_recovery_continuity") is True,
            "boot-recovery continuity mismatch")
    require(failures,
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("input", {}).get("read_errors") == 0,
            "input frontend mismatch")
    require(failures, run.get("safe_outputs", {}).get("buzzer_inactive") is True,
            "buzzer safe state mismatch")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures,
            run.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("ble_product_view") == "none",
            "final cleanup/lease mismatch")
    require(failures, set(run.get("screens", {})) == set(SCREENS),
            "screen inventory mismatch")
    for key, name in SCREENS.items():
        screen = run.get("screens", {}).get(key, {})
        for suffix, hash_key in (("png", "png_sha256"),
                                 ("rgb565", "rgb565_sha256")):
            path = root / "frames" / f"{name}.{suffix}"
            require(failures, path.is_file(), f"{name}.{suffix} missing")
            if path.is_file():
                require(failures, screen.get(hash_key) == digest(path),
                        f"{name}.{suffix} hash mismatch")
    verify_manifest(failures, root)
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": args.expected_version,
        "unique_devices": second.get("ble_devices_unique"),
        "list_chrome_changed_pixels": 0,
        "radar_changed_pixels": detail_changes.get("radar_changed_pixels"),
        "detail_static_changed_pixels": 0, "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
