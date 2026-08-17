#!/usr/bin/env python3
"""Fail closed if the retained physical-keypad acceptance is incomplete."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests" / "hil" / "evidence" / "board-01-keypad-0.43.json"
SUITE = ROOT / "tests" / "hil" / "device-smoke.v1.json"
ACCEPTED_FIRMWARE_VERSION = "0.43.0-keypad-burst-buffer-measure"


def main() -> int:
    errors: list[str] = []
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    if value.get("schema") != "leshy.input.physical_acceptance.v1":
        errors.append("unexpected physical-keypad evidence schema")
    if value.get("status") != "pass":
        errors.append("physical-keypad evidence is not a pass")
    if value.get("firmware_version") != ACCEPTED_FIRMWARE_VERSION:
        errors.append("physical-keypad evidence is not for the accepted firmware")
    automatic = value.get("automatic_hil", {})
    if automatic.get("suite") != suite.get("id") or automatic.get("revision") != suite.get("revision"):
        errors.append("physical-keypad evidence is not bound to the current HIL suite")
    for field in ("firmware_sha256", "app_elf_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))):
            errors.append(f"invalid candidate identity: {field}")
    for field in ("run_id",):
        if not re.fullmatch(r"[0-9a-f]{32}", str(automatic.get(field, ""))):
            errors.append(f"invalid automatic HIL identity: {field}")
    for field in ("run_sha256", "artifact_index_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(automatic.get(field, ""))):
            errors.append(f"invalid automatic HIL digest: {field}")

    before = value.get("before", {})
    after = value.get("after", {})
    expected = value.get("procedure", {}).get("expected_total")
    expected_per_key = value.get("procedure", {}).get("expected_per_key")
    for field in (
        "press_events", "release_events", "dispatched_press_events",
        "read_errors", "ambiguous_presses", "queue_depth", "queue_high_water",
        "queue_drops",
    ):
        if before.get(field) != 0:
            errors.append(f"nonzero acceptance baseline: {field}")
    for field in ("press_events", "release_events", "dispatched_press_events"):
        if after.get(field) != expected:
            errors.append(f"physical-keypad total mismatch: {field}")
    presses = after.get("presses", {})
    for action in ("select", "up", "down", "left", "right"):
        if presses.get(action) != expected_per_key:
            errors.append(f"physical-keypad mapping mismatch: {action}")
    for field in ("read_errors", "ambiguous_presses", "queue_depth", "queue_drops"):
        if after.get(field) != 0:
            errors.append(f"physical-keypad failure counter is nonzero: {field}")
    if after.get("raw_transitions") != expected * 2 or after.get("stable_transitions") != expected * 2:
        errors.append("physical-keypad press/release transition count mismatch")
    capacity = after.get("queue_capacity")
    high_water = after.get("queue_high_water")
    if not isinstance(capacity, int) or not isinstance(high_water, int) or not (0 < high_water < capacity):
        errors.append("physical-keypad queue has no measured headroom")
    if after.get("maximum_sample_gap_ms", 999) > 10:
        errors.append("physical-keypad sample gap exceeds 10 ms")
    if after.get("latest_raw") != 255 or after.get("stable_raw") != 255:
        errors.append("physical-keypad did not finish released")
    if after.get("ui_revision", 0) - before.get("ui_revision", 0) != expected:
        errors.append("not every physical press reached the public UI action path")

    if errors:
        for error in errors:
            print(f"keypad acceptance failed: {error}")
        return 1
    print("physical keypad acceptance passed: 50/50 dispatched, high-water 6/64, zero drops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
