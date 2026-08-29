#!/usr/bin/env python3
"""Fail closed unless the current periodic full HIL checkpoint is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_RELATIVE = (
    "tests/hil/evidence/board-01-cadence-full-1.0.0-dev.252.json"
)
SUMMARY_PATH = ROOT / SUMMARY_RELATIVE
POLICY_PATH = ROOT / "tests/hil/hil-cadence.v1.json"
SOURCE = "30530812efe045aadd112d8b1b0961a48a48b89b"
CID = "FE343253440000002000000055019CB7"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest_shape(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value))


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        require(
            failures,
            value["schema"] == "leshy.hil_cadence_full.summary.v2" and
            value["status"] == "pass_full_checkpoint" and
            value["evidence_ids"] == [
                "E-AUTO-155", "E-HIL-196", "E-CADENCE-002"
            ] and value["firmware_source_commit"] == SOURCE,
            "summary/source identity mismatch")
        require(
            failures,
            candidate == {
                "version": "1.0.0-dev.252",
                "firmware_sha256":
                    "7cab8fd8a85b9fb437d21cdbc6d81e4a24aa050a814a9714337697d5cdb100a1",
                "factory_sha256":
                    "b581fff7b8911250b549e20414a409f797fd133086782139fee599fd2ce4bd45",
                "app_elf_sha256":
                    "19f2667f3b3a1a755417dce602f29977f04cc977541c04b33045bd8f4e3bf101",
                "map_sha256":
                    "f46bdc1d538014a3c8f4cb5b053354d279cb543d1da8a083d9fc65c045da1d34",
                "partitions_sha256":
                    "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3",
                "firmware_bytes": 3436112,
                "factory_bytes": 3501648,
                "static_ram_bytes": 231056,
                "linked_flash_bytes": 3435604,
                "ota_slot_free_bytes": 758192,
            }, "candidate identity/build budget mismatch")

        board = value["board"]
        require(
            failures,
            board == {
                "id": "board-01",
                "port": "/dev/cu.usbmodem2101",
                "mac": "1c:db:d4:87:90:d4",
                "exact_cid": CID,
                "candidate_flash_count": 1,
                "additional_full_checkpoint_flashes": 0,
                "serial_port_discovery_calls": 0,
                "cardputer_ports_opened": 0,
                "active_mac_wifi_touched": False,
            }, "board/USB/flash isolation mismatch")

        home = value["home_matrix"]
        require(
            failures,
            digest_shape(home["raw_run_sha256"]) and
            home["independent_checker"] == "pass" and
            home["home_items"] == [
                "wifi", "ble", "spectrum24", "subghz", "capture",
                "targets", "library", "device"
            ] and home["automatic_screens"] == 20 and
            home["manual_button_presses"] == 0 and
            home["tx_or_storage_side_effects"] == 0,
            "Home matrix mismatch")
        for receiver in ("nrf24_waterfall", "cc1101_waterfall"):
            waterfall = home[receiver]
            require(
                failures,
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
        require(
            failures,
            digest_shape(targets["raw_run_sha256"]) and
            targets["exact_flash_reused"] is True and
            targets["survey_pair"] == [165, 166] and
            targets["new_survey_cycles"] == 0 and
            targets["catalog_count"] == 16 and
            targets["visible_target_count"] == 5 and
            targets["comparison_count"] == 5 and
            targets["compare_counts"] == {
                "added": 2, "changed": 0,
                "removed": 2, "unchanged": 1,
            } and targets["detail_opened"] is True and
            targets["released_heap_bytes"] == 73608 and
            targets["cleanup_complete"] is True and
            targets["radio_tx_commands"] == 0 and
            targets["storage_writes"] == 0,
            "Targets matrix mismatch")

        companion = value["companion_matrix"]
        require(
            failures,
            digest_shape(companion["raw_run_sha256"]) and
            companion["exact_flash_reused"] is True and
            companion["transport"] == "usb_serial_ndjson" and
            companion["max_frame_bytes"] == 512 and
            companion["sessions"] == 2 and
            companion["session_generations"] == [165, 166] and
            companion["catalog_count"] == 16 and
            companion["comparison_count"] == 5 and
            companion["read_scopes"] == [
                "session.read", "target.read", "target.compare"
            ] and companion["negative_contracts"] == {
                "home": "scope_unavailable",
                "oversized_513": "frame_too_large",
                "truncated": "malformed_json",
                "unknown_field": "unknown_field",
                "invalid_offset": "offset_out_of_range",
                "mutation": "scope_dependency_missing",
                "after_exit": "not_connected",
            } and companion["heap_free_before"] == 73608 and
            companion["heap_free_after"] == 73608 and
            companion["radio_tx_commands"] == 0 and
            companion["storage_write_commands"] == 0 and
            companion["host_network_tools_invoked"] is False and
            companion["active_mac_wifi_touched"] is False,
            "companion matrix mismatch")

        require(
            failures,
            value["continuity"] == {
                "generation_before": 166,
                "generation_after": 166,
                "observations_before": 17,
                "observations_after": 17,
                "physical_write_calls": 0,
                "heap_total_before": 147748,
                "heap_total_after": 147748,
                "heap_free_before": 73608,
                "heap_free_after": 73608,
                "input_read_errors": 0,
                "input_queue_drops": 0,
            }, "storage/heap/input continuity mismatch")
        require(
            failures,
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
        require(
            failures,
            len(lineage) == 2 and
            digest_shape(lineage[0]["raw_run_sha256"]) and
            lineage[1]["raw_run_sha256"] is None and
            all(item["reason"] for item in lineage),
            "fail-closed lineage mismatch")
        require(
            failures,
            value["cadence"] == {
                "trigger": "accepted_delta_interval",
                "accepted_deltas_before_checkpoint": 15,
                "full_after_accepted_deltas": 15,
                "previous_anchor":
                    "tests/hil/evidence/board-01-cadence-full-0.171.json",
                "next_anchor": SUMMARY_RELATIVE,
                "accepted_deltas_after_checkpoint": 0,
            } and policy["anchor_evidence"] == SUMMARY_RELATIVE and
            policy["full_after_accepted_deltas"] == 15,
            "cadence reset/policy anchor mismatch")
        limitations = value["limitations"]
        require(
            failures,
            all(limitations[field] is False for field in (
                "release_promotion", "s5_rf_positive_gate",
                "instrumented_rf_claim", "physical_led_color_photo_claim"
            )), "checkpoint limitations are not explicit")
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
