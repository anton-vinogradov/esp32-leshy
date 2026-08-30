#!/usr/bin/env python3
"""Fail closed unless exact dev.276 Product Survey terminal evidence is intact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retain_1x_product_survey_terminal_hil import (
    APP_ELF_SHA256,
    ARTIFACT_INDEX_SHA256,
    CID,
    CORRECTED_FAILURE,
    CORRECTED_RUNNER_SHA256,
    EVIDENCE_IDS,
    FIRMWARE_SHA256,
    PRECURSOR_RUN_SHA256,
    RAW_RUNNER_SHA256,
    RAW_RUN_SHA256,
    RUNNER_TEST_SHA256,
    SCREEN_SHA256,
    SOURCE_COMMIT,
    VERIFIER_SHA256,
    VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence" /
            "board-01-product-survey-terminal-1.0.0-dev.276.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact(value, {
        "schema": "leshy.product_survey_terminal_hil.acceptance.v1",
        "status": "pass_terminal_commit_and_exact_cold_reopen",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
    }, "acceptance")
    exact(value["candidate"], {
        "version": VERSION, "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flashed": False, "flash_mode": "reuse_exact",
    }, "candidate")
    exact(value["evidence"], {
        "raw_run_sha256": RAW_RUN_SHA256,
        "artifact_index_sha256": ARTIFACT_INDEX_SHA256,
        "raw_runner_sha256": RAW_RUNNER_SHA256,
        "corrected_runner_sha256": CORRECTED_RUNNER_SHA256,
        "verifier_sha256": VERIFIER_SHA256,
        "runner_test_sha256": RUNNER_TEST_SHA256,
        "rejected_precursor_run_sha256": PRECURSOR_RUN_SHA256,
        "screenshots": SCREEN_SHA256,
    }, "evidence")
    exact(value["verified"], {
        "raw_runner_passed": False,
        "corrected_oracle_recheck": True,
        "corrected_oracle_failure": CORRECTED_FAILURE,
        "generation_before": 175, "generation_after": 176,
        "observations": 51, "wifi_observations": 20,
        "ble_observations": 31, "forwarded": 51, "drops": 0,
        "scan_cycles": 1, "wifi_scan_cycles": 1,
        "ble_scan_cycles": 1, "queue_depth_final": 0,
        "identity_attempts": 1, "identity_transient_retries": 0,
        "cold_reopen_physical_write_calls": 0,
        "heap_total_before": 148124, "heap_total_after": 148124,
        "heap_free_before": 74828, "heap_free_after": 74828,
        "library_session_id": "field-visit-live",
        "final_page": "home", "final_runtime_owner": "none",
        "final_lease_mask": 0,
    }, "verified")
    exact(value["privacy"], {
        "raw_wifi_identifiers_retained": False,
        "raw_ble_addresses_retained": False,
        "raw_export_retained": False, "screenshots_retained": False,
        "screenshot_hashes_retained": True,
    }, "privacy")
    exact(value["scope"], {
        "exact_firmware_reuse": True, "application_flash": False,
        "radio_cycles": 1, "manual_button_presses": 0,
        "host_wifi_control_calls": 0, "clone_touched": False,
        "cardputer_touched": False, "terminal_zero_lease": True,
    }, "scope")
    print("Product Survey terminal acceptance passed: exact dev.276, "
          "generation 175->176, 51 records, exact-CID cold reopen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
