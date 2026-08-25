#!/usr/bin/env python3
"""One-flash, read-only regression for Targets storage/heap ordering."""

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


SCHEMA = "leshy.targets_mount_regression_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


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
                raise RuntimeError("short regression needs an existing Session pair")
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
                    # The storage recovery itself is read-only, while the
                    # Targets product now supports explicit metadata actions.
                    # A passive list row must therefore expose no pending write
                    # without misreporting the whole product as read-only.
                    read_only=False, write_enabled=False,
                    blocked_write_attempts=0, filesystem_mount_error=0,
                    cleanup_complete=True, lease_mask=13)
            target_count = int(listed["target_count"])
            if not 1 <= target_count <= 16:
                raise RuntimeError(f"invalid bounded Target count: {listed}")
            screens["list"] = capture(device, frames, "targets-mount-list")

            compare_ui = action(device, "right")
            trace.append(compare_ui)
            require(compare_ui, "open Compare", page="targets")
            compared = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
            require(compared, "Targets compare", status="ready",
                    workspace_allocated=True, page_open=True, view="compare",
                    compare_available=True,
                    baseline_generation=baseline_generation,
                    current_generation=current_generation,
                    filesystem_mount_error=0, lease_mask=13)
            classified = sum(int(compared[key]) for key in
                             ("added", "removed", "changed", "unchanged"))
            if classified != target_count:
                raise RuntimeError(f"comparison count mismatch: {compared}")
            screens["compare"] = capture(
                device, frames, "targets-mount-compare")

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
            "targets": {"list": listed, "compare": compared,
                        "released": released},
            "safe_outputs": safe,
            "input": inputs,
            "trace": trace,
            "screens": screens,
            "cleanup": cleanup,
            "flash_count": 1,
            "storage_write_calls": 0,
            "radio_tx_commands": 0,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({"schema": SCHEMA, "status": "pass",
                          "run": str(args.output / "run.json"),
                          "targets": target_count,
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
                       "trace": trace, "screens": screens,
                       "cleanup": cleanup, "flash_count": 1,
                       "storage_write_calls": 0,
                       "radio_tx_commands": 0})
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
