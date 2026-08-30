#!/usr/bin/env python3
"""Fail closed unless the current periodic full HIL checkpoint is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_RELATIVE = (
    "tests/hil/evidence/board-01-cadence-full-1.0.0-dev.302.json"
)
SUMMARY_PATH = ROOT / SUMMARY_RELATIVE
POLICY_PATH = ROOT / "tests/hil/hil-cadence.v1.json"
SOURCE = "48a27c74cfb3dca1ff1c2ed612bb4a3019133451"
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
                "E-BUILD-205", "E-AUTO-180", "E-HIL-214",
                "E-CADENCE-003", "RB-M216"
            ] and value["firmware_source_commit"] == SOURCE and
            value["harness_commits"] == [
                SOURCE, "a7c9aca3bad9e278e857271df5f331bf72ad9f26"
            ], "summary/source/harness identity mismatch")
        require(
            failures,
            candidate == {
                "version": "1.0.0-dev.302",
                "firmware_sha256":
                    "bf20b0d6f163e5bb27d9fb948c72a0a5c7635bc5c8039cdf5878e5ca2be7cbc0",
                "factory_sha256":
                    "1b570ea9fcfc43b563aa0dc9ab3dec34a4aa576dbdf6b227fc2fcb326a115bf9",
                "app_elf_sha256":
                    "f10daa7434e147b0dedbac03d8724de5d68c2596ac59ee1ceb096a98a3928559",
                "map_sha256":
                    "dc6b90c1749fb7f45f9aa76d17d3fe3819a77fa290e13be11ce6103ae1871262",
                "partitions_sha256":
                    "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3",
                "firmware_bytes": 3534480,
                "factory_bytes": 3600016,
                "static_ram_bytes": 232496,
                "linked_flash_bytes": 3533980,
                "ota_slot_free_bytes": 659824,
            }, "candidate identity/build budget mismatch")

        require(failures, value["board"] == {
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
                "targets", "library", "lab", "device"
            ] and home["automatic_screens"] == 21 and
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
            targets["survey_pair"] == [7, 8] and
            targets["new_survey_cycles"] == 0 and
            targets["catalog_count"] == 16 and
            targets["visible_target_count"] == 16 and
            targets["comparison_count"] == 16 and
            targets["compare_counts"] == {
                "added": 1, "changed": 1,
                "removed": 1, "unchanged": 13,
            } and targets["evidence_views_opened"] == 16 and
            targets["automatic_screens"] == 4 and
            targets["released_heap_bytes"] == 71744 and
            targets["cleanup_complete"] is True and
            targets["radio_tx_commands"] == 0 and
            targets["storage_writes"] == 0,
            "Targets matrix mismatch")
        require(
            failures,
            targets["device_lock_fixture"] == {
                "ram_only_admission": True,
                "protected_ui_only": True,
                "credential_written": False,
                "data_key_replaced": False,
                "product_namespace_written_or_erased": False,
                "cleanup_proven": True,
                "hil_ended": True,
            }, "Targets Device Lock fixture mismatch")

        companion = value["companion_matrix"]
        require(
            failures,
            digest_shape(companion["raw_run_sha256"]) and
            companion["exact_flash_reused"] is True and
            companion["transport"] == "usb_serial_ndjson" and
            companion["max_frame_bytes"] == 512 and
            companion["sessions"] == 2 and
            companion["session_generations"] == [7, 8] and
            companion["catalog_count"] == 16 and
            companion["comparison_count"] == 16 and
            companion["compare_counts"] == {
                "added": 1, "changed": 1,
                "removed": 1, "unchanged": 13,
            } and companion["read_scopes"] == [
                "session.read", "target.read", "target.compare"
            ] and companion["negative_contracts"] == {
                "home": "scope_unavailable",
                "oversized_513": "frame_too_large",
                "truncated": "malformed_json",
                "unknown_field": "unknown_field",
                "invalid_offset": "offset_out_of_range",
                "mutation": "scope_denied",
                "after_exit": "not_connected",
            } and companion["offline_snapshot"] == {
                "snapshot_id":
                    "93997691f1d95149cce0c3e11cb611f6b325f334d4fea5b8a385ef7576e6ab3d",
                "sha256":
                    "7b471c94f30c77f953c8aa85caf7e3880b8b88e997f3fb4784a72dc0df9a8aea",
                "canonical_round_trip": True,
            } and companion["heap_free_before"] == 71744 and
            companion["heap_free_after"] == 71744 and
            companion["radio_tx_commands"] == 0 and
            companion["storage_write_commands"] == 0 and
            companion["host_network_tools_invoked"] is False and
            companion["active_mac_wifi_touched"] is False,
            "companion matrix mismatch")
        require(
            failures,
            companion["device_lock_fixture"] == {
                "ram_only_admission": True,
                "protected_ui_allowed": True,
                "companion_read_only": True,
                "mutation_scope_allowed": False,
                "credential_written": False,
                "data_key_replaced": False,
                "product_namespace_written_or_erased": False,
                "cleanup_proven": True,
                "hil_ended": True,
            }, "companion Device Lock fixture mismatch")

        require(failures, value["continuity"] == {
            "generation_before": 8,
            "generation_after": 8,
            "observations_before": 54,
            "observations_after": 54,
            "physical_write_calls": 0,
            "heap_total_before": 146308,
            "heap_total_after": 146308,
            "heap_free_before": 71744,
            "heap_free_after": 71744,
            "input_read_errors": 0,
            "input_queue_drops": 0,
        }, "storage/heap/input continuity mismatch")
        require(failures, value["cold_runtime_warmup"] == {
            "raw_run_sha256":
                "d492d54ec147c13acf5808c91c8124ce26001bd11aabcdb188ee1501b29c0496",
            "result": "fail_closed_then_stable",
            "cold_baseline_heap_free": 72004,
            "post_matrix_heap_free": 71744,
            "one_time_lazy_init_bytes": 260,
            "second_matrix_baseline_heap_free": 71744,
            "second_matrix_final_heap_free": 71744,
            "resources_released": True,
            "storage_continuity_preserved": True,
        }, "cold/warm heap lineage mismatch")
        require(failures, value["final"] == {
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
            len(lineage) == 6 and
            all(digest_shape(item["raw_run_sha256"]) and item["reason"]
                for item in lineage),
            "fail-closed lineage mismatch")
        require(
            failures,
            value["cadence"] == {
                "trigger": "accepted_delta_interval",
                "accepted_deltas_before_checkpoint": 15,
                "full_after_accepted_deltas": 15,
                "previous_anchor":
                    "tests/hil/evidence/board-01-cadence-full-1.0.0-dev.252.json",
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
                "instrumented_rf_claim", "physical_led_color_photo_claim",
                "cold_first_matrix_heap_invariance",
            )) and "260-byte" in limitations["reason"],
            "checkpoint limitations are not explicit")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Periodic full HIL checkpoint passed: Home/RF/Targets/companion, "
          "read-only Device Lock fixture, exact CID, stable warm heap, "
          "final Home/lease 0, cadence 0/15")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
