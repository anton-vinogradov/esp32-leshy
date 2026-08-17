#!/usr/bin/env python3
"""Validate the retained 0.49 Product Start resilience evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-start-resilience-0.49.json"
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
        "schema": "leshy.product_start_resilience_acceptance.v1",
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

    candidate = evidence.get("candidate", {})
    exact(candidate, {
        "version": "0.49.0-product-start-resilience-measure",
        "firmware_sha256": "8d79084a27c6e0c4c6c5d731ac3e2f95be37360f317f7d4d0d5cad39a761e5ec",
        "app_elf_sha256": "2e711359c9d484a2e945a5cc41067f2086a7a6c3c966c6f22d322a3d01f78cb0",
        "linked_flash_bytes": 1061852, "static_ram_bytes": 125456,
        "app_image_bytes": 1062256, "factory_image_bytes": 1127792,
        "rtc_noinit_bytes": 20, "raw_identification_spi_hz": 100000,
        "product_start_maximum_identity_attempts": 8,
        "product_start_maximum_backoff_ms": 7000,
        "boot_recovery_maximum_attempts": 3,
    }, "candidate.", failures)

    failed = evidence.get("retained_release_attempt", {})
    exact(failed, {
        "evidence_id": "E-HIL-065", "status": "failed",
        "gate_eligible": False, "cycles_completed": 1,
        "failure_stage": "explicit_product_start",
        "identity_status": "exchange_failed", "identity_attempts": 3,
        "identity_transient_retries": 2, "observed_cid": "0" * 32,
        "prior_generation": 30, "prior_observations": 15,
        "prior_generation_preserved": True, "cleanup_complete": True,
        "final_owner": "none", "final_lease_mask": 0,
        "fail_closed_checkpoint_recovered": True,
    }, "retained_release_attempt.", failures)
    require(failures, "TypeError" in failed.get("orchestrator_exception", ""),
            "retained_release_attempt.orchestrator_exception: missing TypeError")

    comparison = evidence.get("frequency_comparison", {})
    exact(comparison, {
        "evidence_id": "E-HIL-066", "attempts_per_frequency": 32,
        "comparison_is_diagnostic_not_release_gate": True,
        "all_cleanup_complete": True, "all_owned_after_zero": True,
        "all_write_commands_false": True, "all_valid_cid_exact": True,
        "final_owner": "none", "final_lease_mask": 0,
    }, "frequency_comparison.", failures)
    at_400 = comparison.get("at_400_khz", {})
    at_100 = comparison.get("at_100_khz", {})
    exact(at_400, {"valid": 13, "exchange_failed": 16,
                   "parse_rejected": 3, "maximum_failure_streak": 7},
          "frequency_comparison.at_400_khz.", failures)
    exact(at_100, {"valid": 24, "exchange_failed": 7,
                   "parse_rejected": 1, "maximum_failure_streak": 2},
          "frequency_comparison.at_100_khz.", failures)
    require(failures, at_100.get("valid", 0) > at_400.get("valid", 32),
            "frequency comparison: 100 kHz did not improve valid reads")

    product = evidence.get("exact_product_run", {})
    exact(product, {
        "evidence_id": "E-HIL-067", "status": "pass",
        "candidate_flashed": True, "cid": CID,
        "generation_before": 34, "generation_after": 35,
        "observations_accepted": 13, "observations_forwarded": 13,
        "scan_dropped": 0, "pipeline_dropped": 0,
        "final_owner": "none", "final_lease_mask": 0,
    }, "exact_product_run.", failures)

    regression = evidence.get("final_regression", {})
    exact(regression, {
        "evidence_id": "E-HIL-068", "status": "pass",
        "cycles_completed": 3, "generation_before": 35,
        "generation_after": 38, "observations_accepted": 46,
        "observations_forwarded": 46, "scan_dropped": 0,
        "pipeline_dropped": 0, "cold_boots": 6, "boot_attempts": 8,
        "boot_transient_retries": 2, "boot_timeout_restarts": 0,
        "heap_total_bytes": 276304, "heap_free_bytes": 227864,
        "heap_min_free_bytes": 192432, "heap_drift_bytes": 0,
        "final_generation": 38, "final_observations": 15,
        "final_owner": "none", "final_lease_mask": 0,
    }, "final_regression.", failures)
    require(failures, 0 < regression.get("maximum_ready_marker_ms", 0) <= 18000,
            "final_regression.maximum_ready_marker_ms: outside budget")

    for record in (candidate, failed, at_400, at_100, product, regression):
        if isinstance(record, dict):
            for field, value in record.items():
                if field.endswith("sha256"):
                    require(failures, isinstance(value, str) and
                            SHA256.fullmatch(value) is not None,
                            f"{field}: invalid SHA-256")
    limitations = evidence.get("limitations", [])
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("eight-hour", "local unsigned", "one board",
                   "physical power cut"):
        require(failures, phrase in joined,
                f"limitations: missing {phrase!r}")

    if failures:
        print("product start resilience acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product start resilience acceptance passed: failed 0.48 retained, "
        "100 kHz improved 13/32 to 24/32, generation 35->38 smoke pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
