#!/usr/bin/env python3
"""Retain compact source-bound exact 0.154 Targets notes HIL."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-notes-0.154"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-notes-0.154.json"
EXPECTED_SOURCE = "16ccf285713cbb2cd33382fd95992f4e6e77199f"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_VERSION = "0.154.0-targets-notes-edit"
EXPECTED_FIRMWARE = "f2d151dcfc955260a4cd0bee67de1887a46af9bab53b18477bb6633ae99dd095"
EXPECTED_ELF = "9eaf3896cd681932f397f87cdb4cc07a087b9ef6914f2693c485bc40330a6ebd"
EXPECTED_MAP = "4888aa7c2b1ef182121364a2e72e1e1f2a19eee769f4820613ac377574309ed7"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/ui/UiStrings.def",
    "tests/hil/delta-scopes/targets-notes-0.154.json",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/run_1x_targets_notes_hil.py",
)
FRAMES = {
    "editor-before": "targets-notes-editor-before",
    "editor-changed": "targets-notes-editor-changed",
    "editor-saved": "targets-notes-editor-saved",
    "detail-set-reopened": "targets-notes-detail-set-reopened",
    "editor-cleared": "targets-notes-editor-cleared",
    "editor-clear-saved": "targets-notes-editor-clear-saved",
    "detail-clear-reopened": "targets-notes-detail-clear-reopened",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def mutation_metrics(state: dict[str, Any]) -> dict[str, Any]:
    return {key: state[key] for key in (
        "mutation_action_us", "mutation_elapsed_us",
        "mutation_bytes_written", "mutation_write_calls",
        "mutation_file_syncs", "mutation_directory_syncs",
        "mutation_heap_free_before_mount",
        "mutation_heap_largest_before_mount",
        "mutation_identity_attempts",
        "mutation_identity_transient_retries",
    )}


def validate(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_notes_hil.run.v1" and
            run.get("status") == "pass", "passing notes run required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "exact source mismatch")
    candidate = run.get("candidate", {})
    require(candidate.get("version") == EXPECTED_VERSION and
            candidate.get("firmware_bytes") == 3138688 and
            candidate.get("firmware_sha256") == EXPECTED_FIRMWARE and
            candidate.get("app_elf_sha256") == EXPECTED_ELF and
            candidate.get("elf_sha256") == EXPECTED_ELF and
            candidate.get("map_sha256") == EXPECTED_MAP,
            "exact candidate mismatch")
    require(run.get("exact_cid") == EXPECTED_CID and
            run.get("session_generation") == 114 and
            run.get("target_id") ==
            "F37CBAC2BD0F95D9FA95F192DDE4C007",
            "exact media/session/Target mismatch")
    require(run.get("note_hex") == "41" and
            run.get("target_state_generation_before") == 5 and
            run.get("target_state_generation_set") == 6 and
            run.get("target_state_generation_cleared") == 7,
            "note/generation transitions mismatch")
    states = run["states"]
    saved = states["saved"]
    set_reopened = states["set_reopened"]
    clear_saved = states["clear_saved"]
    clear_reopened = states["clear_reopened"]
    require(saved.get("view") == "notes_edit" and
            saved.get("selected_notes_length") == 1 and
            saved.get("selected_notes_prefix_hex") == "41" and
            saved.get("mutation_generation") == 6 and
            saved.get("mutation_persisted") is True and
            set_reopened.get("selected_notes_prefix_hex") == "41" and
            set_reopened.get("target_state_generation") == 6,
            "set note did not cold-reopen")
    require(clear_saved.get("view") == "notes_edit" and
            clear_saved.get("selected_notes_length") == 0 and
            clear_saved.get("mutation_generation") == 7 and
            clear_saved.get("mutation_persisted") is True and
            clear_reopened.get("view") == "detail" and
            clear_reopened.get("selected_notes_length") == 0 and
            clear_reopened.get("target_state_generation") == 7,
            "cleared note did not stay empty after cold reopen")
    require(mutation_metrics(saved) == {
        "mutation_action_us": 153,
        "mutation_elapsed_us": 2942650,
        "mutation_bytes_written": 1690,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75656,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "set mutation metrics mismatch")
    require(mutation_metrics(clear_saved) == {
        "mutation_action_us": 153,
        "mutation_elapsed_us": 2964667,
        "mutation_bytes_written": 1689,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75656,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "clear mutation metrics mismatch")
    released = run.get("released", {})
    final = run.get("cleanup", {}).get("final_state", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("lease_mask") == 0 and
            released.get("cleanup_complete") is True and
            released.get("heap_free_after_release", 0) >=
            released.get("heap_free_before", 0) - 512,
            "workspace/heap release mismatch")
    require(run.get("cleanup", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("library_generation") == 114,
            "terminal cleanup mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    run_dir = args.run.resolve()
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        validate(run)
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_dir / "run.json", args.bundle / "run.json")
    shutil.copyfile(run_dir / "targets-notes-set-cold-reopen.ndjson",
                    args.bundle / "set-cold-reopen.ndjson")
    shutil.copyfile(run_dir / "targets-notes-clear-cold-reopen.ndjson",
                    args.bundle / "clear-cold-reopen.ndjson")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")

    provenance = {
        "schema": "leshy.targets_notes_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256": digest(
            run_dir / "artifacts.sha256"),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)

    saved = run["states"]["saved"]
    clear_saved = run["states"]["clear_saved"]
    summary = {
        "schema": "leshy.targets_notes_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-112", "E-HIL-172", "E-UX-049"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_count": 1,
        "cold_reset_count": 2,
        "session_generation": 114,
        "target_id": run["target_id"],
        "note": {
            "hex": run["note_hex"],
            "generation_before": run["target_state_generation_before"],
            "generation_set": run["target_state_generation_set"],
            "generation_cleared": run["target_state_generation_cleared"],
            "cold_reopened_hex":
                run["states"]["set_reopened"]["selected_notes_prefix_hex"],
            "cold_cleared_length":
                run["states"]["clear_reopened"]["selected_notes_length"],
        },
        "atomic_set": mutation_metrics(saved),
        "atomic_clear": mutation_metrics(clear_saved),
        "workspace_bytes": 16384,
        "cold_resets": [run["reset_set"], run["reset_clear"]],
        "heap": {
            "before": run["released"]["heap_free_before"],
            "after_release": run["released"]["heap_free_after_release"],
        },
        "final": {key: run["cleanup"]["final_state"][key] for key in
                  ("page", "runtime_owner", "lease_mask",
                   "library_generation")},
        "screens": {
            name: {"png": f"frames/{name}.png",
                   "png_sha256": digest(frames / f"{name}.png")}
            for name in FRAMES
        },
        "raw_run_sha256": provenance["raw_run_sha256"],
        "raw_artifacts_manifest_sha256":
            provenance["raw_artifacts_manifest_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
