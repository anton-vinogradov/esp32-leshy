#!/usr/bin/env python3
"""Fail closed unless exact 0.172 companion Target-mutation evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-companion-target-mutate-0.172.json"


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] == "leshy.companion_target_mutation_hil.summary.v1"
            and value["status"] == "pass"
            and value["evidence_ids"] == [
                "E-BUILD-149", "E-AUTO-121", "E-HIL-180",
                "E-COMPANION-003"
            ]
            and value["firmware_source_commit"] ==
            "6ec3a198562c2cffc998b18bbd5e0738dcae3428"
            and value["verification_source_commit"] ==
            "48d296537a8eb358663420918b19151e2aa19c09"
            and candidate["version"] == "0.172.0-companion-target-mutate"
            and candidate["firmware_sha256"] ==
            "7038ac9bd5995cea7b1dd203342e38514ced0b5b678fb625ef506c093b104e1c"
            and candidate["app_elf_sha256"] ==
            "36ae2320517acf5625904aa5989d9253cce53c895ca6453ece39f81864df8da7"
            and candidate["factory_sha256"] ==
            "edf50e23cf071428c29c3031a1ecee7510e605bdd6c96aa0d9f9a4f0cb1f6658"
            and candidate["map_sha256"] ==
            "8abb1b91b2273838171604ac427bedb22a16144cd23f3d483d249a4e1d926210"
            and candidate["partitions_sha256"] ==
            "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3"
            and candidate["firmware_bytes"] == 3183200
            and candidate["static_ram_bytes"] == 214992
            and candidate["linked_flash_bytes"] == 3183044
        ):
            failures.append("candidate identity/build budget mismatch")

        connection = value["connection"]
        if not (
            connection["transport"] == "usb_serial_ndjson"
            and connection["max_frame_bytes"] == 512
            and connection["scopes"] == ["target.read", "target.mutate"]
            and connection["capabilities"] == [
                "target.list", "target.detail", "target.favorite.set",
                "target.name.set", "target.notes.set", "target.tag.add",
                "target.tag.remove"
            ]
        ):
            failures.append("scoped connection/capability mismatch")

        installation = value["installation"]
        if not (
            value["exact_cid"] == "FE343253440000002000000055019CB7"
            and installation == {
                "candidate_reused_by_pass": True,
                "lineage_flash_count": 1,
                "pass_flash_count": 0,
                "precursor_run_sha256":
                "f9a1339045dc8a400d6b31fbc48912507cfd381bc38853a4275e6ddaec3e685b",
            }
            and value["usb"] == {
                "cardputer_ports_opened": 0,
                "opened_ports": ["/dev/cu.usbmodem2101"],
                "port_discovery_calls": 0,
            }
        ):
            failures.append("candidate installation/CID/USB isolation mismatch")

        mutation = value["mutation"]
        if not (
            mutation["action"] == "target.favorite.set"
            and mutation["target_id"] == "3D62133018D6600F54F93D57F0CAD54A"
            and mutation["atomic_commits"] == 2
            and mutation["revision_sequence"] == [10, 11, 12]
            and mutation["state_generation_sequence"] == [15, 16, 17]
            and mutation["favorite_sequence"] == [False, True, False]
            and mutation["write_calls_per_commit"] == [3, 3]
            and mutation["file_syncs_per_commit"] == [3, 3]
            and mutation["directory_syncs_per_commit"] == [3, 3]
            and len(mutation["mutation_ids"]) == 2
            and len(set(mutation["mutation_ids"])) == 2
            and all(len(item) == 32 and int(item, 16) != 0
                    for item in mutation["mutation_ids"])
        ):
            failures.append("confirmed mutation/atomic publication mismatch")

        if value["negative"] != {
            "changed_token": "unknown_mutation",
            "home_denied": "scope_unavailable",
            "no_op": "unchanged",
            "replayed_confirm": "already_confirmed",
            "revoked_after_exit": "unknown_mutation",
            "stale_revision": "revision_conflict",
            "unknown_confirm": "unknown_mutation",
        }:
            failures.append("fail-closed negative matrix mismatch")

        cold = value["cold_reopen"]
        if not (
            cold["target_state_generation"] == 17
            and cold["target_revision"] == 12
            and cold["favorite"] is False
            and cold["catalog_generation"] == 161
            and cold["catalog_observations"] == 59
            and cold["mounted_read_only"] is True
            and cold["physical_write_calls"] == 0
            and cold["boot_recovery_attempts"] == 1
            and cold["boot_recovery_transient_retries"] == 0
            and cold["boot_recovery_timeout_restarts"] == 0
            and cold["boot_recovery_cleanup_complete"] is True
            and cold["reset_capture"]["open_attempts"] == 1
            and cold["reset_capture"]["ready_marker_ms"] < 2000
            and len(cold["reset_capture"]["sha256"]) == 64
        ):
            failures.append("cold reopen/native USB reconnect mismatch")

        precursors = value["failed_precursors"]
        if not (
            len(precursors) == 2
            and [item["classification"] for item in precursors] == [
                "harness_navigation_assumption", "stale_native_usb_descriptor"
            ]
            and [item["cleanup_complete"] for item in precursors] == [True, False]
            and all(item["firmware_failure"] is False for item in precursors)
            and [item["physical_power_cycle_required"] for item in precursors] ==
                [False, True]
            and all(len(item["run_sha256"]) == 64 for item in precursors)
        ):
            failures.append("failed precursor/root-cause lineage mismatch")

        reset_fix = value["reset_transport_fix"]
        if not (
            reset_fix["root_cause"] ==
            "host_kept_stale_native_usb_descriptor_open_across_reset"
            and reset_fix["strategy"] ==
            "close_reset_handle_then_reopen_exact_port_until_ready"
            and reset_fix["firmware_change_required"] is False
            and reset_fix["fixed_source_commit"] ==
            "48d296537a8eb358663420918b19151e2aa19c09"
            and reset_fix["contract_checker"] ==
            "tools/check_native_usb_reset_contract.py"
        ):
            failures.append("native USB reset fix mismatch")

        final = value["final"]
        if not (
            final["heap_total"] == 163812
            and final["heap_free_before"] == final["heap_free_after"] == 91068
            and final["heap_min_after_reset"] == 17344
            and final["input_queue_drops"] == 0
            and final["input_read_errors"] == 0
            and final["radio_tx_commands"] == 0
            and final["buzzer_inactive"] is True
            and final["nrf_ce_inactive"] is True
            and final["software_quiesce_complete"] is True
            and final["page"] == "home"
            and final["runtime_owner"] == "none"
            and final["lease_mask"] == 0
            and value["physical_cadence"] == {
                "accepted_since_full": 1, "full_gate_at": 15
            }
            and len(value["raw_run_sha256"]) == 64
        ):
            failures.append("final safety/resource/cadence mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Companion mutation delta acceptance passed: exact preview/confirm, "
        "two atomic restores, reconnect-aware cold reopen, zero Cardputer/TX/leaks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
