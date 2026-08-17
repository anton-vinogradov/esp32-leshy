#!/usr/bin/env python3
"""Machine-check retained 0.50 failure and the unpromoted 0.51 host fix."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-hardware-watchdog-0.51.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
CID = "FE343253440000002000000055019CB7"


def exact(record: dict[str, Any], expected: dict[str, Any], prefix: str,
          failures: list[str]) -> None:
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(f"{prefix}{field}: {record.get(field)!r} != {value!r}")


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    failures: list[str] = []
    exact(evidence, {
        "schema": "leshy.product_hardware_watchdog_acceptance.v1",
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
        "evidence_id": "E-HIL-072",
        "candidate_version": "0.50.0-product-boot-resilience-measure",
        "candidate_firmware_sha256": "c77ccc475c71b8c7d14ae16a06e9b904a0197f431ddaacd8c65dbe373915d801",
        "candidate_app_elf_sha256": "31dfed2fed9c0fe84c5ddb83aa3f35cc89bb3813409ea0333a64c3ce6169f12a",
        "aggregate_run_sha256": "636feeb8568ca5b6e1b5273076ef4a756118df199cefb843467ed1a556cb7cfa",
        "aggregate_artifact_index_sha256": "16c480b474e808b641a18105e47cc57ea1812c934543cc76fb279957222bf9f6",
        "status": "failed", "gate_eligible": False,
        "required_seconds": 28800, "required_cycles": 32,
        "elapsed_seconds": 1013.839983, "cycles_completed": 1,
        "successful_cycles": 1, "generation_before": 47,
        "generation_after_last_success": 48,
        "observations_accepted": 16, "observations_forwarded": 16,
        "scan_dropped": 0, "pipeline_dropped": 0,
        "heap_total_bytes": 276304, "heap_free_bytes": 227864,
        "heap_min_free_bytes": 192432, "heap_drift_bytes": 0,
        "exact_cid": CID, "last_completed_final_owner": "none",
        "last_completed_final_lease_mask": 0,
        "failure_cycle": 2, "failure_stage": "boot_before_console_sync",
        "child_run_created": False,
        "console_error": "timed out synchronizing the firmware console",
        "failed_child_stderr_sha256": "a23cd68b35b0532f7436ef8a13cfc7c69324c83aca6fcd7891934e34404f0d80",
        "failed_boot_raw_sha256": "32f6a3eea32ab0a2910de687cc8c169616fc45930d3773f02d5b0d994dd1455b",
        "failed_boot_raw_bytes": 1231, "boot_attempts_started": 3,
        "boot_restarts_completed": 2,
        "boot_transient_retries_observed": 2,
        "retry_records_cleanup_complete": True,
        "retry_records_owned_after_zero": True,
        "third_attempt_rom_loader_seen": True,
        "third_attempt_app_entry_seen": True,
        "third_attempt_firmware_output_seen": False,
        "third_attempt_software_watchdog_reset_seen": False,
        "third_attempt_final_cleanup_known": False,
        "third_attempt_final_lease_known": False,
        "third_attempt_sd_write_status_known": False,
    }, "retained_release_attempt.", failures)

    diagnostics = evidence.get("safe_post_failure_diagnostics", {})
    exact(diagnostics, {
        "serial_endpoint_path_present": True,
        "serial_endpoint_responsive": False,
        "external_dtr_rts_reset_capture_bytes": 0,
        "external_dtr_rts_reset_capture_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "esptool_chip_id_received_serial_data": False,
        "flash_attempted": False, "second_hil_started": False,
        "physical_power_removal_required": True,
    }, "safe_post_failure_diagnostics.", failures)

    diagnosis = evidence.get("diagnosis", {})
    exact(diagnosis, {
        "scheduler_based_watchdog_failed_to_run": True,
        "software_restart_path_insufficient": True,
        "failure_observed_after_rom_app_entry": True,
        "automatic_gate_restart_allowed": False,
        "preconditions_completed": True,
    }, "diagnosis.", failures)
    required = diagnosis.get("required_before_gate_restart", [])
    require(failures, required == [
        "physical power removal",
        "exact 0.51 candidate flash and identity verification",
        "hardware-watchdog injection HIL",
        "short product regression HIL",
    ], "diagnosis.required_before_gate_restart: fail-closed sequence mismatch")

    candidate = evidence.get("host_candidate", {})
    exact(candidate, {
        "evidence_id": "E-BUILD-053", "status": "pass",
        "version": "0.51.0-hardware-boot-watchdog-measure",
        "firmware_sha256": "a2931c87bc2a26330777b06dad4bb5eb6e42d28112717af086251a2b7b14f76d",
        "factory_sha256": "2b61a6db78fe459ff133f6de406b146c2c3f5545f8f871c26b90cc13c70f7303",
        "app_elf_sha256": "75b3939d1e4331ea2605814858f4fb0483368d88365176af2fe0fc47e007d828",
        "map_sha256": "c374e899e50cadf03b57871343d80e5cc6223cf8bc2d057d265ac578e4688f03",
        "linked_flash_bytes": 1062900, "static_ram_bytes": 125464,
        "app_image_bytes": 1063312, "factory_image_bytes": 1128848,
        "rtc_noinit_bytes": 20, "software_watchdog_ms": 4000,
        "hardware_task_watchdog_ms": 5000,
        "task_watchdog_panic_enabled": True,
        "task_watchdog_initialized_at_boot": True,
        "isr_handler_in_iram": True, "atomic_claim_in_iram": True,
        "native_and_host_checks_passed": True,
        "firmware_build_passed": True, "physical_hil_passed": True,
    }, "host_candidate.", failures)

    injection = evidence.get("hardware_watchdog_injection", {})
    exact(injection, {
        "evidence_id": "E-HIL-073", "status": "pass",
        "gate_eligible": True, "candidate_flashed_and_verified": True,
        "run_sha256": "c0fa78499a2e068e0b4f6dd2b9e7e832860ec67448c8d68cb367d6774bc8455b",
        "artifact_index_sha256": "4a95f526faff3e32ff4c60278dbf962b9a3d434eea4835d3f01c336e1f16cd2e",
        "watchdog_raw_sha256": "e246ae098ae4fa492b531f4115ebf079222c1c93133d7836d9a16951b3e7c60e",
        "cid": CID, "generation": 48, "observations": 16,
        "filesystem_write_attempted": False, "physical_write_calls": 0,
        "task_watchdog_triggered": True, "timed_out_task": "loopTask",
        "reset_reason_code": 6, "ready_marker_ms": 6697.964,
        "attempts": 2, "transient_retries": 1, "timeout_restarts": 1,
        "mounted_read_only": True, "read_only_guaranteed": True,
        "catalog_admitted": True, "cleanup_complete": True,
        "blocked_write_attempts": 0, "owned_after": 0,
        "heap_total_bytes": 276040, "heap_free_bytes": 227588,
        "heap_min_free_bytes": 192128,
        "final_owner": "none", "final_lease_mask": 0,
    }, "hardware_watchdog_injection.", failures)

    regression = evidence.get("final_regression", {})
    exact(regression, {
        "evidence_id": "E-HIL-074", "status": "pass",
        "gate_eligible": False, "cycles_completed": 3,
        "aggregate_run_sha256": "18814b571596c5b1f494cf3bcfa621eed64f89b4c33d812af73be74a9642eb4f",
        "aggregate_artifact_index_sha256": "922804315486d0a5f3fcdee28e325996fbc22bdc4890c80e394d8385db42f483",
        "elapsed_seconds": 152.234899, "cid": CID,
        "generation_before": 48, "generation_after": 51,
        "observations_accepted": 37, "observations_forwarded": 37,
        "scan_dropped": 0, "pipeline_dropped": 0,
        "cold_boots": 6, "boot_attempts": 6,
        "boot_transient_retries": 0, "boot_timeout_restarts": 0,
        "product_start_identity_attempts": 3,
        "product_start_identity_transient_retries": 0,
        "visual_captures": 12,
        "heap_total_bytes": 276040, "heap_free_bytes": 227588,
        "heap_min_free_bytes": 192128, "heap_drift_bytes": 0,
        "maximum_ready_marker_ms": 923.202,
        "final_generation": 51, "final_observations": 11,
        "final_owner": "none", "final_lease_mask": 0,
    }, "final_regression.", failures)

    for record in (failed, diagnostics, candidate, injection, regression):
        if isinstance(record, dict):
            for field, value in record.items():
                if field.endswith("sha256"):
                    require(failures, isinstance(value, str) and
                            SHA256.fullmatch(value) is not None,
                            f"{field}: invalid SHA-256")
    require(failures,
            failed.get("candidate_firmware_sha256") != candidate.get("firmware_sha256"),
            "candidate identity: failed 0.50 and untested 0.51 must differ")
    limitations = evidence.get("limitations", [])
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("eight-hour", "unknown", "three-cycle regression",
                   "local unsigned", "physical power-cut"):
        require(failures, phrase in joined, f"limitations: missing {phrase!r}")

    if failures:
        print("product hardware watchdog evidence failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product hardware watchdog evidence passed: 0.50 failure retained; "
        "0.51 hardware timeout recovered and generation 48->51 regression passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
