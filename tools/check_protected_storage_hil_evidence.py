#!/usr/bin/env python3
"""Fail closed when the retained CAP-052 protected-storage proof drifts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "tests"
    / "hil"
    / "evidence"
    / "board-01-protected-storage-1.0.0-dev.283.json"
)

EXPECTED: dict[str, Any] = {
    "board": "board-01",
    "schema": "leshy.protected_storage_hil.acceptance.v1",
    "status": "pass_authenticated_encryption_at_rest",
    "exact_cid": "FE343253440000002000000055019CB7",
    "open": [],
    "evidence_ids": ["E-BUILD-198", "E-AUTO-173", "E-HIL-210", "E-STORAGE-037"],
    "candidate": {
        "app_elf_sha256": "380a98d6106843417d417f916622cf697ff2f4b0a72dd6366dc791ea43c36325",
        "elf_sha256": "380a98d6106843417d417f916622cf697ff2f4b0a72dd6366dc791ea43c36325",
        "firmware_sha256": "28dee1f8a715396b5c7846f3e90ba6bb910bc91dba6752e68950b56d15800482",
        "flash_mode": "fresh",
        "flashed": True,
        "map_sha256": "da413356e51f281f36b0d23bb6d5cf25f65811a26b5290893d734a89320d18bd",
        "runner_sha256": "6b5db63800266cfccc5bfb93ca58792ba57d1abb850429a505d45e4ebb8980bf",
        "source_commit": "695b2e9fc09ca9f34aa2175b5866972b54c224e3",
        "version": "1.0.0-dev.283",
    },
    "evidence": {
        "checker_sha256": "cadcac424d295a64ecb48d60767255f7e850bb12f15b55f3a169cb7c85c24f47",
        "oracle_precursor_sha256": "69b5a52aca34650426845689add141ca2ff6bc8d5a3581d6050017ba6b7b623f",
        "run_id": "76c9d209decbcda04791c4ca5353eada",
        "run_sha256": "0e3018621df64aeff0ffb8f6aeff86dd3df56c5f3be58496f2f73f7bb7db28f8",
        "runner_sha256": "6b5db63800266cfccc5bfb93ca58792ba57d1abb850429a505d45e4ebb8980bf",
        "watchdog_metrics_sha256": "bde2eb374a2e4791dc07dbddd4771b4db253fc8a2378365b65a98330339509bd",
        "watchdog_precursor_sha256": "a6c1d577ae5f812e43de6eb98a78c82932ece52f503b0cf186868bf74c7cd99d",
        "watchdog_safety_sha256": "c10604b24fa77926c55264509029d39cfcc68ae11936b5797837e314abb1e34e",
    },
    "verified": {
        "append_drops": 0,
        "application_raw_tx_calls": 0,
        "authenticated_catalog_reopen": True,
        "cardputer_touched": False,
        "ciphertext_differs_from_known_plaintext": True,
        "clone_touched": False,
        "cold_reopen_physical_write_calls": 0,
        "cold_reopen_read_only": True,
        "encrypted_namespace": True,
        "envelope": "LENC chunked AES-256-GCM",
        "envelope_header_valid": True,
        "final_lease_mask": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_safety_state": "armed",
        "mac_wifi_touched": False,
        "oracle_precursor_rejected": True,
        "physical_size_exact": True,
        "protected_generation": 3,
        "protected_physical_bytes": 695,
        "protected_plaintext_bytes": 615,
        "queue_drops": 0,
        "radio_connect_calls": 0,
        "reopened_generation": 2,
        "watchdog_precursor_failed_closed": True,
    },
}


def main() -> int:
    actual = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    if actual != EXPECTED:
        raise SystemExit(f"FAIL: retained CAP-052 evidence drifted: {EVIDENCE}")
    print(f"protected storage HIL evidence: OK ({EVIDENCE.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
