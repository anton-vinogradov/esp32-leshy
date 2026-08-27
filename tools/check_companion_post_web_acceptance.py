#!/usr/bin/env python3
"""Fail closed unless exact 0.196.2 post-Web acceptance is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT / "tests/hil/evidence/board-01-companion-post-web-0.196.2.json"
)


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] ==
            "leshy.hil.companion_post_web.acceptance.v1"
            and value["status"] == "pass_post_web_reopen"
            and value["evidence_ids"] == [
                "E-BUILD-153", "E-AUTO-125", "E-HIL-183",
                "E-COMPANION-007",
            ]
            and value["firmware_source_commit"] ==
            "7272d237ebb65e4b700ad8c64a32b48fc779ad75"
            and value["verification_source_commit"] ==
            "7272d237ebb65e4b700ad8c64a32b48fc779ad75"
            and candidate == {
                "app_elf_sha256":
                "e62de8246ef55246837271f97737f1aae53357869e2f5f81fc80a9d2711a8764",
                "firmware_bytes": 3360560,
                "firmware_sha256":
                "3bbf0bf64f3f3ea75af1c2ee50ade8ce3c3dbc680e38de662c48d8369ac5e946",
                "linked_flash_bytes": 3360064,
                "map_sha256":
                "5b9d66eb045098ade3e9f64c4dd37049c1a871c9e1d3ace2d6df7785cacd53c2",
                "static_ram_bytes": 223112,
                "version":
                "0.196.2-companion-post-web-shared-scratch",
            }
        ):
            failures.append("candidate/source/evidence identity mismatch")

        if not (
            value["exact_cid"] ==
            "FE343253440000002000000055019CB7"
            and value["installation"] == {
                "application_flash_count": 1,
                "exact_flash_reused": False,
            }
            and value["transport"] == {
                "active_mac_wifi_touched": False,
                "cardputer_ports_opened": 0,
                "host_network_tools_invoked": False,
                "opened_ports": ["/dev/cu.usbmodem2101"],
                "serial_port_discovery_calls": 0,
                "softap_associated_stations": 0,
            }
        ):
            failures.append("CID/install/USB/Mac-network isolation mismatch")

        memory = value["memory_contract"]
        if not (
            memory == {
                "admission_scratch_bytes": 11272,
                "esp_netif_deinit_supported": False,
                "network_core_process_lifetime": True,
                "session_codec_bytes": 22856,
                "shared_union_static_ram_added_bytes": 0,
                "survey_worker_lifecycle_exclusive_after_web": True,
                "target_codec_bytes": 24808,
                "target_codec_heap_allocation_removed": True,
            }
        ):
            failures.append("static shared-memory contract mismatch")

        lifecycle = value["softap_lifecycle"]
        active = lifecycle["active"]
        stopped = lifecycle["stopped"]
        reopened = lifecycle["post_web_targets"]
        final = lifecycle["final"]
        if not (
            lifecycle["staged_inert"] is True
            and active["server_active"] is True
            and active["associated_stations"] == 0
            and active["credential_exposed_over_diagnostic"] is False
            and active["credential_persisted"] is False
            and active["survey_worker_suspended"] is True
            and active["targets_suspended"] is True
            and active["lease_mask"] == 15
            and stopped["server_active"] is False
            and stopped["cleanup_complete"] is True
            and stopped["credential_present"] is False
            and stopped["associated_stations"] == 0
            and stopped["survey_worker_suspended"] is True
            and stopped["lease_mask"] == 13
            and reopened == {
                "associated_stations": 0,
                "lease_mask": 13,
                "network_core_ready": True,
                "server_active": False,
                "survey_worker_suspended": True,
            }
            and final == {
                "associated_stations": 0,
                "credential_present": False,
                "lease_mask": 0,
                "network_core_ready": True,
                "server_active": False,
                "survey_worker_suspended": False,
            }
        ):
            failures.append("device-only SoftAP/reopen/final lifecycle mismatch")

        reopen = value["post_web_reopen"]
        if not (
            reopen == {
                "blocked_write_attempts": 0,
                "comparison_items": 7,
                "filesystem_mount_attempts": 1,
                "filesystem_mount_error": 0,
                "heap_free_after_targets_release": 75760,
                "heap_free_before_targets_load": 96624,
                "identity_attempts": 1,
                "identity_cleanup_complete": True,
                "load_watchdog_feeds": 11,
                "target_state_generation": 17,
                "targets": 16,
                "workspace_allocated": True,
            }
        ):
            failures.append("post-Web Targets reopen mismatch")

        snapshot = value["offline_regression"]
        if not (
            snapshot["schema"] == "leshy.companion.offline.v1"
            and snapshot["snapshot_id"] ==
            "29537acfa1b9f0b6a51851ecb8b8b585cf17391c63a13329ed59db5b1eeede89"
            and snapshot["file_sha256"] ==
            "487eb2c6efbfd0644f951e5f97b4dc1b549cfec391601693d40ad74bceeee6bc"
            and snapshot["bytes"] == 11521
            and snapshot["counts"] == {
                "comparison_items": 7, "sessions": 2, "targets": 16,
            }
            and snapshot["complete_target_details"] == 16
            and snapshot["canonical_round_trip"] is True
            and snapshot["matched_accepted_0_195_snapshot"] is True
            and snapshot["private_payload_retained"] is False
        ):
            failures.append("offline USB regression/privacy mismatch")

        precursors = value["precursors"]
        if not (
            len(precursors) == 2
            and [item["candidate"] for item in precursors] == [
                "0.196.0-companion-post-web-admission",
                "0.196.1-companion-post-web-shared-codec",
            ]
            and [item["status"] for item in precursors] == [
                "target_state_workspace_unavailable", "admission_rejected",
            ]
            and [item["workspace_allocated"] for item in precursors] == [
                False, True,
            ]
            and all(item["cleanup_complete"] is True for item in precursors)
            and all(item["final_lease_mask"] == 0 for item in precursors)
            and all(len(item["run_sha256"]) == 64 for item in precursors)
        ):
            failures.append("fail-closed precursor lineage mismatch")

        final_safety = value["safety_and_final"]
        if not (
            final_safety == {
                "buzzer_inactive": True,
                "input_queue_drops": 0,
                "input_read_errors": 0,
                "lease_mask": 0,
                "nrf_ce_inactive": True,
                "page": "home",
                "raw_radio_tx_commands": 0,
                "runtime_owner": "none",
                "software_quiesce_complete": True,
                "storage_write_commands": 0,
                "survey_worker_restored": True,
            }
            and value["physical_cadence"] == {
                "accepted_since_full": 4, "full_gate_at": 15,
            }
            and len(value["raw_run_sha256"]) == 64
        ):
            failures.append("final safety/cadence/run identity mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Companion post-Web acceptance passed: device-only SoftAP had zero "
        "clients, Targets reopened through shared static RAM, offline USB "
        "stayed deterministic, Mac Wi-Fi untouched and final lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
