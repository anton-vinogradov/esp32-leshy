#!/usr/bin/env python3
"""Fail closed unless exact Device Lock UI/KDF acceptance is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT / "tests/hil/evidence/board-01-device-lock-1.0.0-dev.278.json")


def main() -> int:
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    value = json.loads(SUMMARY.read_text(encoding="utf-8"))
    failures: list[str] = []
    expected_candidate = {
        "app_elf_sha256":
            "ec752911e4250e26b1c8be67f7fd4470f82339ccd4f46cbeb6f00a674e6b46e5",
        "firmware_sha256":
            "b832b856ba60ce6dfb49ebd0c1d6e4ad0810f500e140b02ec631ee85185e7fd1",
        "flash_mode": "fresh",
        "flashed": True,
        "source_commit": "e6d6ecbaa957015335bec986fe11d32809072d39",
        "version": "1.0.0-dev.278",
    }
    if value.get("schema") != "leshy.device_lock_hil.acceptance.v1" or \
            value.get("status") != "pass_ui_kdf_slice" or \
            value.get("board") != "board-01" or \
            value.get("exact_cid") != "FE343253440000002000000055019CB7" or \
            value.get("candidate") != expected_candidate:
        failures.append("exact accepted candidate mismatch")
    if value.get("evidence_ids") != [
            "E-BUILD-195", "E-AUTO-170", "E-HIL-207", "E-UX-064"]:
        failures.append("evidence ID mismatch")

    verified = value.get("verified", {})
    expected_exact = {
        "pbkdf2_hmac_sha256_iterations": 120000,
        "benchmark_vector_verified_twice": True,
        "one_time_heap_initialization_bytes": 120,
        "repeat_heap_before": 67488,
        "repeat_heap_after": 67488,
        "status_render_mode": "full",
        "editor_render_mode": "full",
        "pin_navigation_render_mode": "incremental",
        "credential_enrollment": False,
        "credential_generation_before": 0,
        "credential_generation_after": 0,
        "storage_generation_before": 176,
        "storage_generation_after": 176,
        "storage_physical_write_calls": 0,
        "radio_touched": False,
        "input_read_errors": 0,
        "input_queue_drops": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
        "final_safety_state": "armed",
        "clone_touched": False,
        "cardputer_touched": False,
        "mac_wifi_touched": False,
    }
    for field, expected in expected_exact.items():
        if verified.get(field) != expected:
            failures.append(f"verified field mismatch: {field}")
    for field in ("warmup_elapsed_us", "repeat_elapsed_us"):
        elapsed = verified.get(field)
        if not isinstance(elapsed, int) or not 0 < elapsed <= 15_000_000:
            failures.append(f"KDF timing mismatch: {field}")
    ack = verified.get("ui_ack_during_kdf_ms")
    if not isinstance(ack, (int, float)) or not 0 < ack <= 500:
        failures.append("UI response timing mismatch")
    for field in ("status_png_sha256", "editor_png_sha256",
                  "pin_delta_png_sha256"):
        digest = verified.get(field)
        if not isinstance(digest, str) or len(digest) != 64:
            failures.append(f"screen hash mismatch: {field}")
    evidence = value.get("evidence", {})
    for field in ("run_sha256", "runner_sha256",
                  "watchdog_precursor_run_sha256",
                  "watchdog_metrics_sha256", "watchdog_safety_sha256",
                  "delta_precursor_run_sha256"):
        digest = evidence.get(field)
        if not isinstance(digest, str) or len(digest) != 64:
            failures.append(f"evidence hash mismatch: {field}")
    if value.get("open") != [
            "physical credential enrollment and cold credential restore",
            "physical retry-delay and recovery-only transitions",
            "protected-action admission",
            "encrypted data at rest"]:
        failures.append("open-scope boundary mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Device Lock HIL acceptance passed: exact KDF twice, responsive incremental UI, zero credential/storage/radio mutation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
