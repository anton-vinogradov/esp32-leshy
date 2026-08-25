#!/usr/bin/env python3
"""Fail closed unless compact exact 0.153 Targets tags HIL is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-tags-0.153.json"


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
        "added-cold-reopen.ndjson", "removed-cold-reopen.ndjson",
        "provenance.json", "run.json",
    }
    frames = (
        "list-before", "editor-before", "editor-changed", "list-added",
        "list-added-reopened", "list-removed", "detail-removed-reopened",
    )
    for name in frames:
        expected.update({f"frames/{name}.json", f"frames/{name}.png"})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.targets_tags_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-111", "E-HIL-171", "E-UX-048"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "042b120e85766d6d3762a7d07f8bf3c183f83cc5",
            "source identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "0.153.0-targets-tags-edit" and
            candidate.get("firmware_bytes") == 3135872 and
            candidate.get("firmware_sha256") ==
            "b9a49fe887baf595da01ea798eb1efa8dada57c5ac20af090f467fcb7b688651" and
            candidate.get("app_elf_sha256") ==
            "49d9c7cbb058158bda4ef19c88e6cfbf56c05f38b4a055e616841cb4091a0d56" and
            candidate.get("map_sha256") ==
            "0cdaa2ec9f4874991d5c9738f876f7f87fe6e4f96064dd42f3c0685273a3adde",
            "candidate identity mismatch")
    require(failures,
            summary.get("exact_cid") ==
            "FE343253440000002000000055019CB7" and
            summary.get("flash_count") == 1 and
            summary.get("cold_reset_count") == 2 and
            summary.get("session_generation") == 114 and
            summary.get("target_id") ==
            "F37CBAC2BD0F95D9FA95F192DDE4C007",
            "media/session/Target identity mismatch")
    require(failures, summary.get("tag") == {
        "hex": "41", "count_before": 0,
        "generation_before": 3, "generation_added": 4,
        "generation_removed": 5, "cold_reopened_hex": "41",
        "cold_removed_count": 0,
    }, "tag add/remove cold-reopen transition mismatch")
    require(failures, summary.get("atomic_add") == {
        "mutation_action_us": 158, "mutation_elapsed_us": 2914830,
        "mutation_bytes_written": 1691, "mutation_write_calls": 3,
        "mutation_file_syncs": 3, "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75992,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "bounded atomic add metrics mismatch")
    require(failures, summary.get("atomic_remove") == {
        "mutation_action_us": 141, "mutation_elapsed_us": 2918739,
        "mutation_bytes_written": 1689, "mutation_write_calls": 3,
        "mutation_file_syncs": 3, "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75992,
        "mutation_heap_largest_before_mount": 34804,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "bounded atomic remove metrics mismatch")
    require(failures, summary.get("workspace_bytes") == 16384 and
            summary.get("heap", {}).get("after_release", 0) >=
            summary.get("heap", {}).get("before", 0) - 512,
            "bounded workspace/heap mismatch")
    require(failures, summary.get("final") == {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_generation": 114,
    }, "terminal cleanup mismatch")
    expected_screens = {
        "detail-removed-reopened":
            "09e108f90103aad848426404bf72bf4427716278efce318156f827627d077105",
        "editor-before":
            "b0d4da6cad280e8c5613fc6adc8f6081f1cc7d82d45a57e5a8fc903d33c07e0e",
        "editor-changed":
            "b36d75db8968656821f2c1aeee07715f61b3d8b5f895c7c6a366473e17c30d15",
        "list-added":
            "8e32d58d90ea07957941b62eebb18256e12f6d09405a03c054ebc77f439d6ebc",
        "list-added-reopened":
            "8e32d58d90ea07957941b62eebb18256e12f6d09405a03c054ebc77f439d6ebc",
        "list-before":
            "0abf1eda0e99fe0db6810d46fc5eb63e5c37d5dec9e995c866f3beb07c234e88",
        "list-removed":
            "0abf1eda0e99fe0db6810d46fc5eb63e5c37d5dec9e995c866f3beb07c234e88",
    }
    require(failures, summary.get("screens") == {
        name: {"png": f"frames/{name}.png", "png_sha256": sha}
        for name, sha in expected_screens.items()
    }, "screenshot set/hash mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    provenance_path = bundle / "provenance.json"
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        for relative, expected_hash in provenance.get(
                "source_sha256", {}).items():
            path = ROOT / relative
            require(failures, path.is_file() and digest(path) == expected_hash,
                    f"accepted source drift: {relative}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets tags HIL acceptance passed: bounded add/remove, exact CID, two cold reopens, clean heap/lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
