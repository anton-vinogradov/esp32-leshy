#!/usr/bin/env python3
"""Fail closed unless exact 0.195 offline companion evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-companion-offline-0.195.json"


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] == "leshy.hil.companion_offline.acceptance.v1"
            and value["status"] == "pass_offline"
            and value["evidence_ids"] == [
                "E-BUILD-152", "E-AUTO-124", "E-HIL-182",
                "E-COMPANION-006",
            ]
            and value["firmware_source_commit"] ==
            "52570c587b34f73a9d35628b554cbac5b76063f8"
            and value["verification_source_commit"] ==
            "ad3e63d484700ab174286d38e8e704805f5bd8d9"
            and candidate == {
                "app_elf_sha256":
                "8b1a0cdaa6ddc0e149285811a39e533cd1b3bc3025715828b88d42c832fb214a",
                "firmware_bytes": 3360400,
                "firmware_sha256":
                "3e0fe72549d8400aa573089f4235e457bd643ee2b0f879a73eb05b94602326a6",
                "linked_flash_bytes": 3359896,
                "map_sha256":
                "761ce2a47cbbb39a7f0523675195b023acabbc7bd9dbe5072791665161334a61",
                "static_ram_bytes": 223112,
                "version": "0.195.0-companion-web-gzip-index",
            }
        ):
            failures.append("candidate/source/evidence identity mismatch")

        if not (
            value["exact_cid"] == "FE343253440000002000000055019CB7"
            and value["installation"] == {
                "application_flash_count": 0,
                "exact_flash_reused": True,
            }
            and value["transport"] == {
                "active_mac_wifi_touched": False,
                "cardputer_ports_opened": 0,
                "network_tools_invoked": False,
                "opened_ports": ["/dev/cu.usbmodem2101"],
                "serial_port_discovery_calls": 0,
            }
        ):
            failures.append("CID/install/USB/network isolation mismatch")

        connection = value["connection"]
        if connection != {
            "capabilities": [
                "session.list", "session.detail", "target.list",
                "target.detail", "target.compare",
            ],
            "max_frame_bytes": 512,
            "protocol": 1,
            "scopes": ["session.read", "target.read", "target.compare"],
            "transport": "usb_serial_ndjson",
        }:
            failures.append("native USB grant mismatch")

        snapshot = value["offline_snapshot"]
        retry = snapshot["deterministic_retry"]
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
            and snapshot["private_payload_retained"] is False
            and retry["matched"] is True
            and retry["earlier_snapshot_id"] == snapshot["snapshot_id"]
            and retry["earlier_file_sha256"] == snapshot["file_sha256"]
        ):
            failures.append("offline snapshot/determinism/privacy mismatch")

        search = value["search"]
        if not (
            search["host_covered_fields"] == [
                "name", "notes", "tags", "identities",
            ]
            and search["private_queries_retained"] is False
            and [item["field"] for item in search["physical_proofs"]] == [
                "identities", "name",
            ]
            and all(item["expected_target_matched"] is True
                    for item in search["physical_proofs"])
            and all(item["matches"] >= 1
                    for item in search["physical_proofs"])
            and all(len(item["query_sha256"]) == 64
                    for item in search["physical_proofs"])
        ):
            failures.append("offline search proof mismatch")

        media = value["media"]
        final = value["safety_and_final"]
        if not (
            media == {
                "blocked_write_attempts": 0,
                "boot_recovery_attempts": 1,
                "boot_recovery_cleanup_complete": True,
                "boot_recovery_transient_retries": 0,
                "generation": 161,
                "mounted_read_only": True,
                "observations": 59,
                "physical_write_calls": 0,
            }
            and final == {
                "buzzer_inactive": True,
                "heap_free_after": 82892,
                "heap_free_before": 82892,
                "input_queue_drops": 0,
                "input_read_errors": 0,
                "lease_mask": 0,
                "nrf_ce_inactive": True,
                "page": "home",
                "radio_tx_commands": 0,
                "runtime_owner": "none",
                "software_quiesce_complete": True,
                "storage_write_commands": 0,
                "targets_released_heap": 82892,
            }
        ):
            failures.append("read-only media/final safety mismatch")

        if value["framing"] != {
            "exact_512": "ok",
            "invalid_offset": "offset_out_of_range",
            "mutation_dependency": "scope_dependency_missing",
            "oversized_513": "frame_too_large",
            "post_exit": "not_connected",
            "truncated": "malformed_json",
            "unknown_field": "unknown_field",
        }:
            failures.append("bounded framing/negative matrix mismatch")

        precursors = value["precursors"]
        defect = value["known_open_defects"]
        if not (
            len(precursors) == 2
            and [item["checkpoint"] for item in precursors] == [
                "open_targets", "scope_denial",
            ]
            and precursors[0]["firmware_failure"] is True
            and precursors[0]["filesystem_mount_error"] == 257
            and precursors[0]["reset_regression"]["targets_runtime_event"] ==
            "ready"
            and precursors[0]["reset_regression"]["final_lease_mask"] == 0
            and precursors[1]["firmware_failure"] is False
            and all(item["cleanup_complete"] is True for item in precursors)
            and all(len(item["run_sha256"]) == 64 for item in precursors)
            and len(defect) == 1
            and defect[0]["classification"] ==
            "post_web_runtime_memory_not_fully_reclaimed"
            and defect[0]["firmware_failure"] is True
            and defect[0]["resolution"].startswith("open;")
        ):
            failures.append("precursor/open-defect lineage mismatch")

        if not (
            value["physical_cadence"] == {
                "accepted_since_full": 3, "full_gate_at": 15,
            }
            and len(value["raw_run_sha256"]) == 64
        ):
            failures.append("cadence/raw run identity mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Companion offline acceptance passed: canonical deterministic USB "
        "snapshot/search, private payload omitted, zero Mac Wi-Fi changes; "
        "post-Web device-memory defect remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
