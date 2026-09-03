#!/usr/bin/env python3
"""Verify retained runtime-WDT NVS/SD incident-to-fix evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-runtime-watchdog-journal-1.0.0-dev.376.json"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"runtime watchdog journal acceptance failed: {message}")


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        require(isinstance(current, dict) and key in current,
                f"missing {'.'.join(keys)}")
        current = current[key]
    return current


def git_blob(commit: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(completed.returncode == 0,
            f"missing source blob {commit}:{relative}")
    return completed.stdout


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(evidence.get("schema") ==
            "leshy.runtime_watchdog_journal.acceptance.v1",
            "schema mismatch")
    require(evidence.get("status") ==
            "pass_with_retained_negative_evidence", "status mismatch")
    require(evidence.get("evidence_ids") == [
        "E-BUILD-245", "E-AUTO-224", "E-HIL-241", "E-SAFETY-089",
        "RB-M258",
    ], "evidence IDs mismatch")
    require(nested(evidence, "retained_failure", "gate_eligible") is False and
            nested(evidence, "retained_failure", "failure") ==
            "loopTask_stack_canary_during_sd_mirror" and
            nested(evidence, "retained_failure", "journal_sequence") == 1 and
            nested(evidence, "retained_failure", "nvs_first_boot_status") ==
            "written_verified" and
            nested(evidence, "retained_failure", "nvs_restart_status") ==
            "already_persisted",
            "negative incident chain mismatch")

    candidate = nested(evidence, "candidate")
    require(candidate.get("version") == "1.0.0-dev.376" and
            candidate.get("flashed") is True, "candidate mismatch")
    runner = git_blob(candidate["source_commit"],
                      "tools/run_1x_safety_watchdog_hil.py")
    require(hashlib.sha256(runner).hexdigest() == candidate["runner_sha256"],
            "runner is not source-bound")
    require(nested(evidence, "correction", "write_sd_stack_bytes_before") ==
            4496 and
            nested(evidence, "correction", "write_sd_stack_bytes_after") ==
            384 and
            nested(evidence, "correction", "exact_file_stack_bytes_after") ==
            160 and
            nested(evidence, "correction", "nvs_required_sd_opportunistic") is
            True,
            "bounded stack correction mismatch")

    journal = nested(evidence, "accepted_run", "journal")
    require(journal.get("watchdog_journal_sequence") == 2 and
            journal.get("watchdog_journal_reset_reason_code") == 6 and
            journal.get("watchdog_journal_triggered_cpu_mask") != 0 and
            journal.get("watchdog_journal_persist_status") ==
            "written_verified" and
            journal.get("watchdog_journal_nvs_verified") is True and
            journal.get("watchdog_journal_sd_status") == "deferred_safe_mode",
            "first safe boot journal mismatch")
    require(nested(evidence, "accepted_run", "deduplicated_restart",
                   "watchdog_journal_persist_status") == "already_persisted" and
            nested(evidence, "accepted_run", "deduplicated_restart",
                   "watchdog_journal_nvs_write_attempted") is False,
            "restart deduplication mismatch")
    final = nested(evidence, "accepted_run", "final")
    require(final.get("state") == "armed" and
            final.get("watchdog_journal_sd_status") == "written_verified" and
            final.get("watchdog_journal_sd_write_status") == "written" and
            final.get("watchdog_journal_sd_mirrored_sequence") == 2 and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "final SD/lease state mismatch")
    require(nested(evidence, "media", "cid") ==
            "FE343253440000002000000055019CB7", "CID mismatch")
    require(nested(evidence, "build", "ota_free_bytes") >= 524288,
            "OTA reserve below floor")
    for key, expected in {
        "cause_available_without_reproduction": True,
        "nvs_survives_reset": True,
        "same_incident_not_duplicated": True,
        "safe_mode_defers_sd": True,
        "exact_cid_sd_mirror_atomic_and_verified": True,
        "final_home_none_zero_lease": True,
        "mac_wifi_untouched": True,
        "rf_transmit_invoked": False,
    }.items():
        require(nested(evidence, "verified", key) == expected,
                f"verified field mismatch: {key}")
    serialized = EVIDENCE.read_text(encoding="utf-8").lower()
    for forbidden in ("/dev/", "usbmodem", "\"ssid\"", "\"bssid\""):
        require(forbidden not in serialized,
                f"privacy-minimal evidence contains {forbidden!r}")
    print(
        "runtime watchdog journal acceptance passed: retained failed dev.375 "
        "incident, bounded dev.376 stack fix, verified NVS dedupe and exact-CID "
        "atomic SD mirror"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
