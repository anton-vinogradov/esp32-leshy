#!/usr/bin/env python3
"""Fail closed unless compact exact 0.152 Targets name HIL is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-name-0.152.json"


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
    expected = {"cold-reopen.ndjson", "provenance.json", "run.json"}
    for name in ("actions-saved", "detail-before", "detail-reopened",
                 "editor-before", "editor-changed"):
        expected.update({f"frames/{name}.json", f"frames/{name}.png"})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.targets_name_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-110", "E-HIL-170", "E-UX-047"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "7c9e358493afcf0d4fbaf8b27d567745a7138e0e",
            "source identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "0.152.0-targets-name-edit" and
            candidate.get("firmware_bytes") == 3132288 and
            candidate.get("firmware_sha256") ==
            "0599cb880921ec5cb11d39a681e64a324acc84f048f7dedfacae4ff200703506" and
            candidate.get("app_elf_sha256") ==
            "075a137a5b0cbe0dba1428e30f9fc223e59c940da87d3ca971406ea5f53941dd" and
            candidate.get("map_sha256") ==
            "c52778fcfd8619a5847de5fb04ceddfeeccb5fcd1ff546a75a00792f4817198f",
            "candidate identity mismatch")
    require(failures,
            summary.get("exact_cid") ==
            "FE343253440000002000000055019CB7" and
            summary.get("flash_count") == 1 and
            summary.get("session_generation") == 114 and
            summary.get("target_id") ==
            "F37CBAC2BD0F95D9FA95F192DDE4C007",
            "media/session/target identity mismatch")
    require(failures, summary.get("name") == {
        "edit_kind": "append_A", "before_hex": "", "after_hex": "41",
        "generation_before": 2, "generation_after": 3,
        "cold_reopened_hex": "41", "cold_reopened_generation": 3,
    }, "name cold-reopen transition mismatch")
    require(failures, summary.get("atomic_write") == {
        "mutation_action_us": 155,
        "mutation_elapsed_us": 2824907,
        "mutation_bytes_written": 1689,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 75992,
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
    expected_screens = {
        "actions-saved": "d903c9cc511af12371eca93dc3516a0901a670b1e6f11b123127074c6d469064",
        "detail-before": "041588de34973f072eb794b28bb06fc9da335400e3d21af2cdf8f387ff2a56bd",
        "detail-reopened": "85e5cee72a5b0c850dc1360bfd3f6cc8c9384fae40d6adb8f5fb835e0decd195",
        "editor-before": "3228f8c360e41edd4ac4f8b0047bbf58aebb8c334190fd0bb9710248632afb19",
        "editor-changed": "0266bbde97f89bcadb62b7939dbe3061e1199bf013a24010c33afdc22e588f50",
    }
    require(failures, summary.get("screens") == {
        name: {"png": f"frames/{name}.png", "png_sha256": sha}
        for name, sha in expected_screens.items()
    }, "screenshot set/hash mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets name HIL acceptance passed: bounded editor, exact CID, atomic save, cold reopen, clean heap/lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
