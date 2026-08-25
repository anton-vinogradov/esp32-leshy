#!/usr/bin/env python3
"""Retain compact source-bound exact 0.153 Targets tags HIL."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-tags-0.153"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-tags-0.153.json"
EXPECTED_SOURCE = "042b120e85766d6d3762a7d07f8bf3c183f83cc5"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_VERSION = "0.153.0-targets-tags-edit"
EXPECTED_FIRMWARE = "b9a49fe887baf595da01ea798eb1efa8dada57c5ac20af090f467fcb7b688651"
EXPECTED_ELF = "49d9c7cbb058158bda4ef19c88e6cfbf56c05f38b4a055e616841cb4091a0d56"
EXPECTED_MAP = "0cdaa2ec9f4874991d5c9738f876f7f87fe6e4f96064dd42f3c0685273a3adde"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/ui/UiStrings.def",
    "tests/hil/delta-scopes/targets-tags-0.153.json",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/run_1x_targets_tags_hil.py",
)
FRAMES = {
    "list-before": "targets-tags-list-before",
    "editor-before": "targets-tags-editor-before",
    "editor-changed": "targets-tags-editor-changed",
    "list-added": "targets-tags-list-added",
    "list-added-reopened": "targets-tags-list-added-reopened",
    "list-removed": "targets-tags-list-removed",
    "detail-removed-reopened": "targets-tags-detail-removed-reopened",
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
    require(run.get("schema") == "leshy.targets_tags_hil.run.v1" and
            run.get("status") == "pass", "passing tags run required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "exact source mismatch")
    candidate = run.get("candidate", {})
    require(candidate.get("version") == EXPECTED_VERSION and
            candidate.get("firmware_bytes") == 3135872 and
            candidate.get("firmware_sha256") == EXPECTED_FIRMWARE and
            candidate.get("app_elf_sha256") == EXPECTED_ELF and
            candidate.get("elf_sha256") == EXPECTED_ELF and
            candidate.get("map_sha256") == EXPECTED_MAP,
            "exact candidate mismatch")
    require(run.get("exact_cid") == EXPECTED_CID and
            run.get("session_generation") == 114 and
            run.get("target_id") == "F37CBAC2BD0F95D9FA95F192DDE4C007",
            "exact media/session/Target mismatch")
    require(run.get("tag_hex") == "41" and
            run.get("tag_count_before") == 0 and
            run.get("target_state_generation_before") == 3 and
            run.get("target_state_generation_added") == 4 and
            run.get("target_state_generation_removed") == 5,
            "tag/generation transitions mismatch")
    states = run["states"]
    added = states["added"]
    added_reopened = states["added_reopened"]
    removed = states["removed"]
    removed_reopened = states["removed_reopened"]
    require(added.get("view") == "tag_list" and
            added.get("selected_tag_count") == 1 and
            added.get("mutation_generation") == 4 and
            added.get("mutation_persisted") is True and
            added_reopened.get("selected_tag_hex") == "41" and
            added_reopened.get("target_state_generation") == 4,
            "added tag did not cold-reopen")
    require(removed.get("view") == "tag_list" and
            removed.get("selected_tag_count") == 0 and
            removed.get("mutation_generation") == 5 and
            removed.get("mutation_persisted") is True and
            removed_reopened.get("view") == "detail" and
            removed_reopened.get("selected_tag_count") == 0 and
            removed_reopened.get("target_state_generation") == 5,
            "removed tag did not stay absent after cold reopen")
    require(mutation_metrics(added) == {
        "mutation_action_us": 158,
        "mutation_elapsed_us": 2914830,
        "mutation_bytes_written": 1691,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75992,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "add mutation metrics mismatch")
    require(mutation_metrics(removed) == {
        "mutation_action_us": 141,
        "mutation_elapsed_us": 2918739,
        "mutation_bytes_written": 1689,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75992,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "remove mutation metrics mismatch")
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
    shutil.copyfile(run_dir / "targets-tags-added-cold-reopen.ndjson",
                    args.bundle / "added-cold-reopen.ndjson")
    shutil.copyfile(run_dir / "targets-tags-removed-cold-reopen.ndjson",
                    args.bundle / "removed-cold-reopen.ndjson")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")

    provenance = {
        "schema": "leshy.targets_tags_hil.provenance.v1",
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

    added = run["states"]["added"]
    removed = run["states"]["removed"]
    summary = {
        "schema": "leshy.targets_tags_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-111", "E-HIL-171", "E-UX-048"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_count": 1,
        "cold_reset_count": 2,
        "session_generation": 114,
        "target_id": run["target_id"],
        "tag": {
            "hex": run["tag_hex"],
            "count_before": run["tag_count_before"],
            "generation_before": run["target_state_generation_before"],
            "generation_added": run["target_state_generation_added"],
            "generation_removed": run["target_state_generation_removed"],
            "cold_reopened_hex":
                run["states"]["added_reopened"]["selected_tag_hex"],
            "cold_removed_count":
                run["states"]["removed_reopened"]["selected_tag_count"],
        },
        "atomic_add": mutation_metrics(added),
        "atomic_remove": mutation_metrics(removed),
        "workspace_bytes": 16384,
        "cold_resets": [run["reset_added"], run["reset_removed"]],
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
