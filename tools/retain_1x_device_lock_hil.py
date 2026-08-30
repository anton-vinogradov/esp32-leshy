#!/usr/bin/env python3
"""Retain privacy-minimal exact Device Lock UI/KDF HIL acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.278"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "e6d6ecbaa957015335bec986fe11d32809072d39"
FIRMWARE_SHA256 = (
    "b832b856ba60ce6dfb49ebd0c1d6e4ad0810f500e140b02ec631ee85185e7fd1")
APP_ELF_SHA256 = (
    "ec752911e4250e26b1c8be67f7fd4470f82339ccd4f46cbeb6f00a674e6b46e5")
RUNNER_SHA256 = (
    "3585aa62320e63cacdff15c7c1b41845e48625a71568e6cdd04e7c980fab6947")
DEFAULT_DESTINATION = (
    ROOT / "tests/hil/evidence/board-01-device-lock-1.0.0-dev.278.json")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--watchdog-precursor", required=True, type=Path)
    parser.add_argument("--watchdog-metrics", required=True, type=Path)
    parser.add_argument("--watchdog-safety", required=True, type=Path)
    parser.add_argument("--delta-precursor", required=True, type=Path)
    parser.add_argument("--destination", type=Path,
                        default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    destination = args.destination.resolve()
    require(not destination.exists(), "destination must not exist")

    run_path = args.run.resolve() / "run.json"
    run = load(run_path)
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.device_lock_hil.run.v1" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    require(candidate == {
        "app_elf_sha256": APP_ELF_SHA256,
        "firmware_sha256": FIRMWARE_SHA256,
        "flash_mode": "fresh",
        "flashed": True,
        "source_commit": SOURCE_COMMIT,
        "version": VERSION,
    }, "exact candidate binding mismatch")
    require(run.get("expected_cid") == CID and
            run.get("runner_sha256") == RUNNER_SHA256,
            "board or runner binding mismatch")

    warmup = run["reports"]["benchmark_warmup"]
    repeat = run["reports"]["benchmark"]
    for report in (warmup, repeat):
        require(report["benchmark_vector_verified"] is True and
                report["benchmark_success"] is True and
                report["persistence_touched_by_benchmark"] is False and
                report["radio_touched"] is False and
                report["status"] == "unconfigured" and
                report["credential_generation"] == 0 and
                report["failed_attempts"] == 0,
                "KDF or no-persistence invariant mismatch")
        require(0 < report["benchmark_elapsed_us"] <= 15_000_000,
                "KDF timing is outside the accepted bound")
    require(warmup["benchmark_heap_before"] -
            warmup["benchmark_heap_after"] == 120,
            "expected bounded first-use mbedTLS initialization")
    require(repeat["benchmark_heap_before"] ==
            repeat["benchmark_heap_after"] ==
            warmup["benchmark_heap_after"],
            "repeat KDF heap must be byte-invariant")

    reports = run["reports"]
    require(reports["ui_during_kdf"]["host_ack_ms"] <= 500.0,
            "UI response exceeded the physical bound")
    require(reports["metrics_before"]["heap_free"] -
            reports["metrics_after"]["heap_free"] == 120,
            "final heap does not match measured warm baseline")
    require(reports["recovery_before"]["generation"] ==
            reports["recovery_after"]["generation"] == 176 and
            reports["recovery_before"]["observations"] ==
            reports["recovery_after"]["observations"] == 51 and
            reports["recovery_after"]["physical_write_calls"] == 0,
            "storage changed during Device Lock HIL")
    require(reports["input"]["read_errors"] == 0 and
            reports["input"]["queue_drops"] == 0,
            "input frontend is not clean")
    require(reports["safe_outputs"]["buzzer_inactive"] is True and
            reports["safe_outputs"]["buzzer_level"] == "low",
            "safe outputs are not quiescent")

    screens = run["screens"]
    require(screens["device_lock_status"]["state"]["render_mode"] ==
            "full" and
            screens["device_lock_editor"]["state"]["render_mode"] ==
            "full" and
            screens["device_lock_editor_delta"]["state"]["render_mode"] ==
            "incremental", "PIN repaint contract mismatch")
    final = run["cleanup_after"]["final_state"]
    require(run["cleanup_after"]["complete"] is True and
            final["page"] == "home" and
            final["runtime_owner"] == "none" and
            final["lease_mask"] == 0 and
            final["safety_state"] == "armed" and
            run["hil_ended"]["active"] is False,
            "final cleanup mismatch")
    require(run["scope"] == {
        "cardputer": False,
        "clone": False,
        "credential_enrollment": False,
        "credential_persistence": False,
        "mac_wifi": False,
        "radio": False,
        "storage_write": False,
    }, "scope widened unexpectedly")

    watchdog_run = load(args.watchdog_precursor.resolve())
    delta_run = load(args.delta_precursor.resolve())
    watchdog_metrics = load(args.watchdog_metrics.resolve())
    watchdog_safety = load(args.watchdog_safety.resolve())
    require(watchdog_run.get("passed") is False and
            watchdog_run.get("gate_eligible") is False and
            watchdog_metrics.get("reset_reason_code") == 6 and
            watchdog_safety.get("state") == "latched" and
            watchdog_safety.get("reason") == "runtime_watchdog" and
            watchdog_safety.get("runtime_owner") == "none" and
            watchdog_safety.get("lease_mask") == 0,
            "watchdog precursor is not the retained fail-closed reset")
    require(delta_run.get("passed") is False and
            delta_run.get("gate_eligible") is False and
            any("render_mode" in item for item in delta_run["failures"]) and
            any("heap" in item.lower() for item in delta_run["failures"]),
            "delta precursor does not preserve the rejected UI/heap gate")

    value = {
        "schema": "leshy.device_lock_hil.acceptance.v1",
        "status": "pass_ui_kdf_slice",
        "board": "board-01",
        "evidence_ids": ["E-BUILD-195", "E-AUTO-170", "E-HIL-207",
                         "E-UX-064"],
        "exact_cid": CID,
        "candidate": candidate,
        "evidence": {
            "run_id": run["run_id"],
            "run_sha256": digest(run_path),
            "runner_sha256": RUNNER_SHA256,
            "watchdog_precursor_run_sha256":
                digest(args.watchdog_precursor.resolve()),
            "watchdog_metrics_sha256":
                digest(args.watchdog_metrics.resolve()),
            "watchdog_safety_sha256": digest(args.watchdog_safety.resolve()),
            "delta_precursor_run_sha256":
                digest(args.delta_precursor.resolve()),
        },
        "verified": {
            "pbkdf2_hmac_sha256_iterations": 120000,
            "benchmark_vector_verified_twice": True,
            "warmup_elapsed_us": warmup["benchmark_elapsed_us"],
            "repeat_elapsed_us": repeat["benchmark_elapsed_us"],
            "one_time_heap_initialization_bytes": 120,
            "repeat_heap_before": repeat["benchmark_heap_before"],
            "repeat_heap_after": repeat["benchmark_heap_after"],
            "ui_ack_during_kdf_ms": reports["ui_during_kdf"]["host_ack_ms"],
            "status_render_mode": "full",
            "editor_render_mode": "full",
            "pin_navigation_render_mode": "incremental",
            "status_png_sha256":
                screens["device_lock_status"]["png_sha256"],
            "editor_png_sha256":
                screens["device_lock_editor"]["png_sha256"],
            "pin_delta_png_sha256":
                screens["device_lock_editor_delta"]["png_sha256"],
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
        },
        "open": [
            "physical credential enrollment and cold credential restore",
            "physical retry-delay and recovery-only transitions",
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
