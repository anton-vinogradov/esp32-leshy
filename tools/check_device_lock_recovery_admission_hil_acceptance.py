#!/usr/bin/env python3
"""Fail closed unless exact CAP-052 recovery/admission evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / (
    "tests/hil/evidence/"
    "board-01-device-lock-recovery-admission-1.0.0-dev.281.json")


def main() -> int:
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    value = json.loads(SUMMARY.read_text(encoding="utf-8"))
    failures: list[str] = []
    expected_candidate = {
        "app_elf_sha256":
            "100d0d498e27c06b0a6d0c06489de0d6ff904a205c9ac315d3999b6a09415e0e",
        "firmware_sha256":
            "d5f77b79bd5f550fd3657a21fde6052b3b136622ce665e9bc9ebe805f7904c26",
        "flash_mode": "fresh",
        "flashed": True,
        "source_commit": "4abf92b10e55adfdd1287962bc7da6f14fad8f92",
        "version": "1.0.0-dev.281",
    }
    if (value.get("schema") !=
            "leshy.device_lock_recovery_admission_hil.acceptance.v1" or
            value.get("status") != "pass_recovery_admission_slice" or
            value.get("board") != "board-01" or
            value.get("exact_cid") !=
            "FE343253440000002000000055019CB7" or
            value.get("candidate") != expected_candidate):
        failures.append("exact accepted candidate mismatch")
    if value.get("evidence_ids") != [
            "E-BUILD-197", "E-AUTO-172", "E-HIL-209", "E-UX-065",
            "E-STORAGE-036"]:
        failures.append("evidence ID mismatch")
    verified = value.get("verified", {})
    exact = {
        "credential_generation_sequence": [0, 1, 2, 3, 4, 5, 6],
        "failed_attempt_sequence": [0, 1, 2, 3, 4, 5],
        "recovery_only_cold_restored": True,
        "protected_operations": [
            "protected_ui", "protected_evidence", "secret_read", "export",
            "backup", "companion", "sensitive_settings",
        ],
        "safe_operations": [
            "status", "lock", "safe_stop", "panic", "cleanup",
            "update_recovery", "factory_reset",
        ],
        "unconfigured_protected_access": "setup_required",
        "locked_protected_access": "locked",
        "recovery_protected_access": "recovery_required",
        "unlocked_protected_access": "allowed",
        "safe_operations_always_allowed": True,
        "actual_protected_ui_launch_blocked": True,
        "actual_export_blocked_without_content": True,
        "reset_preview_non_destructive": True,
        "protected_erase_before_credential_clear": True,
        "fixture_cleanup_proven": True,
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
    retry = verified.get("retry_remaining_ms")
    bounds = ((4000, 5000), (14000, 15000), (59000, 60000),
              (299000, 300000))
    if not isinstance(retry, list) or len(retry) != 4:
        failures.append("retry vector mismatch")
    else:
        for observed, (low, high) in zip(retry, bounds):
            if (not isinstance(observed, int) or
                    not low <= observed <= high):
                failures.append("retry interval mismatch")
    kdf = verified.get("kdf_us")
    if (not isinstance(kdf, list) or len(kdf) != 6 or
            any(not isinstance(item, int) or not 0 < item <= 15_000_000
                for item in kdf)):
        failures.append("KDF vector mismatch")
    for field in ("run_sha256", "runner_sha256"):
        observed = value.get("evidence", {}).get(field)
        if not isinstance(observed, str) or len(observed) != 64:
            failures.append(f"evidence hash mismatch: {field}")
    if value.get("open") != ["encrypted protected data at rest"]:
        failures.append("open-scope boundary mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Device Lock recovery/admission HIL acceptance passed: five real "
        "retry stages, cold recovery-only, protected deny/safe allow matrix, "
        "destructive ordering and virgin product cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
