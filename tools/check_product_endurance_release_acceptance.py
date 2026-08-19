#!/usr/bin/env python3
"""Verify retained exact-candidate 0.89 release-endurance evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-product-endurance-0.89.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-endurance-0.89"
VERSION = "0.89.0-touch-storage-dma"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "450d5d886e517c3d12576d9e0fa425898e682535"
FIRMWARE = "db6378aef217cc2d8d413b3915b9c1a4350e6236503283db652e1cb0ca5042b8"
APP = "2f62f98279ec38fe96a23f9337ba7335a507105ac0b8f94b40eaa8a79e7d0493"
FACTORY = "30186764716ab510cbb10d0b2ddb7a8fd6505c37c5595a4aebb454f352172cb0"
HEAP = [231772, 166812, 147460]
AGGREGATE = "995c1f99b9797e6f60ffe94e3327cc2d8670c516f6270251458b2cab1fe46074"
INDEX = "f5bc777d08bb6d190b147957384ab1a4516c67b7b07c9a75a0fabacf4a8fb342"
ENDURANCE_RUNNER = "a14d527b3506e987fef6c5570989e4284c281f6bbdb4a679925a4ade36575c66"
SURVEY_RUNNER = "cad284eff80953d0ee5c7e897a87109ca637e79e8325513147d08b1b1b080dd0"
SHA256 = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{path.relative_to(ROOT)}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{path.relative_to(ROOT)}: expected JSON object")
        return {}
    return value


def mismatch(failures: list[str], record: dict[str, Any], field: str,
             expected: Any, prefix: str = "") -> None:
    if record.get(field) != expected:
        failures.append(
            f"{prefix}{field}: {record.get(field)!r} != {expected!r}"
        )


def object_field(failures: list[str], record: dict[str, Any], field: str,
                 prefix: str) -> dict[str, Any]:
    value = record.get(field)
    if not isinstance(value, dict):
        failures.append(f"{prefix}{field}: missing object")
        return {}
    return value


def retry_metrics(failures: list[str], recovery: dict[str, Any],
                  prefix: str) -> tuple[int, int, int]:
    attempts = recovery.get("attempts")
    retries = recovery.get("transient_retries")
    timeouts = recovery.get("timeout_restarts", 0)
    if (not isinstance(attempts, int) or isinstance(attempts, bool)
            or not 1 <= attempts <= 8 or retries != attempts - 1):
        failures.append(f"{prefix}: invalid attempts/retries")
        attempts = 0
        retries = 0
    if (not isinstance(timeouts, int) or isinstance(timeouts, bool)
            or timeouts < 0 or timeouts > retries):
        failures.append(f"{prefix}: invalid timeout restarts")
        timeouts = 0
    return attempts, retries, timeouts


def verify_manifest(failures: list[str]) -> tuple[int, str]:
    manifest = BUNDLE / "artifacts.sha256"
    if not manifest.is_file():
        failures.append("bundle artifacts.sha256: missing")
        return 0, ""
    entries: dict[str, str] = {}
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"artifacts.sha256:{number}: malformed")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in entries:
            failures.append(f"artifacts.sha256:{number}: unsafe/duplicate path")
            continue
        path = BUNDLE / relative
        if not path.is_file():
            failures.append(f"artifacts.sha256:{number}: missing {name}")
        elif digest(path) != expected:
            failures.append(f"artifacts.sha256:{number}: hash mismatch {name}")
        entries[name] = expected
    actual = {
        str(path.relative_to(BUNDLE))
        for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(entries) != actual:
        failures.append("artifacts.sha256: inventory does not exactly cover bundle")
    return len(actual) + 1, digest(manifest)


def verify_boot(failures: list[str], boot: dict[str, Any], generation: int,
                observations: int, prefix: str) -> tuple[int, int, int]:
    ready = object_field(failures, boot, "ready", prefix)
    recovery = object_field(failures, boot, "recovery", prefix)
    mismatch(failures, ready, "version", VERSION, prefix + "ready.")
    mismatch(failures, ready, "app_elf_sha256", APP, prefix + "ready.")
    heap = [ready.get("heap_total"), ready.get("heap_free"),
            ready.get("heap_min_free")]
    if heap != HEAP:
        failures.append(f"{prefix}ready.heap: {heap!r} != {HEAP!r}")
    for field, expected in {
        "generation": generation,
        "observations": observations,
        "expected_fingerprint": CID,
        "observed_fingerprint": CID,
        "fingerprint_matched": True,
        "integrity": "valid",
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "blocked_write_attempts": 0,
        "physical_write_calls": 0,
        "cleanup_complete": True,
        "owned_after": 0,
    }.items():
        mismatch(failures, recovery, field, expected, prefix + "recovery.")
    return retry_metrics(failures, recovery, prefix + "recovery.retry")


def verify_cycle(failures: list[str], cycle: dict[str, Any], number: int,
                 generation: int, observations_before: int,
                 survey_runner_hash: str) -> tuple[int, int, dict[str, int]]:
    prefix = f"cycle[{number}]."
    for field, expected in {
        "schema": "leshy.product_survey_hil.run.v1",
        "passed": True,
        "gate_eligible": number == 1,
        "failures": [],
        "expected_cid": CID,
        "release_cycle": True,
        "runner_source_sha256": survey_runner_hash,
    }.items():
        mismatch(failures, cycle, field, expected, prefix)
    candidate = object_field(failures, cycle, "candidate", prefix)
    for field, expected in {
        "version": VERSION,
        "firmware_sha256": FIRMWARE,
        "app_elf_sha256": APP,
        "flashed": number == 1,
    }.items():
        mismatch(failures, candidate, field, expected, prefix + "candidate.")

    before = object_field(failures, cycle, "boot_before", prefix)
    before_metrics = verify_boot(
        failures, before, generation, observations_before,
        prefix + "boot_before.",
    )
    running = object_field(failures, cycle, "running", prefix)
    paused = object_field(failures, cycle, "paused", prefix)
    browser = object_field(failures, cycle, "paused_browser", prefix)
    committed = object_field(failures, cycle, "committed", prefix)
    observations = running.get("survey_observations")
    wifi = running.get("survey_scan_accepted")
    ble = running.get("survey_ble_scan_accepted")
    if (not isinstance(observations, int) or observations < 1
            or not isinstance(wifi, int) or not isinstance(ble, int)
            or wifi + ble != observations):
        failures.append(prefix + "running: invalid radio observation accounting")
        observations = 0
        wifi = 0
        ble = 0
    for state_name, state, status, source_active, cleanup in (
        ("running", running, "running", True, False),
        ("paused", paused, "paused", False, False),
        ("committed", committed, "committed", False, True),
    ):
        state_prefix = f"{prefix}{state_name}."
        for field, expected in {
            "page": "survey",
            "runtime_owner": "survey",
            "lease_mask": 15,
            "survey_product_status": status,
            "survey_product_source_active": source_active,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_cleanup_complete": cleanup,
            "survey_product_scan_cycles": 1,
            "survey_product_wifi_scan_cycles": 1,
            "survey_product_ble_scan_cycles": 1,
            "survey_observations": observations,
            "survey_received": observations,
            "survey_forwarded": observations,
            "survey_scan_accepted": wifi,
            "survey_ble_scan_accepted": ble,
            "survey_scan_rejected": 0,
            "survey_scan_dropped": 0,
            "survey_ble_scan_rejected": 0,
            "survey_ble_scan_dropped": 0,
            "survey_dropped": 0,
        }.items():
            mismatch(failures, state, field, expected, state_prefix)
    start_attempts = running.get("survey_product_identity_attempts")
    start_retries = running.get("survey_product_identity_transient_retries")
    if (not isinstance(start_attempts, int) or isinstance(start_attempts, bool)
            or not 1 <= start_attempts <= 8
            or start_retries != start_attempts - 1):
        failures.append(prefix + "running: invalid Product Start retry metrics")
        start_attempts = 0
        start_retries = 0
    for field, expected in {
        "view": "list", "filter_focused": True, "total": observations,
        "selected": False, "radio_touched": False, "storage_touched": False,
    }.items():
        mismatch(failures, browser, field, expected, prefix + "paused_browser.")
    mismatch(failures, committed, "survey_generation", generation + 1,
             prefix + "committed.")
    mismatch(failures, committed, "survey_workflow_state", "result",
             prefix + "committed.")
    mismatch(failures, committed, "survey_workflow_status", "committed",
             prefix + "committed.")

    after = object_field(failures, cycle, "boot_after", prefix)
    after_metrics = verify_boot(
        failures, after, generation + 1, observations,
        prefix + "boot_after.",
    )
    export = object_field(failures, cycle, "library_export", prefix)
    for field, expected in {
        "generation": generation + 1,
        "persistent": True,
        "simulated": False,
        "integrity": "valid",
        "radio_touched": False,
    }.items():
        mismatch(failures, export, field, expected, prefix + "library_export.")
    session = object_field(failures, export, "session", prefix + "library_export.")
    for field, expected in {
        "id": "product-passive-live", "observations": observations,
        "dropped": 0,
    }.items():
        mismatch(failures, session, field, expected,
                 prefix + "library_export.session.")
    sources = object_field(failures, session, "sources",
                           prefix + "library_export.session.")
    mismatch(failures, sources, "wifi", wifi,
             prefix + "library_export.session.sources.")
    mismatch(failures, sources, "ble", ble,
             prefix + "library_export.session.sources.")
    final = object_field(failures, cycle, "final_state", prefix)
    for field, expected in {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
    }.items():
        mismatch(failures, final, field, expected, prefix + "final_state.")
    captures = cycle.get("captures")
    if not isinstance(captures, dict) or set(captures) != {
            "setup", "paused", "committed", "export"}:
        failures.append(prefix + "captures: exact four-state set required")
    else:
        for name, capture in captures.items():
            if not isinstance(capture, dict):
                failures.append(f"{prefix}captures.{name}: missing object")
                continue
            for field in ("png_sha256", "rgb565_sha256"):
                if SHA256.fullmatch(str(capture.get(field, ""))) is None:
                    failures.append(f"{prefix}captures.{name}.{field}: invalid")
    return generation + 1, observations, {
        "wifi": wifi,
        "ble": ble,
        "observations": observations,
        "boot_attempts": before_metrics[0] + after_metrics[0],
        "boot_retries": before_metrics[1] + after_metrics[1],
        "boot_timeouts": before_metrics[2] + after_metrics[2],
        "product_attempts": start_attempts,
        "product_retries": start_retries,
    }


def main() -> int:
    failures: list[str] = []
    summary = load(SUMMARY, failures)
    files, index_hash = verify_manifest(failures)
    for field, expected in {
        "schema": "leshy.product_endurance_acceptance.v1",
        "status": "pass_release_endurance",
        "trust_status": "unsigned_local_result",
        "gate_eligible": True,
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
    }.items():
        mismatch(failures, summary, field, expected)
    candidate = object_field(failures, summary, "candidate", "")
    for field, expected in {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE,
        "app_elf_sha256": APP,
        "factory_sha256": FACTORY,
        "endurance_runner_sha256": ENDURANCE_RUNNER,
        "survey_runner_sha256": SURVEY_RUNNER,
    }.items():
        mismatch(failures, candidate, field, expected, "candidate.")
    for name, expected in {
        "firmware.bin": FIRMWARE,
        "firmware.factory.bin": FACTORY,
        "firmware.elf": APP,
        "product-endurance-runner.py": ENDURANCE_RUNNER,
        "product-survey-runner.py": SURVEY_RUNNER,
    }.items():
        path = BUNDLE / name
        if not path.is_file() or digest(path) != expected:
            failures.append(f"bundle.{name}: missing or hash mismatch")
    firmware_path = BUNDLE / "firmware.bin"
    elf_path = BUNDLE / "firmware.elf"
    if firmware_path.is_file() and elf_path.is_file():
        if app_elf_sha256(firmware_path) != digest(elf_path):
            failures.append("candidate app image/ELF identity mismatch")

    evidence = object_field(failures, summary, "evidence", "")
    for field, expected in {
        "bundle": "tests/hil/evidence/board-01-product-endurance-0.89",
        "files": files,
        "aggregate_run_sha256": AGGREGATE,
        "aggregate_original_sha256": AGGREGATE,
        "artifact_index_sha256": INDEX,
    }.items():
        mismatch(failures, evidence, field, expected, "evidence.")
    if index_hash != INDEX:
        failures.append(f"bundle index digest: {index_hash} != {INDEX}")

    aggregate_path = BUNDLE / "run.json"
    aggregate = load(aggregate_path, failures)
    if aggregate_path.is_file() and digest(aggregate_path) != AGGREGATE:
        failures.append("aggregate run digest mismatch")
    for field, expected in {
        "schema": "leshy.product_endurance_hil.run.v1",
        "status": "pass", "passed": True, "gate_eligible": True,
        "trust_status": "unsigned_local_result", "failures": [],
        "expected_cid": CID, "baseline_heap": HEAP,
    }.items():
        mismatch(failures, aggregate, field, expected, "aggregate.")
    aggregate_candidate = object_field(
        failures, aggregate, "candidate", "aggregate."
    )
    for field, expected in {
        "version": VERSION, "firmware_sha256": FIRMWARE,
        "app_elf_sha256": APP, "first_cycle_flashed": True,
    }.items():
        mismatch(failures, aggregate_candidate, field, expected,
                 "aggregate.candidate.")
    policy = object_field(failures, aggregate, "policy", "aggregate.")
    for field, expected in {
        "release_endurance_requested": True,
        "release_policy_satisfied": True,
        "release_policy_failures": [],
        "required_release_duration_seconds": 2700,
        "maximum_release_elapsed_seconds": 3600,
        "required_release_minimum_cycles": 8,
        "duration_seconds": 2700.0,
        "minimum_cycles": 8,
        "maximum_cycles": 12,
        "interval_seconds": 340.0,
        "measured_elapsed_within_budget": True,
    }.items():
        mismatch(failures, policy, field, expected, "aggregate.policy.")
    elapsed = aggregate.get("elapsed_seconds")
    if (not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool)
            or not 2700 <= elapsed <= 3600):
        failures.append("aggregate.elapsed_seconds: outside 2700..3600")
    cycles = aggregate.get("cycles")
    if not isinstance(cycles, list) or len(cycles) < 8:
        failures.append("aggregate.cycles: require at least eight")
        cycles = []
    mismatch(failures, aggregate, "cycles_completed", len(cycles), "aggregate.")

    generation = None
    observations = None
    totals = {key: 0 for key in (
        "wifi", "ble", "observations", "boot_attempts", "boot_retries",
        "boot_timeouts", "product_attempts", "product_retries",
    )}
    first_generation = None
    first_observations = None
    run_hashes: list[str] = []
    index_hashes: list[str] = []
    for number, cycle_summary in enumerate(cycles, start=1):
        if not isinstance(cycle_summary, dict):
            failures.append(f"aggregate.cycle[{number}]: not an object")
            continue
        cycle_path = BUNDLE / f"cycle-{number:04d}/run.json"
        cycle = load(cycle_path, failures)
        run_hash = digest(cycle_path) if cycle_path.is_file() else ""
        child_index = BUNDLE / f"cycle-{number:04d}/artifacts.sha256"
        child_index_hash = digest(child_index) if child_index.is_file() else ""
        run_hashes.append(run_hash)
        index_hashes.append(child_index_hash)
        mismatch(failures, cycle_summary, "number", number,
                 f"aggregate.cycle[{number}].")
        mismatch(failures, cycle_summary, "passed", True,
                 f"aggregate.cycle[{number}].")
        mismatch(failures, cycle_summary, "failures", [],
                 f"aggregate.cycle[{number}].")
        mismatch(failures, cycle_summary, "candidate_flashed", number == 1,
                 f"aggregate.cycle[{number}].")
        mismatch(failures, cycle_summary, "run_sha256", run_hash,
                 f"aggregate.cycle[{number}].")
        mismatch(failures, cycle_summary, "artifact_index_sha256",
                 child_index_hash, f"aggregate.cycle[{number}].")
        before_recovery = cycle.get("boot_before", {}).get("recovery", {}) \
            if isinstance(cycle.get("boot_before"), dict) else {}
        if not isinstance(before_recovery, dict):
            before_recovery = {}
        if generation is None:
            generation = before_recovery.get("generation")
            observations = before_recovery.get("observations")
            first_generation = generation
            first_observations = observations
        if not isinstance(generation, int) or not isinstance(observations, int):
            failures.append(f"cycle[{number}]: invalid continuity origin")
            generation = 0
            observations = 0
        generation_before = generation
        observations_before = observations
        generation, observations, measured = verify_cycle(
            failures, cycle, number, generation, observations, SURVEY_RUNNER
        )
        for key, value in measured.items():
            totals[key] += value
        expected_summary = {
            "generation_before": generation_before,
            "observations_before": observations_before,
            "generation_after": generation,
            "observations_after": observations,
            "scan_accepted": measured["wifi"],
            "ble_scan_accepted": measured["ble"],
            "forwarded": observations,
            "scan_dropped": 0,
            "ble_scan_dropped": 0,
            "pipeline_dropped": 0,
            "heap_before": HEAP,
            "heap_after": HEAP,
            "final_owner": "none",
            "final_lease_mask": 0,
        }
        for field, expected in expected_summary.items():
            mismatch(failures, cycle_summary, field, expected,
                     f"aggregate.cycle[{number}].")
    mismatch(failures, evidence, "cycle_run_sha256", run_hashes, "evidence.")
    mismatch(failures, evidence, "cycle_artifact_index_sha256", index_hashes,
             "evidence.")
    mismatch(failures, aggregate, "final_generation", generation, "aggregate.")
    mismatch(failures, aggregate, "final_observations", observations, "aggregate.")

    measured_summary = object_field(failures, summary, "summary", "")
    for field, expected in {
        "elapsed_seconds": elapsed,
        "cycles_completed": len(cycles),
        "cold_boots": len(cycles) * 2,
        "generation_before": first_generation,
        "generation_after": generation,
        "total_observations": totals["observations"],
        "wifi_observations": totals["wifi"],
        "ble_observations": totals["ble"],
        "forwarded_observations": totals["observations"],
        "scan_dropped": 0,
        "ble_scan_dropped": 0,
        "pipeline_dropped": 0,
        "boot_attempts": totals["boot_attempts"],
        "boot_transient_retries": totals["boot_retries"],
        "boot_timeout_restarts": totals["boot_timeouts"],
        "product_start_identity_attempts": totals["product_attempts"],
        "product_start_identity_transient_retries": totals["product_retries"],
        "heap": HEAP,
        "heap_drift_bytes": 0,
        "captures": len(cycles) * 4,
        "final_generation": generation,
        "final_observations": observations,
        "final_owner": "none",
        "final_lease_mask": 0,
    }.items():
        mismatch(failures, measured_summary, field, expected, "summary.")
    limits = object_field(failures, summary, "limits", "")
    for field, expected in {
        "release_endurance_complete": True,
        "controlled_physical_power_cut_complete": False,
        "demo_s4_complete": False,
        "release_1_0_complete": False,
        "rf_instrumented_no_tx_complete": False,
        "second_board_complete": False,
    }.items():
        mismatch(failures, limits, field, expected, "limits.")

    if failures:
        print("product release-endurance acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        f"product release-endurance acceptance passed: {len(cycles)} cycles, "
        f"{elapsed:.3f} s, generation {first_generation}->{generation}, "
        f"{totals['observations']} observations, zero drops/heap drift/final lease"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
