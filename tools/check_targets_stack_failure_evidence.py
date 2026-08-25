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
    print("targets 0.146 stack and 0.147 mount failure evidence: OK")


if __name__ == "__main__":
    main()
