#!/usr/bin/env python3
"""Validate the retained three-cycle product endurance-runner smoke evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-endurance-smoke-0.46.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "df4a012aa6243e647a1a2a4bf81bb5911f761c46557bf281380eb35afeadc22e"
APP = "bf461a9a64238a3e2481480b6b90a7da7a91e913307225c986cc296daa0513a7"
HEAP = [276312, 227876, 194956]


def mismatch(failures: list[str], record: dict[str, Any], field: str,
             expected: Any, prefix: str = "") -> None:
    if record.get(field) != expected:
        failures.append(f"{prefix}{field}: {record.get(field)!r} != {expected!r}")


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    failures: list[str] = []
    for field, expected in {
        "schema": "leshy.product_endurance_smoke_acceptance.v1",
        "status": "pass",
        "trust_status": "unsigned_local_result",
        "gate_eligible": False,
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
        "firmware_version": "0.46.0-product-boot-retry-measure",
        "firmware_sha256": FIRMWARE,
        "app_elf_sha256": APP,
    }.items():
        mismatch(failures, evidence, field, expected)

    media = evidence.get("media")
    if not isinstance(media, dict):
        failures.append("media: missing")
        media = {}
    for field, expected in {
        "cid": CID, "product_root": "/leshy/sessions/v1",
        "disposable_test_card": True,
    }.items():
        mismatch(failures, media, field, expected, "media.")

    policy = evidence.get("policy")
    if not isinstance(policy, dict):
        failures.append("policy: missing")
        policy = {}
    for field, expected in {
        "runner_schema": "leshy.product_endurance_hil.run.v1",
        "release_endurance_requested": False,
        "required_release_duration_seconds": 28800,
        "required_release_minimum_cycles": 32,
        "configured_duration_seconds": 0,
        "configured_minimum_cycles": 3,
        "configured_maximum_cycles": 3,
    }.items():
        mismatch(failures, policy, field, expected, "policy.")

    cycles = evidence.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 3:
        failures.append("cycles: require exactly three retained cycles")
        cycles = []
    generation = 12
    prior_observations = 21
    total = 0
    maximum_ready = 0.0
    run_hashes: set[str] = set()
    boot_attempts = 0
    transient_retries = 0
    for index, cycle in enumerate(cycles, start=1):
        if not isinstance(cycle, dict):
            failures.append(f"cycle[{index}]: not an object")
            continue
        prefix = f"cycle[{index}]."
        for field, expected in {
            "number": index,
            "passed": True,
            "candidate_flashed": index == 1,
            "generation_before": generation,
            "observations_before": prior_observations,
            "generation_after": generation + 1,
            "scan_dropped": 0,
            "pipeline_dropped": 0,
            "heap_before": HEAP,
            "heap_after": HEAP,
            "boot_before_attempts": 1,
            "boot_before_transient_retries": 0,
            "boot_after_attempts": 1,
            "boot_after_transient_retries": 0,
            "visual_captures": 4,
            "final_owner": "none",
            "final_lease_mask": 0,
        }.items():
            mismatch(failures, cycle, field, expected, prefix)
        observations = cycle.get("observations_after")
        if not isinstance(observations, int) or observations < 1:
            failures.append(f"{prefix}observations_after: expected positive integer")
            observations = 0
        for field in ("scan_accepted", "forwarded"):
            mismatch(failures, cycle, field, observations, prefix)
        for field in ("ready_before_ms", "ready_after_ms"):
            value = cycle.get(field)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not 0 < value <= 1500):
                failures.append(f"{prefix}{field}: outside 0..1500 ms")
            else:
                maximum_ready = max(maximum_ready, float(value))
        for field in ("run_sha256", "artifact_index_sha256"):
            value = cycle.get(field)
            if not isinstance(value, str) or SHA256.fullmatch(value) is None:
                failures.append(f"{prefix}{field}: invalid SHA-256")
            elif field == "run_sha256":
                run_hashes.add(value)
        generation += 1
        prior_observations = observations
        total += observations
        boot_attempts += 2
        transient_retries += (
            cycle.get("boot_before_transient_retries", 0)
            + cycle.get("boot_after_transient_retries", 0)
        )
    if len(run_hashes) != len(cycles):
        failures.append("cycles: run hashes must be distinct")

    summary = evidence.get("summary")
    if not isinstance(summary, dict):
        failures.append("summary: missing")
        summary = {}
    for field, expected in {
        "cycles_requested": 3,
        "cycles_completed": 3,
        "cold_boots": 6,
        "generation_before": 12,
        "generation_after": 15,
        "observations_accepted": total,
        "observations_forwarded": total,
        "scan_dropped": 0,
        "pipeline_dropped": 0,
        "visual_captures": 12,
        "boot_attempts": boot_attempts,
        "transient_retries_observed": transient_retries,
        "heap_total_bytes": HEAP[0],
        "heap_free_bytes": HEAP[1],
        "heap_min_free_bytes": HEAP[2],
        "heap_drift_bytes": 0,
        "final_generation": 15,
        "final_observations": prior_observations,
        "final_owner": "none",
        "final_lease_mask": 0,
    }.items():
        mismatch(failures, summary, field, expected, "summary.")
    recorded_maximum = summary.get("maximum_ready_marker_ms")
    if (not isinstance(recorded_maximum, (int, float))
            or abs(float(recorded_maximum) - maximum_ready) > 0.001):
        failures.append("summary.maximum_ready_marker_ms: inconsistent")
    for field in ("aggregate_run_sha256", "aggregate_artifact_index_sha256"):
        value = summary.get(field)
        if not isinstance(value, str) or SHA256.fullmatch(value) is None:
            failures.append(f"summary.{field}: invalid SHA-256")

    limitations = evidence.get("limitations")
    joined = "\n".join(item for item in limitations if isinstance(item, str)) \
        if isinstance(limitations, list) else ""
    for phrase in ("eight-hour endurance", "no positive physical retry event"):
        if phrase not in joined:
            failures.append(f"limitations: must contain {phrase!r}")

    if failures:
        print("product endurance smoke acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product endurance smoke acceptance passed: generation 12->15, "
        "51/51 forwarded, six cold boots, zero heap drift; not endurance-gate eligible"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
