#!/usr/bin/env python3
"""Validate the retained, fail-closed Targets 0.146 physical failure."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-targets-stack-failure-0.146.json"


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
    print("targets stack failure evidence: OK")


if __name__ == "__main__":
    main()
