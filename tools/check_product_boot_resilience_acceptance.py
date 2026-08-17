#!/usr/bin/env python3
"""Validate retained 0.49 failure and 0.50 boot-resilience evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-boot-resilience-0.50.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
CID = "FE343253440000002000000055019CB7"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def exact(record: dict[str, Any], expected: dict[str, Any], prefix: str,
          failures: list[str]) -> None:
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(
                f"{prefix}{field}: {record.get(field)!r} != {value!r}"
            )


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    failures: list[str] = []
    exact(evidence, {
        "schema": "leshy.product_boot_resilience_acceptance.v1",
        "status": "pass_with_retained_negative_evidence",
        "trust_status": "unsigned_local_result",
        "gate_eligible": False,
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
    }, "", failures)
    exact(evidence.get("media", {}), {
        "cid": CID, "product_root": "/leshy/sessions/v1",
        "disposable_test_card": True,
    }, "media.", failures)

    failed = evidence.get("retained_release_attempt", {})
    exact(failed, {
        "evidence_id": "E-HIL-069", "status": "failed",
        "gate_eligible": False, "required_seconds": 28800,
        "required_cycles": 32, "cycles_completed": 7,
        "successful_cycles": 6, "generation_before": 38,
        "generation_after_last_success": 44,
        "observations_accepted": 96, "observations_forwarded": 96,
        "scan_dropped": 0, "pipeline_dropped": 0,
        "heap_total_bytes": 276304, "heap_free_bytes": 227864,
        "heap_min_free_bytes": 192432, "heap_drift_bytes": 0,
        "failure_cycle": 7, "failure_stage": "boot_before",
        "boot_attempts_exhausted": 3, "boot_transient_retries": 2,
        "boot_timeout_restarts": 0, "observed_cid": "0" * 32,
        "mounted_read_only": False, "catalog_admitted": False,
        "cleanup_complete": True, "blocked_write_attempts": 0,
        "physical_write_calls": 0, "owned_after": 0,
    }, "retained_release_attempt.", failures)
    require(failures, 0 < failed.get("elapsed_seconds", 0) < 28800,
            "retained_release_attempt.elapsed_seconds: invalid")

    probe = evidence.get("post_failure_readonly_probe", {})
    exact(probe, {
        "attempts": 8, "valid": 6, "response_timeouts": 2,
        "exact_cid_valid": 6, "all_cleanup_complete": True,
        "all_owned_after_zero": True, "all_write_commands_false": True,
        "media_intact_after_failure": True,
        "final_owner": "none", "final_lease_mask": 0,
    }, "post_failure_readonly_probe.", failures)

    experiment = evidence.get("r1_polling_experiment", {})
    exact(experiment, {
        "evidence_id": "E-HIL-070", "attempts_per_candidate": 32,
        "diagnostic_not_release_gate": True, "extended_r1_rejected": True,
        "all_cleanup_complete": True, "all_owned_after_zero": True,
        "all_write_commands_false": True, "all_valid_cid_exact": True,
    }, "r1_polling_experiment.", failures)
    extended = experiment.get("extended_r1_polling", {})
    retained = experiment.get("retained_r1_polling", {})
    exact(extended, {
        "r1_poll_bytes": 64, "valid": 13, "exchange_failed": 17,
        "parse_rejected": 2, "response_timeouts": 4,
        "maximum_failure_streak": 4,
    }, "r1_polling_experiment.extended_r1_polling.", failures)
    exact(retained, {
        "r1_poll_bytes": 16, "valid": 15, "exchange_failed": 15,
        "parse_rejected": 2, "response_timeouts": 0,
        "maximum_failure_streak": 4,
    }, "r1_polling_experiment.retained_r1_polling.", failures)
    require(failures, retained.get("valid", 0) > extended.get("valid", 32),
            "r1_polling_experiment: extended polling was not rejected by data")

    candidate = evidence.get("candidate", {})
    exact(candidate, {
        "evidence_id": "E-BUILD-052",
        "version": "0.50.0-product-boot-resilience-measure",
        "firmware_sha256": "c77ccc475c71b8c7d14ae16a06e9b904a0197f431ddaacd8c65dbe373915d801",
        "app_elf_sha256": "31dfed2fed9c0fe84c5ddb83aa3f35cc89bb3813409ea0333a64c3ce6169f12a",
        "linked_flash_bytes": 1061852, "static_ram_bytes": 125456,
        "app_image_bytes": 1062256, "factory_image_bytes": 1127792,
        "rtc_noinit_bytes": 20, "raw_identification_spi_hz": 100000,
        "r1_poll_bytes": 16,
        "product_start_maximum_identity_attempts": 8,
        "boot_recovery_maximum_attempts": 8,
        "boot_recovery_cumulative_backoff_ms": 7000,
        "boot_recovery_watchdog_ms": 4000,
    }, "candidate.", failures)
    require(
        failures,
        candidate.get("boot_recovery_maximum_attempts", 0) >
        retained.get("maximum_failure_streak", 32),
        "candidate.boot_recovery_maximum_attempts: insufficient measured margin",
    )

    regression = evidence.get("final_regression", {})
    exact(regression, {
        "evidence_id": "E-HIL-071", "status": "pass",
        "cycles_completed": 3, "cid": CID,
        "generation_before": 44, "generation_after": 47,
        "observations_accepted": 39, "observations_forwarded": 39,
        "scan_dropped": 0, "pipeline_dropped": 0,
        "cold_boots": 6, "boot_attempts": 8,
        "boot_transient_retries": 2, "boot_timeout_restarts": 0,
        "product_start_identity_attempts": 3,
        "product_start_identity_transient_retries": 0,
        "heap_total_bytes": 276304, "heap_free_bytes": 227864,
        "heap_min_free_bytes": 192432, "heap_drift_bytes": 0,
        "final_generation": 47, "final_observations": 13,
        "final_owner": "none", "final_lease_mask": 0,
    }, "final_regression.", failures)
    require(failures, 0 < regression.get("maximum_ready_marker_ms", 0) <= 30000,
            "final_regression.maximum_ready_marker_ms: outside budget")

    for record in (failed, probe, extended, retained, candidate, regression):
        if isinstance(record, dict):
            for field, value in record.items():
                if field.endswith("sha256"):
                    require(failures, isinstance(value, str) and
                            SHA256.fullmatch(value) is not None,
                            f"{field}: invalid SHA-256")
    limitations = evidence.get("limitations", [])
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("eight-hour", "three-cycle", "local unsigned",
                   "one board", "physical power cut"):
        require(failures, phrase in joined,
                f"limitations: missing {phrase!r}")

    if failures:
        print("product boot resilience acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product boot resilience acceptance passed: failed 0.49 gate retained, "
        "R1 extension rejected, generation 44->47 regression pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
