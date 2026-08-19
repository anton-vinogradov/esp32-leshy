#!/usr/bin/env python3
"""Run bounded foreground product Survey endurance on one enrolled test device."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import sha256_file, write_json
from run_1x_product_survey_hil import valid_cid


RUN_SCHEMA = "leshy.product_endurance_hil.run.v1"
RELEASE_MINIMUM_SECONDS = 45 * 60
RELEASE_MAXIMUM_SECONDS = 60 * 60
RELEASE_MINIMUM_CYCLES = 8
RELEASE_DEFAULT_MAXIMUM_CYCLES = 12
RELEASE_DEFAULT_INTERVAL_SECONDS = 5 * 60
NORMAL_MAXIMUM_READY_MS = 1500.0
RETRY_MAXIMUM_READY_MS = 30000.0


def execute(command: Sequence[str], log_prefix: Path) -> int:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    log_prefix.with_suffix(".stdout.log").write_text(
        result.stdout, encoding="utf-8"
    )
    log_prefix.with_suffix(".stderr.log").write_text(
        result.stderr, encoding="utf-8"
    )
    return result.returncode


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def heap_tuple(ready: dict[str, Any]) -> tuple[int, int, int] | None:
    values = (ready.get("heap_total"), ready.get("heap_free"),
              ready.get("heap_min_free"))
    if not all(isinstance(value, int) and not isinstance(value, bool)
               for value in values):
        return None
    total, free, minimum = values
    if minimum < 0 or free < minimum or total < free:
        return None
    return total, free, minimum


def summarize_cycle(run: dict[str, Any], number: int, expected_firmware: str,
                    expected_app: str, expected_version: str,
                    expected_cid: str | None,
                    prior_generation: int | None,
                    prior_observations: int | None,
                    baseline_heap: tuple[int, int, int] | None,
                    expected_flashed: bool) -> tuple[dict[str, Any], list[str],
                                                      str | None,
                                                      tuple[int, int, int] | None]:
    failures: list[str] = []
    prefix = f"cycle[{number}]"
    if run.get("schema") != "leshy.product_survey_hil.run.v1":
        failures.append(f"{prefix}.schema: unexpected")
    if run.get("passed") is not True:
        failures.append(f"{prefix}.passed: not true")
    candidate = run.get("candidate")
    if not isinstance(candidate, dict):
        failures.append(f"{prefix}.candidate: missing")
        candidate = {}
    for field, expected in {
        "firmware_sha256": expected_firmware,
        "app_elf_sha256": expected_app,
        "version": expected_version,
        "flashed": expected_flashed,
    }.items():
        if candidate.get(field) != expected:
            failures.append(
                f"{prefix}.candidate.{field}: {candidate.get(field)!r} != {expected!r}"
            )
    cid = run.get("expected_cid")
    if not valid_cid(cid):
        failures.append(f"{prefix}.expected_cid: invalid")
        cid = None
    elif expected_cid is not None and cid != expected_cid:
        failures.append(f"{prefix}.expected_cid: changed")

    before = run.get("boot_before")
    after = run.get("boot_after")
    running = run.get("running")
    committed = run.get("committed")
    export = run.get("library_export")
    final = run.get("final_state")
    if not isinstance(before, dict): before = {}
    if not isinstance(after, dict): after = {}
    if not isinstance(running, dict): running = {}
    if not isinstance(committed, dict): committed = {}
    if not isinstance(export, dict): export = {}
    if not isinstance(final, dict): final = {}
    before_recovery = before.get("recovery")
    after_recovery = after.get("recovery")
    before_ready = before.get("ready")
    after_ready = after.get("ready")
    before_timing = before.get("timing")
    after_timing = after.get("timing")
    if not isinstance(before_recovery, dict): before_recovery = {}
    if not isinstance(after_recovery, dict): after_recovery = {}
    if not isinstance(before_ready, dict): before_ready = {}
    if not isinstance(after_ready, dict): after_ready = {}
    if not isinstance(before_timing, dict): before_timing = {}
    if not isinstance(after_timing, dict): after_timing = {}

    generation_before = before_recovery.get("generation")
    observations_before = before_recovery.get("observations")
    generation_after = committed.get("survey_generation")
    observations_after = committed.get("survey_observations")
    if not isinstance(generation_before, int) or generation_before < 1:
        failures.append(f"{prefix}.generation_before: invalid")
    if not isinstance(observations_before, int) or observations_before < 1:
        failures.append(f"{prefix}.observations_before: invalid")
    if prior_generation is not None and generation_before != prior_generation:
        failures.append(
            f"{prefix}.generation_before: {generation_before!r} != {prior_generation}"
        )
    if prior_observations is not None and observations_before != prior_observations:
        failures.append(
            f"{prefix}.observations_before: {observations_before!r} "
            f"!= {prior_observations}"
        )
    if (not isinstance(generation_before, int)
            or generation_after != generation_before + 1):
        failures.append(f"{prefix}.generation_after: not the next generation")
    if not isinstance(observations_after, int) or observations_after < 1:
        failures.append(f"{prefix}.observations_after: invalid")
        observations_after = 0
    wifi_accepted = committed.get("survey_scan_accepted")
    ble_accepted = committed.get("survey_ble_scan_accepted")
    if (not isinstance(wifi_accepted, int)
            or not isinstance(ble_accepted, int)
            or wifi_accepted + ble_accepted != observations_after):
        failures.append(f"{prefix}.radio_accepted: accounting mismatch")
    if committed.get("survey_forwarded") != observations_after:
        failures.append(f"{prefix}.survey_forwarded: accounting mismatch")
    for field in (
        "survey_scan_rejected", "survey_scan_dropped",
        "survey_ble_scan_rejected", "survey_ble_scan_dropped",
        "survey_dropped",
    ):
        if committed.get(field) != 0:
            failures.append(f"{prefix}.{field}: expected zero")
    start_attempts = running.get("survey_product_identity_attempts")
    start_retries = running.get("survey_product_identity_transient_retries")
    if (not isinstance(start_attempts, int) or isinstance(start_attempts, bool)
            or start_attempts < 1 or start_attempts > 8
            or start_retries != start_attempts - 1):
        failures.append(f"{prefix}.product_start.retry_metrics: invalid")
    for field, expected in {
        "generation": generation_after,
        "observations": observations_after,
        "blocked_write_attempts": 0,
        "physical_write_calls": 0,
        "cleanup_complete": True,
        "read_only_guaranteed": True,
    }.items():
        if after_recovery.get(field) != expected:
            failures.append(f"{prefix}.boot_after.recovery.{field}: mismatch")
    attempt_metrics: dict[str, int | None] = {}
    for name, recovery in (("before", before_recovery),
                           ("after", after_recovery)):
        attempts = recovery.get("attempts")
        retries = recovery.get("transient_retries")
        timeouts = recovery.get("timeout_restarts", 0)
        attempt_metrics[f"{name}_attempts"] = attempts
        attempt_metrics[f"{name}_transient_retries"] = retries
        attempt_metrics[f"{name}_timeout_restarts"] = timeouts
        if (not isinstance(attempts, int) or isinstance(attempts, bool)
                or attempts < 1 or attempts > 8 or retries != attempts - 1):
            failures.append(f"{prefix}.boot_{name}.retry_metrics: invalid")
        if (not isinstance(timeouts, int) or isinstance(timeouts, bool)
                or timeouts < 0
                or not isinstance(retries, int) or isinstance(retries, bool)
                or timeouts > retries):
            failures.append(f"{prefix}.boot_{name}.timeout_metrics: invalid")
    for field, expected in {
        "generation": generation_after,
        "persistent": True,
        "simulated": False,
        "integrity": "valid",
        "radio_touched": False,
    }.items():
        if export.get(field) != expected:
            failures.append(f"{prefix}.library_export.{field}: mismatch")
    session = export.get("session")
    if (not isinstance(session, dict)
            or session.get("id") != "product-passive-live"
            or session.get("observations") != observations_after
            or session.get("dropped") != 0):
        failures.append(f"{prefix}.library_export.session: accounting mismatch")
    for field, expected in {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": True,
    }.items():
        if final.get(field) != expected:
            failures.append(f"{prefix}.final_state.{field}: mismatch")
    captures = run.get("captures")
    if (not isinstance(captures, dict)
            or set(captures) != {"setup", "paused", "committed", "export"}):
        failures.append(f"{prefix}.captures: require four ordered product states")

    heaps = (heap_tuple(before_ready), heap_tuple(after_ready))
    if heaps[0] is None or heaps[1] is None or heaps[0] != heaps[1]:
        failures.append(f"{prefix}.heap: invalid or changed across cold boot")
    cycle_heap = heaps[0]
    if baseline_heap is not None and cycle_heap != baseline_heap:
        failures.append(f"{prefix}.heap: drift from first-cycle baseline")
    for name, timing, recovery in (
        ("before", before_timing, before_recovery),
        ("after", after_timing, after_recovery),
    ):
        ready_ms = timing.get("ready_marker_ms")
        retries = recovery.get("transient_retries", 0)
        maximum_ready = (
            RETRY_MAXIMUM_READY_MS if isinstance(retries, int) and retries > 0
            else NORMAL_MAXIMUM_READY_MS
        )
        if (not isinstance(ready_ms, (int, float)) or isinstance(ready_ms, bool)
                or not 0 < ready_ms <= maximum_ready):
            failures.append(f"{prefix}.ready_{name}_ms: outside budget")
    summary = {
        "number": number,
        "run_id": run.get("run_id"),
        "passed": not failures,
        "candidate_flashed": candidate.get("flashed"),
        "cid": cid,
        "generation_before": generation_before,
        "observations_before": observations_before,
        "generation_after": generation_after,
        "observations_after": observations_after,
        "scan_accepted": committed.get("survey_scan_accepted"),
        "ble_scan_accepted": committed.get("survey_ble_scan_accepted"),
        "forwarded": committed.get("survey_forwarded"),
        "scan_dropped": committed.get("survey_scan_dropped"),
        "ble_scan_dropped": committed.get("survey_ble_scan_dropped"),
        "pipeline_dropped": committed.get("survey_dropped"),
        "heap_before": list(heaps[0]) if heaps[0] is not None else None,
        "heap_after": list(heaps[1]) if heaps[1] is not None else None,
        "ready_before_ms": before_timing.get("ready_marker_ms"),
        "ready_after_ms": after_timing.get("ready_marker_ms"),
        "boot_before_attempts": attempt_metrics["before_attempts"],
        "boot_before_transient_retries": attempt_metrics[
            "before_transient_retries"
        ],
        "boot_before_timeout_restarts": attempt_metrics[
            "before_timeout_restarts"
        ],
        "boot_after_attempts": attempt_metrics["after_attempts"],
        "boot_after_transient_retries": attempt_metrics[
            "after_transient_retries"
        ],
        "boot_after_timeout_restarts": attempt_metrics[
            "after_timeout_restarts"
        ],
        "product_start_identity_attempts": start_attempts,
        "product_start_identity_transient_retries": start_retries,
        "final_owner": final.get("runtime_owner"),
        "final_lease_mask": final.get("lease_mask"),
        "failures": failures,
    }
    return summary, failures, cid, cycle_heap


def release_policy(flash: bool, acknowledged: bool, duration_seconds: float,
                   minimum_cycles: int) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not flash:
        failures.append("exact candidate must be flashed")
    if not acknowledged:
        failures.append("--release-endurance acknowledgement is required")
    if duration_seconds < RELEASE_MINIMUM_SECONDS:
        failures.append(f"duration must be at least {RELEASE_MINIMUM_SECONDS} seconds")
    if duration_seconds > RELEASE_MAXIMUM_SECONDS:
        failures.append(f"duration must be at most {RELEASE_MAXIMUM_SECONDS} seconds")
    if minimum_cycles < RELEASE_MINIMUM_CYCLES:
        failures.append(f"minimum cycles must be at least {RELEASE_MINIMUM_CYCLES}")
    return not failures, failures


def artifact_manifest(output: Path) -> None:
    lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "artifacts.sha256":
            lines.append(f"{sha256_file(path)}  {path.relative_to(output)}")
    (output / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def checkpoint(output: Path, result: dict[str, Any]) -> None:
    write_json(output / "run.json", result)
    artifact_manifest(output)


def foreground_wait(seconds: float, completed: int) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        print(json.dumps({
            "status": "waiting", "cycles_completed": completed,
            "next_cycle_in_seconds": round(remaining, 1),
        }, sort_keys=True), flush=True)
        time.sleep(min(30.0, remaining))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration-seconds", type=float, default=RELEASE_MINIMUM_SECONDS)
    parser.add_argument("--minimum-cycles", type=int, default=RELEASE_MINIMUM_CYCLES)
    parser.add_argument(
        "--maximum-cycles", type=int, default=RELEASE_DEFAULT_MAXIMUM_CYCLES
    )
    parser.add_argument(
        "--interval-seconds", type=float,
        default=RELEASE_DEFAULT_INTERVAL_SECONDS,
    )
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--release-endurance", action="store_true")
    parser.add_argument("--flash-offset", default="0x10000")
    parser.add_argument("--flash-baud", default="460800")
    parser.add_argument("--boot-seconds", default="20.0")
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not 0 <= args.duration_seconds <= 172800:
        parser.error("--duration-seconds must be in 0..172800")
    if not 1 <= args.minimum_cycles <= args.maximum_cycles <= 1024:
        parser.error("require 1 <= minimum-cycles <= maximum-cycles <= 1024")
    if not 0 <= args.interval_seconds <= 3600:
        parser.error("--interval-seconds must be in 0..3600")
    policy_ok, policy_failures = release_policy(
        args.flash, args.release_endurance, args.duration_seconds,
        args.minimum_cycles,
    )
    if args.release_endurance and not policy_ok:
        parser.error("release endurance policy: " + "; ".join(policy_failures))

    args.output.mkdir(parents=True)
    firmware_hash = sha256_file(args.firmware)
    app_identity = app_elf_sha256(args.firmware)
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    summaries: list[dict[str, Any]] = []
    failures: list[str] = []
    cid: str | None = None
    prior_generation: int | None = None
    prior_observations: int | None = None
    baseline_heap: tuple[int, int, int] | None = None

    result: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "passed": False,
        "gate_eligible": False,
        "trust_status": "unsigned_local_result",
        "started_at": started_at,
        "candidate": {
            "firmware_sha256": firmware_hash,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "first_cycle_flashed": args.flash,
        },
        "policy": {
            "release_endurance_requested": args.release_endurance,
            "release_policy_satisfied": policy_ok,
            "release_policy_failures": policy_failures,
            "required_release_duration_seconds": RELEASE_MINIMUM_SECONDS,
            "maximum_release_elapsed_seconds": RELEASE_MAXIMUM_SECONDS,
            "required_release_minimum_cycles": RELEASE_MINIMUM_CYCLES,
            "duration_seconds": args.duration_seconds,
            "minimum_cycles": args.minimum_cycles,
            "maximum_cycles": args.maximum_cycles,
            "interval_seconds": args.interval_seconds,
        },
        "cycles": summaries,
        "failures": failures,
    }
    checkpoint(args.output, result)
    try:
        while True:
            number = len(summaries) + 1
            cycle_dir = args.output / f"cycle-{number:04d}"
            command = [
                sys.executable,
                str(Path(__file__).with_name("run_1x_product_survey_hil.py")),
                "--port", args.port,
                "--firmware", str(args.firmware.resolve()),
                "--expected-version", args.expected_version,
                "--output", str(cycle_dir),
                "--flash-offset", args.flash_offset,
                "--flash-baud", args.flash_baud,
                "--boot-seconds", args.boot_seconds,
                "--release-cycle",
            ]
            if number == 1 and args.flash:
                command.append("--flash")
            if cid is not None:
                command.extend(["--expected-cid", cid])
            cycle_started = time.monotonic()
            return_code = execute(command, args.output / f"cycle-{number:04d}-runner")
            run_path = cycle_dir / "run.json"
            if not run_path.is_file():
                failures.append(f"cycle[{number}]: runner exited {return_code} without run.json")
                break
            run = load_object(run_path)
            summary, cycle_failures, observed_cid, cycle_heap = summarize_cycle(
                run, number, firmware_hash, app_identity, args.expected_version,
                cid, prior_generation, prior_observations, baseline_heap,
                number == 1 and args.flash,
            )
            summary["return_code"] = return_code
            summary["elapsed_seconds"] = round(time.monotonic() - cycle_started, 6)
            summary["run_sha256"] = sha256_file(run_path)
            summary["artifact_index_sha256"] = sha256_file(
                cycle_dir / "artifacts.sha256"
            ) if (cycle_dir / "artifacts.sha256").is_file() else None
            if return_code != 0:
                cycle_failures.append(f"cycle[{number}]: runner exit {return_code}")
                summary["failures"] = cycle_failures
                summary["passed"] = False
            summaries.append(summary)
            failures.extend(cycle_failures)
            if observed_cid is not None:
                cid = observed_cid
            if baseline_heap is None and cycle_heap is not None:
                baseline_heap = cycle_heap
            if isinstance(summary.get("generation_after"), int):
                prior_generation = summary["generation_after"]
            if isinstance(summary.get("observations_after"), int):
                prior_observations = summary["observations_after"]
            elapsed = time.monotonic() - started_monotonic
            result["elapsed_seconds"] = round(elapsed, 6)
            result["cycles_completed"] = len(summaries)
            result["expected_cid"] = cid
            result["baseline_heap"] = list(baseline_heap) if baseline_heap else None
            checkpoint(args.output, result)
            print(json.dumps({
                "status": "cycle_complete", "cycle": number,
                "passed": summary["passed"], "generation": prior_generation,
                "observations": prior_observations,
                "elapsed_seconds": round(elapsed, 1),
            }, sort_keys=True), flush=True)
            if failures:
                break
            if len(summaries) >= args.minimum_cycles and elapsed >= args.duration_seconds:
                break
            if len(summaries) >= args.maximum_cycles:
                failures.append("maximum cycles reached before duration/minimum gate")
                break
            foreground_wait(args.interval_seconds, len(summaries))
    except KeyboardInterrupt:
        failures.append("operator interrupted endurance run")
        result["status"] = "interrupted"
    except Exception as error:
        failures.append(
            f"orchestrator exception: {type(error).__name__}: {error}"
        )
        result["status"] = "failed"

    elapsed = time.monotonic() - started_monotonic
    if (args.release_endurance and elapsed > RELEASE_MAXIMUM_SECONDS
            and "release endurance exceeded one-hour operational budget"
            not in failures):
        failures.append("release endurance exceeded one-hour operational budget")
    requirements_met = (
        len(summaries) >= args.minimum_cycles and elapsed >= args.duration_seconds
    )
    if not requirements_met and result.get("status") != "interrupted":
        failures.append("configured duration/minimum cycles were not completed")
    result.update({
        "status": "pass" if not failures and requirements_met else result.get(
            "status", "failed"
        ),
        "passed": not failures and requirements_met,
        "gate_eligible": (
            not failures and requirements_met and policy_ok
            and args.release_endurance
        ),
        "elapsed_seconds": round(elapsed, 6),
        "cycles_completed": len(summaries),
        "expected_cid": cid,
        "baseline_heap": list(baseline_heap) if baseline_heap else None,
        "final_generation": prior_generation,
        "final_observations": prior_observations,
        "failures": failures,
    })
    result["policy"]["measured_elapsed_within_budget"] = (
        elapsed <= RELEASE_MAXIMUM_SECONDS
        if args.release_endurance else None
    )
    if result["status"] == "in_progress":
        result["status"] = "failed"
    checkpoint(args.output, result)
    print(json.dumps({
        "output": str(args.output.resolve()), "status": result["status"],
        "passed": result["passed"], "gate_eligible": result["gate_eligible"],
        "cycles_completed": len(summaries),
        "elapsed_seconds": result["elapsed_seconds"], "failures": failures,
    }, sort_keys=True))
    if result["status"] == "interrupted":
        return 130
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
