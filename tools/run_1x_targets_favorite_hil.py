#!/usr/bin/env python3
"""One-flash delta HIL for durable on-device Target favorite mutation."""

from __future__ import annotations

import argparse
import shutil
import subprocess
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
    reset_capture,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.targets_favorite_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def open_first_target(device: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    home = normalize_home(device)
    for _ in range(5):
        home = action(device, "down")
    require(home, "select Targets", page="home", selection=5,
            selected_id="targets")
    opened = action(device, "right")
    require(opened, "open Targets", page="targets",
            runtime_owner="targets", lease_mask=13)
    listed = query(device, b"targets.state",
                   "leshy.targets.product.v1", "state")
    require(listed, "Targets list", status="ready", page_open=True,
            workspace_allocated=True, view="list", compare_available=True,
            read_only=False, write_enabled=False,
            blocked_write_attempts=0, filesystem_mount_error=0,
            cleanup_complete=True, lease_mask=13)
    if int(listed.get("target_count", 0)) < 1:
        raise RuntimeError(f"no Target is available: {listed}")
    action(device, "down")  # comparison is row 0; first Target is row 1
    action(device, "right")
    detail = query(device, b"targets.state",
                   "leshy.targets.product.v1", "state")
    require(detail, "Target detail", status="ready", view="detail",
            selected_target_present=True, lease_mask=13)
    target_id = detail.get("selected_target_id")
    if (not isinstance(target_id, str) or len(target_id) != 32 or
            any(character not in "0123456789ABCDEF" for character in target_id)):
        raise RuntimeError(f"invalid stable Target ID: {detail}")
    return listed, detail


def close_targets(device: Any) -> dict[str, Any]:
    state = query(device, b"targets.state",
                  "leshy.targets.product.v1", "state")
    if state.get("view") == "actions":
        action(device, "left")
        state = query(device, b"targets.state",
                      "leshy.targets.product.v1", "state")
    if state.get("view") == "detail":
        action(device, "left")
    home = action(device, "left")
    require(home, "Targets cleanup", page="home",
            runtime_owner="none", lease_mask=0)
    return query(device, b"targets.state",
                 "leshy.targets.product.v1", "state")


def wait_mutation(device: Any, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"targets.state",
                     "leshy.targets.product.v1", "state")
        if last.get("mutation_state") in ("saved", "failed"):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"Target mutation did not finish: {last}")


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
    except (FileNotFoundError, subprocess.CalledProcessError,
            ValueError) as error:
        parser.error(f"unsafe or unverifiable Targets stack: {error}")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    cleanup: dict[str, Any] = {"attempted": False}
    states: dict[str, Any] = {}
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

    device: PassiveSerial | None = None
    try:
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        time.sleep(1.0)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
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

        listed, detail = open_first_target(device)
        states["before"] = detail
        screens["detail_before"] = capture(
            device, frames, "targets-favorite-detail-before")
        target_id = detail["selected_target_id"]
        favorite_before = bool(detail["selected_favorite"])
        state_generation_before = int(detail["target_state_generation"])

        action(device, "right")
        actions_before = query(device, b"targets.state",
                               "leshy.targets.product.v1", "state")
        require(actions_before, "Target actions", status="ready",
                view="actions", selected_target_id=target_id,
                selected_favorite=favorite_before, write_enabled=True,
                lease_mask=13)
        screens["actions_before"] = capture(
            device, frames, "targets-favorite-actions-before")
        action(device, "right")
        saved = wait_mutation(device)
        states["saved"] = saved
        require(saved, "favorite save", status="ready", view="actions",
                selected_target_id=target_id,
                selected_favorite=not favorite_before,
                mutation_state="saved", mutation_status="saved",
                mutation_persisted=True, cleanup_complete=True,
                mutation_expected_cid=EXPECTED_CID,
                mutation_observed_cid=EXPECTED_CID,
                lease_mask=13)
        generation_after = int(saved["target_state_generation"])
        if generation_after != state_generation_before + 1:
            raise RuntimeError(
                f"Target state generation did not advance exactly once: {saved}")
        if saved.get("mutation_generation") != generation_after:
            raise RuntimeError(f"reopen generation mismatch: {saved}")
        attempts = int(saved.get("mutation_identity_attempts", 0))
        retries = int(saved.get("mutation_identity_transient_retries", -1))
        if not 1 <= attempts <= 8 or retries != attempts - 1:
            raise RuntimeError(f"invalid bounded identity retries: {saved}")
        if (int(saved.get("mutation_action_us", 0)) <= 0 or
                int(saved.get("mutation_action_us", 0)) > 10000 or
                int(saved.get("mutation_elapsed_us", 0)) <= 0 or
                int(saved.get("mutation_elapsed_us", 0)) > 8000000 or
                int(saved.get("mutation_bytes_written", 0)) <= 0 or
                int(saved.get("mutation_write_calls", 0)) < 3 or
                int(saved.get("mutation_file_syncs", 0)) < 3 or
                int(saved.get("mutation_directory_syncs", 0)) < 3):
            raise RuntimeError(f"unbounded or incomplete atomic save: {saved}")
        screens["actions_saved"] = capture(
            device, frames, "targets-favorite-actions-saved")
        released_before_reset = close_targets(device)
        require(released_before_reset, "release before reboot",
                status="not_loaded", workspace_allocated=False,
                page_open=False, view="none", cleanup_complete=True,
                lease_mask=0)
        device.close()
        device = None

        ready_after, _, reset_timing = reset_capture(
            args.port, args.output, "targets-favorite-cold-reopen", 20.0)
        require(ready_after, "cold candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        # Boot recovery is completed after the early ready marker.  The raw
        # reset capture proves boot identity/timing, while the command reply is
        # the authoritative post-recovery state (the same ordering used by the
        # release Product Survey runner).
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        recovery_after = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery_after, "cold exact media", status="admitted",
                expected_fingerprint=EXPECTED_CID,
                observed_fingerprint=EXPECTED_CID,
                fingerprint_matched=True, mounted_read_only=True,
                read_only_guaranteed=True, blocked_write_attempts=0,
                cleanup_complete=True, physical_write_calls=0)
        _, reopened = open_first_target(device)
        states["reopened"] = reopened
        require(reopened, "cold favorite reopen", status="ready",
                view="detail", selected_target_id=target_id,
                selected_favorite=not favorite_before,
                target_state_generation=generation_after,
                cleanup_complete=True, lease_mask=13)
        screens["detail_reopened"] = capture(
            device, frames, "targets-favorite-detail-reopened")
        released = close_targets(device)
        require(released, "final release", status="not_loaded",
                workspace_allocated=False, page_open=False, view="none",
                cleanup_complete=True, lease_mask=0)
        if int(released.get("heap_free_after_release", 0)) + 512 < int(
                released.get("heap_free_before", 0)):
            raise RuntimeError(f"Targets workspace heap did not recover: {released}")
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            raise RuntimeError(f"final cleanup failed: {cleanup}")

        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "session_generation": int(recovery["generation"]),
            "target_id": target_id,
            "favorite_before": favorite_before,
            "favorite_after": not favorite_before,
            "target_state_generation_before": state_generation_before,
            "target_state_generation_after": generation_after,
            "states": states,
            "screens": screens,
            "reset": reset_timing,
            "released": released,
            "cleanup": cleanup,
        })
    except Exception as error:
        if device is not None:
            cleanup = best_effort_cleanup(device)
        record.update({
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "states": states,
            "screens": screens,
            "cleanup": cleanup,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        raise
    finally:
        if device is not None:
            device.close()

    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(str(args.output / "run.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
