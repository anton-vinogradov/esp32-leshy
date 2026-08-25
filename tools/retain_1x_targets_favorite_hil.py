#!/usr/bin/env python3
"""Retain compact source-bound exact 0.151 Targets favorite HIL."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-favorite-0.151"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-favorite-0.151.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_SOURCE = "02c55b61b0ec5e1efc82efce5423b5c34bf82bcb"
EXPECTED_VERSION = "0.151.2-targets-favorite-compact"
EXPECTED_FIRMWARE = "62a300adeb76514719a93de58757a78537a14766243140024920ebcd01d9dfee"
EXPECTED_ELF = "bab922a10e4dd6d1ddf0215f0ec9cb97c85379da37cdebe61941884378ada0e5"
EXPECTED_MAP = "7a7c598338633c0e6dae8ac7736be35021e6ecf6df36271e0510879583744c49"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/kernel/safety/WorkerDeadlineSupervisor.cpp",
    "firmware/leshy1/src/kernel/safety/WorkerDeadlineSupervisor.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/storage/TargetCodec.cpp",
    "firmware/leshy1/src/storage/TargetCodec.h",
    "firmware/leshy1/src/storage/TargetStateStore.cpp",
    "firmware/leshy1/src/storage/TargetStateStore.h",
    "firmware/leshy1/src/ui/UiStrings.def",
    "tests/hil/delta-scopes/targets-favorite-0.151.json",
    "tests/native/clean_target_tests.cpp",
    "tests/native/target_state_persistence_tests.cpp",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/check_worker_deadline_supervision.py",
    "tools/run_1x_targets_favorite_hil.py",
)
FRAMES = {
    "detail-before": "targets-favorite-detail-before",
    "actions-before": "targets-favorite-actions-before",
    "actions-saved": "targets-favorite-actions-saved",
    "detail-reopened": "targets-favorite-detail-reopened",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pass(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_favorite_hil.run.v1" and
            run.get("status") == "pass", "passing favorite run required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "exact source mismatch")
    candidate = run.get("candidate", {})
    require(candidate.get("version") == EXPECTED_VERSION and
            candidate.get("firmware_bytes") == 3129008 and
            candidate.get("firmware_sha256") == EXPECTED_FIRMWARE and
            candidate.get("app_elf_sha256") == EXPECTED_ELF and
            candidate.get("elf_sha256") == EXPECTED_ELF and
            candidate.get("map_sha256") == EXPECTED_MAP,
            "exact candidate mismatch")
    require(run.get("exact_cid") == EXPECTED_CID and
            run.get("session_generation") == 114,
            "exact media/session mismatch")
    require(run.get("favorite_before") is True and
            run.get("favorite_after") is False and
            run.get("target_state_generation_before") == 1 and
            run.get("target_state_generation_after") == 2,
            "favorite/generation transition mismatch")
    before = run["states"]["before"]
    saved = run["states"]["saved"]
    reopened = run["states"]["reopened"]
    target_id = run.get("target_id")
    require(before.get("selected_target_id") == target_id and
            reopened.get("selected_target_id") == target_id and
            before.get("selected_favorite") is True and
            reopened.get("selected_favorite") is False and
            reopened.get("target_state_generation") == 2,
            "cold reopen did not preserve target mutation")
    require(saved.get("mutation_state") == "saved" and
            saved.get("mutation_status") == "saved" and
            saved.get("mutation_persisted") is True and
            saved.get("mutation_generation") == 2 and
            saved.get("mutation_expected_cid") == EXPECTED_CID and
            saved.get("mutation_observed_cid") == EXPECTED_CID and
            saved.get("mutation_action_us") == 148 and
            saved.get("mutation_elapsed_us") == 2689541 and
            saved.get("mutation_bytes_written") == 1688 and
            saved.get("mutation_write_calls") == 3 and
            saved.get("mutation_file_syncs") == 3 and
            saved.get("mutation_directory_syncs") == 3 and
            saved.get("mutation_heap_free_before_mount") == 76152 and
            saved.get("mutation_heap_largest_before_mount") == 34804 and
            saved.get("mutation_identity_attempts") == 1 and
            saved.get("mutation_identity_transient_retries") == 0,
            "atomic mutation metrics mismatch")
    released = run.get("released", {})
    final = run.get("cleanup", {}).get("final_state", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("lease_mask") == 0 and
            released.get("heap_free_after_release", 0) >=
            released.get("heap_free_before", 0) - 512,
            "workspace/heap release mismatch")
    require(run.get("cleanup", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("library_generation") == 114,
            "terminal cleanup mismatch")


def validate_precursors(after_mount: dict[str, Any],
                        before_mount: dict[str, Any],
                        harness: dict[str, Any]) -> None:
    expected = (
        (after_mount, "595ff08098ebc0232b1891a099a10f43f8d931e3",
         "workspace_unavailable"),
        (before_mount, "ce6ba5b2ff2b1918c2bb761c87c4846f8dcaa9ff",
         "workspace_unavailable_before_mount"),
    )
    for run, source, status in expected:
        saved = run.get("states", {}).get("saved", {})
        require(run.get("status") == "failed" and
                run.get("source_commit") == source and
                saved.get("mutation_status") == status and
                saved.get("mutation_bytes_written") == 0 and
                saved.get("mutation_write_calls") == 0 and
                saved.get("selected_favorite") is False and
                run.get("cleanup", {}).get("complete") is True,
                f"invalid fail-closed precursor: {status}")
    saved = harness.get("states", {}).get("saved", {})
    require(harness.get("status") == "failed" and
            harness.get("source_commit") ==
            "d31ff8d66922bf490e54a5ff97e949cc056e2244" and
            harness.get("candidate", {}).get("firmware_sha256") ==
            EXPECTED_FIRMWARE and
            saved.get("mutation_status") == "saved" and
            saved.get("selected_favorite") is True and
            saved.get("target_state_generation") == 1 and
            "actual={'status': None" in harness.get("error", ""),
            "invalid early-boot harness precursor")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--after-mount-failure", required=True, type=Path)
    parser.add_argument("--before-mount-failure", required=True, type=Path)
    parser.add_argument("--harness-failure", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        run_dir = args.run.resolve()
        run = load(run_dir / "run.json")
        after_mount = load(args.after_mount_failure.resolve() / "run.json")
        before_mount = load(args.before_mount_failure.resolve() / "run.json")
        harness = load(args.harness_failure.resolve() / "run.json")
        validate_pass(run)
        validate_precursors(after_mount, before_mount, harness)
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_dir / "run.json", args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")
    precursors = args.bundle / "precursors"
    precursors.mkdir()
    precursor_inputs = {
        "workspace-after-mount.json": args.after_mount_failure,
        "workspace-before-mount.json": args.before_mount_failure,
        "early-boot-harness.json": args.harness_failure,
    }
    for name, directory in precursor_inputs.items():
        shutil.copyfile(directory.resolve() / "run.json", precursors / name)

    provenance = {
        "schema": "leshy.targets_favorite_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256":
            digest(run_dir / "artifacts.sha256"),
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
        "schema": "leshy.targets_favorite_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-109", "E-HIL-169", "E-UX-046"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_count": 1,
        "session_generation": run["session_generation"],
        "target_id": run["target_id"],
        "favorite": {
            "before": run["favorite_before"],
            "after": run["favorite_after"],
            "generation_before": run["target_state_generation_before"],
            "generation_after": run["target_state_generation_after"],
            "cold_reopened": reopened["selected_favorite"],
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
                  ("page", "runtime_owner", "lease_mask",
                   "library_generation")},
        "screens": {
            name: {"png": f"frames/{name}.png",
                   "png_sha256": digest(frames / f"{name}.png")}
            for name in FRAMES
        },
        "precursors": {
            "workspace_after_mount": {
                "status": "rejected_fail_closed_zero_writes",
                "source_commit": after_mount["source_commit"],
                "record": "precursors/workspace-after-mount.json",
            },
            "workspace_before_mount": {
                "status": "rejected_fail_closed_zero_writes",
                "source_commit": before_mount["source_commit"],
                "largest_block": before_mount["states"]["saved"]
                    ["mutation_heap_largest_before_mount"],
                "record": "precursors/workspace-before-mount.json",
            },
            "early_boot_harness": {
                "status": "rejected_harness_observation_order",
                "source_commit": harness["source_commit"],
                "persisted_generation": harness["states"]["saved"]
                    ["target_state_generation"],
                "record": "precursors/early-boot-harness.json",
            },
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
