#!/usr/bin/env python3
"""Fail closed unless compact exact 0.151 Targets favorite HIL is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-favorite-0.151.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    bundle = ROOT / summary.get("bundle", "missing")
    manifest_path = bundle / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {})
    require(failures, manifest_path.is_file() and
            digest(manifest_path) == summary.get("manifest_sha256"),
            "manifest missing or hash mismatch")
    expected = {
        "frames/actions-before.json", "frames/actions-before.png",
        "frames/actions-saved.json", "frames/actions-saved.png",
        "frames/detail-before.json", "frames/detail-before.png",
        "frames/detail-reopened.json", "frames/detail-reopened.png",
        "precursors/early-boot-harness.json",
        "precursors/workspace-after-mount.json",
        "precursors/workspace-before-mount.json",
        "provenance.json", "run.json",
    }
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.targets_favorite_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-109", "E-HIL-169", "E-UX-046"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "02c55b61b0ec5e1efc82efce5423b5c34bf82bcb",
            "source identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") ==
            "0.151.2-targets-favorite-compact" and
            candidate.get("firmware_bytes") == 3129008 and
            candidate.get("firmware_sha256") ==
            "62a300adeb76514719a93de58757a78537a14766243140024920ebcd01d9dfee" and
            candidate.get("app_elf_sha256") ==
            "bab922a10e4dd6d1ddf0215f0ec9cb97c85379da37cdebe61941884378ada0e5" and
            candidate.get("map_sha256") ==
            "7a7c598338633c0e6dae8ac7736be35021e6ecf6df36271e0510879583744c49",
            "candidate identity mismatch")
    require(failures,
            summary.get("exact_cid") ==
            "FE343253440000002000000055019CB7" and
            summary.get("flash_count") == 1 and
            summary.get("session_generation") == 114 and
            summary.get("target_id") ==
            "F37CBAC2BD0F95D9FA95F192DDE4C007",
            "media/session/target identity mismatch")
    require(failures, summary.get("favorite") == {
        "before": True, "after": False, "generation_before": 1,
        "generation_after": 2, "cold_reopened": False,
        "cold_reopened_generation": 2,
    }, "favorite cold-reopen transition mismatch")
    require(failures, summary.get("atomic_write") == {
        "mutation_action_us": 148,
        "mutation_elapsed_us": 2689541,
        "mutation_bytes_written": 1688,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 76152,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    } and summary.get("workspace_bytes") == 16384,
            "bounded atomic write metrics mismatch")
    require(failures,
            summary.get("heap", {}).get("after_release", 0) >=
            summary.get("heap", {}).get("before", 0) - 512,
            "Targets heap did not recover")
    require(failures, summary.get("final") == {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_generation": 114,
    }, "terminal cleanup mismatch")
    require(failures, summary.get("screens", {}) == {
        "actions-before": {
            "png": "frames/actions-before.png",
            "png_sha256":
            "e95f73931f8ae45beefb2b4d4e6c6bfa5f8564006d0ffae33779a75f01a9c8fb",
        },
        "actions-saved": {
            "png": "frames/actions-saved.png",
            "png_sha256":
            "5b70edaf4ba9c8c2caefa365b42b143d5dc022c20392cf8c1f80ba70de0f1a64",
        },
        "detail-before": {
            "png": "frames/detail-before.png",
            "png_sha256":
            "c8c24bdc3cd445516cfe7e1e258d9b39a2565183cdcf6f340aba086cf0138eae",
        },
        "detail-reopened": {
            "png": "frames/detail-reopened.png",
            "png_sha256":
            "041588de34973f072eb794b28bb06fc9da335400e3d21af2cdf8f387ff2a56bd",
        },
    }, "screenshot set/hash mismatch")
    precursors = summary.get("precursors", {})
    require(failures,
            precursors.get("workspace_after_mount", {}).get("status") ==
            "rejected_fail_closed_zero_writes" and
            precursors.get("workspace_before_mount", {}).get("status") ==
            "rejected_fail_closed_zero_writes" and
            precursors.get("workspace_before_mount", {}).get("largest_block") ==
            31732 and
            precursors.get("early_boot_harness", {}).get("status") ==
            "rejected_harness_observation_order" and
            precursors.get("early_boot_harness", {}).get(
                "persisted_generation") == 1,
            "failure precursor chain mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets favorite HIL acceptance passed: exact CID, atomic save, cold reopen, clean heap/lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
