#!/usr/bin/env python3
"""Fail closed unless exact dev.276 BLE GATT negative evidence is intact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retain_1x_ble_gatt_negative_hil import (
    APP_ELF_SHA256,
    CID,
    EVIDENCE_IDS,
    FACTORY_SHA256,
    FIRMWARE_SHA256,
    FULL_INDEX_SHA256,
    FULL_RUN_SHA256,
    FRESH_INDEX_SHA256,
    FRESH_RUN_SHA256,
    FIXTURE_SHA256,
    MAP_SHA256,
    RUNNER_SHA256,
    SCREEN_SHA256,
    SOURCE_COMMIT,
    SOURCE_GUARD_SHA256,
    VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence" /
            "board-01-ble-gatt-negative-1.0.0-dev.276.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact(value, {
        "schema": "leshy.ble_gatt_negative_hil.acceptance.v1",
        "status": "pass_ble_gatt_fail_closed_matrix",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
    }, "acceptance")
    exact(value["candidate"], {
        "version": VERSION, "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flashed": False, "flash_mode": "reuse_exact",
    }, "candidate")
    exact(value["build"], {
        "static_ram_bytes": 230680, "linked_flash_bytes": 3480736,
        "firmware_bytes": 3480896, "factory_bytes": 3546432,
        "firmware_sha256": FIRMWARE_SHA256,
        "factory_sha256": FACTORY_SHA256,
        "app_elf_sha256": APP_ELF_SHA256, "map_sha256": MAP_SHA256,
        "ota_slot_free_bytes": 713408,
    }, "build")
    exact(value["evidence"], {
        "fresh_raw_run_sha256": FRESH_RUN_SHA256,
        "fresh_artifact_index_sha256": FRESH_INDEX_SHA256,
        "full_raw_run_sha256": FULL_RUN_SHA256,
        "full_artifact_index_sha256": FULL_INDEX_SHA256,
        "runner_sha256": RUNNER_SHA256,
        "source_guard_sha256": SOURCE_GUARD_SHA256,
        "fixture_executable_sha256": FIXTURE_SHA256,
        "screenshots": SCREEN_SHA256,
    }, "evidence")
    exact(value["verified"], {
        "fresh_application_flash": True,
        "full_matrix_exact_reuse": True,
        "fresh_boot_heap_total": 148124, "fresh_boot_heap_free": 74828,
        "reuse_heap_free": 73308,
        "scenario_order": ["wrong-peer", "timeout", "resource-conflict",
                           "failed-cleanup", "recovery-success"],
        "post_failure_services": 5, "post_failure_characteristics": 7,
        "heap_free_before": 73308, "heap_free_after_init": 1540,
        "heap_minimum": 1480, "passive_queue_capacity": 32,
        "passive_queue_high_water": 3, "passive_queue_drops": 0,
        "characteristic_reads": 0, "characteristic_writes": 0,
        "subscriptions": 0, "pairings": 0,
        "host_wifi_control_calls": 0, "final_page": "home",
        "final_runtime_owner": "none", "final_lease_mask": 0,
        "final_safety_state": "armed",
    }, "verified")
    expected_failures = [
        ("wrong-peer", "unexpected_peer", "unexpected_peer"),
        ("timeout", "timeout", "timeout"),
        ("resource-conflict", "resource_busy", "none"),
        ("failed-cleanup", "disconnect_failed", "none"),
    ]
    observed = value["verified"].get("failures", [])
    require(len(observed) == len(expected_failures),
            "negative failure summary count mismatch")
    for record, expected in zip(observed, expected_failures):
        exact(record, {
            "request": expected[0], "failure": expected[1],
            "cleanup_cause": expected[2], "cleanup_complete": True,
            "terminal_esp_rf_owner": 0, "terminal_page": "home",
            "terminal_lease_mask": 0,
        }, expected[0])
    exact(value["privacy"], {
        "raw_ble_addresses_retained": False,
        "raw_fixture_label_retained": False,
        "fixture_pid_retained": False,
        "screenshots_retained": False,
        "screenshot_hashes_retained": True,
        "selected_identity_hash_retained": False,
    }, "privacy")
    exact(value["scope"], {
        "run_mode": "all", "single_flash_or_exact_reuse": True,
        "manual_button_presses": 0, "screenshots_automatic": True,
        "enumeration_only": True, "characteristic_reads": 0,
        "characteristic_writes": 0, "subscriptions": 0, "pairings": 0,
        "host_wifi_control_calls": 0, "clone_touched": False,
        "cardputer_touched": False, "storage_write_authorized": False,
        "terminal_zero_lease": True,
    }, "scope")
    print("BLE GATT negative acceptance passed: exact dev.276, four "
          "fail-closed paths, bounded queue and positive recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
