#!/usr/bin/env python3
"""Fail closed unless the dev.357 full checkpoint summary is intact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-cadence-full-1.0.0-dev.357.json"
SOURCE = "56e6ebe67b2b4d2e77e28bbf2cf0d29bed17a568"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest_shape(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def main() -> int:
    failures: list[str] = []
    value = json.loads(SUMMARY.read_text(encoding="utf-8"))
    candidate = value.get("candidate", {})
    require(
        failures,
        value.get("schema") == "leshy.hil_cadence_full.summary.v3"
        and value.get("status") == "pass_full_checkpoint"
        and value.get("firmware_source_commit") == SOURCE,
        "summary/source identity mismatch",
    )
    require(
        failures,
        value.get("evidence_ids")
        == [
            "E-BUILD-231",
            "E-AUTO-207",
            "E-HIL-230",
            "E-UX-084",
            "E-STORAGE-075",
            "E-CADENCE-004",
            "RB-M243",
        ],
        "evidence identifiers mismatch",
    )
    require(
        failures,
        candidate.get("version") == "1.0.0-dev.357"
        and candidate.get("firmware_bytes") == 3637024
        and candidate.get("factory_bytes") == 3702560
        and candidate.get("static_ram_bytes") == 234976
        and candidate.get("linked_flash_bytes") == 3636516
        and candidate.get("ota_slot_free_bytes") == 557280
        and all(
            digest_shape(candidate.get(field))
            for field in (
                "firmware_sha256",
                "factory_sha256",
                "app_elf_sha256",
                "map_sha256",
                "partitions_sha256",
            )
        ),
        "candidate identity/resource mismatch",
    )
    board = value.get("board", {})
    require(
        failures,
        board.get("id") == "board-01"
        and board.get("media_profile") == "media-01"
        and board.get("configured_identity_match") is True
        and board.get("raw_identifiers_retained") is False
        and not any(field in board for field in ("port", "mac", "exact_cid"))
        and board.get("candidate_flash_count") == 1
        and board.get("additional_checkpoint_flashes") == 0
        and board.get("clone_port_touched") is False
        and board.get("cardputer_ports_opened") == 0
        and board.get("active_mac_wifi_touched") is False,
        "board isolation mismatch",
    )
    ble = value.get("ble_lifecycle", {})
    require(
        failures,
        ble.get("independent_checker") == "pass"
        and ble.get("entry_transport_retries") == 0
        and ble.get("unique_devices", 0) > 0
        and ble.get("list_changed_pixels", 0) > 0
        and ble.get("list_chrome_changed_pixels") == 0
        and ble.get("list_row_repaints")
        == ble.get("list_full_row_repaints") + ble.get("list_signal_delta_repaints")
        and ble.get("list_full_row_repaints", 0)
        >= ble.get("list_identity_replacements", 0)
        and ble.get("detail_changed_pixels", 0) > 0
        and ble.get("detail_static_changed_pixels") == 0
        and ble.get("detail_chrome_changed_pixels") == 0
        and ble.get("allocation_failures") == 0
        and ble.get("direct_fallbacks") == 0
        and ble.get("heap_total_after_first") == ble.get("heap_total_after_second")
        and ble.get("heap_free_after_first") == ble.get("heap_free_after_second")
        and ble.get("driver_drops") == 0
        and ble.get("storage_writes") == 0,
        "BLE lifecycle/repaint/heap mismatch",
    )
    home = value.get("home_matrix", {})
    require(
        failures,
        home.get("automatic_screens") == 21
        and home.get("manual_button_presses") == 0
        and len(home.get("home_items", [])) == 9
        and home.get("nrf_graph_changed_pixels", 0) > 0
        and home.get("cc_graph_changed_pixels", 0) > 0
        and home.get("waterfall_chrome_changed_pixels") == 0
        and home.get("heap_total_before") == home.get("heap_total_after")
        and home.get("heap_free_before") == home.get("heap_free_after")
        and home.get("input_read_errors") == 0
        and home.get("input_queue_drops") == 0,
        "Home/RF matrix mismatch",
    )
    targets = value.get("targets_matrix", {})
    require(
        failures,
        targets.get("exact_flash_reused") is True
        and targets.get("survey_pair") == [7, 8]
        and targets.get("new_survey_cycles") == 0
        and targets.get("catalog_count") == 16
        and targets.get("comparison_count") == 16
        and targets.get("compare_counts")
        == {"added": 1, "changed": 1, "removed": 1, "unchanged": 13}
        and targets.get("cleanup_complete") is True
        and targets.get("radio_tx_commands") == 0
        and targets.get("storage_writes") == 0,
        "Targets matrix mismatch",
    )
    companion = value.get("companion_matrix", {})
    require(
        failures,
        companion.get("exact_flash_reused") is True
        and companion.get("transport") == "usb_serial_ndjson"
        and companion.get("max_frame_bytes") == 512
        and companion.get("sessions") == 2
        and companion.get("session_generations") == [7, 8]
        and companion.get("catalog_count") == 16
        and companion.get("comparison_count") == 16
        and companion.get("heap_total_before") == companion.get("heap_total_after")
        and companion.get("heap_free_before") == companion.get("heap_free_after")
        and companion.get("radio_tx_commands") == 0
        and companion.get("storage_write_commands") == 0
        and companion.get("host_network_tools_invoked") is False
        and companion.get("active_mac_wifi_touched") is False
        and companion.get("wifi_softap_started") is False
        and companion.get("offline_snapshot", {}).get("canonical_round_trip") is True,
        "companion matrix mismatch",
    )
    require(
        failures,
        all(
            digest_shape(section.get("raw_run_sha256"))
            for section in (ble, home, targets, companion)
        )
        and all(
            digest_shape(item.get("raw_run_sha256"))
            for item in value.get("fail_closed_lineage", [])
        ),
        "run/lineage digest shape mismatch",
    )
    require(
        failures,
        value.get("final")
        == {
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "buzzer_inactive": True,
            "nrf_ce_inactive": True,
            "software_quiesce_complete": True,
        }
        and value.get("cadence", {}).get("accepted_deltas_after_checkpoint") == 0
        and value.get("limitations", {}).get("release_promotion") is False,
        "final/cadence/limitations mismatch",
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        json.dumps(
            {
                "schema": value["schema"],
                "status": value["status"],
                "version": candidate["version"],
                "source_commit": SOURCE,
                "sha256": hashlib.sha256(SUMMARY.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
