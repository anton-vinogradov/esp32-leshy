#!/usr/bin/env python3
"""Validate and retain privacy-minimal physical BLE GATT acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.272"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "fcd0683cb169ac41e42ff302d074a146457c1b1d"
FIRMWARE_SHA256 = "5b6e12091e5704ef05b29f8e8095ce48b50eee4c0753f3931bda3fde3e70e1ca"
APP_ELF_SHA256 = "afe1793ec768a65b914c878bddaf2f6150cfa767d43035a9bc582c102e786e11"
RAW_RUN_SHA256 = "265cd2e73cc2ac46e8735aa44d8d3fa87f6960f9514c882781e1b7b798e4fc2e"
RAW_INDEX_SHA256 = "d1d60dca88069c9dc7637669dd4e8a0fee57d8daeba5e83824146866d7f0389d"
RUNNER_SHA256 = "fb45bb53c446e9be9f32bd4360a4648876e141bdcbce45d07a516cc4976bd2c4"
SOURCE_GUARD_SHA256 = "06a57dbc5b6d4e2a8170325d594df846985739bb2d1465f6783a9f08fc0de8d1"
FIXTURE_SHA256 = "da3cec0a11116e563b8d34d7c3ef042b5aeba0978db069b2b7c89bce6d64106d"
EVIDENCE_IDS = ["E-BUILD-191", "E-AUTO-166", "E-HIL-204", "E-UX-061", "RB-M202"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    require(source.is_dir() and not source.is_symlink(),
            "regular source directory required")
    require(not destination.exists(), "destination must not exist")
    run_path = source / "run.json"
    index_path = source / "artifacts.sha256"
    firmware = source / "firmware.bin"
    for path in (run_path, index_path, firmware):
        require(path.is_file(), f"missing artifact: {path}")
    require(digest(run_path) == RAW_RUN_SHA256, "raw run hash mismatch")
    require(digest(index_path) == RAW_INDEX_SHA256, "artifact index hash mismatch")
    require(digest(firmware) == FIRMWARE_SHA256, "firmware hash mismatch")
    require(digest(ROOT / "tools/run_1x_ble_gatt_hil.py") == RUNNER_SHA256,
            "runner source hash mismatch")
    require(digest(ROOT / "tools/check_ble_inspector_contract.py") ==
            SOURCE_GUARD_SHA256, "source guard hash mismatch")

    run = json.loads(run_path.read_text(encoding="utf-8"))
    exact(run, {
        "schema": "leshy.ble_gatt_hil.run.v1",
        "passed": True,
        "gate_eligible": True,
        "expected_cid": CID,
        "failures": [],
    }, "run")
    exact(run["candidate"], {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flashed": True,
        "flash_mode": "fresh",
    }, "candidate")
    exact(run["preflight"], {
        "expected_cid": CID,
        "observed_cid": CID,
        "fingerprint_matched": True,
        "performed_before_application_flash": True,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
    }, "preflight")
    exact(run["selector"], {
        "selected": True,
        "match_count": 1,
        "strongest_match": True,
        "connectable": True,
        "identifier_disclosed": False,
        "storage_mounted": False,
        "storage_written": False,
        "rf_hardware_touched": False,
        "radio_started": False,
    }, "selector")
    identity_hash = int(run["ready"].get("selected_identity_hash", 0))
    require(identity_hash != 0, "selected identity hash must be nonzero")
    for label, state_name in (("permission", "permission_review"),
                              ("confirmation", "awaiting_confirmation")):
        exact(run[label], {
            "view": "inspector_gatt",
            "state": state_name,
            "failure": "none",
            "selected_identity_hash": identity_hash,
            "permission_visible": True,
            "confirmation_required": True,
            "connected": False,
            "owns_radio": False,
            "enumeration_only": True,
            "pairing_allowed": False,
            "read_allowed": False,
            "write_allowed": False,
            "subscribe_allowed": False,
        }, label)
    ready = run["ready"]
    exact(ready, {
        "view": "inspector_gatt",
        "state": "ready",
        "failure": "none",
        "selected_identity_hash": identity_hash,
        "permission_visible": False,
        "host_ready": True,
        "connected": True,
        "cleanup_complete": False,
        "owns_radio": True,
        "esp_rf_owner": 6,
        "gatt_owner": 6,
        "enumeration_only": True,
        "pairing_allowed": False,
        "read_allowed": False,
        "write_allowed": False,
        "subscribe_allowed": False,
        "services": 5,
        "characteristics": 7,
        "service_capacity": 16,
        "characteristic_capacity": 48,
        "content_clears": 1,
    }, "ready")
    for key in ("heap_free_before", "heap_largest_before",
                "heap_free_after_init", "heap_largest_after_init",
                "heap_minimum"):
        require(int(ready.get(key, 0)) > 0, f"ready.{key} must be positive")
    exact(run["terminal_gatt"], {
        "view": "none",
        "state": "idle",
        "target_present": False,
        "host_ready": False,
        "connected": False,
        "cleanup_complete": True,
        "owns_radio": False,
        "esp_rf_owner": 0,
        "read_allowed": False,
        "write_allowed": False,
        "subscribe_allowed": False,
    }, "terminal_gatt")
    exact(run["pixel_proof"], {
        "changed_pixels": 0,
        "total_pixels": 76800,
    }, "pixel_proof")
    exact(run["hil_session"]["begin"], {
        "active": True,
        "app_elf_sha256": APP_ELF_SHA256,
        "firmware_version": VERSION,
    }, "hil.begin")
    exact(run["hil_session"]["end"], {
        "active": False,
        "app_elf_sha256": APP_ELF_SHA256,
    }, "hil.end")
    require(run["hil_session"]["begin"]["session_id"] ==
            run["hil_session"]["end"]["session_id"] == run["run_id"],
            "HIL session continuity mismatch")
    fixture = run["external_ble_fixture"]
    exact(fixture, {
        "kind": "macos_corebluetooth",
        "executable_sha256": FIXTURE_SHA256,
        "host_wifi_control_calls": 0,
        "terminated": True,
        "returncode": -15,
    }, "fixture")
    exact(run["cleanup_after"], {"complete": True}, "cleanup_after")
    exact(run["cleanup_after"]["final_state"], {
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "safety_state": "armed",
    }, "cleanup_after.final_state")
    exact(run["scope"], {
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

    screen_hashes = {
        label: {
            "png_sha256": frame["png_sha256"],
            "rgb565_sha256": frame["rgb565_sha256"],
        }
        for label, frame in sorted(run["screens"].items())
    }
    summary = {
        "schema": "leshy.ble_gatt_hil.acceptance.v1",
        "status": "pass_ble_gatt_enumeration",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
        "candidate": run["candidate"],
        "evidence": {
            "run_id": run["run_id"],
            "raw_run_sha256": RAW_RUN_SHA256,
            "raw_artifact_index_sha256": RAW_INDEX_SHA256,
            "runner_sha256": RUNNER_SHA256,
            "source_guard_sha256": SOURCE_GUARD_SHA256,
            "fixture_executable_sha256": FIXTURE_SHA256,
            "screenshots": screen_hashes,
        },
        "verified": {
            "preflight_before_flash": True,
            "single_application_flash": True,
            "boot_reset_reason_code": run["boot"]["reset_reason_code"],
            "boot_heap_total": run["boot"]["heap_total"],
            "boot_heap_free": run["boot"]["heap_free"],
            "permission_review": True,
            "second_confirmation": True,
            "exact_connectable_match_count": 1,
            "services": ready["services"],
            "characteristics": ready["characteristics"],
            "service_capacity": ready["service_capacity"],
            "characteristic_capacity": ready["characteristic_capacity"],
            "heap_free_before": ready["heap_free_before"],
            "heap_free_after_init": ready["heap_free_after_init"],
            "heap_minimum": ready["heap_minimum"],
            "content_clears": ready["content_clears"],
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
        },
        "privacy": {
            "raw_ble_addresses_retained": False,
            "raw_fixture_label_retained": False,
            "fixture_pid_retained": False,
            "screenshots_retained": False,
            "screenshot_hashes_retained": True,
            "selected_identity_hash_retained": False,
        },
        "scope": run["scope"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination": str(destination)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
