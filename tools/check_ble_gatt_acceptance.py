#!/usr/bin/env python3
"""Fail closed unless exact dev.272 BLE GATT evidence is intact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retain_1x_ble_gatt_hil import (
    APP_ELF_SHA256,
    CID,
    EVIDENCE_IDS,
    FIRMWARE_SHA256,
    FIXTURE_SHA256,
    RAW_INDEX_SHA256,
    RAW_RUN_SHA256,
    RUNNER_SHA256,
    SOURCE_COMMIT,
    SOURCE_GUARD_SHA256,
    VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence" /
            "board-01-ble-gatt-1.0.0-dev.272.json")


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
        "schema": "leshy.ble_gatt_hil.acceptance.v1",
        "status": "pass_ble_gatt_enumeration",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
    }, "acceptance")
    exact(value["candidate"], {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flashed": True,
        "flash_mode": "fresh",
    }, "candidate")
    exact(value["evidence"], {
        "raw_run_sha256": RAW_RUN_SHA256,
        "raw_artifact_index_sha256": RAW_INDEX_SHA256,
        "runner_sha256": RUNNER_SHA256,
        "source_guard_sha256": SOURCE_GUARD_SHA256,
        "fixture_executable_sha256": FIXTURE_SHA256,
    }, "evidence")
    require(isinstance(value["evidence"].get("run_id"), str) and
            len(value["evidence"]["run_id"]) == 32, "run_id missing")
    require(set(value["evidence"].get("screenshots", {})) ==
            {"permission", "ready_first", "ready_second"},
            "screenshot hash set mismatch")
    exact(value["verified"], {
        "preflight_before_flash": True,
        "single_application_flash": True,
        "boot_reset_reason_code": 1,
        "permission_review": True,
        "second_confirmation": True,
        "exact_connectable_match_count": 1,
        "services": 5,
        "characteristics": 7,
        "service_capacity": 16,
        "characteristic_capacity": 48,
        "content_clears": 1,
        "stable_changed_pixels": 0,
        "stable_total_pixels": 76800,
        "characteristic_reads": 0,
        "characteristic_writes": 0,
        "subscriptions": 0,
        "pairings": 0,
        "host_wifi_control_calls": 0,
        "fixture_terminated": True,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
        "final_safety_state": "armed",
    }, "verified")
    require(int(value["verified"].get("boot_heap_total", 0)) == 146836 and
            int(value["verified"].get("boot_heap_free", 0)) == 73668 and
            int(value["verified"].get("heap_free_before", 0)) == 72664 and
            int(value["verified"].get("heap_free_after_init", 0)) == 908 and
            int(value["verified"].get("heap_minimum", 0)) == 820,
            "exact bounded heap lifecycle mismatch")
    exact(value["privacy"], {
        "raw_ble_addresses_retained": False,
        "raw_fixture_label_retained": False,
        "fixture_pid_retained": False,
        "screenshots_retained": False,
        "screenshot_hashes_retained": True,
        "selected_identity_hash_retained": False,
    }, "privacy")
    exact(value["scope"], {
        "single_flash_or_exact_reuse": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "exact_fixture_selected_without_identifier_disclosure": True,
        "active_connection_explicitly_confirmed_twice": True,
        "enumeration_only": True,
        "characteristic_reads": 0,
        "characteristic_writes": 0,
        "subscriptions": 0,
        "pairings": 0,
        "host_wifi_control_calls": 0,
        "clone_touched": False,
        "cardputer_touched": False,
        "stable_ready_card_changed_pixels": 0,
        "terminal_zero_lease": True,
        "storage_write_authorized": False,
    }, "scope")
    print("BLE GATT physical acceptance passed: exact dev.272, permission + "
          "confirmation, bounded enumeration, stable TFT and clean disconnect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
