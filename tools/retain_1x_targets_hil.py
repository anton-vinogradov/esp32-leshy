#!/usr/bin/env python3
"""Retain compact source-bound exact 0.149 Targets acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-0.149"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-0.149.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_SOURCE = "8d4a2e86d88807f0de21d5afd9680912d8b7797f"
EXPECTED_VERSION = "0.149.0-targets-inplace-reset"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/domain/targets/TargetComparison.cpp",
    "firmware/leshy1/src/domain/targets/TargetComparison.h",
    "firmware/leshy1/src/services/targets/TargetComparisonService.cpp",
    "tests/hil/delta-scopes/targets-inplace-reset-0.149.json",
    "tools/check_targets_product_contract.py",
    "tools/check_targets_stack_elf_contract.py",
    "tools/run_1x_targets_hil.py",
    "tools/run_1x_targets_mount_regression_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_run(run_dir: Path, schema: str) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    require(run_path.is_file(), f"missing {run_path}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    require(run.get("schema") == schema and run.get("status") == "pass",
            f"passing {schema} required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "exact source mismatch")
    require(run.get("exact_cid") == EXPECTED_CID, "exact CID mismatch")
    candidate = run.get("candidate", {})
    require(candidate.get("version") == EXPECTED_VERSION,
            "candidate version mismatch")
    firmware = run_dir / "firmware.bin"
    require(firmware.is_file() and
            digest(firmware) == candidate.get("firmware_sha256"),
            "candidate firmware hash mismatch")
    return run


def require_target_state(state: dict[str, Any], *, view: str,
                         generations: tuple[int, int]) -> None:
    require(state.get("status") == "ready" and state.get("view") == view,
            f"Targets {view} not ready")
    require(state.get("target_count") == 16, "unexpected Target count")
    require(state.get("compare_available") is True, "Compare unavailable")
    require((state.get("baseline_generation"),
             state.get("current_generation")) == generations,
            "Targets source generations mismatch")
    require(state.get("workspace_allocated") is True and
            state.get("page_open") is True, "Targets workspace not owned")
    require(state.get("read_only") is True and
            state.get("write_enabled") is False and
            state.get("blocked_write_attempts") == 0,
            "Targets read-only contract mismatch")
    require(state.get("filesystem_mount_error") == 0 and
            state.get("cleanup_complete") is True and
            state.get("lease_mask") == 13, "Targets resource state mismatch")


def require_terminal(run: dict[str, Any], generation: int) -> None:
    safe = run.get("safe_outputs", {})
    require(safe.get("buzzer_inactive") is True and
            safe.get("nrf_ce_inactive") is True and
            safe.get("software_quiesce_complete") is True,
            "unsafe final outputs")
    inputs = run.get("input", {})
    require(inputs.get("status") == "ready" and
            inputs.get("read_errors") == 0 and
            inputs.get("queue_drops") == 0 and
            inputs.get("ambiguous_presses") == 0,
            "input failure or drop")
    cleanup = run.get("cleanup", {})
    final = cleanup.get("final_state", {})
    require(cleanup.get("complete") is True and not cleanup.get("errors") and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("library_generation") == generation,
            "final cleanup mismatch")
    released = run.get("targets", {}).get("released", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("page_open") is False and
            released.get("lease_mask") == 0 and
            released.get("heap_free_after_release", 0) >=
            released.get("heap_free_before", 0) - 512,
            "Targets workspace/heap not released")
    require(run.get("radio_tx_commands") == 0, "radio TX observed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--short", required=True, type=Path)
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    short_dir = args.short.resolve()
    full_dir = args.full.resolve()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        short = load_run(
            short_dir, "leshy.targets_mount_regression_hil.run.v1")
        full = load_run(full_dir, "leshy.targets_product_hil.run.v1")
        require(short["candidate"] == full["candidate"],
                "short/full candidate mismatch")
        require(short.get("flash_count") == 1 and
                full.get("flash_count") == 0,
                "exact one-flash/reuse sequence mismatch")
        require(short.get("generations") == [111, 112] and
                short.get("storage_write_calls") == 0,
                "short read-only regression mismatch")
        require(full.get("generation_before") == 112 and
                full.get("survey_generations") == [113, 114] and
                all(value > 0 for value in full.get("survey_observations", [])),
                "full visit-generation continuity mismatch")
        for name in ("list", "compare"):
            require_target_state(short["targets"][name], view=name,
                                 generations=(111, 112))
        for name in ("list", "compare", "detail"):
            require_target_state(full["targets"][name], view=name,
                                 generations=(113, 114))
        for run in (short, full):
            comparison = run["targets"]["compare"]
            classified = sum(int(comparison[key]) for key in
                             ("added", "removed", "changed", "unchanged"))
            require(classified == comparison["target_count"],
                    "comparison does not classify every Target")
        require_terminal(short, 112)
        require_terminal(full, 114)
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(short_dir / "run.json", args.bundle / "short-run.json")
    shutil.copyfile(full_dir / "run.json", args.bundle / "full-run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    frame_sources = {
        "short-list": short_dir / "frames/targets-mount-list",
        "short-compare": short_dir / "frames/targets-mount-compare",
        "full-list": full_dir / "frames/targets-list",
        "full-compare": full_dir / "frames/targets-compare",
        "full-detail": full_dir / "frames/targets-detail",
    }
    for retained, source in frame_sources.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(source.with_suffix(suffix),
                            frames / f"{retained}{suffix}")

    provenance = {
        "schema": "leshy.targets_product_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": short["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "raw_run_sha256": {
            "short": digest(short_dir / "run.json"),
            "full": digest(full_dir / "run.json"),
        },
        "raw_artifacts_manifest_sha256": {
            "short": digest(short_dir / "artifacts.sha256"),
            "full": digest(full_dir / "artifacts.sha256"),
        },
    }
    write_json(args.bundle / "provenance.json", provenance)

    manifest: dict[str, str] = {}
    for path in sorted(args.bundle.rglob("*")):
        if path.is_file():
            manifest[str(path.relative_to(args.bundle))] = digest(path)
    write_json(args.bundle / "manifest.json", manifest)

    summary = {
        "schema": "leshy.targets_product_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-107", "E-HIL-167", "E-UX-044"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": short["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_sequence": {"short": 1, "full_reuse": 0, "total": 1},
        "short_regression": {
            "generations": short["generations"],
            "target_count": short["targets"]["list"]["target_count"],
            "comparison": {key: short["targets"]["compare"][key] for key in
                           ("added", "removed", "changed", "unchanged")},
            "storage_write_calls": short["storage_write_calls"],
            "heap_free_before": short["targets"]["released"]["heap_free_before"],
            "heap_free_after_release":
                short["targets"]["released"]["heap_free_after_release"],
        },
        "full_delta": {
            "generation_before": full["generation_before"],
            "survey_generations": full["survey_generations"],
            "survey_observations": full["survey_observations"],
            "target_count": full["targets"]["list"]["target_count"],
            "comparison": {key: full["targets"]["compare"][key] for key in
                           ("added", "removed", "changed", "unchanged")},
            "heap_free_before": full["targets"]["released"]["heap_free_before"],
            "heap_free_after_release":
                full["targets"]["released"]["heap_free_after_release"],
        },
        "read_only_targets": {
            "filesystem_mount_error": 0,
            "write_enabled": False,
            "blocked_write_attempts": 0,
        },
        "safe_outputs": {key: full["safe_outputs"][key] for key in
                         ("buzzer_inactive", "nrf_ce_inactive",
                          "software_quiesce_complete")},
        "input": {key: full["input"][key] for key in
                  ("status", "read_errors", "queue_drops",
                   "ambiguous_presses")},
        "final": {key: full["cleanup"]["final_state"][key] for key in
                  ("page", "runtime_owner", "lease_mask",
                   "library_generation")},
        "radio_tx_commands": 0,
        "screens": {
            name: {
                "png": f"frames/{name}.png",
                "png_sha256": digest(frames / f"{name}.png"),
            } for name in frame_sources
        },
        "raw_run_sha256": provenance["raw_run_sha256"],
        "raw_artifacts_manifest_sha256":
            provenance["raw_artifacts_manifest_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(json.dumps({
        "schema": summary["schema"], "status": "pass",
        "summary": str(args.summary.relative_to(ROOT)),
        "bundle_files": len(manifest),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
