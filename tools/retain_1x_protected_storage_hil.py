#!/usr/bin/env python3
"""Retain privacy-minimal CAP-052 authenticated storage acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.283"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "695b2e9fc09ca9f34aa2175b5866972b54c224e3"
FIRMWARE_SHA256 = (
    "28dee1f8a715396b5c7846f3e90ba6bb910bc91dba6752e68950b56d15800482")
APP_ELF_SHA256 = (
    "380a98d6106843417d417f916622cf697ff2f4b0a72dd6366dc791ea43c36325")
RUNNER_SHA256 = (
    "6b5db63800266cfccc5bfb93ca58792ba57d1abb850429a505d45e4ebb8980bf")
CHECKER_SHA256 = (
    "cadcac424d295a64ecb48d60767255f7e850bb12f15b55f3a169cb7c85c24f47")
DEFAULT_DESTINATION = ROOT / (
    "tests/hil/evidence/board-01-protected-storage-1.0.0-dev.283.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def load_last_json_line(path: Path) -> dict[str, Any]:
    records = [json.loads(line) for line in
               path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records or not isinstance(records[-1], dict):
        raise ValueError(f"JSONL object required: {path}")
    return records[-1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--watchdog-precursor", required=True, type=Path)
    parser.add_argument("--watchdog-metrics", required=True, type=Path)
    parser.add_argument("--watchdog-safety", required=True, type=Path)
    parser.add_argument("--oracle-precursor", required=True, type=Path)
    parser.add_argument("--destination", type=Path,
                        default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    destination = args.destination.resolve()
    require(not destination.exists(), "destination must not exist")

    run_path = args.run.resolve() / "run.json"
    run = load(run_path)
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.protected_storage_hil.run.v1" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    for field, expected in {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flashed": True,
        "flash_mode": "fresh",
        "runner_sha256": RUNNER_SHA256,
    }.items():
        require(candidate.get(field) == expected,
                f"candidate binding mismatch: {field}")
    require(run.get("expected_cid") == CID, "exact CID mismatch")
    require(digest(ROOT / "tools/run_1x_protected_storage_hil.py") ==
            RUNNER_SHA256, "runner changed after physical run")
    require(digest(ROOT / "tools/check_protected_storage_hil_acceptance.py") ==
            CHECKER_SHA256, "acceptance checker changed")

    records = run["records"]
    recovery = records["recovery_before"]
    stored = records["protected_store"]
    cleanup = records["cleanup_after"]
    require(recovery.get("status") == "admitted" and
            recovery.get("integrity") == "valid" and
            recovery.get("mounted_read_only") is True and
            recovery.get("read_only_guaranteed") is True and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID,
            "authenticated cold reopen mismatch")
    for field, expected in {
        "schema": "leshy.storage.product_bootstrap.v2",
        "status": "valid",
        "cid_hex": CID,
        "fingerprint_matched": True,
        "encrypted_namespace": True,
        "envelope_header_valid": True,
        "physical_size_exact": True,
        "ciphertext_differs": True,
        "io_failure": "none",
        "io_result": "ok",
        "catalog_admitted": True,
        "queue_drops": 0,
        "append_drops": 0,
        "owned_after": 0,
        "radio_connect_calls": 0,
        "application_raw_tx_calls": 0,
    }.items():
        require(stored.get(field) == expected,
                f"protected store mismatch: {field}")
    require(stored["protected_plaintext_bytes"] > 0 and
            stored["protected_physical_bytes"] >
            stored["protected_plaintext_bytes"] + 32,
            "authenticated envelope overhead missing")
    final = cleanup["final_state"]
    require(cleanup.get("complete") is True and
            final == {
                "lease_mask": 0,
                "page": "home",
                "runtime_owner": "none",
                "safety_reason": "none",
                "safety_state": "armed",
            }, "terminal cleanup mismatch")
    require(run.get("scope") == {
        "application_raw_tx_calls": 0,
        "cardputer_touched": False,
        "clone_touched": False,
        "factory_reset": False,
        "host_wifi_control_calls": 0,
        "manual_button_presses": 0,
        "normal_product_commit": True,
        "radio_connect_calls": 0,
        "screenshots": 0,
        "sd_format": False,
        "single_application_flash": True,
        "terminal_zero_lease": True,
    }, "scope widened unexpectedly")

    watchdog_path = args.watchdog_precursor.resolve()
    oracle_path = args.oracle_precursor.resolve()
    watchdog = load(watchdog_path)
    oracle = load(oracle_path)
    metrics = load_last_json_line(args.watchdog_metrics.resolve())
    safety = load_last_json_line(args.watchdog_safety.resolve())
    require(watchdog.get("passed") is False and
            any("timed out waiting" in item
                for item in watchdog.get("failures", [])) and
            metrics.get("reset_reason_code") == 6 and
            safety.get("state") == "latched" and
            safety.get("reason") == "runtime_watchdog" and
            safety.get("trip_count") == 1 and
            safety.get("runtime_owner") == "none" and
            safety.get("lease_mask") == 0,
            "watchdog precursor is not the fail-closed reset")
    require(oracle.get("passed") is False and
            oracle.get("failures") == [
                "protected_store.io_result: 'ok' != 'FR_OK'"],
            "oracle precursor is not the exact one-token rejection")
    oracle_stored = oracle["records"]["protected_store"]
    require(oracle_stored.get("status") == "valid" and
            oracle_stored.get("ciphertext_differs") is True and
            oracle_stored.get("catalog_admitted") is True and
            oracle_stored.get("owned_after") == 0,
            "oracle precursor did not complete protected I/O")

    value = {
        "schema": "leshy.protected_storage_hil.acceptance.v1",
        "status": "pass_authenticated_encryption_at_rest",
        "board": "board-01",
        "evidence_ids": [
            "E-BUILD-198", "E-AUTO-173", "E-HIL-210", "E-STORAGE-037",
        ],
        "exact_cid": CID,
        "candidate": candidate,
        "evidence": {
            "run_id": run["run_id"],
            "run_sha256": digest(run_path),
            "runner_sha256": RUNNER_SHA256,
            "checker_sha256": CHECKER_SHA256,
            "watchdog_precursor_sha256": digest(watchdog_path),
            "watchdog_metrics_sha256": digest(args.watchdog_metrics.resolve()),
            "watchdog_safety_sha256": digest(args.watchdog_safety.resolve()),
            "oracle_precursor_sha256": digest(oracle_path),
        },
        "verified": {
            "envelope": "LENC chunked AES-256-GCM",
            "protected_generation": stored["generation"],
            "reopened_generation": recovery["generation"],
            "protected_plaintext_bytes": stored["protected_plaintext_bytes"],
            "protected_physical_bytes": stored["protected_physical_bytes"],
            "encrypted_namespace": True,
            "envelope_header_valid": True,
            "physical_size_exact": True,
            "ciphertext_differs_from_known_plaintext": True,
            "authenticated_catalog_reopen": True,
            "cold_reopen_read_only": True,
            "cold_reopen_physical_write_calls": 0,
            "queue_drops": 0,
            "append_drops": 0,
            "radio_connect_calls": 0,
            "application_raw_tx_calls": 0,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
            "final_safety_state": "armed",
            "clone_touched": False,
            "cardputer_touched": False,
            "mac_wifi_touched": False,
            "watchdog_precursor_failed_closed": True,
            "oracle_precursor_rejected": True,
        },
        "open": [],
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
