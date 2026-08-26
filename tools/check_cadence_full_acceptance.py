#!/usr/bin/env python3
"""Fail closed unless the exact 0.171 periodic full checkpoint is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = (
    ROOT / "tests/hil/evidence/board-01-cadence-full-0.171.json"
)
POLICY_PATH = ROOT / "tests/hil/hil-cadence.v1.json"
SOURCE = "c2413c9e31b89efd646a0ca15d2eb2b574d90fe5"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "77d14d9ac10f64cb60fb97f2f3b6b3986d2cdac71085b454d6d25267794e0784"
APP = "e5189daa424da4e2ca04e5e94390f19e9ef3d483c894b10a62c8da9da08d247c"
MAP = "04e897a24e7bb68e1933bb95d19b9c30a546ae56a8a598f9138256ad9ac1a8b4"
SUMMARY_RELATIVE = "tests/hil/evidence/board-01-cadence-full-0.171.json"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        require(failures,
                value["schema"] == "leshy.hil_cadence_full.summary.v1" and
                value["status"] == "pass_full_checkpoint" and
                value["evidence_ids"] == [
                    "E-AUTO-120", "E-HIL-179", "E-CADENCE-001"
                ] and value["firmware_source_commit"] == SOURCE,
                "summary/source identity mismatch")
        require(failures,
                candidate["version"] == "0.171.0-antenna-status-leds" and
                candidate["firmware_sha256"] == FIRMWARE and
                candidate["factory_sha256"] ==
                "04bb4a4fb78cd4de7e12e5a2c4b43311e8e1af097c8e5181173a0bc08500a0fe" and
                candidate["app_elf_sha256"] == APP and
                candidate["map_sha256"] == MAP and
                candidate["partitions_sha256"] ==
                "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3" and
                candidate["firmware_bytes"] == 3175536 and
                candidate["factory_bytes"] == 3241072 and
                candidate["static_ram_bytes"] == 214696 and
                candidate["linked_flash_bytes"] == 3175040,
                "candidate identity/build budget mismatch")

        board = value["board"]
        require(failures,
                board == {
                    "id": "board-01",
                    "port": "/dev/cu.usbmodem2101",
                    "mac": "1c:db:d4:87:90:d4",
                    "exact_cid": CID,
                    "candidate_flash_count": 1,
                    "additional_full_checkpoint_flashes": 0,
                    "serial_port_discovery_calls": 0,
                    "cardputer_ports_opened": 0,
                }, "board/USB/flash isolation mismatch")

        home = value["home_matrix"]
        require(failures,
                home["independent_checker"] == "pass" and
                home["home_items"] == [
                    "wifi", "ble", "spectrum24", "subghz", "capture",
                    "targets", "library", "device"
                ] and home["automatic_screens"] == 20 and
                home["manual_button_presses"] == 0 and
                home["tx_or_storage_side_effects"] == 0 and
                len(home["raw_run_sha256"]) == 64,
                "Home matrix mismatch")
        for receiver in ("nrf24_waterfall", "cc1101_waterfall"):
            waterfall = home[receiver]
            require(failures,
                    waterfall["history_rows"] == 224 and
                    waterfall["measurements_consumed"] ==
                    waterfall["source_sweeps"] and
                    waterfall["measurements_consumed"] >= 224 and
                    waterfall["measurements_skipped"] == 0 and
                    waterfall["graph_changed_pixels"] > 0 and
                    waterfall["chrome_changed_pixels"] == 0 and
                    waterfall["rx_only"] is True,
                    f"{receiver} one-pixel/RX-only mismatch")

        targets = value["targets_matrix"]
        require(failures,
                targets["exact_flash_reused"] is True and
                targets["survey_pair"] == [160, 161] and
                targets["new_survey_cycles"] == 0 and
                targets["catalog_count"] == 16 and
                targets["visible_target_count"] == 7 and
                targets["comparison_count"] == 7 and
                sum(targets["compare_counts"].values()) == 7 and
                targets["compare_counts"] == {
                    "added": 2, "changed": 0,
                    "removed": 1, "unchanged": 4,
                } and targets["detail_opened"] is True and
                targets["released_heap_bytes"] == 91068 and
                targets["cleanup_complete"] is True and
                targets["radio_tx_commands"] == 0 and
                len(targets["raw_run_sha256"]) == 64,
                "Targets matrix mismatch")

        companion = value["companion_matrix"]
        require(failures,
                companion["exact_flash_reused"] is True and
                companion["transport"] == "usb_serial_ndjson" and
                companion["max_frame_bytes"] == 512 and
                companion["sessions"] == 2 and
                companion["session_generations"] == [160, 161] and
                companion["catalog_count"] == 16 and
                companion["comparison_count"] == 7 and
                companion["read_scopes"] == [
                    "session.read", "target.read", "target.compare"
                ] and companion["negative_contracts"] == {
                    "home": "scope_unavailable",
                    "oversized_513": "frame_too_large",
                    "truncated": "malformed_json",
                    "unknown_field": "unknown_field",
                    "invalid_offset": "offset_out_of_range",
                    "mutation": "scope_denied",
                    "after_exit": "not_connected",
                } and companion["heap_free_before"] == 91068 and
                companion["heap_free_after"] == 91068 and
                companion["radio_tx_commands"] == 0 and
                companion["storage_write_commands"] == 0 and
                len(companion["raw_run_sha256"]) == 64,
                "companion matrix mismatch")

        continuity = value["continuity"]
        require(failures,
                continuity == {
                    "generation_before": 161,
                    "generation_after": 161,
                    "observations_before": 59,
                    "observations_after": 59,
                    "physical_write_calls": 0,
                    "heap_total_before": 164108,
                    "heap_total_after": 164108,
                    "heap_free_before": 91068,
                    "heap_free_after": 91068,
                    "input_read_errors": 0,
                    "input_queue_drops": 0,
                }, "storage/heap/input continuity mismatch")
        require(failures,
                value["final"] == {
                    "page": "home",
                    "runtime_owner": "none",
                    "lease_mask": 0,
                    "antenna_led_brightness_raw": 2,
                    "antenna_led_receive_mask": 0,
                    "antenna_led_fault_mask": 0,
                    "buzzer_inactive": True,
                    "nrf_ce_inactive": True,
                    "software_quiesce_complete": True,
                }, "final Home/safety/LED state mismatch")

        lineage = value["fail_closed_lineage"]
        require(failures,
                len(lineage) == 5 and
                all(len(item["raw_run_sha256"]) == 64 for item in lineage) and
                "did not name a Git commit" in lineage[-1]["reason"],
                "fail-closed lineage mismatch")
        cadence = value["cadence"]
        require(failures,
                cadence == {
                    "trigger": "accepted_delta_interval",
                    "accepted_deltas_before_checkpoint": 15,
                    "full_after_accepted_deltas": 15,
                    "previous_anchor":
                        "tests/hil/evidence/board-01-s5-runtime-completeness-0.139.json",
                    "next_anchor": SUMMARY_RELATIVE,
                    "accepted_deltas_after_checkpoint": 0,
                } and policy["anchor_evidence"] == SUMMARY_RELATIVE and
                policy["full_after_accepted_deltas"] == 15,
                "cadence reset/policy anchor mismatch")
        limitations = value["limitations"]
        require(failures,
                all(limitations[field] is False for field in (
                    "release_promotion", "s5_rf_positive_gate",
                    "instrumented_rf_claim",
                    "physical_led_color_photo_claim")),
                "checkpoint limitations are not explicit")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Periodic full HIL checkpoint passed: Home/RF/Targets/companion, "
          "exact CID, unchanged storage/heap, final Home/lease 0, cadence 0/15")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
