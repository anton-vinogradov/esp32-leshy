#!/usr/bin/env python3
"""Fail closed unless exact Device Lock persistence HIL acceptance is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / (
    "tests/hil/evidence/"
    "board-01-device-lock-persistence-1.0.0-dev.280.json")


def main() -> int:
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    value = json.loads(SUMMARY.read_text(encoding="utf-8"))
    failures: list[str] = []
    expected_candidate = {
        "app_elf_sha256":
            "c1d60e205635a296c6651dd068b8720683152c0b9e94ed2ff1504e14317841dc",
        "firmware_sha256":
            "df62eee22ecd4dc17b9e33c2189a1081bb154ec42950905341e0136aa21a4653",
        "flash_mode": "reuse_exact",
        "flashed": False,
        "source_commit": "c79e1d24d65e38e3fd1878f2893c8879f43a1b6e",
        "version": "1.0.0-dev.280",
    }
    if value.get("schema") != \
            "leshy.device_lock_persistence_hil.acceptance.v1" or \
            value.get("status") != "pass_persistence_retry_slice" or \
            value.get("board") != "board-01" or \
            value.get("exact_cid") != \
            "FE343253440000002000000055019CB7" or \
            value.get("candidate") != expected_candidate:
        failures.append("exact accepted candidate mismatch")
    if value.get("evidence_ids") != [
            "E-BUILD-196", "E-AUTO-171", "E-HIL-208", "E-STORAGE-035"]:
        failures.append("evidence ID mismatch")

    verified = value.get("verified", {})
    exact = {
        "credential_generation_sequence": [0, 1, 2, 3, 4],
        "cold_locked_generation": 1,
        "cold_retry_generation": 3,
        "cleanup_required_survives_two_cold_starts": True,
        "fixture_cleanup_proven": True,
        "fixture_active_at_end": False,
        "isolated_fixture_namespace": True,
        "whole_nvs_read_or_copied": False,
        "product_namespace_written_or_erased": False,
        "product_generation_after_cleanup": 0,
        "product_generation_after_cleanup_cold": 0,
        "pin_or_digest_retained": False,
        "input_read_errors": 0,
        "input_queue_drops": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
        "final_safety_state": "armed",
        "radio_touched": False,
        "clone_touched": False,
        "cardputer_touched": False,
        "mac_wifi_touched": False,
    }
    for field, expected in exact.items():
        if verified.get(field) != expected:
            failures.append(f"verified field mismatch: {field}")
    intervals = {
        "first_retry_remaining_ms": (4250, 5000),
        "second_retry_remaining_ms": (14250, 15000),
        "cold_retry_remaining_ms": (1, 15000),
    }
    for field, bounds in intervals.items():
        observed = verified.get(field)
        if not isinstance(observed, int) or not bounds[0] <= observed <= bounds[1]:
            failures.append(f"retry interval mismatch: {field}")
    for field in ("configure_kdf_us", "first_wrong_pin_kdf_us",
                  "second_wrong_pin_kdf_us", "successful_unlock_kdf_us"):
        observed = verified.get(field)
        if not isinstance(observed, int) or not 0 < observed <= 15_000_000:
            failures.append(f"KDF timing mismatch: {field}")
    for field in ("unconfigured_png_sha256", "configured_png_sha256",
                  "retry_png_sha256", "unlocked_png_sha256"):
        observed = verified.get(field)
        if not isinstance(observed, str) or len(observed) != 64:
            failures.append(f"screen hash mismatch: {field}")
    for field in ("run_sha256", "runner_sha256",
                  "fresh_oracle_precursor_run_sha256"):
        observed = value.get("evidence", {}).get(field)
        if not isinstance(observed, str) or len(observed) != 64:
            failures.append(f"evidence hash mismatch: {field}")
    if value.get("open") != [
            "physical recovery-only transition after the fifth wrong PIN",
            "protected-action admission",
            "encrypted data at rest"]:
        failures.append("open-scope boundary mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Device Lock persistence HIL acceptance passed: cold credential/retry restore, full 5/15-second bounds, isolated fixture cleanup, virgin product namespace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
