#!/usr/bin/env python3
"""One-flash delta HIL for durable on-device Target note set/clear."""

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


SCHEMA = "leshy.targets_notes_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def open_first_target(device: Any) -> dict[str, Any]:
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
    action(device, "down")
    action(device, "right")
    detail = query(device, b"targets.state",
                   "leshy.targets.product.v1", "state")
    require(detail, "Target detail", status="ready", view="detail",
            selected_target_present=True, lease_mask=13)
    target_id = detail.get("selected_target_id")
    if (not isinstance(target_id, str) or len(target_id) != 32 or
            any(character not in "0123456789ABCDEF"
                for character in target_id)):
        raise RuntimeError(f"invalid stable Target ID: {detail}")
    return detail


def open_notes_editor(device: Any, target_id: str) -> dict[str, Any]:
    action(device, "right")
    for _ in range(3):
        action(device, "down")
    actions = query(device, b"targets.state",
                    "leshy.targets.product.v1", "state")
    require(actions, "Notes action", status="ready", view="actions",
            selected_target_id=target_id, action_selection=3,
            write_enabled=False, lease_mask=13)
    action(device, "right")
    editor = query(device, b"targets.state",
                   "leshy.targets.product.v1", "state")
    require(editor, "Notes editor", status="ready", view="notes_edit",
            selected_target_id=target_id, notes_editor_selection=0,
            notes_editor_dirty=False, write_enabled=False, lease_mask=13)
    return editor


def close_targets(device: Any) -> dict[str, Any]:
    for _ in range(6):
        state = query(device, b"targets.state",
                      "leshy.targets.product.v1", "state")
        if state.get("view") == "none":
            break
        action(device, "left")
    home = query(device, b"ui.state", "leshy.ui.v1", "state")
    require(home, "Targets cleanup", page="home",
            runtime_owner="none", lease_mask=0)
    released = query(device, b"targets.state",
                     "leshy.targets.product.v1", "state")
    require(released, "Targets released", status="not_loaded",
            workspace_allocated=False, page_open=False, view="none",
            cleanup_complete=True, lease_mask=0)
    return released


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


def check_atomic_mutation(state: dict[str, Any], generation: int) -> None:
    require(state, "atomic mutation", mutation_state="saved",
            mutation_status="saved", mutation_persisted=True,
            mutation_generation=generation, cleanup_complete=True,
            mutation_expected_cid=EXPECTED_CID,
            mutation_observed_cid=EXPECTED_CID, lease_mask=13)
    attempts = int(state.get("mutation_identity_attempts", 0))
    retries = int(state.get("mutation_identity_transient_retries", -1))
    if (not 1 <= attempts <= 8 or retries != attempts - 1 or
            not 0 < int(state.get("mutation_action_us", 0)) <= 10000 or
            not 0 < int(state.get("mutation_elapsed_us", 0)) <= 8000000 or
            int(state.get("mutation_bytes_written", 0)) <= 0 or
            int(state.get("mutation_write_calls", 0)) < 3 or
            int(state.get("mutation_file_syncs", 0)) < 3 or
            int(state.get("mutation_directory_syncs", 0)) < 3):
        raise RuntimeError(f"unbounded or incomplete atomic mutation: {state}")


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

        detail = open_first_target(device)
        states["before"] = detail
        target_id = str(detail["selected_target_id"])
        generation_before = int(detail["target_state_generation"])
        if int(detail.get("selected_notes_length", -1)) != 0:
            raise RuntimeError("exact delta requires an initially empty note")
        editor = open_notes_editor(device, target_id)
        require(editor, "empty Notes editor", notes_editor_length=0,
                notes_editor_prefix_hex="")
        screens["editor_before"] = capture(
            device, frames, "targets-notes-editor-before")
        action(device, "down")
        action(device, "right")
        edited = query(device, b"targets.state",
                       "leshy.targets.product.v1", "state")
        require(edited, "edited note", status="ready", view="notes_edit",
                selected_target_id=target_id, notes_editor_selection=1,
                notes_editor_length=1, notes_editor_prefix_hex="41",
                notes_editor_dirty=True, write_enabled=True, lease_mask=13)
        states["edited"] = edited
        screens["editor_changed"] = capture(
            device, frames, "targets-notes-editor-changed")
        action(device, "down")
        action(device, "down")
        action(device, "right")
        generation_set = generation_before + 1
        saved = wait_mutation(device)
        check_atomic_mutation(saved, generation_set)
        require(saved, "note saved", status="ready", view="notes_edit",
                selected_target_id=target_id, selected_notes_length=1,
                selected_notes_prefix_hex="41", notes_editor_length=1,
                notes_editor_prefix_hex="41", notes_editor_dirty=False,
                target_state_generation=generation_set)
        states["saved"] = saved
        screens["editor_saved"] = capture(
            device, frames, "targets-notes-editor-saved")
        released_set = close_targets(device)
        device.close()
        device = None

        ready_set, _, reset_set = reset_capture(
            args.port, args.output, "targets-notes-set-cold-reopen", 20.0)
        require(ready_set, "cold set candidate",
                version=args.expected_version, app_elf_sha256=app_identity)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        detail_set = open_first_target(device)
        require(detail_set, "cold set detail", status="ready", view="detail",
                selected_target_id=target_id, selected_notes_length=1,
                selected_notes_prefix_hex="41",
                target_state_generation=generation_set, lease_mask=13)
        states["set_reopened"] = detail_set
        screens["detail_set_reopened"] = capture(
            device, frames, "targets-notes-detail-set-reopened")
        open_notes_editor(device, target_id)
        action(device, "down")
        action(device, "down")
        action(device, "right")
        cleared = query(device, b"targets.state",
                        "leshy.targets.product.v1", "state")
        require(cleared, "cleared note before save", view="notes_edit",
                notes_editor_selection=2, notes_editor_length=0,
                notes_editor_prefix_hex="", notes_editor_dirty=True,
                write_enabled=True)
        states["cleared"] = cleared
        screens["editor_cleared"] = capture(
            device, frames, "targets-notes-editor-cleared")
        action(device, "down")
        action(device, "right")
        generation_cleared = generation_set + 1
        saved_clear = wait_mutation(device)
        check_atomic_mutation(saved_clear, generation_cleared)
        require(saved_clear, "note clear saved", status="ready",
                view="notes_edit", selected_target_id=target_id,
                selected_notes_length=0, selected_notes_prefix_hex="",
                notes_editor_length=0, notes_editor_prefix_hex="",
                notes_editor_dirty=False,
                target_state_generation=generation_cleared)
        states["clear_saved"] = saved_clear
        screens["editor_clear_saved"] = capture(
            device, frames, "targets-notes-editor-clear-saved")
        released_clear = close_targets(device)
        device.close()
        device = None

        ready_clear, _, reset_clear = reset_capture(
            args.port, args.output, "targets-notes-clear-cold-reopen", 20.0)
        require(ready_clear, "cold clear candidate",
                version=args.expected_version, app_elf_sha256=app_identity)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        detail_clear = open_first_target(device)
        require(detail_clear, "cold clear detail", status="ready",
                view="detail", selected_target_id=target_id,
                selected_notes_length=0, selected_notes_prefix_hex="",
                target_state_generation=generation_cleared, lease_mask=13)
        states["clear_reopened"] = detail_clear
        screens["detail_clear_reopened"] = capture(
            device, frames, "targets-notes-detail-clear-reopened")
        released = close_targets(device)
        if int(released.get("heap_free_after_release", 0)) + 512 < int(
                released.get("heap_free_before", 0)):
            raise RuntimeError(
                f"Targets workspace heap did not recover: {released}")
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            raise RuntimeError(f"final cleanup failed: {cleanup}")

        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "session_generation": int(recovery["generation"]),
            "target_id": target_id,
            "note_hex": "41",
            "target_state_generation_before": generation_before,
            "target_state_generation_set": generation_set,
            "target_state_generation_cleared": generation_cleared,
            "states": states,
            "screens": screens,
            "reset_set": reset_set,
            "reset_clear": reset_clear,
            "released_set": released_set,
            "released_clear": released_clear,
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
