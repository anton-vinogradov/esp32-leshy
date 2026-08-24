#!/usr/bin/env python3
"""Fail closed unless compact exact 0.145 Settings evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-interface-settings-0.145.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    bundle = ROOT / summary.get("bundle", "missing")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        failures.append("retained manifest missing")
        manifest = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if digest(manifest_path) != summary.get("manifest_sha256"):
            failures.append("manifest hash mismatch")
    for relative, expected in manifest.items():
        path = bundle / relative
        if not path.is_file() or digest(path) != expected:
            failures.append(f"retained artifact mismatch: {relative}")

    candidate = summary.get("candidate", {})
    if summary.get("status") != "pass" or \
            candidate.get("version") != "0.145.0-interface-settings" or \
            summary.get("source_commit") != \
            "0a2b22d0943b85969308e2b6f606bd669c34b30c":
        failures.append("exact candidate identity mismatch")
    expected_initial = {
        "brightness_duty": 255, "brightness_percent": 100,
        "language": "ru", "theme": "forest",
    }
    expected_persisted = {
        "brightness_duty": 176, "brightness_percent": 69,
        "language": "en", "theme": "high_contrast",
    }
    if summary.get("initial") != expected_initial:
        failures.append("initial preferences mismatch")
    if summary.get("persisted") != expected_persisted:
        failures.append("reset-persisted preferences mismatch")
    final = summary.get("final", {})
    for key, value in expected_initial.items():
        if final.get(key) != value:
            failures.append(f"final preference not restored: {key}")
    for key, value in {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "sound_available": False,
    }.items():
        if final.get(key) != value:
            failures.append(f"final state mismatch: {key}")
    if summary.get("flash_count") != 1 or \
            summary.get("hardware_reset_count") != 2 or \
            summary.get("radio_tx_commands") != 0:
        failures.append("bounded flash/reset/TX count mismatch")
    if summary.get("safe_outputs") != {
        "buzzer_inactive": True, "buzzer_level": "low",
        "nrf_ce_inactive": True, "software_quiesce_complete": True,
    }:
        failures.append("safe-output state mismatch")
    if summary.get("input") != {
        "status": "ready", "read_errors": 0, "queue_drops": 0,
    }:
        failures.append("input state mismatch")
    screens = summary.get("screens", {})
    if set(screens) != {"settings_initial", "settings_changed", "home_restored"}:
        failures.append("exact screenshot set mismatch")
    for record in screens.values():
        path = bundle / record.get("png", "missing")
        if not path.is_file() or digest(path) != record.get("png_sha256"):
            failures.append(f"screenshot mismatch: {record.get('png')}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("interface-settings HIL acceptance passed: one flash, two resets, preferences restored, zero TX/drops/leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
