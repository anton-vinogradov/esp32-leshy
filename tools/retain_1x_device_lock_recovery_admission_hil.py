#!/usr/bin/env python3
"""Retain privacy-minimal CAP-052 recovery/admission acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.281"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "4abf92b10e55adfdd1287962bc7da6f14fad8f92"
FIRMWARE_SHA256 = (
    "d5f77b79bd5f550fd3657a21fde6052b3b136622ce665e9bc9ebe805f7904c26")
APP_ELF_SHA256 = (
    "100d0d498e27c06b0a6d0c06489de0d6ff904a205c9ac315d3999b6a09415e0e")
RUNNER_SHA256 = (
    "9dc8c68f5741b796cd54976ac2a8c90c3266b6343dc9b780e848489f891f9aa6")
DEFAULT_DESTINATION = ROOT / (
    "tests/hil/evidence/"
    "board-01-device-lock-recovery-admission-1.0.0-dev.281.json")

PROTECTED = (
    "protected_ui", "protected_evidence", "secret_read", "export",
    "backup", "companion", "sensitive_settings",
)
SAFE = (
    "status", "lock", "safe_stop", "panic", "cleanup",
    "update_recovery", "factory_reset",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_state(record: dict[str, Any], *, status: str, failure: str,
                  attempts: int, generation: int, protected: bool,
                  fixture_active: bool, cleanup_required: bool) -> None:
    expected = {
        "status": status,
        "failure": failure,
        "failed_attempts": attempts,
        "credential_generation": generation,
        "protected_access": protected,
        "worker_active": False,
        "persistence_fixture_active": fixture_active,
        "persistence_fixture_cleanup_required": cleanup_required,
        "radio_touched": False,
    }
    for field, value in expected.items():
        require(record.get(field) == value,
                f"Device Lock state mismatch: {field}")


def require_admission(record: dict[str, Any], *, state: str,
                      protected: str, unlock: str, configure: str,
                      protected_allowed: bool) -> None:
    require(record.get("state") == state and
            record.get("protected_all_allowed") is protected_allowed and
            record.get("safe_all_allowed") is True and
            record.get("protected_content_returned") is False and
            record.get("radio_touched") is False,
            f"admission summary mismatch: {state}")
    access = record.get("access")
    require(isinstance(access, dict), "admission access object missing")
    expected = {name: protected for name in PROTECTED}
    expected.update({name: "allowed" for name in SAFE})
    expected["unlock"] = unlock
    expected["configure"] = configure
    require(access == expected, f"admission matrix mismatch: {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--destination", type=Path,
                        default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    destination = args.destination.resolve()
    require(not destination.exists(), "destination must not exist")
    run_path = args.run.resolve() / "run.json"
    run = load(run_path)
    candidate = run.get("candidate", {})
    expected_candidate = {
        "app_elf_sha256": APP_ELF_SHA256,
        "firmware_sha256": FIRMWARE_SHA256,
        "flash_mode": "fresh",
        "flashed": True,
        "source_commit": SOURCE_COMMIT,
        "version": VERSION,
    }
    require(run.get("schema") ==
            "leshy.device_lock_recovery_admission_hil.run.v1" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    require(candidate == expected_candidate, "exact candidate mismatch")
    require(run.get("expected_cid") == CID and
            run.get("runner_sha256") == RUNNER_SHA256,
            "board or runner binding mismatch")
    require(digest(ROOT / "tools/run_1x_device_lock_recovery_admission_hil.py")
            == RUNNER_SHA256, "runner changed after physical run")

    reports = run["reports"]
    require_state(reports["product_baseline"], status="unconfigured",
                  failure="none", attempts=0, generation=0,
                  protected=False, fixture_active=False,
                  cleanup_required=False)
    require_state(reports["configured"], status="unlocked", failure="none",
                  attempts=0, generation=1, protected=True,
                  fixture_active=True, cleanup_required=True)
    require_state(reports["locked"], status="locked", failure="none",
                  attempts=0, generation=1, protected=False,
                  fixture_active=True, cleanup_required=True)
    retry_bounds = {
        1: (4000, 5000),
        2: (14000, 15000),
        3: (59000, 60000),
        4: (299000, 300000),
    }
    for attempt in range(1, 5):
        record = reports[f"wrong_pin_{attempt}"]
        require_state(record, status="retry_delay", failure="wrong_pin",
                      attempts=attempt, generation=attempt + 1,
                      protected=False, fixture_active=True,
                      cleanup_required=True)
        remaining = record.get("retry_remaining_ms")
        low, high = retry_bounds[attempt]
        require(isinstance(remaining, int) and low <= remaining <= high,
                f"retry interval mismatch: {attempt}")
    require_state(reports["wrong_pin_5"], status="recovery_only",
                  failure="recovery_required", attempts=5, generation=6,
                  protected=False, fixture_active=True,
                  cleanup_required=True)
    require_state(reports["product_after_recovery_reset"],
                  status="unconfigured", failure="none", attempts=0,
                  generation=0, protected=False, fixture_active=False,
                  cleanup_required=True)
    require_state(reports["restored_recovery"], status="recovery_only",
                  failure="recovery_required", attempts=5, generation=6,
                  protected=False, fixture_active=True,
                  cleanup_required=True)
    require_state(reports["product_final"], status="unconfigured",
                  failure="none", attempts=0, generation=0,
                  protected=False, fixture_active=False,
                  cleanup_required=False)

    require_admission(reports["admission_unconfigured"],
                      state="unconfigured", protected="setup_required",
                      unlock="setup_required", configure="allowed",
                      protected_allowed=False)
    require_admission(reports["admission_unlocked"], state="unlocked",
                      protected="allowed", unlock="allowed",
                      configure="locked", protected_allowed=True)
    require_admission(reports["admission_locked"], state="locked",
                      protected="locked", unlock="allowed",
                      configure="locked", protected_allowed=False)
    for name in ("admission_recovery", "admission_recovery_after_cold"):
        require_admission(reports[name], state="recovery_only",
                          protected="recovery_required",
                          unlock="recovery_required", configure="locked",
                          protected_allowed=False)

    blocked_launch = reports["blocked_launch"]
    require(blocked_launch.get("page") == "home" and
            blocked_launch.get("selected_id") == "library" and
            blocked_launch.get("runtime_event") == "setup_required" and
            blocked_launch.get("runtime_owner") == "none" and
            blocked_launch.get("lease_mask") == 0,
            "actual protected UI launch was not denied cleanly")
    require(reports["blocked_export"] == {
        "access": "setup_required",
        "kind": "blocked",
        "operation": "export",
        "protected_content_returned": False,
        "schema": "leshy.device_lock.admission.v1",
    }, "actual protected export denial mismatch")

    preview = reports["factory_reset_preview"]
    require(preview.get("status") == "confirmation_required" and
            preview.get("lock_status") == "recovery_only" and
            preview.get("factory_reset_result") is False and
            preview.get("protected_erase_calls") == 0 and
            preview.get("destructive_order_proven") is False,
            "factory reset preview mutated protected state")
    confirmed = reports["factory_reset_confirm"]
    require(confirmed.get("status") == "recovered" and
            confirmed.get("lock_status") == "unconfigured" and
            confirmed.get("factory_reset_result") is True and
            confirmed.get("protected_erase_calls") == 1 and
            confirmed.get("credential_present_during_erase") is True and
            confirmed.get("fixture_protected_data_erased") is True and
            confirmed.get("destructive_order_proven") is True,
            "destructive recovery ordering mismatch")

    require(run.get("privacy") == {
        "ephemeral_pin_length": 6,
        "pin_editor_replies_retained": False,
        "pin_or_digest_retained": False,
        "whole_nvs_or_product_namespace_retained": False,
    }, "privacy boundary mismatch")
    require(run.get("scope") == {
        "admission_matrix": True,
        "cardputer": False,
        "clone": False,
        "destructive_reset_order": True,
        "mac_wifi": False,
        "product_storage_write": False,
        "protected_export_block": True,
        "protected_ui_block": True,
        "radio": False,
        "recovery_only": True,
    }, "scope widened unexpectedly")
    fixture = run["fixture"]
    require(fixture.get("cleanup_proven") is True and
            fixture.get("active_at_end") is False and
            fixture.get("isolated_namespace") is True and
            fixture.get("whole_nvs_read_or_copied") is False and
            fixture.get("product_namespace_written_or_erased") is False,
            "fixture isolation/cleanup mismatch")
    final_input = reports["final_input"]
    require(final_input.get("status") == "ready" and
            final_input.get("read_errors") == 0 and
            final_input.get("queue_drops") == 0,
            "final input frontend is not clean")
    final = run["cleanup"]["final_state"]
    require(run["cleanup"].get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("safety_state") == "armed",
            "terminal cleanup mismatch")
    require(len(run["sessions"]) == 3 and
            run["sessions"][-1].get("status") == "ended" and
            run["sessions"][-1].get("active") is False,
            "HIL session continuity mismatch")
    require(run["final_boot"].get("version") == VERSION and
            run["final_boot"].get("app_elf_sha256") == APP_ELF_SHA256 and
            run["final_boot"].get("input_detected") is True,
            "final cold boot identity mismatch")

    retry_remaining = [
        reports[f"wrong_pin_{attempt}"]["retry_remaining_ms"]
        for attempt in range(1, 5)
    ]
    kdf_us = [
        reports[name]["last_kdf_us"]
        for name in ("configured", "wrong_pin_1", "wrong_pin_2",
                     "wrong_pin_3", "wrong_pin_4", "wrong_pin_5")
    ]
    require(all(isinstance(value, int) and 0 < value <= 15_000_000
                for value in kdf_us), "KDF timing bounds mismatch")
    value = {
        "schema": "leshy.device_lock_recovery_admission_hil.acceptance.v1",
        "status": "pass_recovery_admission_slice",
        "board": "board-01",
        "evidence_ids": [
            "E-BUILD-197", "E-AUTO-172", "E-HIL-209", "E-UX-065",
            "E-STORAGE-036",
        ],
        "exact_cid": CID,
        "candidate": candidate,
        "evidence": {
            "run_id": run["run_id"],
            "run_sha256": digest(run_path),
            "runner_sha256": RUNNER_SHA256,
        },
        "verified": {
            "credential_generation_sequence": [0, 1, 2, 3, 4, 5, 6],
            "failed_attempt_sequence": [0, 1, 2, 3, 4, 5],
            "retry_remaining_ms": retry_remaining,
            "kdf_us": kdf_us,
            "recovery_only_cold_restored": True,
            "protected_operations": list(PROTECTED),
            "safe_operations": list(SAFE),
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
        },
        "open": ["encrypted protected data at rest"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": str(destination.relative_to(ROOT)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
