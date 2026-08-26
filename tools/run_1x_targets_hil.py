#!/usr/bin/env python3
"""One-flash delta HIL for the read-only on-device Targets product slice."""

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
    committed_failures,
    expect,
    paused_failures,
    query,
    running_failures,
    setup_failures,
    wait_ui_state,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.targets_product_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def run_survey_cycle(device: PassiveSerial, before_generation: int,
                     trace: list[dict[str, Any]]) -> dict[str, Any]:
    normalize_home(device)
    wifi_menu = action(device, "select")
    trace.append(wifi_menu)
    require(wifi_menu, "open Wi-Fi menu", page="survey",
            wifi_product_view="menu", runtime_owner="wifi")
    for selection in range(1, 4):
        selected = action(device, "down")
        trace.append(selected)
        require(selected, "select Record visit", page="survey",
                wifi_product_view="menu", wifi_product_selection=selection)
    setup = action(device, "right")
    trace.append(setup)
    failures = setup_failures(setup, "wifi")
    if failures:
        raise RuntimeError("; ".join(failures))
    require(setup, "Record visit sources", survey_setup_view="plan",
            survey_setup_selection=0, survey_source_selected_mask=3,
            survey_source_selected_count=2,
            survey_source_wifi_state="available",
            survey_source_ble_state="available")
    trace.append(action(device, "down"))
    start_row = action(device, "down")
    trace.append(start_row)
    require(start_row, "Record visit Start", survey_setup_view="plan",
            survey_setup_selection=2, survey_source_selected_mask=3,
            survey_source_selected_count=2)
    started = action(device, "select")
    trace.append(started)
    running = wait_ui_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "running" and
            state.get("survey_product_scan_cycles", 0) >= 1 and
            state.get("survey_scan_accepted", 0) >= 1 and
            state.get("survey_ble_scan_accepted", 0) >= 1 and
            state.get("survey_observations", 0) >= 2
        ),
        20.0,
        "Targets precursor Survey did not collect observations",
    )
    trace.append(running)
    failures = running_failures(running, EXPECTED_CID, "wifi")
    if failures:
        raise RuntimeError("; ".join(failures))
    require(running, "combined visit", survey_source_selected_mask=3,
            survey_source_selected_count=2,
            survey_product_selected_source_mask=3,
            survey_product_active_source_mask=3)
    observations = int(running["survey_observations"])
    scan_cycles = int(running["survey_product_scan_cycles"])
    trace.append(action(device, "up"))
    paused = wait_ui_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False
        ),
        20.0,
        "Targets precursor Survey did not pause",
    )
    trace.append(paused)
    failures = paused_failures(paused, observations, scan_cycles, "wifi")
    if failures:
        raise RuntimeError("; ".join(failures))
    trace.append(action(device, "down"))
    detail = action(device, "right")
    trace.append(detail)
    require(detail, "paused detail", page="survey", survey_view="detail",
            survey_product_status="paused")
    committed = action(device, "select", timeout=40.0)
    trace.append(committed)
    if committed.get("survey_product_status") != "committed":
        committed = wait_ui_state(
            device,
            lambda state: state.get("survey_product_status") == "committed",
            20.0,
            "Targets precursor Survey did not commit",
        )
        trace.append(committed)
    failures = committed_failures(committed, before_generation, "wifi")
    if failures:
        raise RuntimeError("; ".join(failures))
    menu = action(device, "back")
    trace.append(menu)
    require(menu, "Visit result cleanup", page="survey",
            wifi_product_view="menu", runtime_owner="wifi")
    home = action(device, "back")
    trace.append(home)
    require(home, "Survey cleanup", page="home", runtime_owner="none",
            lease_mask=0, survey_product_cleanup_complete=True,
            survey_product_source_active=False)
    return committed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument(
        "--reuse-existing-pair", action="store_true",
        help="reuse the already persisted exact session pair without new scans")
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
        stdout=subprocess.PIPE, text=True).stdout.strip()
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

    cleanup: dict[str, Any] = {"attempted": False}
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
            require(recovery, "exact product media", status="admitted",
                    expected_fingerprint=EXPECTED_CID,
                    observed_fingerprint=EXPECTED_CID,
                    fingerprint_matched=True, mounted_read_only=True,
                    read_only_guaranteed=True, blocked_write_attempts=0,
                    cleanup_complete=True, physical_write_calls=0)
            generation_before = int(recovery["generation"])
            first: dict[str, Any] | None = None
            second: dict[str, Any] | None = None
            first_generation = 0
            second_generation = 0
            if not args.reuse_existing_pair:
                first = run_survey_cycle(device, generation_before, trace)
                second = run_survey_cycle(
                    device, int(first["survey_generation"]), trace)
                first_generation = int(first["survey_generation"])
                second_generation = int(second["survey_generation"])

            home = normalize_home(device)
            for _ in range(5):
                home = action(device, "down")
                trace.append(home)
            require(home, "select Targets", page="home", selection=5,
                    selected_id="targets")
            opened = action(device, "right")
            trace.append(opened)
            listed = query(device, b"targets.state",
                           "leshy.targets.product.v1", "state")
            record["targets_after_open"] = listed
            write_json(args.output / "run.json", record)
            require(opened, "open Targets", page="targets",
                    runtime_owner="targets", lease_mask=13)
            if args.reuse_existing_pair:
                first_generation = int(listed["baseline_generation"])
                second_generation = int(listed["current_generation"])
                if not (0 < first_generation < second_generation):
                    raise RuntimeError(
                        f"invalid existing session pair: {listed}")
            require(listed, "Targets list", status="ready",
                    workspace_allocated=True, page_open=True, view="list",
                    compare_available=True,
                    baseline_generation=first_generation,
                    current_generation=second_generation,
                    read_only=False, write_enabled=False,
                    blocked_write_attempts=0, filesystem_mount_error=0,
                    cleanup_complete=True,
                    lease_mask=13)
            target_count = int(listed["target_count"])
            source_count = int(listed["source_identity_count"])
            if not (1 <= target_count <= 16 and source_count >= target_count):
                raise RuntimeError(f"invalid bounded Target counts: {listed}")
            if int(listed["entry_count"]) != target_count + 1:
                raise RuntimeError(f"Compare row missing: {listed}")
            screens["list"] = capture(device, frames, "targets-list")

            compare_ui = action(device, "right")
            trace.append(compare_ui)
            require(compare_ui, "open Compare", page="targets")
            compared = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
            require(compared, "Targets compare", status="ready",
                    page_open=True, view="compare", compare_available=True,
                    baseline_generation=first_generation,
                    current_generation=second_generation, lease_mask=13)
            classified = sum(int(compared[key]) for key in
                             ("added", "removed", "changed", "unchanged"))
            if classified != target_count:
                raise RuntimeError(f"comparison does not classify every row: {compared}")
            screens["compare"] = capture(device, frames, "targets-compare")

            trace.append(action(device, "left"))
            trace.append(action(device, "down"))
            detail_ui = action(device, "select")
            trace.append(detail_ui)
            require(detail_ui, "open Target detail", page="targets")
            detail = query(device, b"targets.state",
                           "leshy.targets.product.v1", "state")
            require(detail, "Target detail", status="ready", page_open=True,
                    view="detail", lease_mask=13)
            if int(detail["selected_generation"]) not in (
                    first_generation, second_generation):
                raise RuntimeError(f"detail evidence generation is not exact: {detail}")
            if not (-127 <= int(detail["selected_rssi_dbm"]) <= 0):
                raise RuntimeError(f"detail RSSI is invalid: {detail}")
            screens["detail"] = capture(device, frames, "targets-detail")

            trace.append(action(device, "left"))
            final_ui = action(device, "left")
            trace.append(final_ui)
            require(final_ui, "Targets cleanup", page="home",
                    runtime_owner="none", lease_mask=0)
            released = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
            require(released, "released Targets", status="not_loaded",
                    workspace_allocated=False, page_open=False, view="none",
                    read_only=False, write_enabled=False,
                    blocked_write_attempts=0, filesystem_mount_error=0,
                    cleanup_complete=True,
                    lease_mask=0)
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
            "generation_before": generation_before,
            "survey_generations": [first_generation, second_generation],
            "survey_cycles_executed": 0 if args.reuse_existing_pair else 2,
            "survey_observations": [] if first is None or second is None else
                [int(first["survey_observations"]),
                 int(second["survey_observations"])],
            "targets": {"list": listed, "compare": compared,
                        "detail": detail, "released": released},
            "safe_outputs": safe,
            "input": inputs,
            "trace": trace,
            "screens": screens,
            "cleanup": cleanup,
            "flash_count": 0 if args.reuse_exact_flash else 1,
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
                cleanup = {
                    "attempted": True,
                    "complete": False,
                    "errors": [
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    ],
                }
        record.update({"status": "failed", "error": str(error),
                       "trace": trace, "screens": screens,
                       "cleanup": cleanup,
                       "flash_count": 0 if args.reuse_exact_flash else 1})
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
