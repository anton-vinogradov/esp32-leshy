#!/usr/bin/env python3
"""Fail closed unless the exact 0.171 antenna-LED delta remains intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-antenna-status-leds-0.171.json"


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] == "leshy.antenna_status_leds_hil.summary.v1"
            and value["status"] == "pass"
            and value["evidence_ids"] == [
                "E-BUILD-148", "E-AUTO-119", "E-HIL-178", "E-UX-053"
            ]
            and value["firmware_source_commit"] ==
            "c2413c9962998281dd54080a1fb67f54db8776b3"
            and candidate == {
                "version": "0.171.0-antenna-status-leds",
                "firmware_sha256":
                    "77d14d9ac10f64cb60fb97f2f3b6b3986d2cdac71085b454d6d25267794e0784",
                "factory_sha256":
                    "04bb4a4fb78cd4de7e12e5a2c4b43311e8e1af097c8e5181173a0bc08500a0fe",
                "app_elf_sha256":
                    "e5189daa424da4e2ca04e5e94390f19e9ef3d483c894b10a62c8da9da08d247c",
                "map_sha256":
                    "04e897a24e7bb68e1933bb95d19b9c30a546ae56a8a598f9138256ad9ac1a8b4",
                "partitions_sha256":
                    "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3",
                "firmware_bytes": 3175536,
                "factory_bytes": 3241072,
                "static_ram_bytes": 214696,
                "linked_flash_bytes": 3175040,
            }
        ):
            failures.append("candidate identity/build budget mismatch")
        board = value["board"]
        if not (
            board == {
                "id": "board-01",
                "port": "/dev/cu.usbmodem2101",
                "mac": "1c:db:d4:87:90:d4",
                "exact_cid": "FE343253440000002000000055019CB7",
                "flash_count": 1,
                "port_discovery_calls": 0,
                "cardputer_ports_opened": 0,
            }
        ):
            failures.append("board/USB isolation mismatch")
        contract = value["contract"]
        if not (
            contract["gpio"] == 1
            and contract["pixel_count"] == 4
            and [item["receiver"] for item in contract["pixels"]] == [
                "cc1101", "nrf24-slot-1", "nrf24-slot-2", "nrf24-slot-3"
            ]
            and contract["brightness_raw_ladder"] == [0, 2, 3, 5, 8, 12]
            and contract["default_brightness_raw"] == 2
            and contract["active_color"] == "green"
            and contract["fault_color"] == "red"
            and contract["inactive_color"] == "off"
            and contract["safe_mode"] == "all_off"
            and contract["update_policy"] == "state_change_only"
            and contract["rx_only"] is True
        ):
            failures.append("0.x-derived LED contract mismatch")
        nrf = value["runtime"]["nrf24"]
        cc = value["runtime"]["cc1101"]
        if not (
            nrf["status"] == "ready"
            and nrf["state"] == "running"
            and nrf["modules"] == 3
            and nrf["active_slot_mask"] == 0b111
            and nrf["all_available_antennas"] is True
            and nrf["ui_receive_mask"] == 0b1110
            and nrf["ui_fault_mask"] == 0
            and nrf["rx_only"] is True
            and all(nrf[field] == 0 for field in (
                "tx_mode_entries", "tx_payload_commands",
                "cc_command_strobes", "storage_writes"
            ))
        ):
            failures.append("nRF24 receive-mask/side-effect mismatch")
        if not (
            cc["status"] == "ready"
            and cc["state"] == "running"
            and cc["partnum"] == 0
            and cc["version"] == 20
            and cc["ui_receive_mask"] == 0b0001
            and cc["ui_fault_mask"] == 0
            and cc["rx_only"] is True
            and all(cc[field] == 0 for field in (
                "tx_strobes", "pa_table_writes", "fifo_writes",
                "rejected_strobes", "storage_writes"
            ))
        ):
            failures.append("CC1101 receive-mask/side-effect mismatch")
        preference = value["preference"]
        if not (
            preference["first_observed_raw"] == 2
            and preference["all_levels_exercised"] == [0, 2, 3, 5, 8, 12]
            and preference["temporary_raw_after_interrupted_camera_attempt"] == 12
            and preference["restore_only_requested_raw"] == 2
            and preference["final_raw_after_hardware_reset"] == 2
        ):
            failures.append("brightness persistence/restore mismatch")
        final = value["final"]
        if not (
            final["page"] == "home"
            and final["runtime_owner"] == "none"
            and final["lease_mask"] == 0
            and final["antenna_led_brightness_raw"] == 2
            and final["antenna_led_receive_mask"] == 0
            and final["antenna_led_fault_mask"] == 0
            and final["input_status"] == "ready"
            and final["input_read_errors"] == 0
            and final["input_queue_drops"] == 0
            and final["buzzer_inactive"] is True
            and final["nrf_ce_inactive"] is True
            and final["software_quiesce_complete"] is True
            and final["radio_tx_commands"] == 0
            and final["storage_generation"] == 161
            and final["storage_observations"] == 59
            and final["storage_physical_write_calls"] == 0
        ):
            failures.append("final safety/storage/ownership mismatch")
        camera = value["camera"]
        if not (
            camera["status"] == "unavailable_permission_denied"
            and camera["required_for_acceptance"] is False
            and camera["physical_color_claim"] is False
        ):
            failures.append("camera limitation is not explicit")
        lineage = value["run_lineage"]
        if not (
            len(lineage) == 4
            and [item["status"] for item in lineage] == [
                "failed", "failed", "pass", "pass"
            ]
            and sum(item["flash_count"] for item in lineage) == 1
            and all(len(item["run_sha256"]) == 64 for item in lineage)
            and value["physical_cadence"] == {
                "accepted": 15,
                "full_gate_at": 15,
                "full_checkpoint_due": True,
            }
        ):
            failures.append("fail-closed lineage/cadence mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Antenna LED delta acceptance passed: exact CC/N1/N2/N3 mapping, "
          "0.x raw ladder, RX-only masks, stock 2/255 restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
