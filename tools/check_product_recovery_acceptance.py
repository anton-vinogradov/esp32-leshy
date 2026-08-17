#!/usr/bin/env python3
"""Validate retained negative incidents and the accepted 0.48 recovery path."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-recovery-0.48.json"
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
        "schema": "leshy.product_recovery_acceptance.v1",
        "status": "pass_with_retained_negative_evidence",
        "trust_status": "unsigned_local_result",
        "gate_eligible": False,
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
    }, "", failures)
    media = evidence.get("media")
    require(failures, isinstance(media, dict), "media: missing")
    if isinstance(media, dict):
        exact(media, {"cid": CID, "product_root": "/leshy/sessions/v1",
                      "disposable_test_card": True}, "media.", failures)

    candidate = evidence.get("candidate")
    require(failures, isinstance(candidate, dict), "candidate: missing")
    if isinstance(candidate, dict):
        exact(candidate, {
            "version": "0.48.0-product-boot-timeout-measure",
            "firmware_sha256": "92739ca85bf3a37fb433d07e9a62e5ab88d8e6571309ec9d3e15963a1021f530",
            "app_elf_sha256": "64f7eff5e1e3c8d2e16c3d700eaecc7bfc9f13d57ee988bd72f7552f04fae451",
            "linked_flash_bytes": 1061848,
            "static_ram_bytes": 125456,
            "app_image_bytes": 1062256,
            "factory_image_bytes": 1127792,
            "rtc_noinit_bytes": 20,
        }, "candidate.", failures)
        for field in ("firmware_sha256", "factory_sha256", "app_elf_sha256",
                      "map_sha256"):
            require(failures,
                    isinstance(candidate.get(field), str) and
                    SHA256.fullmatch(candidate[field]) is not None,
                    f"candidate.{field}: invalid SHA-256")

    incidents = evidence.get("retained_failures")
    require(failures, isinstance(incidents, list) and len(incidents) == 3,
            "retained_failures: require three incidents")
    if not isinstance(incidents, list):
        incidents = []
    by_id = {item.get("evidence_id"): item for item in incidents
             if isinstance(item, dict)}
    require(failures, set(by_id) == {"E-HIL-060", "E-HIL-061", "E-HIL-062"},
            "retained_failures: IDs mismatch")
    start = by_id.get("E-HIL-060", {})
    exact(start, {"status": "failed", "gate_eligible": False,
                  "cycles_completed": 2}, "E-HIL-060.", failures)
    retry = start.get("positive_boot_retry", {})
    exact(retry, {"attempts": 2, "transient_retries": 1,
                  "reason": "transient_missing_media",
                  "blocked_write_attempts": 0, "physical_write_calls": 0,
                  "cleanup_complete": True, "owned_after": 0},
          "E-HIL-060.retry.", failures)
    failed_start = start.get("failed_start", {})
    exact(failed_start, {"status": "identity_failed",
                         "observed_cid": "0" * 32,
                         "cleanup_complete": True,
                         "prior_generation_preserved": True,
                         "filesystem_attempted": False},
          "E-HIL-060.start.", failures)
    probe = start.get("immediate_read_only_probe", {})
    exact(probe, {"status": "valid", "cid": CID, "commands_completed": 9,
                  "cleanup_complete": True, "mount_attempted": False,
                  "write_commands": False, "owned_after": 0},
          "E-HIL-060.probe.", failures)

    hang = by_id.get("E-HIL-061", {})
    exact(hang, {"status": "failed", "gate_eligible": False,
                 "cycles_completed": 2, "completed_generation_before": 16,
                 "completed_generation_after": 18}, "E-HIL-061.", failures)
    third = hang.get("third_commit", {})
    exact(third, {"generation": 19, "observations": 18,
                  "scan_accepted": 18, "pipeline_dropped": 0,
                  "cleanup_complete": True}, "E-HIL-061.commit.", failures)
    boot_after = hang.get("boot_after", {})
    exact(boot_after, {"rom_loader_seen": True, "firmware_ready_seen": False,
                       "run_json_created": False},
          "E-HIL-061.boot_after.", failures)

    blocking = by_id.get("E-HIL-062", {})
    exact(blocking, {"status": "failed", "cycles_completed": 0,
                     "commit_completed": True, "firmware_ready_seen": False,
                     "rejected_behavior":
                         "watchdog logging or flushing before restart",
                     "accepted_mitigation":
                         "RTC-only marker followed immediately by esp_restart_noos"},
          "E-HIL-062.", failures)

    injection = evidence.get("watchdog_injection")
    require(failures, isinstance(injection, dict), "watchdog_injection: missing")
    if isinstance(injection, dict):
        exact(injection, {"evidence_id": "E-HIL-063", "status": "pass",
                          "filesystem_write_attempted": False,
                          "physical_write_calls": 0,
                          "recovery_status": "admitted", "attempts": 2,
                          "transient_retries": 1, "timeout_restarts": 1,
                          "generation": 27, "observations": 13, "cid": CID,
                          "mounted_read_only": True,
                          "read_only_guaranteed": True,
                          "blocked_write_attempts": 0,
                          "cleanup_complete": True, "final_owner": "none",
                          "final_lease_mask": 0},
              "watchdog_injection.", failures)

    regression = evidence.get("final_regression")
    require(failures, isinstance(regression, dict), "final_regression: missing")
    if isinstance(regression, dict):
        exact(regression, {
            "evidence_id": "E-HIL-064", "status": "pass",
            "cycles_completed": 3, "generation_before": 27,
            "generation_after": 30, "observations_accepted": 45,
            "observations_forwarded": 45, "scan_dropped": 0,
            "pipeline_dropped": 0, "cold_boots": 6, "boot_attempts": 8,
            "transient_retries": 2, "timeout_restarts": 0,
            "product_start_identity_attempts": 3,
            "product_start_identity_transient_retries": 0,
            "heap_total_bytes": 276304, "heap_free_bytes": 227864,
            "heap_min_free_bytes": 192432, "heap_drift_bytes": 0,
            "final_generation": 30, "final_observations": 15,
            "final_owner": "none", "final_lease_mask": 0,
        }, "final_regression.", failures)
        require(failures,
                0 < regression.get("maximum_ready_marker_ms", 0) <= 18000,
                "final_regression.maximum_ready_marker_ms: outside budget")

    limitations = evidence.get("limitations")
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("eight-hour", "local unsigned", "one board", "physical power cut"):
        require(failures, phrase in joined,
                f"limitations: missing {phrase!r}")

    for record in [candidate, start, hang, blocking, injection, regression]:
        if isinstance(record, dict):
            for field, value in record.items():
                if field.endswith("sha256"):
                    require(failures, isinstance(value, str) and
                            SHA256.fullmatch(value) is not None,
                            f"{field}: invalid SHA-256")

    if failures:
        print("product recovery acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product recovery acceptance passed: three failures retained, "
        "watchdog timeout recovered read-only, generation 27->30 regression pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
