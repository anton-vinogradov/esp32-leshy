#!/usr/bin/env python3
"""Retain privacy-minimal Device Lock persistence/retry HIL acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.280"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "c79e1d24d65e38e3fd1878f2893c8879f43a1b6e"
FIRMWARE_SHA256 = (
    "df62eee22ecd4dc17b9e33c2189a1081bb154ec42950905341e0136aa21a4653")
APP_ELF_SHA256 = (
    "c1d60e205635a296c6651dd068b8720683152c0b9e94ed2ff1504e14317841dc")
RUNNER_SHA256 = (
    "bd9767da957463cf83983cdc0f0306ef371109cb8eec9bfdba4bde896bdc22ee")
DEFAULT_DESTINATION = ROOT / (
    "tests/hil/evidence/"
    "board-01-device-lock-persistence-1.0.0-dev.280.json")


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


def require_lock(record: dict[str, Any], *, status: str, failure: str,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--fresh-precursor", required=True, type=Path)
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
        "flash_mode": "reuse_exact",
        "flashed": False,
        "source_commit": SOURCE_COMMIT,
        "version": VERSION,
    }
    require(run.get("schema") ==
            "leshy.device_lock_persistence_hil.run.v2" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    require(candidate == expected_candidate, "exact candidate mismatch")
    require(run.get("expected_cid") == CID and
            run.get("runner_sha256") == RUNNER_SHA256,
            "board or runner binding mismatch")

    fresh_path = args.fresh_precursor.resolve()
    fresh = load(fresh_path)
    fresh_candidate = dict(expected_candidate)
    fresh_candidate.update({"flash_mode": "fresh", "flashed": True})
    require(fresh.get("candidate") == fresh_candidate and
            fresh.get("passed") is False and
            fresh.get("gate_eligible") is False and
            fresh.get("fixture", {}).get("cleanup_proven") is True,
            "fresh exact-image precursor mismatch")
    fresh_failures = fresh.get("failures", [])
    require(isinstance(fresh_failures, list) and fresh_failures and all(
        item.startswith("boot_recovery.") or
        item.startswith(
            "product_after_reset.persistence_fixture_cleanup_required")
        for item in fresh_failures), "fresh precursor was not oracle-only")

    reports = run["reports"]
    require_lock(reports["product_baseline"], status="unconfigured",
                 failure="none", attempts=0, generation=0,
                 protected=False, fixture_active=False,
                 cleanup_required=False)
    require_lock(reports["configured"], status="unlocked",
                 failure="none", attempts=0, generation=1,
                 protected=True, fixture_active=True,
                 cleanup_required=True)
    require_lock(reports["locked_before_reset"], status="locked",
                 failure="none", attempts=0, generation=1,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    for name in ("product_after_reset", "product_after_retry_reset"):
        require_lock(reports[name], status="unconfigured", failure="none",
                     attempts=0, generation=0, protected=False,
                     fixture_active=False, cleanup_required=True)
    require_lock(reports["restored_locked"], status="locked",
                 failure="none", attempts=0, generation=1,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    require_lock(reports["retry_one"], status="retry_delay",
                 failure="wrong_pin", attempts=1, generation=2,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    require(4250 <= reports["retry_one"]["retry_remaining_ms"] <= 5000,
            "first retry interval is not a full 5-second bound")
    require_lock(reports["retry_two"], status="retry_delay",
                 failure="wrong_pin", attempts=2, generation=3,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    require(14250 <= reports["retry_two"]["retry_remaining_ms"] <= 15000,
            "second retry interval is not a full 15-second bound")
    require_lock(reports["restored_retry"], status="retry_delay",
                 failure="retry_delay", attempts=2, generation=3,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    require(0 < reports["restored_retry"]["retry_remaining_ms"] <= 15000,
            "cold-restored retry interval is invalid")
    require_lock(reports["unlocked_after_retry"], status="unlocked",
                 failure="none", attempts=0, generation=4,
                 protected=True, fixture_active=True,
                 cleanup_required=True)
    require_lock(reports["terminal_locked"], status="locked",
                 failure="none", attempts=0, generation=4,
                 protected=False, fixture_active=True,
                 cleanup_required=True)
    for name in ("product_after_cleanup", "product_after_cleanup_cold"):
        require_lock(reports[name], status="unconfigured", failure="none",
                     attempts=0, generation=0, protected=False,
                     fixture_active=False, cleanup_required=False)

    fixture = run["fixture"]
    require(fixture == {
        "active_at_end": False,
        "cleanup": reports["fixture_cleanup"],
        "cleanup_proven": True,
        "ever_started": True,
        "isolated_namespace": True,
        "product_namespace_written_or_erased": False,
        "whole_nvs_read_or_copied": False,
    }, "fixture cleanup or isolation mismatch")
    cleanup_report = reports["fixture_cleanup"]
    require(cleanup_report["status"] == "cleaned" and
            cleanup_report["fixture_cleanup_complete"] is True and
            cleanup_report["product_restored"] is True and
            cleanup_report["active"] is False and
            cleanup_report["cleanup_required"] is False and
            cleanup_report["product_namespace_written_or_erased"] is False and
            cleanup_report["whole_nvs_read_or_copied"] is False,
            "explicit fixture cleanup mismatch")
    require(run["privacy"] == {
        "ephemeral_pin_length": 6,
        "pin_editor_replies_retained": False,
        "pin_or_digest_retained": False,
        "whole_nvs_or_product_namespace_retained": False,
    }, "privacy boundary mismatch")
    require(run["scope"] == {
        "cardputer": False,
        "clone": False,
        "credential_enrollment": True,
        "credential_persistence": True,
        "mac_wifi": False,
        "product_storage_write": False,
        "radio": False,
        "wrong_pin_backoff": True,
    }, "scope widened unexpectedly")
    require(reports["final_input"]["status"] == "ready" and
            reports["final_input"]["read_errors"] == 0 and
            reports["final_input"]["queue_drops"] == 0,
            "final input frontend is not clean")
    final = run["cleanup"]["final_state"]
    require(run["cleanup"]["complete"] is True and
            final["page"] == "home" and
            final["runtime_owner"] == "none" and
            final["lease_mask"] == 0 and
            final["safety_state"] == "armed",
            "terminal cleanup mismatch")
    require(len(run["sessions"]) == 4 and
            all(item["session_id"] == run["run_id"]
                for item in run["sessions"]) and
            run["sessions"][-1]["status"] == "ended" and
            run["sessions"][-1]["active"] is False,
            "HIL session continuity mismatch")
    require(run["final_boot"]["version"] == VERSION and
            run["final_boot"]["app_elf_sha256"] == APP_ELF_SHA256 and
            run["final_boot"]["input_detected"] is True,
            "final cold boot identity mismatch")

    screens = run["screens"]
    value = {
        "schema": "leshy.device_lock_persistence_hil.acceptance.v1",
        "status": "pass_persistence_retry_slice",
        "board": "board-01",
        "evidence_ids": ["E-BUILD-196", "E-AUTO-171", "E-HIL-208",
                         "E-STORAGE-035"],
        "exact_cid": CID,
        "candidate": candidate,
        "evidence": {
            "run_id": run["run_id"],
            "run_sha256": digest(run_path),
            "runner_sha256": RUNNER_SHA256,
            "fresh_oracle_precursor_run_sha256": digest(fresh_path),
        },
        "verified": {
            "credential_generation_sequence": [0, 1, 2, 3, 4],
            "cold_locked_generation": 1,
            "cold_retry_generation": 3,
            "first_retry_remaining_ms":
                reports["retry_one"]["retry_remaining_ms"],
            "second_retry_remaining_ms":
                reports["retry_two"]["retry_remaining_ms"],
            "cold_retry_remaining_ms":
                reports["restored_retry"]["retry_remaining_ms"],
            "configure_kdf_us": reports["configured"]["last_kdf_us"],
            "first_wrong_pin_kdf_us": reports["retry_one"]["last_kdf_us"],
            "second_wrong_pin_kdf_us": reports["retry_two"]["last_kdf_us"],
            "successful_unlock_kdf_us":
                reports["unlocked_after_retry"]["last_kdf_us"],
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
            "unconfigured_png_sha256": screens["unconfigured"]["png_sha256"],
            "configured_png_sha256": screens["configured"]["png_sha256"],
            "retry_png_sha256": screens["retry"]["png_sha256"],
            "unlocked_png_sha256": screens["unlocked"]["png_sha256"],
        },
        "open": [
            "physical recovery-only transition after the fifth wrong PIN",
            "protected-action admission",
            "encrypted data at rest",
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination":
                      str(destination.relative_to(ROOT))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
