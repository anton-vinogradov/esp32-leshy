#!/usr/bin/env python3
"""Retain compact source-bound exact 0.152 Targets name HIL."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-name-0.152"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-name-0.152.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_SOURCE = "7c9e358493afcf0d4fbaf8b27d567745a7138e0e"
EXPECTED_VERSION = "0.152.0-targets-name-edit"
EXPECTED_FIRMWARE = "0599cb880921ec5cb11d39a681e64a324acc84f048f7dedfacae4ff200703506"
EXPECTED_ELF = "075a137a5b0cbe0dba1428e30f9fc223e59c940da87d3ca971406ea5f53941dd"
EXPECTED_MAP = "c52778fcfd8619a5847de5fb04ceddfeeccb5fcd1ff546a75a00792f4817198f"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/ui/UiStrings.def",
    "tests/hil/delta-scopes/targets-name-0.152.json",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/run_1x_targets_name_hil.py",
)
FRAMES = {
    "detail-before": "targets-name-detail-before",
    "editor-before": "targets-name-editor-before",
    "editor-changed": "targets-name-editor-changed",
    "actions-saved": "targets-name-actions-saved",
    "detail-reopened": "targets-name-detail-reopened",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_name_hil.run.v1" and
            run.get("status") == "pass", "passing name run required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "exact source mismatch")
    candidate = run.get("candidate", {})
    require(candidate.get("version") == EXPECTED_VERSION and
            candidate.get("firmware_bytes") == 3132288 and
            candidate.get("firmware_sha256") == EXPECTED_FIRMWARE and
            candidate.get("app_elf_sha256") == EXPECTED_ELF and
            candidate.get("elf_sha256") == EXPECTED_ELF and
            candidate.get("map_sha256") == EXPECTED_MAP,
            "exact candidate mismatch")
    require(run.get("exact_cid") == EXPECTED_CID and
            run.get("session_generation") == 114,
            "exact media/session mismatch")
    require(run.get("edit_kind") == "append_A" and
            run.get("name_before_hex") == "" and
            run.get("name_after_hex") == "41" and
            run.get("target_state_generation_before") == 2 and
            run.get("target_state_generation_after") == 3,
            "name/generation transition mismatch")
    states = run["states"]
    before, edited, saved, reopened = (
        states[name] for name in ("before", "edited", "saved", "reopened")
    )
    target_id = run.get("target_id")
    require(all(state.get("selected_target_id") == target_id
                for state in (before, edited, saved, reopened)),
            "stable Target identity mismatch")
    require(before.get("view") == "detail" and
            before.get("selected_name_hex") == "" and
            edited.get("view") == "name_edit" and
            edited.get("action_selection") == 1 and
            edited.get("name_editor_selection") == 1 and
            edited.get("name_editor_glyph") == 65 and
            edited.get("name_editor_hex") == "41" and
            edited.get("name_editor_dirty") is True,
            "bounded editor state mismatch")
    require(saved.get("view") == "actions" and
            saved.get("action_selection") == 1 and
            saved.get("selected_name_hex") == "41" and
            saved.get("mutation_state") == "saved" and
            saved.get("mutation_status") == "saved" and
            saved.get("mutation_persisted") is True and
            saved.get("mutation_generation") == 3 and
            saved.get("mutation_expected_cid") == EXPECTED_CID and
            saved.get("mutation_observed_cid") == EXPECTED_CID and
            saved.get("mutation_action_us") == 155 and
            saved.get("mutation_elapsed_us") == 2824907 and
            saved.get("mutation_bytes_written") == 1689 and
            saved.get("mutation_write_calls") == 3 and
            saved.get("mutation_file_syncs") == 3 and
            saved.get("mutation_directory_syncs") == 3 and
            saved.get("mutation_heap_free_before_mount") == 75992 and
            saved.get("mutation_heap_largest_before_mount") == 34804 and
            saved.get("mutation_identity_attempts") == 1 and
            saved.get("mutation_identity_transient_retries") == 0,
            "atomic name mutation metrics mismatch")
    require(reopened.get("view") == "detail" and
            reopened.get("selected_name_hex") == "41" and
            reopened.get("selected_name_length") == 1 and
            reopened.get("target_state_generation") == 3,
            "cold reopen did not preserve name")
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
    shutil.copyfile(run_dir / "targets-name-cold-reopen.ndjson",
                    args.bundle / "cold-reopen.ndjson")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")

    provenance = {
        "schema": "leshy.targets_name_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256": digest(run_dir / "artifacts.sha256"),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)

    saved = run["states"]["saved"]
    reopened = run["states"]["reopened"]
    summary = {
        "schema": "leshy.targets_name_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-110", "E-HIL-170", "E-UX-047"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_count": 1,
        "session_generation": run["session_generation"],
        "target_id": run["target_id"],
        "name": {
            "edit_kind": run["edit_kind"],
            "before_hex": run["name_before_hex"],
            "after_hex": run["name_after_hex"],
            "generation_before": run["target_state_generation_before"],
            "generation_after": run["target_state_generation_after"],
            "cold_reopened_hex": reopened["selected_name_hex"],
            "cold_reopened_generation": reopened["target_state_generation"],
        },
        "atomic_write": {key: saved[key] for key in (
            "mutation_action_us", "mutation_elapsed_us",
            "mutation_bytes_written", "mutation_write_calls",
            "mutation_file_syncs", "mutation_directory_syncs",
            "mutation_heap_free_before_mount",
            "mutation_heap_largest_before_mount",
            "mutation_identity_attempts",
            "mutation_identity_transient_retries",
        )},
        "workspace_bytes": 16384,
        "cold_reset": run["reset"],
        "heap": {
            "before": run["released"]["heap_free_before"],
            "after_release": run["released"]["heap_free_after_release"],
        },
        "final": {key: run["cleanup"]["final_state"][key] for key in
                  ("page", "runtime_owner", "lease_mask", "library_generation")},
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
