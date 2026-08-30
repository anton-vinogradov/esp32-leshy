#!/usr/bin/env python3
"""Fail closed unless retained exact dev.270 BLE Inspector evidence is intact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ble_nearby_entry_gate import BLE_ENTRY_STABILITY_MINIMUM_MS
from retain_1x_ble_inspector_hil import (
    APP_ELF_SHA256,
    CID,
    EVIDENCE_IDS,
    FACTORY_SHA256,
    FIRMWARE_SHA256,
    MAP_SHA256,
    SOURCE_COMMIT,
    VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence" /
            "board-01-ble-inspector-1.0.0-dev.270.json")
REJECTED = (ROOT / "tests/hil/evidence" /
            "board-01-ble-inspector-1.0.0-dev.269-failed.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    rejected = json.loads(REJECTED.read_text(encoding="utf-8"))
    exact(rejected, {
        "schema": "leshy.ble_inspector_hil.rejected.v1",
        "status": "failed_ble_entry_bounced_home",
        "board": "board-01",
        "exact_cid": CID,
    }, "rejected")
    exact(rejected.get("candidate", {}), {
        "version": "1.0.0-dev.269",
        "source_commit": "ee5d41e2c7a6680b9a2d718fb1783e147e3912d4",
        "firmware_sha256":
            "872713b9ea1e8aeed1c3d642326e1ad93d11d74f3298c0207b43869a0927caea",
        "app_elf_sha256":
            "4ae9af54a1e434f4e05bc87ef1dee69106cf799a62d6370bfa9ed47f450c88fb",
    }, "rejected.candidate")
    exact(rejected.get("observed", {}), {
        "preflight_before_flash": True,
        "single_application_flash": True,
        "live_ble_reached": False,
        "route_bounced_home": True,
        "gate_eligible": False,
        "cleanup_complete": True,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
    }, "rejected.observed")
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact(value, {
        "schema": "leshy.ble_inspector_hil.acceptance.v1",
        "status": "pass_ble_inspector_receive_capture",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
    }, "acceptance")
    exact(value.get("candidate", {}), {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "factory_sha256": FACTORY_SHA256,
        "map_sha256": MAP_SHA256,
    }, "candidate")
    verified = value.get("verified", {})
    exact(verified, {
        "preflight_before_flash": True,
        "single_application_flash": True,
        "ble_begin_stage": "ready",
        "ble_begin_error": 0,
        "selected_target_stable": True,
        "content_clears": 1,
        "atomic_row_allocation_failures": 0,
        "direct_row_fallbacks": 0,
        "invalid_records": 0,
        "dropped_records": 0,
        "gatt_started": False,
        "passive_only": True,
        "receive_only": True,
        "export_complete": True,
        "input_read_errors": 0,
        "input_queue_drops": 0,
        "buzzer_inactive": True,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
        "final_safety_state": "armed",
    }, "verified")
    require(int(verified.get("entry_stability_ms", 0)) >=
            BLE_ENTRY_STABILITY_MINIMUM_MS,
            "full bounded BLE entry stability is unproven")
    require(int(verified.get("entry_stability_samples", 0)) >= 2 and
            int(verified.get("entry_scan_cycles", 0)) >= 1,
            "live BLE observations are unproven")
    records = int(verified.get("records", 0))
    require(1 <= records <= 32 and
            0 < int(verified.get("payload_bytes", 0)) <= records * 31 and
            int(verified.get("atomic_row_pushes", 0)) > 0,
            "bounded selected-packet capture is unproven")
    privacy = value.get("privacy", {})
    exact(privacy, {
        "raw_ble_addresses_retained": False,
        "raw_payload_retained": False,
        "screenshots_retained": False,
        "screenshot_hashes_retained": True,
    }, "privacy")
    scope = value.get("scope", {})
    exact(scope, {
        "single_flash": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "passive_ble_only": True,
        "selected_target_only": True,
        "incremental_rows_only": True,
        "raw_export_checked_in_memory": True,
        "raw_private_evidence_retained": False,
        "mac_wifi_touched": False,
        "clone_touched": False,
        "cardputer_touched": False,
    }, "scope")
    evidence = value.get("evidence", {})
    for key in ("run_id", "raw_run_sha256", "raw_artifact_index_sha256",
                "runner_sha256", "checker_sha256", "source_guard_sha256"):
        require(isinstance(evidence.get(key), str) and evidence.get(key),
                f"evidence.{key} missing")
    screens = evidence.get("screenshots", {})
    require(set(screens) == {
        "running_first", "running_second", "frozen", "home_after"},
        "screenshot hash set mismatch")
    print("BLE Inspector physical acceptance passed: exact dev.270, bounded "
          "entry, selected passive packets, incremental TFT and clean Home")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
