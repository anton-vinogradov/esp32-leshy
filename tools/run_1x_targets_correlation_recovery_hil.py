#!/usr/bin/env python3
"""Cold-recovery HIL for an accepted correlation after a harness-only abort."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from check_targets_stack_elf_contract import stack_frames
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    capture,
    query,
    reset_capture,
)
from run_1x_targets_correlation_hil import open_targets, require
from run_1x_targets_notes_hil import close_targets


SCHEMA = "leshy.targets_correlation_recovery_hil.run.v1"
PRECURSOR_SCHEMA = "leshy.targets_correlation_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def load_precursor(path: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != PRECURSOR_SCHEMA or record.get("status") != "failed":
        raise ValueError("precursor must be the retained failed correlation run")
    proposal = record.get("states", {}).get("proposal_selected")
    if not isinstance(proposal, dict):
        raise ValueError("precursor has no exact selected proposal")
    error = str(record.get("error", ""))
    identities = int(proposal.get("source_identity_count", -1))
    expected_fragment = f"'source_identity_count': {identities + 1}"
    actual_fragment = f"'source_identity_count': {identities}"
    if ("RuntimeError: accepted ownership:" not in error or
            expected_fragment not in error or actual_fragment not in error):
        raise ValueError("precursor did not stop solely at the known cardinality assertion")
    precursor_candidate = record.get("candidate", {})
    for key in ("version", "firmware_sha256", "elf_sha256", "map_sha256",
                "app_elf_sha256"):
        if precursor_candidate.get(key) != candidate.get(key):
            raise ValueError(f"precursor candidate mismatch at {key}")
    return {"record": record, "proposal": proposal}


def select_target(device: PassiveSerial, target_id: str,
                  target_count: int) -> dict[str, Any]:
    for _ in range(target_count + 1):
        selected = query(device, b"targets.state",
                         "leshy.targets.product.v1", "state")
        if selected.get("selected_target_id") == target_id:
            return selected
        action(device, "down")
    raise RuntimeError(f"accepted Target is absent after cold reopen: {target_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--precursor", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map, args.precursor):
        if not path.is_file():
            parser.error(f"required input missing: {path}")
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

    checked_stack_frames = stack_frames(args.elf)
    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate_path = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate_path)
    app_identity = app_elf_sha256(candidate_path)
    candidate = {
        "version": args.expected_version,
        "firmware_sha256": sha256_file(candidate_path),
        "firmware_bytes": candidate_path.stat().st_size,
        "elf_sha256": sha256_file(args.elf),
        "map_sha256": sha256_file(args.map),
        "app_elf_sha256": app_identity,
        "checked_stack_frames": checked_stack_frames,
    }
    precursor = load_precursor(args.precursor, candidate)
    before = precursor["proposal"]
    target_id = str(before["selected_target_id"])
    generation_before = int(before["target_state_generation"])
    decisions_before = int(before["correlation_decision_count"])
    identities_before = int(before["source_identity_count"])
    target_count = int(before["target_count"])
    revision_before = int(before["selected_revision"])
    cleanup: dict[str, Any] = {"attempted": False}
    device: PassiveSerial | None = None
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "candidate": candidate,
        "precursor": {
            "path": str(args.precursor),
            "source_commit": precursor["record"]["source_commit"],
            "proposal_id": before["correlation_proposal_id"],
            "candidate_identity_hex": before["correlation_candidate_identity_hex"],
            "target_id": target_id,
        },
    }
    write_json(args.output / "run.json", record)

    try:
        ready, _, reset = reset_capture(
            args.port, args.output, "targets-correlation-recovery-cold-boot", 20.0)
        require(ready, "cold candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics, "running candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        recovery = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery, "cold exact media", status="admitted",
                expected_fingerprint=EXPECTED_CID,
                observed_fingerprint=EXPECTED_CID,
                fingerprint_matched=True, mounted_read_only=True,
                read_only_guaranteed=True, blocked_write_attempts=0,
                cleanup_complete=True, physical_write_calls=0)

        listed = open_targets(device)
        require(listed, "cold decision log", status="ready", view="list",
                target_state_generation=generation_before + 1,
                correlation_decision_count=decisions_before + 1,
                target_count=target_count,
                source_identity_count=identities_before)
        selected = select_target(device, target_id, target_count)
        require(selected, "accepted Target", status="ready", view="list",
                selected_target_id=target_id,
                selected_revision=revision_before + 1,
                correlation_count=0,
                correlation_proposal_present=False,
                correlation_decision_count=decisions_before + 1,
                target_state_generation=generation_before + 1,
                source_identity_count=identities_before)
        screen = capture(device, frames, "targets-correlation-recovered-target")
        released = close_targets(device)
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            raise RuntimeError(f"final cleanup failed: {cleanup}")
        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "flash_count": 0,
            "radio_tx_commands": 0,
            "cardputer_ports_opened": 0,
            "reset": reset,
            "boot_recovery": recovery,
            "listed": listed,
            "accepted_target": selected,
            "screen": screen,
            "released": released,
            "cleanup": cleanup,
            "transition": {
                "proposal_id": before["correlation_proposal_id"],
                "candidate_identity_hex": before["correlation_candidate_identity_hex"],
                "target_id": target_id,
                "target_revision_before": revision_before,
                "target_revision_after": revision_before + 1,
                "target_state_generation_before": generation_before,
                "target_state_generation_after": generation_before + 1,
                "decision_count_before": decisions_before,
                "decision_count_after": decisions_before + 1,
                "source_identity_count_before": identities_before,
                "source_identity_count_after": identities_before,
            },
        })
    except Exception as error:
        if device is not None:
            cleanup = best_effort_cleanup(device)
        record.update({
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
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
    print(json.dumps({"schema": SCHEMA, "status": "pass",
                      "run": str(args.output / "run.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
