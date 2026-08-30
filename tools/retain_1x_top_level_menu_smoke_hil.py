#!/usr/bin/env python3
"""Retain privacy-minimal, machine-checked top-level menu HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
import run_1x_top_level_menu_smoke_hil as runner


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.288"
NEGATIVE_VERSION = "1.0.0-dev.287"
CID = "FE343253440000002000000055019CB7"
MENU_IDS = [case.item_id for case in runner.MENU_CASES]
EVIDENCE_IDS = ["E-BUILD-202", "E-AUTO-177", "E-HIL-212", "E-UX-067"]
SOURCE_FILES = {
    "platform": "firmware/leshy1/platformio.ini",
    "firmware": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "ble_contract": "tools/check_ble_nearby_contract.py",
    "runner": "tools/run_1x_top_level_menu_smoke_hil.py",
    "runner_tests": "tools/test_top_level_menu_smoke_hil.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def menu(run: dict[str, Any], item_id: str) -> dict[str, Any]:
    records = [record for record in run.get("menus", [])
               if record.get("id") == item_id]
    require(len(records) == 1, f"missing or duplicate menu: {item_id}")
    return records[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--negative-source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--negative-source-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    source_run_path = args.source.resolve() / "run.json"
    negative_run_path = args.negative_source.resolve() / "run.json"
    destination = args.destination.resolve()
    firmware = args.firmware.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    map_file = args.map.resolve()
    required = (source_run_path, negative_run_path, firmware, factory,
                elf, map_file, *(ROOT / value for value in SOURCE_FILES.values()))
    require(all(path.is_file() for path in required),
            "run, build, or source artifact missing")
    require(not destination.exists(), "destination already exists")
    require(len(args.source_commit) == 40 and
            len(args.negative_source_commit) == 40,
            "source commits must be full IDs")

    run = load(source_run_path)
    negative = load(negative_run_path)
    candidate = run.get("candidate", {})
    negative_candidate = negative.get("candidate", {})
    require(run.get("schema") == runner.RUN_SCHEMA and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [] and
            runner.result_contract_failures(run) == [],
            "positive run does not pass the independent retained contract")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.source_commit and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("verified") is True and
            candidate.get("firmware_sha256") == digest(firmware) and
            candidate.get("app_elf_sha256") == app_elf_sha256(firmware) and
            run.get("expected_cid") == CID and
            run.get("runner_source_sha256") ==
                digest(ROOT / SOURCE_FILES["runner"]),
            "positive candidate binding mismatch")
    require([record.get("id") for record in run.get("menus", [])] == MENU_IDS and
            all(record.get("passed") is True and
                record.get("failures") == []
                for record in run.get("menus", [])),
            "all nine top-level menus must pass in catalog order")

    ble = menu(run, "ble")
    ready_samples = [sample for sample in ble.get("dwell_samples", [])
                     if sample.get("ble_begin_stage") == "ready"]
    require(ready_samples and
            min(sample.get("ble_begin_heap_free_before", 0)
                for sample in ready_samples) >=
                runner.BLE_MINIMUM_FREE_HEAP_BEFORE_BEGIN and
            min(sample.get("ble_begin_heap_largest_before", 0)
                for sample in ready_samples) >=
                runner.BLE_MINIMUM_LARGEST_HEAP_BEFORE_BEGIN and
            min(sample.get("ble_begin_heap_free_after", 0)
                for sample in ready_samples) > 0 and
            min(sample.get("ble_begin_heap_largest_after", 0)
                for sample in ready_samples) > 0,
            "bounded BLE ready/heap evidence missing")
    fixture = run.get("device_lock_fixture", {})
    cleanup = fixture.get("cleanup", {})
    require(cleanup.get("status") == "cleaned" and
            cleanup.get("product_restored") is True and
            cleanup.get("product_namespace_written_or_erased") is False and
            fixture.get("product_before", {}).get("status") == "unconfigured" and
            fixture.get("product_after", {}).get("status") == "unconfigured",
            "isolated Device Lock cleanup/continuity missing")
    final = run.get("post_hil_end", {})
    final_ui = final.get("ui", {})
    require(run.get("cleanup_after", {}).get("complete") is True and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("safe_outputs", {}).get("nrf_ce_inactive") is True and
            run.get("safe_outputs", {}).get("software_quiesce_complete") is True and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("boot_recovery_continuity") is True and
            run.get("hil_session", {}).get("end", {}).get("active") is False and
            final.get("hil", {}).get("active") is False and
            final_ui.get("page") == "home" and
            final_ui.get("runtime_owner") == "none" and
            final_ui.get("lease_mask") == 0 and
            final_ui.get("ble_product_view") == "none" and
            final_ui.get("survey_ble_scan_dropped") == 0 and
            final_ui.get("survey_product_cleanup_complete") is True and
            final_ui.get("survey_product_storage_mounted") is False,
            "terminal safety, input, storage, or HIL cleanup missing")

    require(negative.get("schema") == runner.RUN_SCHEMA and
            negative.get("passed") is False and
            negative.get("gate_eligible") is False and
            bool(negative.get("failures")) and
            negative_candidate.get("version") == NEGATIVE_VERSION and
            negative_candidate.get("source_commit") ==
                args.negative_source_commit and
            negative_candidate.get("verified") is True,
            "negative predecessor binding mismatch")
    negative_ble = menu(negative, "ble")
    negative_samples = negative_ble.get("dwell_samples", [])
    reboot_index = next((index for index, sample in enumerate(negative_samples)
                         if index > 0 and sample.get("revision") == 0 and
                         negative_samples[index - 1].get("revision", 0) > 0),
                        None)
    require(negative_ble.get("passed") is False and reboot_index is not None and
            negative_samples[reboot_index - 1].get("page") == "survey" and
            negative_samples[reboot_index - 1].get("runtime_owner") == "ble" and
            negative_samples[reboot_index - 1].get("ble_begin_stage") ==
                "not_attempted" and
            negative_samples[reboot_index].get("page") == "home" and
            negative_samples[reboot_index].get("runtime_owner") == "none",
            "negative BLE reboot boundary missing")

    before = negative_samples[reboot_index - 1]
    after = negative_samples[reboot_index]
    recovery_before = run.get("recovery_before", {})
    recovery_after = run.get("recovery_after", {})
    evidence = {
        "schema": "leshy.top_level_menu_smoke.acceptance.v1",
        "status": "pass_top_level_menu_and_ble_startup",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            "version": VERSION,
            "source_commit": args.source_commit,
            "firmware_sha256": digest(firmware),
            "factory_sha256": digest(factory),
            "elf_file_sha256": digest(elf),
            "map_sha256": digest(map_file),
            "app_elf_sha256": app_elf_sha256(firmware),
            "firmware_bytes": firmware.stat().st_size,
            "factory_bytes": factory.stat().st_size,
            "static_ram_bytes": args.static_ram_bytes,
            "linked_flash_bytes": args.linked_flash_bytes,
            "ota_free_bytes": 4194304 - firmware.stat().st_size,
            "source_sha256": {
                label: digest(ROOT / relative)
                for label, relative in SOURCE_FILES.items()
            },
        },
        "positive_run": {
            "run_sha256": digest(source_run_path),
            "runner_sha256": digest(ROOT / SOURCE_FILES["runner"]),
            "fresh_flash": True,
            "catalog_order": MENU_IDS,
            "menus_passed": len(run["menus"]),
            "menu_samples": {
                record["id"]: len(record.get("dwell_samples", []))
                for record in run["menus"]
            },
            "ble_dwell_seconds": ble.get("effective_dwell_seconds"),
            "ble_ready_samples": len(ready_samples),
            "ble_minimum_heap_free_before": min(
                sample["ble_begin_heap_free_before"] for sample in ready_samples),
            "ble_minimum_heap_largest_before": min(
                sample["ble_begin_heap_largest_before"] for sample in ready_samples),
            "ble_minimum_heap_free_after": min(
                sample["ble_begin_heap_free_after"] for sample in ready_samples),
            "ble_minimum_heap_largest_after": min(
                sample["ble_begin_heap_largest_after"] for sample in ready_samples),
            "ble_devices_observed": final_ui.get("ble_devices_unique"),
            "ble_advertisements_accepted":
                final_ui.get("survey_ble_scan_accepted"),
            "ble_driver_drops": final_ui.get("survey_ble_scan_dropped"),
            "ble_queue_high_water":
                final_ui.get("survey_ble_scan_queue_high_water"),
            "isolated_device_lock_cleanup": cleanup.get("status"),
            "product_lock_namespace_written_or_erased": False,
            "recovery_generation_before": recovery_before.get("generation"),
            "recovery_generation_after": recovery_after.get("generation"),
            "recovery_observations_before": recovery_before.get("observations"),
            "recovery_observations_after": recovery_after.get("observations"),
            "physical_product_write_calls":
                recovery_after.get("physical_write_calls"),
            "input_read_errors": 0,
            "input_queue_drops": 0,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
            "final_hil_active": False,
            "final_storage_mounted": False,
            "buzzer_inactive": True,
            "nrf_ce_inactive": True,
            "dangerous_tx_started": False,
            "mac_wifi_or_ble_controlled": False,
            "manual_button_presses": 0,
        },
        "rejected_predecessor": {
            "version": NEGATIVE_VERSION,
            "source_commit": args.negative_source_commit,
            "firmware_sha256": negative_candidate.get("firmware_sha256"),
            "app_elf_sha256": negative_candidate.get("app_elf_sha256"),
            "run_sha256": digest(negative_run_path),
            "gate_eligible": False,
            "ble_begin_stage_before_boundary": before.get("ble_begin_stage"),
            "ui_revision_before_boundary": before.get("revision"),
            "ui_revision_after_boundary": after.get("revision"),
            "page_before_boundary": before.get("page"),
            "page_after_boundary": after.get("page"),
            "owner_before_boundary": before.get("runtime_owner"),
            "owner_after_boundary": after.get("runtime_owner"),
            "final_page": negative.get("post_hil_end", {}).get(
                "ui", {}).get("page"),
            "final_runtime_owner": negative.get("post_hil_end", {}).get(
                "ui", {}).get("runtime_owner"),
            "final_lease_mask": negative.get("post_hil_end", {}).get(
                "ui", {}).get("lease_mask"),
        },
        "scope": {
            "accepts": [
                "nine current top-level product routes",
                "bounded first-process BLE initialization on no-PSRAM board-01",
                "Device Lock fixture isolation and terminal cleanup",
            ],
            "does_not_accept": [
                "nested destructive or transmit actions",
                "Automation/HID signature trust or execution",
                "dense BLE environments exceeding the observed queue load",
                "release endurance or the periodic full HIL checkpoint",
            ],
            "focused_cadence": "15/15",
            "periodic_full_checkpoint_due": True,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": str(destination.relative_to(ROOT)),
        "sha256": digest(destination),
        "menus_passed": len(run["menus"]),
        "ble_ready_samples": len(ready_samples),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
