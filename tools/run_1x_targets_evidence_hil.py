#!/usr/bin/env python3
"""One-flash delta HIL for class/signal-sorted Target comparison evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from check_targets_stack_elf_contract import stack_frames
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    capture,
    query,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.targets_evidence_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
CLASS_RANK = {"added": 0, "removed": 1, "changed": 2, "unchanged": 3}


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def validate_evidence(state: dict[str, Any], baseline: int,
                      current: int) -> tuple[int, int]:
    classification = state.get("selected_change_class")
    if classification not in CLASS_RANK:
        raise RuntimeError(f"invalid comparison class: {state}")
    baseline_present = state.get("baseline_evidence_present") is True
    current_present = state.get("current_evidence_present") is True
    if not baseline_present and not current_present:
        raise RuntimeError(f"comparison row has no exact evidence: {state}")
    if baseline_present and (
            state.get("baseline_evidence_generation") != baseline or
            int(state.get("baseline_observation_sequence", 0)) <= 0):
        raise RuntimeError(f"baseline evidence is not exact: {state}")
    if current_present and (
            state.get("current_evidence_generation") != current or
            int(state.get("current_observation_sequence", 0)) <= 0):
        raise RuntimeError(f"current evidence is not exact: {state}")
    if classification == "added" and (baseline_present or not current_present):
        raise RuntimeError(f"added row has invalid sides: {state}")
    if classification == "removed" and (not baseline_present or current_present):
        raise RuntimeError(f"removed row has invalid sides: {state}")
    if classification in ("changed", "unchanged") and not (
            baseline_present and current_present):
        raise RuntimeError(f"paired row has invalid sides: {state}")
    if classification == "changed" and int(
            state.get("selected_change_mask", 0)) == 0:
        raise RuntimeError(f"changed row has empty change mask: {state}")
    signal = int(state["current_rssi_dbm"] if current_present
                 else state["baseline_rssi_dbm"])
    return CLASS_RANK[classification], signal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="verify and reuse an already flashed exact candidate",
    )
    parser.add_argument(
        "--open-every-evidence", action="store_true",
        help="open and return from the exact evidence view for every comparison row",
    )
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")
    try:
        checked_stack_frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(f"unsafe or unverifiable Targets stack: {error}")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    evidence_details: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {"attempted": False}
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
            "checked_stack_frames": checked_stack_frames,
        },
    }
    write_json(args.output / "run.json", record)

    try:
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(1.0)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 30.0)
            metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics, "candidate", version=args.expected_version,
                    app_elf_sha256=app_identity)
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery, "exact media", status="admitted",
                    expected_fingerprint=EXPECTED_CID,
                    observed_fingerprint=EXPECTED_CID,
                    fingerprint_matched=True, mounted_read_only=True,
                    read_only_guaranteed=True, blocked_write_attempts=0,
                    cleanup_complete=True, physical_write_calls=0)
            current_generation = int(recovery["generation"])
            if current_generation < 2:
                raise RuntimeError("Targets evidence delta needs a Session pair")
            baseline_generation = current_generation - 1

            home = normalize_home(device)
            for _ in range(5):
                home = action(device, "down")
                trace.append(home)
            require(home, "select Targets", page="home", selection=5,
                    selected_id="targets")
            opened = action(device, "right")
            trace.append(opened)
            require(opened, "open Targets", page="targets",
                    runtime_owner="targets", lease_mask=13)
            listed = query(device, b"targets.state",
                           "leshy.targets.product.v1", "state")
            require(listed, "Targets list", status="ready",
                    workspace_allocated=True, page_open=True, view="list",
                    compare_available=True,
                    baseline_generation=baseline_generation,
                    current_generation=current_generation,
                    read_only=True, write_enabled=False,
                    blocked_write_attempts=0, filesystem_mount_error=0,
                    cleanup_complete=True, lease_mask=13)
            target_count = int(listed["target_count"])
            comparison_count = int(listed["comparison_count"])
            if not 1 <= target_count <= 16 or comparison_count != target_count:
                raise RuntimeError(f"invalid bounded comparison: {listed}")
            screens["list"] = capture(device, frames, "targets-evidence-list")

            compare_ui = action(device, "right")
            trace.append(compare_ui)
            require(compare_ui, "open comparison rows", page="targets")
            previous_rank = -1
            previous_signal = 0
            for index in range(comparison_count):
                if index != 0:
                    trace.append(action(device, "down"))
                compared = query(device, b"targets.state",
                                 "leshy.targets.product.v1", "state")
                require(compared, f"comparison row {index}", status="ready",
                        view="compare", comparison_count=comparison_count,
                        comparison_selection=index, lease_mask=13)
                rank, signal = validate_evidence(
                    compared, baseline_generation, current_generation)
                if rank < previous_rank or (
                        rank == previous_rank and signal > previous_signal):
                    raise RuntimeError(
                        f"comparison order is not class/signal stable: {rows + [compared]}")
                previous_rank = rank
                previous_signal = signal
                rows.append(compared)
                if args.open_every_evidence:
                    trace.append(action(device, "right"))
                    evidence = query(
                        device, b"targets.state",
                        "leshy.targets.product.v1", "state")
                    require(
                        evidence, f"comparison evidence {index}",
                        status="ready", view="compare_detail",
                        comparison_count=comparison_count,
                        comparison_selection=index, lease_mask=13)
                    validate_evidence(
                        evidence, baseline_generation, current_generation)
                    evidence_details.append(evidence)
                    trace.append(action(device, "left"))
                    returned_row = query(
                        device, b"targets.state",
                        "leshy.targets.product.v1", "state")
                    require(
                        returned_row, f"comparison return {index}",
                        status="ready", view="compare",
                        comparison_count=comparison_count,
                        comparison_selection=index, lease_mask=13)
                if index == 0:
                    screens["compare_first"] = capture(
                        device, frames, "targets-evidence-compare-first")
            screens["compare_last"] = capture(
                device, frames, "targets-evidence-compare-last")

            for _ in range(comparison_count - 1):
                trace.append(action(device, "up"))
            detail_ui = action(device, "right")
            trace.append(detail_ui)
            require(detail_ui, "open exact comparison evidence", page="targets")
            detail = query(device, b"targets.state",
                           "leshy.targets.product.v1", "state")
            require(detail, "comparison evidence detail", status="ready",
                    view="compare_detail", comparison_selection=0,
                    comparison_count=comparison_count, lease_mask=13)
            validate_evidence(detail, baseline_generation, current_generation)
            screens["evidence"] = capture(
                device, frames, "targets-evidence-detail")

            trace.append(action(device, "left"))
            returned = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
            require(returned, "return to comparison", view="compare",
                    comparison_selection=0, comparison_count=comparison_count)
            trace.append(action(device, "left"))
            home = action(device, "left")
            trace.append(home)
            require(home, "Targets cleanup", page="home",
                    runtime_owner="none", lease_mask=0)
            released = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
            require(released, "released Targets", status="not_loaded",
                    workspace_allocated=False, page_open=False, view="none",
                    blocked_write_attempts=0, filesystem_mount_error=0,
                    cleanup_complete=True, lease_mask=0)
            heap_before = int(released["heap_free_before"])
            heap_after = int(released["heap_free_after_release"])
            if heap_before <= 0 or heap_after + 512 < heap_before:
                raise RuntimeError(f"Targets heap was not released: {released}")
            safe = query(device, b"hardware.safe-outputs",
                         "leshy.hardware.safe-outputs.v1", "state")
            require(safe, "safe outputs", buzzer_inactive=True,
                    nrf_ce_inactive=True, software_quiesce_complete=True)
            inputs = query(device, b"input.state",
                           "leshy.input.frontend.v1", "state")
            require(inputs, "input", status="ready", read_errors=0,
                    queue_drops=0)
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("final cleanup state is unproven")

        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "generations": [baseline_generation, current_generation],
            "targets": {"list": listed, "rows": rows, "detail": detail,
                        "evidence_details": evidence_details,
                        "returned": returned, "released": released},
            "safe_outputs": safe,
            "input": inputs,
            "trace": trace,
            "screens": screens,
            "cleanup": cleanup,
            "flash_count": 0 if args.reuse_exact_flash else 1,
            "exact_flash_reused": args.reuse_exact_flash,
            "storage_write_calls": 0,
            "radio_tx_commands": 0,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({"schema": SCHEMA, "status": "pass",
                          "run": str(args.output / "run.json"),
                          "targets": target_count,
                          "rows": len(rows),
                          "screens": len(screens)}, sort_keys=True))
        return 0
    except Exception as error:
        if not cleanup.get("attempted"):
            try:
                with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                    synchronize_console(device, 10.0)
                    cleanup = best_effort_cleanup(device)
            except Exception as cleanup_error:
                cleanup = {"attempted": True, "complete": False,
                           "errors": [
                               f"{type(cleanup_error).__name__}: {cleanup_error}"
                           ]}
        record.update({"status": "failed", "error": str(error),
                       "trace": trace, "screens": screens, "rows": rows,
                       "cleanup": cleanup,
                       "flash_count": 0 if args.reuse_exact_flash else 1,
                       "exact_flash_reused": args.reuse_exact_flash,
                       "storage_write_calls": 0,
                       "radio_tx_commands": 0})
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
