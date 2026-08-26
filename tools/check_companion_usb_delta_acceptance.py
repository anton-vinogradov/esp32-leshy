#!/usr/bin/env python3
"""Fail closed unless exact 0.170 native-USB read evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-companion-usb-read-0.170.json"


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] == "leshy.companion_usb_delta_hil.summary.v1"
            and value["status"] == "pass"
            and value["evidence_ids"] == [
                "E-BUILD-147", "E-AUTO-118", "E-HIL-177",
                "E-COMPANION-002"
            ]
            and value["firmware_source_commit"] ==
            "b58fbc054522cecfca5dd4afcd6ea61098cb05c0"
            and candidate["version"] == "0.170.0-companion-usb-rx"
            and candidate["firmware_sha256"] ==
            "6275e94fd34cf28018cb761dc877717a668e2fedb8b5f4d9de6a213dfe0583ad"
            and candidate["app_elf_sha256"] ==
            "6c4da4273bfa0d11fc5b022125a320f61f45342ac34cc0ac870a3178fc0832cf"
            and candidate["factory_sha256"] ==
            "8f0a7a1696069225a96984480e88d66f9beacb7530399e28291e8ffde1b66528"
            and candidate["partitions_sha256"] ==
            "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3"
            and candidate["firmware_bytes"] == 3172576
            and candidate["static_ram_bytes"] == 214664
            and candidate["linked_flash_bytes"] == 3172080
        ):
            failures.append("candidate identity/build budget mismatch")
        if not (
            value["exact_cid"] == "FE343253440000002000000055019CB7"
            and value["flash_count"] == 1
            and value["usb"] == {
                "opened_ports": ["/dev/cu.usbmodem2101"],
                "cardputer_ports_opened": 0,
                "port_discovery_calls": 0,
            }
        ):
            failures.append("CID/USB isolation mismatch")
        connection = value["connection"]
        if not (
            connection["home_reason"] == "scope_unavailable"
            and connection["home_capabilities"] == []
            and connection["transport"] == "usb_serial_ndjson"
            and connection["max_frame_bytes"] == 512
            and connection["scopes"] == [
                "session.read", "target.read", "target.compare"
            ]
            and connection["capabilities"] == [
                "session.list", "session.detail", "target.list",
                "target.detail", "target.compare"
            ]
        ):
            failures.append("connection grant/lifecycle mismatch")
        if value["sessions"] != [
            {
                "source_id": "6097B09767B64D5064AC7C6050129303",
                "generation": 160, "observations": 49, "dropped": 0,
            },
            {
                "source_id": "F55E4440B07EDF00BBC2C84663B043F5",
                "generation": 161, "observations": 59, "dropped": 0,
            },
        ]:
            failures.append("Session projection mismatch")
        targets = value["targets"]
        if not (
            targets["catalog_count"] == targets["list_pages"] == 16
            and targets["compare_pages"] == 7
            and targets["compare_counts"] == {
                "added": 2, "removed": 1, "changed": 0, "unchanged": 4
            }
            and targets["detail_sections"] == [
                "summary", "notes", "tags", "identities", "evidence"
            ]
            and 1 <= targets["identity_attempts"] <= 8
            and targets["identity_transient_retries"] ==
                targets["identity_attempts"] - 1
            and targets["identity_cleanup_complete"] is True
            and 1 <= targets["filesystem_mount_attempts"] <= 3
            and targets["filesystem_mount_transient_retries"] ==
                targets["filesystem_mount_attempts"] - 1
            and targets["released_heap"] >= 92000
        ):
            failures.append("Target projection/retry/pagination mismatch")
        if value["framing"] != {
            "exact_512": "ok",
            "invalid_offset": "offset_out_of_range",
            "mutation_scope": "scope_denied",
            "oversized_513": "frame_too_large",
            "post_exit": "not_connected",
            "truncated": "malformed_json",
            "unknown_field": "unknown_field",
        }:
            failures.append("bounded frame/negative matrix mismatch")
        media = value["media"]
        final = value["final"]
        if not (
            media["mounted_read_only"] is True
            and media["physical_write_calls"] == 0
            and media["blocked_write_attempts"] == 0
            and media["cleanup_complete"] is True
            and media["generation"] == 161
            and media["observations"] == 59
            and final == {
                "buzzer_inactive": True,
                "heap_free_after": 92972,
                "heap_free_before": 92972,
                "input_queue_drops": 0,
                "lease_mask": 0,
                "page": "home",
                "radio_tx_commands": 0,
                "runtime_owner": "none",
                "safe_outputs_quiesced": True,
                "storage_write_commands": 0,
            }
        ):
            failures.append("read-only/final safety state mismatch")
        precursors = value["rejected_precursors"]
        if not (
            len(precursors) == 3
            and [item["checkpoint"] for item in precursors] == [
                "open_targets", "target_compare", "target_compare"
            ]
            and all(len(item["run_sha256"]) == 64 for item in precursors)
            and value["physical_cadence"] == {
                "accepted": 14, "full_gate_at": 15
            }
            and len(value["raw_run_sha256"]) == 64
        ):
            failures.append("rejected lineage/cadence mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Companion USB delta acceptance passed: exact bounded read API, "
          "read-only media, zero Cardputer ports/TX/writes/leaked lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
