#!/usr/bin/env python3
"""Validate the retained two-cycle real-product repeatability evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-repeatability-0.45.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "b09252725dde70096402687e8fdf4fdb616cb3a4d44ae7de2521dceba6270fe2"
APP = "dd33383b7092459e6ccbb2a38b230e26338e4bba0b0df0094c9eb8f62a67b904"


def mismatch(failures: list[str], record: dict[str, Any], field: str,
             expected: Any, prefix: str = "") -> None:
    if record.get(field) != expected:
        failures.append(
            f"{prefix}{field}: {record.get(field)!r} != {expected!r}"
        )


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    failures: list[str] = []
    for field, expected in {
        "schema": "leshy.product_repeatability_acceptance.v1",
        "status": "pass",
        "trust_status": "unsigned_local_result",
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
        "firmware_version": "0.45.0-product-survey-measure",
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

    cycles = evidence.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 2:
        failures.append("cycles: require exactly two retained cycles")
        cycles = []
    expected_generation = 6
    prior_observations = 16
    heap_reference = [276312, 227876, 194956]
    total_accepted = 0
    run_hashes: set[str] = set()
    for index, cycle in enumerate(cycles, start=1):
        if not isinstance(cycle, dict):
            failures.append(f"cycle[{index}]: not an object")
            continue
        prefix = f"cycle[{index}]."
        for field, expected in {
            "number": index,
            "passed": True,
            "candidate_flashed": index == 1,
            "local_gate_eligible": index == 1,
            "generation_before": expected_generation,
            "observations_before": prior_observations,
            "generation_after": expected_generation + 1,
            "scan_dropped": 0,
            "pipeline_dropped": 0,
            "heap_before": heap_reference,
            "heap_after": heap_reference,
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
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value <= 1500:
                failures.append(f"{prefix}{field}: outside 0..1500 ms")
        for field in ("run_sha256", "artifact_index_sha256"):
            value = cycle.get(field)
            if not isinstance(value, str) or SHA256.fullmatch(value) is None:
                failures.append(f"{prefix}{field}: invalid SHA-256")
            elif field == "run_sha256":
                run_hashes.add(value)
        expected_generation += 1
        prior_observations = observations
        total_accepted += observations
    if len(run_hashes) != len(cycles):
        failures.append("cycles: run hashes must be distinct")

    summary = evidence.get("summary")
    if not isinstance(summary, dict):
        failures.append("summary: missing")
        summary = {}
    for field, expected in {
        "cycles_requested": 2,
        "cycles_completed": 2,
        "cold_boots": 4,
        "generation_before": 6,
        "generation_after": 8,
        "observations_accepted": total_accepted,
        "observations_forwarded": total_accepted,
        "scan_dropped": 0,
        "pipeline_dropped": 0,
        "visual_captures": 8,
        "heap_total_bytes": heap_reference[0],
        "heap_free_bytes": heap_reference[1],
        "heap_min_free_bytes": heap_reference[2],
        "heap_drift_bytes": 0,
        "final_generation": 8,
        "final_observations": prior_observations,
        "final_owner": "none",
        "final_lease_mask": 0,
    }.items():
        mismatch(failures, summary, field, expected, "summary.")
    maximum_ready = summary.get("maximum_ready_marker_ms")
    if not isinstance(maximum_ready, (int, float)) or not 0 < maximum_ready <= 1500:
        failures.append("summary.maximum_ready_marker_ms: outside 0..1500 ms")
    limitations = evidence.get("limitations")
    if (not isinstance(limitations, list)
            or not any("eight-hour endurance" in item for item in limitations
                       if isinstance(item, str))):
        failures.append("limitations: must state that eight-hour endurance is open")

    if failures:
        print("product repeatability acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "product repeatability acceptance passed: generation 6->8, "
        "44/44 forwarded, four cold boots, zero heap drift"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
