#!/usr/bin/env python3
"""Fail closed unless compact exact 0.154 Targets notes HIL is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-notes-0.154.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_git_blob(commit: str, relative: str) -> str | None:
    try:
        blob = subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(blob).hexdigest()


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
        "set-cold-reopen.ndjson", "clear-cold-reopen.ndjson",
        "provenance.json", "run.json",
    }
    frames = (
        "editor-before", "editor-changed", "editor-saved",
        "detail-set-reopened", "editor-cleared", "editor-clear-saved",
        "detail-clear-reopened",
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
            summary.get("schema") ==
            "leshy.targets_notes_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-112", "E-HIL-172", "E-UX-049"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "16ccf285713cbb2cd33382fd95992f4e6e77199f",
            "source identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "0.154.0-targets-notes-edit" and
            candidate.get("firmware_bytes") == 3138688 and
            candidate.get("firmware_sha256") ==
            "f2d151dcfc955260a4cd0bee67de1887a46af9bab53b18477bb6633ae99dd095" and
            candidate.get("app_elf_sha256") ==
            "9eaf3896cd681932f397f87cdb4cc07a087b9ef6914f2693c485bc40330a6ebd" and
            candidate.get("map_sha256") ==
            "4888aa7c2b1ef182121364a2e72e1e1f2a19eee769f4820613ac377574309ed7",
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
    require(failures, summary.get("note") == {
        "hex": "41", "generation_before": 5,
        "generation_set": 6, "generation_cleared": 7,
        "cold_reopened_hex": "41", "cold_cleared_length": 0,
    }, "note set/clear cold-reopen transition mismatch")
    require(failures, summary.get("atomic_set") == {
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
    }, "bounded atomic set metrics mismatch")
    require(failures, summary.get("atomic_clear") == {
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
    }, "bounded atomic clear metrics mismatch")
    require(failures, summary.get("workspace_bytes") == 16384 and
            summary.get("heap", {}).get("after_release", 0) >=
            summary.get("heap", {}).get("before", 0) - 512,
            "bounded workspace/heap mismatch")
    require(failures, summary.get("final") == {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_generation": 114,
    }, "terminal cleanup mismatch")
    expected_screens = {
        "detail-clear-reopened":
            "09e108f90103aad848426404bf72bf4427716278efce318156f827627d077105",
        "detail-set-reopened":
            "09e108f90103aad848426404bf72bf4427716278efce318156f827627d077105",
        "editor-before":
            "34b2a99035ac66638d04fd8c8711e090b65d085e4ad197203bdc8160669e2d14",
        "editor-changed":
            "129033d2dd22a588da52cf64e78aadd60b4b99a63f329b067e622308a3454032",
        "editor-clear-saved":
            "408e6533f62d01a1025ec3529abbfdc70301b7b4f3804d323b8faedba20961d1",
        "editor-cleared":
            "e92925cf0152693ee95dfe5cf853be4a6d1bd893daf3f4c777c903676c1aa683",
        "editor-saved":
            "cc416112f542f0f8884a60eaef52874469ede670b70e56f6d3d95a2e5c2ba3cc",
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
        source_commit = str(provenance.get("source_commit", ""))
        for relative, expected_hash in provenance.get(
                "source_sha256", {}).items():
            require(failures,
                    digest_git_blob(source_commit, relative) == expected_hash,
                    f"accepted source snapshot mismatch: {relative}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets notes HIL acceptance passed: bounded set/clear, exact CID, "
          "two cold reopens, clean heap/lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
