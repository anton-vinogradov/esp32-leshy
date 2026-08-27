#!/usr/bin/env python3
"""Fail closed unless retained exact 1.0.0-dev.209 DEMO-S6 is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-stage-demo-s6-1.0.0-dev.209.json"
)


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        if not (
            value["schema"] == "leshy.hil.stage_demo_s6.acceptance.v1"
            and value["status"] == "pass_demo_path"
            and value["evidence_ids"] == [
                "E-AUTO-132", "E-HIL-189", "E-DEMO-006",
            ]
            and value["board"] == "board-01"
            and value["port"] == "/dev/cu.usbmodem2101"
            and value["rom_mac"] == "1c:db:d4:87:90:d4"
            and value["exact_cid"] == "FE343253440000002000000055019CB7"
            and value["candidate"] == {
                "app_elf_sha256":
                    "38d3cf0242707a13407c3123a207ab0c8e942242336ec396b31ccfc89083d868",
                "firmware_sha256":
                    "63f55328d23082943945659fb63d55a771d388b427f5eca29dcecd2178aa3bab",
                "version": "1.0.0-dev.209",
            }
            and value["firmware_source_commit"] ==
                "e04d98dd3c5e5d494c615e12f2897dc3207272a9"
            and value["verification_source_commit"] ==
                "410bac40d862ab29c3349a89fa2a026755cdb8fd"
        ):
            failures.append("candidate/board/evidence identity mismatch")

        if value["installation"] != {
            "application_flashes_for_demo_continuation": 0,
            "candidate_application_flashes_total": 1,
            "exact_flash_reused": True,
            "survey_children_reused": True,
        }:
            failures.append("one-flash/reuse lineage mismatch")
        survey = value["survey_pair"]
        if not (
            survey["generation_pair"] == [164, 165]
            and survey["observations"] == [52, 49]
            and survey["both_passed"] is True
            and survey["both_no_flash"] is True
            and survey["both_final_cleanup_complete"] is True
            and len(survey["baseline_run_sha256"]) == 64
            and len(survey["repeat_run_sha256"]) == 64
        ):
            failures.append("contiguous Survey pair mismatch")

        targets = value["targets"]
        if not (
            targets["catalog_targets"] == 16
            and targets["comparison_items"] == 5
            and targets["comparison_classes"] == [
                "removed", "unchanged", "unchanged", "unchanged",
                "unchanged",
            ]
            and targets["evidence_views_opened"] == 5
            and targets["evidence_selections"] == [0, 1, 2, 3, 4]
            and targets["mutation_capable"] is True
            and targets["write_in_flight"] is False
            and targets["blocked_write_attempts"] == 0
            and targets["filesystem_mount_error"] == 0
            and targets["storage_write_calls"] == 0
            and targets["radio_tx_commands"] == 0
            and targets["heap_free_before"] == 80316
            and targets["heap_free_after_release"] == 80316
        ):
            failures.append("Targets/every-evidence/release mismatch")

        companion = value["offline_companion"]
        if not (
            companion["protocol"] == 1
            and companion["transport"] == "usb_serial_ndjson"
            and companion["sessions"] == 2
            and companion["targets"] == 16
            and companion["comparison_items"] == 5
            and companion["snapshot_bytes"] == 11882
            and companion["snapshot_id"] ==
                "840f77ecf3ba46febd1517cb331bbfb9f32ecc0b0eae08e97a3e96ca65e1d035"
            and companion["snapshot_sha256"] ==
                "4f7c61bcd7ea24730f202b343345581f92979627d7f4f18da59ba8519dae5be5"
            and companion["canonical_round_trip"] is True
            and companion["search_fields"] == ["identities", "name"]
            and companion["search_matches"] == [1, 10]
        ):
            failures.append("offline companion snapshot/search mismatch")

        if value["isolation"] != {
            "active_mac_wifi_touched": False,
            "cardputer_ports_opened": 0,
            "host_network_tools_invoked": False,
            "opened_ports": ["/dev/cu.usbmodem2101"],
            "serial_port_discovery_calls": 0,
            "wifi_softap_started": False,
        }:
            failures.append("USB/Cardputer/Mac-network isolation mismatch")
        if value["final_safety"] != {
            "companion_cleanup_complete": True,
            "lease_mask": 0,
            "page": "home",
            "runtime_owner": "none",
            "safety_latched": False,
            "safety_state": "armed",
            "targets_cleanup_complete": True,
        }:
            failures.append("final cleanup/safety mismatch")
        if not (
            value["cadence"] == {
                "accepted_deltas_since_full": 5,
                "advanced_by_demo_reuse": False,
                "full_gate_at": 15,
            }
            and value["s6_exit_eligible"] is False
            and value["remaining_blockers"] == [
                "physical_http_parity_requires_dedicated_client",
                "s5_predecessor_physical_gate_requires_replacement_div",
            ]
            and all(len(item) == 64 for item in value["raw_hashes"].values())
        ):
            failures.append("cadence/hash/blocker honesty mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "DEMO-S6 physical acceptance passed: exact generations 164/165, "
        "all five conclusions opened, canonical offline USB snapshot, zero "
        "Mac Wi-Fi/Cardputer/TX/write effects and final Home/none/lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
