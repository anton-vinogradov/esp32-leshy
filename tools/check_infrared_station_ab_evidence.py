#!/usr/bin/env python3
"""Verify the retained fail-closed three-way infrared station A/B result."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT / "tests/hil/evidence/board-pair-infrared-station-ab-20260824.json"
)


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == "leshy.infrared_station_ab.evidence.v1"
    assert evidence["kind"] == "evidence"
    assert evidence["outcome"] == "blocked_physical_infrared_path"
    assert evidence["passed"] is False
    assert evidence["gate_eligible"] is False
    assert evidence["failure_preserved"] is True

    attempts = evidence["attempts"]
    assert [attempt["name"] for attempt in attempts] == [
        "current-product-current-fixture",
        "current-product-retained-known-good-fixture",
        "retained-previously-accepted-exact-pair",
    ]
    assert [attempt["candidate"]["version"] for attempt in attempts] == [
        "0.137.0-pulse-store-deadline",
        "0.137.0-pulse-store-deadline",
        "0.129.0-pre-app-watchdog",
    ]
    assert [attempt["fixture"]["version"] for attempt in attempts] == [
        "0.2.5-shared-pin-safe",
        "0.1.0-ir-nec",
        "0.1.0-ir-nec",
    ]
    for attempt in attempts:
        assert attempt["passed"] is False
        assert attempt["observation"]["transitions"] == 0
        assert attempt["observation"]["pulses"] == 0
        assert attempt["observation"]["decode_integrity_valid"] is False
        assert attempt["fixture"]["emission_count"] == 1
        assert 68_000 <= attempt["fixture"]["last_duration_us"] <= 69_000
        assert attempt["fixture"]["terminal_state"] == "panicked"
        assert len(attempt["raw_run_json_sha256"]) == 64

    conclusion = evidence["conclusion"]
    assert conclusion["current_firmware_regression_excluded"] is True
    assert conclusion["fixture_gpio14_fix_is_root_cause"] is False
    assert conclusion["rerun_authorized"] is False

    restored = evidence["restored_state"]
    assert restored["product"]["version"] == (
        "0.137.0-pulse-store-deadline"
    )
    assert restored["product"]["page"] == "home"
    assert restored["product"]["runtime_owner"] == "none"
    assert restored["product"]["lease_mask"] == 0
    assert restored["fixture"]["version"] == "0.2.5-shared-pin-safe"
    assert restored["fixture"]["state"] == "panicked"

    print(
        "infrared station A/B evidence passed: three fail-closed zero-transition "
        "runs, physical-path blocker retained, current images restored"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
