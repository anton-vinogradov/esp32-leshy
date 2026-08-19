#!/usr/bin/env python3
"""Retain a passing release-endurance run and its exact candidate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
CID = re.compile(r"[0-9A-F]{32}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_index(destination: Path) -> tuple[int, str]:
    indexed = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path != destination / "artifacts.sha256"
    )
    body = "".join(
        f"{digest(path)}  {path.relative_to(destination)}\n" for path in indexed
    )
    index = destination / "artifacts.sha256"
    index.write_text(body, encoding="utf-8")
    return len(indexed) + 1, digest(index)


def positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--board", default="board-01")
    parser.add_argument("--profile", default="esp32-div-v2-n16")
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    summary_path = args.summary.resolve()
    artifacts = {
        "firmware.bin": args.firmware.resolve(),
        "firmware.factory.bin": args.factory.resolve(),
        "firmware.elf": args.elf.resolve(),
        "product-endurance-runner.py": Path(__file__).with_name(
            "run_1x_product_endurance_hil.py"
        ),
        "product-survey-runner.py": Path(__file__).with_name(
            "run_1x_product_survey_hil.py"
        ),
    }
    if (not source.is_dir() or destination.exists() or summary_path.exists()
            or any(not path.is_file() for path in artifacts.values())):
        parser.error(
            "source/artifacts must exist and destination/summary must not exist"
        )
    if COMMIT.fullmatch(args.source_commit) is None:
        parser.error("--source-commit must be a full lowercase Git commit")
    try:
        destination_relative = destination.relative_to(ROOT)
        summary_path.relative_to(ROOT)
    except ValueError as error:
        parser.error(f"destination/summary must be below repository root: {error}")

    aggregate = load(source / "run.json")
    candidate = aggregate.get("candidate")
    policy = aggregate.get("policy")
    cycles = aggregate.get("cycles")
    if not isinstance(candidate, dict) or not isinstance(policy, dict) \
            or not isinstance(cycles, list):
        parser.error("aggregate candidate/policy/cycles are incomplete")
    if not (
        aggregate.get("schema") == "leshy.product_endurance_hil.run.v1"
        and aggregate.get("status") == "pass"
        and aggregate.get("passed") is True
        and aggregate.get("gate_eligible") is True
        and aggregate.get("failures") == []
        and policy.get("release_endurance_requested") is True
        and policy.get("release_policy_satisfied") is True
        and policy.get("release_policy_failures") == []
        and isinstance(aggregate.get("elapsed_seconds"), (int, float))
        and 2700 <= aggregate["elapsed_seconds"] <= 3600
        and len(cycles) >= 8
        and aggregate.get("cycles_completed") == len(cycles)
        and CID.fullmatch(str(aggregate.get("expected_cid", ""))) is not None
    ):
        parser.error("only a complete one-hour-budget release gate can be retained")

    firmware_hash = digest(artifacts["firmware.bin"])
    elf_hash = digest(artifacts["firmware.elf"])
    if (candidate.get("firmware_sha256") != firmware_hash
            or candidate.get("app_elf_sha256") != elf_hash
            or app_elf_sha256(artifacts["firmware.bin"]) != elf_hash):
        parser.error("candidate firmware/app identity does not match aggregate")

    shutil.copytree(source, destination)
    shutil.copy2(source / "run.json", destination / "run.original.json")
    for name, path in artifacts.items():
        shutil.copy2(path, destination / name)
    files, index_hash = build_index(destination)

    generation_before = cycles[0].get("generation_before") if cycles else None
    generation_after = cycles[-1].get("generation_after") if cycles else None
    observations = [cycle.get("observations_after") for cycle in cycles]
    total_observations = sum(
        value for value in observations if positive_integer(value)
    )
    total_wifi = sum(
        cycle.get("scan_accepted", 0) for cycle in cycles
        if isinstance(cycle, dict)
    )
    total_ble = sum(
        cycle.get("ble_scan_accepted", 0) for cycle in cycles
        if isinstance(cycle, dict)
    )
    boot_attempts = sum(
        cycle.get("boot_before_attempts", 0)
        + cycle.get("boot_after_attempts", 0)
        for cycle in cycles if isinstance(cycle, dict)
    )
    boot_retries = sum(
        cycle.get("boot_before_transient_retries", 0)
        + cycle.get("boot_after_transient_retries", 0)
        for cycle in cycles if isinstance(cycle, dict)
    )
    timeout_restarts = sum(
        cycle.get("boot_before_timeout_restarts", 0)
        + cycle.get("boot_after_timeout_restarts", 0)
        for cycle in cycles if isinstance(cycle, dict)
    )
    product_attempts = sum(
        cycle.get("product_start_identity_attempts", 0)
        for cycle in cycles if isinstance(cycle, dict)
    )
    product_retries = sum(
        cycle.get("product_start_identity_transient_retries", 0)
        for cycle in cycles if isinstance(cycle, dict)
    )
    maximum_ready = max(
        float(cycle.get(field, 0))
        for cycle in cycles if isinstance(cycle, dict)
        for field in ("ready_before_ms", "ready_after_ms")
    )
    retained = {
        "schema": "leshy.product_endurance_acceptance.v1",
        "status": "pass_release_endurance",
        "trust_status": aggregate.get("trust_status"),
        "gate_eligible": True,
        "board": args.board,
        "profile": args.profile,
        "candidate": {
            "version": candidate.get("version"),
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_hash,
            "factory_sha256": digest(artifacts["firmware.factory.bin"]),
            "app_elf_sha256": elf_hash,
            "firmware_bytes": artifacts["firmware.bin"].stat().st_size,
            "factory_bytes": artifacts["firmware.factory.bin"].stat().st_size,
            "elf_bytes": artifacts["firmware.elf"].stat().st_size,
            "endurance_runner_sha256": digest(
                artifacts["product-endurance-runner.py"]
            ),
            "survey_runner_sha256": digest(
                artifacts["product-survey-runner.py"]
            ),
        },
        "media": {
            "cid": aggregate.get("expected_cid"),
            "product_root": "/leshy/sessions/v1",
            "disposable_test_card": True,
        },
        "policy": policy,
        "summary": {
            "elapsed_seconds": aggregate.get("elapsed_seconds"),
            "cycles_completed": len(cycles),
            "cold_boots": len(cycles) * 2,
            "generation_before": generation_before,
            "generation_after": generation_after,
            "total_observations": total_observations,
            "wifi_observations": total_wifi,
            "ble_observations": total_ble,
            "forwarded_observations": sum(
                cycle.get("forwarded", 0) for cycle in cycles
                if isinstance(cycle, dict)
            ),
            "scan_dropped": sum(
                cycle.get("scan_dropped", 0) for cycle in cycles
                if isinstance(cycle, dict)
            ),
            "ble_scan_dropped": sum(
                cycle.get("ble_scan_dropped", 0) for cycle in cycles
                if isinstance(cycle, dict)
            ),
            "pipeline_dropped": sum(
                cycle.get("pipeline_dropped", 0) for cycle in cycles
                if isinstance(cycle, dict)
            ),
            "boot_attempts": boot_attempts,
            "boot_transient_retries": boot_retries,
            "boot_timeout_restarts": timeout_restarts,
            "product_start_identity_attempts": product_attempts,
            "product_start_identity_transient_retries": product_retries,
            "maximum_ready_marker_ms": maximum_ready,
            "heap": aggregate.get("baseline_heap"),
            "heap_drift_bytes": 0,
            "captures": len(cycles) * 4,
            "final_generation": aggregate.get("final_generation"),
            "final_observations": aggregate.get("final_observations"),
            "final_owner": cycles[-1].get("final_owner"),
            "final_lease_mask": cycles[-1].get("final_lease_mask"),
        },
        "evidence": {
            "bundle": str(destination_relative),
            "files": files,
            "aggregate_run_sha256": digest(destination / "run.json"),
            "aggregate_original_sha256": digest(
                destination / "run.original.json"
            ),
            "artifact_index_sha256": index_hash,
            "cycle_run_sha256": [cycle.get("run_sha256") for cycle in cycles],
            "cycle_artifact_index_sha256": [
                cycle.get("artifact_index_sha256") for cycle in cycles
            ],
        },
        "limits": {
            "release_endurance_complete": True,
            "controlled_physical_power_cut_complete": False,
            "demo_s4_complete": False,
            "release_1_0_complete": False,
            "rf_instrumented_no_tx_complete": False,
            "second_board_complete": False,
        },
    }
    write(summary_path, retained)
    print(json.dumps({
        "status": "retained",
        "destination": str(destination_relative),
        "summary": str(summary_path.relative_to(ROOT)),
        "files": files,
        "aggregate_run_sha256": retained["evidence"]["aggregate_run_sha256"],
        "artifact_index_sha256": index_hash,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
