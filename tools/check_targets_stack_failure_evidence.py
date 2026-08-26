#!/usr/bin/env python3
"""Validate the retained, fail-closed Targets 0.146 physical failure."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-targets-stack-failure-0.146.json"
MOUNT_EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-targets-readonly-mount-failure-0.147.json"
)
RESET_EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-targets-inplace-reset-failure-0.148.json"
)
MERGE_EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-targets-merge-stack-failure-0.163.json"
)
FIXTURE_REOPEN_EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-targets-fixture-reopen-failure-0.164.json"
)
MERGED_REOPEN_RUNNER_EVIDENCE = (
    ROOT / "tests/hil/evidence/board-01-targets-merged-reopen-runner-failure-0.165.json"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(data["schema"] == "leshy.targets_stack_failure.evidence.v1", "unexpected schema")
    require(data["status"] == "failed", "failed candidate must not be accepted")
    require(data["classification"] == "retained_fail_closed", "failure must remain fail-closed")
    require(data["candidate"]["version"] == "0.146.0-targets", "unexpected failed version")
    require(len(data["candidate"]["firmware_sha256"]) == 64, "missing firmware identity")
    require(data["board"]["id"] == "board-01", "unexpected physical board")
    require(
        data["manual_reproduction"]["panic"] == "Stack canary watchpoint triggered (loopTask)",
        "stack-canary cause was not retained",
    )
    require(data["manual_reproduction"]["post_reset_reason_code"] == 4, "reset evidence missing")
    require("compareTargetSessions" in data["decoded_backtrace"], "decoded failing frame missing")
    require(data["radio_tx_commands"] == 0, "failure reproduction must remain receive-only")
    require(
        data["repair_gate"]["candidate_version"] == "0.147.0-targets-stack-safe",
        "repair candidate link missing",
    )
    require(data["failed_automated_run"]["status"] == "failed", "runner failure must not be hidden")
    mount = json.loads(MOUNT_EVIDENCE.read_text(encoding="utf-8"))
    require(
        mount["schema"] == "leshy.targets_readonly_mount_failure.evidence.v1",
        "unexpected mount-failure schema",
    )
    require(mount["status"] == "failed", "mount failure must not be accepted")
    require(mount["classification"] == "retained_fail_closed", "mount failure hidden")
    require(mount["failure"]["actual_status"] == "readonly_mount_failed", "wrong failure")
    require(mount["failure"]["expected_generations"] == [111, 112], "visit pair lost")
    require(all(visit["cleanup_complete"] for visit in mount["visits"]), "visit cleanup missing")
    require(sum(visit["scan_drops"] for visit in mount["visits"]) == 0, "visit drops hidden")
    require(mount["observations"]["stack_canary_observed"] is False, "0.146 fix regressed")
    require(mount["post_failure_cleanup"]["complete"] is True, "failure cleanup incomplete")
    require(mount["post_failure_cleanup"]["final_lease_mask"] == 0, "failure leaked lease")
    require(mount["source_binding"]["valid"] is False, "invalid runner binding was hidden")
    require(
        mount["source_binding"]["actual_head"] !=
        mount["source_binding"]["declared_source_commit"],
        "source mismatch evidence is inconsistent",
    )
    require(
        mount["repair_gate"]["short_regression_required_before_full_delta"] is True,
        "short regression gate missing",
    )
    reset = json.loads(RESET_EVIDENCE.read_text(encoding="utf-8"))
    require(
        reset["schema"] == "leshy.targets_inplace_reset_failure.evidence.v1",
        "unexpected in-place-reset failure schema",
    )
    require(reset["status"] == "failed", "0.148 failure must not be accepted")
    require(reset["classification"] == "retained_fail_closed", "0.148 failure hidden")
    require(reset["source_commit"] == "e7eedd8225c5c736b7d3c752b4f89f76da910f84",
            "0.148 exact source lost")
    require(reset["short_regression"]["flash_count"] == 1, "wrong flash count")
    require(reset["short_regression"]["storage_write_calls"] == 0, "write hidden")
    require(reset["short_regression"]["radio_tx_commands"] == 0, "TX hidden")
    require(reset["decoded_reproduction"]["stack_canary_observed"] is True,
            "stack canary missing")
    require(reset["decoded_reproduction"]["post_reset_reason_code"] == 4,
            "panic reset missing")
    require("TargetsController::reset():168" in
            reset["decoded_reproduction"]["decoded_frames"],
            "decoded reset frame missing")
    require(reset["post_failure_cleanup"]["complete"] is True,
            "0.148 cleanup incomplete")
    require(reset["post_failure_cleanup"]["final_lease_mask"] == 0,
            "0.148 lease leaked")
    require(reset["repair_gate"]["candidate_version"] ==
            "0.149.0-targets-inplace-reset", "repair version lost")
    require(reset["repair_gate"]["automatic_full_delta_after_failure"] is False,
            "failed short gate must forbid the full delta")
    merge = json.loads(MERGE_EVIDENCE.read_text(encoding="utf-8"))
    require(
        merge["schema"] == "leshy.targets_merge_stack_failure.evidence.v1",
        "unexpected merge-stack failure schema",
    )
    require(merge["status"] == "failed", "0.163 failure must not be accepted")
    require(merge["classification"] == "retained_fail_closed",
            "0.163 failure hidden")
    require(merge["source_commit"] ==
            "16834b2837302dd916fc4ffa7713e2285cf71f8f",
            "0.163 exact source lost")
    require(merge["failure"]["panic_reset_reason_code"] == 4,
            "0.163 panic reset missing")
    require(merge["failure"]["mutation_stage"] == "workspace_acquired",
            "0.163 last valid mutation stage lost")
    require(merge["failure"]["worker_stack_min_free_before_merge"] == 9896,
            "0.163 pre-merge worker stack observation lost")
    require(any("rebuildMergedCatalog:TargetMerge.cpp:38" in frame for frame in
                merge["failure"]["decoded_backtrace"]),
            "0.163 decoded failing frame missing")
    require(merge["fixture_isolation"]["product_target_state_touched"] is False,
            "0.163 touched product Targets state")
    require(merge["fixture_isolation"]["rf_tx_attempts"] == 0,
            "0.163 RF transmission hidden")
    require(merge["post_failure_restore"]["ota1_restore_verified"] is True,
            "0.163 OTA1 restore missing")
    require(merge["post_failure_restore"]["ota1_before_sha256"] ==
            merge["post_failure_restore"]["ota1_after_sha256"],
            "0.163 OTA1 was not restored exactly")
    require(merge["post_failure_restore"]["partition_table_restore_verified"] is True,
            "0.163 partition-table restore missing")
    require(merge["post_failure_restore"]["partition_table_before_sha256"] ==
            merge["post_failure_restore"]["partition_table_after_sha256"],
            "0.163 partition table was not restored exactly")
    require(merge["post_failure_restore"]["final_lease_mask"] == 0,
            "0.163 leaked a final lease")
    require(merge["post_failure_restore"]["final_cid"] ==
            "FE343253440000002000000055019CB7",
            "0.163 final product CID lost")
    require(merge["usb"]["opened_ports"] == ["/dev/cu.usbmodem2101"],
            "0.163 opened an unexpected serial port")
    require(merge["usb"]["cardputer_ports_opened"] == 0 and
            merge["usb"]["port_discovery_calls"] == 0,
            "0.163 Cardputer isolation lost")
    require(merge["repair_gate"]["candidate_version"] ==
            "0.164.0-targets-merge-inplace", "0.164 repair link missing")
    reopen = json.loads(FIXTURE_REOPEN_EVIDENCE.read_text(encoding="utf-8"))
    require(
        reopen["schema"] ==
        "leshy.targets_fixture_reopen_failure.evidence.v1",
        "unexpected fixture-reopen failure schema",
    )
    require(reopen["status"] == "failed", "0.164 failure must not be accepted")
    require(reopen["classification"] == "retained_fail_closed",
            "0.164 failure hidden")
    require(reopen["source_commit"] ==
            "b5cb6f4e3210ad720fa5924175078fc476c506bf",
            "0.164 exact source lost")
    require(reopen["failure"]["phase"] == "merged_cold_reopen",
            "0.164 failure phase lost")
    require(reopen["failure"]["expected_lease_mask"] == 13 and
            reopen["failure"]["actual_lease_mask"] == 1,
            "0.164 lease mismatch lost")
    require(reopen["merge_checkpoint"]["mutation_persisted"] is True and
            reopen["merge_checkpoint"]["mutation_status"] == "saved",
            "0.164 successful merge checkpoint lost")
    require(reopen["merge_checkpoint"]["stack_min_free"] == 8040,
            "0.164 repaired merge stack observation lost")
    require(reopen["merge_checkpoint"]["write_calls"] == 3 and
            reopen["merge_checkpoint"]["file_syncs"] == 3 and
            reopen["merge_checkpoint"]["directory_syncs"] == 3,
            "0.164 atomic merge save proof lost")
    require(reopen["post_failure_restore"]["ota1_restore_verified"] is True and
            reopen["post_failure_restore"]["ota1_before_sha256"] ==
            reopen["post_failure_restore"]["ota1_after_sha256"],
            "0.164 OTA1 was not restored exactly")
    require(reopen["post_failure_restore"]["partition_table_restore_verified"]
            is True and
            reopen["post_failure_restore"]["partition_table_before_sha256"] ==
            reopen["post_failure_restore"]["partition_table_after_sha256"],
            "0.164 partition table was not restored exactly")
    require(reopen["post_failure_restore"]["final_cid"] ==
            "FE343253440000002000000055019CB7" and
            reopen["post_failure_restore"]["final_lease_mask"] == 0,
            "0.164 final product continuity lost")
    require(reopen["usb"]["opened_ports"] == ["/dev/cu.usbmodem2101"] and
            reopen["usb"]["cardputer_ports_opened"] == 0 and
            reopen["usb"]["port_discovery_calls"] == 0,
            "0.164 Cardputer isolation lost")
    require(reopen["repair_gate"]["candidate_version"] ==
            "0.165.0-targets-fixture-reopen", "0.165 repair link missing")
    runner = json.loads(
        MERGED_REOPEN_RUNNER_EVIDENCE.read_text(encoding="utf-8"))
    require(
        runner["schema"] ==
        "leshy.targets_merged_reopen_runner_failure.evidence.v1",
        "unexpected merged-reopen runner failure schema",
    )
    require(runner["status"] == "failed" and
            runner["classification"] == "retained_fail_closed",
            "0.165 runner failure hidden")
    require(runner["source_commit"] ==
            "19a322c428d6efa52fe18f62041141e0cf6669d8",
            "0.165 exact source lost")
    require(runner["failure"]["phase"] == "merged_cold_reopen_navigation" and
            runner["failure"]["root_cause"] ==
            "runner_reused_pre_merge_two_target_precondition_after_merge",
            "0.165 runner root cause lost")
    require(runner["merged_reopen_checkpoint"]["target_count"] == 1 and
            runner["merged_reopen_checkpoint"]["catalog_count"] == 1 and
            runner["merged_reopen_checkpoint"]["merge_history_count"] == 1 and
            runner["merged_reopen_checkpoint"]["lease_mask"] == 13,
            "0.165 successful cold reopen checkpoint lost")
    require(runner["merge_checkpoint"]["mutation_persisted"] is True and
            runner["merge_checkpoint"]["stack_min_free"] == 8040 and
            runner["merge_checkpoint"]["write_calls"] == 3 and
            runner["merge_checkpoint"]["file_syncs"] == 3 and
            runner["merge_checkpoint"]["directory_syncs"] == 3,
            "0.165 merge proof lost")
    require(runner["post_failure_restore"]["ota1_restore_verified"] is True and
            runner["post_failure_restore"]["ota1_before_sha256"] ==
            runner["post_failure_restore"]["ota1_after_sha256"],
            "0.165 OTA1 was not restored exactly")
    require(runner["post_failure_restore"]
            ["partition_table_restore_verified"] is True and
            runner["post_failure_restore"]
            ["partition_table_before_sha256"] ==
            runner["post_failure_restore"]
            ["partition_table_after_sha256"],
            "0.165 partition table was not restored exactly")
    require(runner["post_failure_restore"]["final_cid"] ==
            "FE343253440000002000000055019CB7" and
            runner["post_failure_restore"]["final_generation"] == 161 and
            runner["post_failure_restore"]["final_observations"] == 59 and
            runner["post_failure_restore"]["final_lease_mask"] == 0,
            "0.165 final product continuity lost")
    require(runner["usb"]["opened_ports"] == ["/dev/cu.usbmodem2101"] and
            runner["usb"]["cardputer_ports_opened"] == 0 and
            runner["usb"]["port_discovery_calls"] == 0,
            "0.165 Cardputer isolation lost")
    require(runner["repair_gate"]["firmware_change_required"] is False and
            runner["repair_gate"]["reuse_exact_flash"] is True and
            runner["repair_gate"]["minimum_target_count_after_merge"] == 1,
            "0.165 runner-only repair gate lost")
    print(
        "targets 0.146/0.147/0.148/0.163/0.164/0.165 "
        "fail-closed evidence: OK")


if __name__ == "__main__":
    main()
