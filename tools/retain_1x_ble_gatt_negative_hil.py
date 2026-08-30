#!/usr/bin/env python3
"""Validate and retain privacy-minimal BLE GATT negative acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.276"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "6b5d27b2253bd7b335bab8754379a5ce51a0a5d2"
FIRMWARE_SHA256 = "e98bf5e4825c438ec5629ffd05ddf58168552a42fef3d40969aa0b9c1206cae9"
APP_ELF_SHA256 = "ae9782374b0a9b17da9e8d7a52c4ed86d9a71b74c10962660c79125d0e561dbd"
MAP_SHA256 = "dbddd1990055251ce6509ea7c176019608aeb289157489207a5348370d7d3bf3"
FACTORY_SHA256 = "6a3f0463819066d4ae8ea8ab548491a0c58da76dcb7d073d56025a66b774c735"
FRESH_RUN_SHA256 = "6be1d87f18dfb7d93ebc66d351921501dadf285dd2ab9309b58fe0602986c00d"
FRESH_INDEX_SHA256 = "58b2c7cf0d89529fccdaa1ad202684b9a259c507553f74b47cecded13c30ca54"
FULL_RUN_SHA256 = "41ca05d4d1e5057bc89baadc3418337f69d840a99e26aedd306276cb1929c3e2"
FULL_INDEX_SHA256 = "3676cfd5f58f3a429df6de5034bff49a032eac19116755930d8aa8ed0a9513d3"
RUNNER_SHA256 = "40880f6783cb6de188a13321277657f05067738107b35b3cf21bfea7420b50c0"
SOURCE_GUARD_SHA256 = "030ede456867b5e49dcd4e8543bdb957331325eae897fb090863125a0b19cde7"
FIXTURE_SHA256 = "da3cec0a11116e563b8d34d7c3ef042b5aeba0978db069b2b7c89bce6d64106d"
SCREEN_SHA256 = {
    "failed-cleanup": {
        "png_sha256": "3c756e7389da3f994a8512a18eee83f44aa8ff4eebbf089e94fa03a857885799",
        "rgb565_sha256": "31c2ba7892a26e9e47ed55bc33cbdd933c72c87c7d149d575d6e74c21954544b",
    },
    "resource-conflict": {
        "png_sha256": "86cd7bbd469f8a50f235270be0c5632712931904f0516c01d865fe0b10ea7968",
        "rgb565_sha256": "ba647a24427ce7af4651231cbd551dfc55a570c102debc460e230d80563055e0",
    },
    "timeout": {
        "png_sha256": "9f05386dd452fac97fe4995c2719e6c6aff554d388fd839c64b8bb68e13663c8",
        "rgb565_sha256": "59190112ba8106e79dd22ed955c14ce57ab07490a177b4ccf4a04aee80af39bc",
    },
    "wrong-peer": {
        "png_sha256": "a731397aaa1d7500f3f504486bd73da108dd789d8189cc31d639714adb420f44",
        "rgb565_sha256": "ae7231101d35ba9eeb1ab94a2e1a66570f1e9bd1fade65aedf473f2e5d1b4473",
    },
}
EVIDENCE_IDS = ["E-BUILD-192", "E-AUTO-167", "E-HIL-205", "E-UX-062", "RB-M203"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def load_run(source: Path, run_hash: str, index_hash: str) -> dict[str, Any]:
    require(source.is_dir() and not source.is_symlink(),
            f"regular source directory required: {source}")
    run_path = source / "run.json"
    index_path = source / "artifacts.sha256"
    firmware = source / "firmware.bin"
    for path in (run_path, index_path, firmware):
        require(path.is_file(), f"missing artifact: {path}")
    require(digest(run_path) == run_hash, f"raw run hash mismatch: {source}")
    require(digest(index_path) == index_hash,
            f"artifact index hash mismatch: {source}")
    require(digest(firmware) == FIRMWARE_SHA256,
            f"firmware hash mismatch: {source}")
    return json.loads(run_path.read_text(encoding="utf-8"))


def validate_common(run: dict[str, Any], *, flash_mode: str,
                    flashed: bool, expected_heap_free: int) -> None:
    exact(run, {
        "schema": "leshy.ble_gatt_negative_hil.run.v1",
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
        "flashed": flashed,
        "flash_mode": flash_mode,
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
    exact(run["boot"], {
        "version": VERSION,
        "app_elf_sha256": APP_ELF_SHA256,
        "heap_total": 148124,
        "heap_free": expected_heap_free,
        "reset_reason_code": 1,
        "psram_found": False,
        "psram_bytes": 0,
        "buzzer_inactive": True,
    }, "boot")
    begin = run["hil_session"]["begin"]
    end = run["hil_session"]["end"]
    exact(begin, {
        "active": True,
        "app_elf_sha256": APP_ELF_SHA256,
        "firmware_version": VERSION,
    }, "hil.begin")
    exact(end, {"active": False, "app_elf_sha256": APP_ELF_SHA256},
          "hil.end")
    require(begin["session_id"] == end["session_id"] == run["run_id"],
            "HIL session continuity mismatch")
    fixture = run["external_ble_fixture"]
    exact(fixture, {
        "kind": "macos_corebluetooth",
        "executable_sha256": FIXTURE_SHA256,
        "host_wifi_control_calls": 0,
        "terminated": True,
        "returncode": -15,
    }, "fixture")
    require(len(fixture.get("states", [])) == 1 and
            fixture["states"][0].get("state") == "advertising",
            "deterministic fixture advertising state missing")
    exact(run["scope"], {
        "single_flash_or_exact_reuse": True,
        "manual_button_presses": 0,
        "enumeration_only": True,
        "characteristic_reads": 0,
        "characteristic_writes": 0,
        "subscriptions": 0,
        "pairings": 0,
        "host_wifi_control_calls": 0,
        "clone_touched": False,
        "cardputer_touched": False,
        "storage_write_authorized": False,
        "terminal_zero_lease": True,
    }, "scope")
    exact(run["cleanup_after"], {"complete": True}, "cleanup_after")
    exact(run["cleanup_after"]["final_state"], {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "safety_state": "armed", "survey_ble_scan_dropped": 0,
    }, "cleanup_after.final_state")
    high_water = int(run["cleanup_after"]["final_state"].get(
        "survey_ble_scan_queue_high_water", 0))
    require(1 <= high_water <= 32,
            f"passive queue high-water outside 1..32: {high_water}")
    exact(run["final_fault_clear"], {
        "status": "cleared", "armed": "none", "hil_active": True,
        "enumeration_only": True, "pairing_allowed": False,
        "read_allowed": False, "write_allowed": False,
        "subscribe_allowed": False, "storage_mounted": False,
        "storage_written": False, "physical_write_calls": 0,
    }, "final_fault_clear")


def validate_failure(scenario: dict[str, Any], *, request: str,
                     canonical: str, failure: str, cleanup_cause: str,
                     consumed_count: int) -> None:
    exact(scenario, {"request": request, "canonical": canonical}, request)
    exact(scenario["armed"], {
        "status": "armed", "armed": canonical, "one_shot": True,
        "enumeration_only": True, "pairing_allowed": False,
        "read_allowed": False, "write_allowed": False,
        "subscribe_allowed": False, "storage_mounted": False,
        "storage_written": False, "physical_write_calls": 0,
    }, f"{request}.armed")
    exact(scenario["terminal"], {
        "state": "failed", "failure": failure,
        "cleanup_cause": cleanup_cause, "host_ready": False,
        "connected": False, "transport_connecting": False,
        "transport_disconnected": True, "cleanup_requested": False,
        "cleanup_complete": True, "owns_radio": False,
        "esp_rf_owner": 0, "gatt_owner": 6,
        "enumeration_only": True, "pairing_allowed": False,
        "read_allowed": False, "write_allowed": False,
        "subscribe_allowed": False,
    }, f"{request}.terminal")
    exact(scenario["consumed"], {
        "status": "state", "armed": "none", "last_consumed": canonical,
        "consumed_count": consumed_count, "hil_active": True,
    }, f"{request}.consumed")
    exact(scenario["home"], {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, f"{request}.home")


def validate_recovery(run: dict[str, Any], consumed_count: int) -> None:
    recovery = run["recovery_success"]
    exact(recovery["ready"], {
        "state": "ready", "failure": "none", "host_ready": True,
        "connected": True, "cleanup_complete": False,
        "owns_radio": True, "esp_rf_owner": 6,
        "hil_fault_armed": "none",
        "hil_fault_consumed_count": consumed_count,
        "services": 5, "characteristics": 7,
        "heap_free_before": 73308, "heap_largest_before": 32756,
        "heap_free_after_init": 1540, "heap_largest_after_init": 1012,
    }, "recovery.ready")
    require(int(recovery["ready"].get("heap_minimum", 0)) >= 1400,
            "recovery heap minimum below accepted bound")
    exact(recovery["home"], {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_ble_scan_dropped": 0,
        "survey_ble_scan_queue_high_water": 3,
    }, "recovery.home")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh-source", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    require(not destination.exists(), "destination must not exist")
    require(digest(ROOT / "tools/run_1x_ble_gatt_negative_hil.py") ==
            RUNNER_SHA256, "runner source hash mismatch")
    require(digest(ROOT / "tools/check_ble_inspector_contract.py") ==
            SOURCE_GUARD_SHA256, "source guard hash mismatch")

    fresh = load_run(args.fresh_source.resolve(), FRESH_RUN_SHA256,
                     FRESH_INDEX_SHA256)
    full = load_run(args.source.resolve(), FULL_RUN_SHA256, FULL_INDEX_SHA256)
    validate_common(fresh, flash_mode="fresh", flashed=True,
                    expected_heap_free=74828)
    exact(fresh["scope"], {"run_mode": "timeout"}, "fresh.scope")
    require(len(fresh["scenarios"]) == 1, "focused scenario count mismatch")
    validate_failure(fresh["scenarios"][0], request="timeout",
                     canonical="timeout", failure="timeout",
                     cleanup_cause="timeout", consumed_count=1)
    validate_recovery(fresh, 1)

    validate_common(full, flash_mode="reuse_exact", flashed=False,
                    expected_heap_free=73308)
    exact(full["scope"], {
        "run_mode": "all",
        "scenario_order": ["wrong-peer", "timeout", "resource-conflict",
                           "failed-cleanup", "recovery-success"],
        "screenshots_automatic": True,
    }, "full.scope")
    definitions = (
        ("wrong-peer", "unexpected_peer", "unexpected_peer",
         "unexpected_peer", 2),
        ("timeout", "timeout", "timeout", "timeout", 3),
        ("resource-conflict", "resource_conflict", "resource_busy",
         "none", 4),
        ("failed-cleanup", "disconnect_failure", "disconnect_failed",
         "none", 5),
    )
    require(len(full["scenarios"]) == len(definitions),
            "full scenario count mismatch")
    for scenario, definition in zip(full["scenarios"], definitions):
        validate_failure(scenario, request=definition[0],
                         canonical=definition[1], failure=definition[2],
                         cleanup_cause=definition[3],
                         consumed_count=definition[4])
    exact(full["scenarios"][3]["ready"], {
        "state": "ready", "failure": "none", "host_ready": True,
        "connected": True, "owns_radio": True, "esp_rf_owner": 6,
        "services": 5, "characteristics": 7,
    }, "failed_cleanup.ready")
    validate_recovery(full, 5)

    screen_hashes = {
        label: {"png_sha256": frame["png_sha256"],
                "rgb565_sha256": frame["rgb565_sha256"]}
        for label, frame in sorted(full["screens"].items())
    }
    require(screen_hashes == SCREEN_SHA256,
            "negative screenshot hash set mismatch")
    summary = {
        "schema": "leshy.ble_gatt_negative_hil.acceptance.v1",
        "status": "pass_ble_gatt_fail_closed_matrix",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
        "candidate": full["candidate"],
        "build": {
            "static_ram_bytes": 230680,
            "linked_flash_bytes": 3480736,
            "firmware_bytes": 3480896,
            "factory_bytes": 3546432,
            "firmware_sha256": FIRMWARE_SHA256,
            "factory_sha256": FACTORY_SHA256,
            "app_elf_sha256": APP_ELF_SHA256,
            "map_sha256": MAP_SHA256,
            "ota_slot_free_bytes": 713408,
        },
        "evidence": {
            "fresh_run_id": fresh["run_id"],
            "fresh_raw_run_sha256": FRESH_RUN_SHA256,
            "fresh_artifact_index_sha256": FRESH_INDEX_SHA256,
            "full_run_id": full["run_id"],
            "full_raw_run_sha256": FULL_RUN_SHA256,
            "full_artifact_index_sha256": FULL_INDEX_SHA256,
            "runner_sha256": RUNNER_SHA256,
            "source_guard_sha256": SOURCE_GUARD_SHA256,
            "fixture_executable_sha256": FIXTURE_SHA256,
            "screenshots": screen_hashes,
        },
        "verified": {
            "fresh_application_flash": True,
            "full_matrix_exact_reuse": True,
            "fresh_boot_heap_total": fresh["boot"]["heap_total"],
            "fresh_boot_heap_free": fresh["boot"]["heap_free"],
            "reuse_heap_free": full["boot"]["heap_free"],
            "scenario_order": full["scope"]["scenario_order"],
            "failures": [
                {"request": item[0], "failure": item[2],
                 "cleanup_cause": item[3], "cleanup_complete": True,
                 "terminal_esp_rf_owner": 0,
                 "terminal_page": "home", "terminal_lease_mask": 0}
                for item in definitions
            ],
            "post_failure_services": 5,
            "post_failure_characteristics": 7,
            "heap_free_before": 73308,
            "heap_free_after_init": 1540,
            "heap_minimum": full["recovery_success"]["ready"]["heap_minimum"],
            "passive_queue_capacity": 32,
            "passive_queue_high_water": 3,
            "passive_queue_drops": 0,
            "characteristic_reads": 0,
            "characteristic_writes": 0,
            "subscriptions": 0,
            "pairings": 0,
            "host_wifi_control_calls": 0,
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
        "scope": full["scope"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination": str(destination)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
