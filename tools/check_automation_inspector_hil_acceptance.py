#!/usr/bin/env python3
"""Fail closed unless retained physical Automation Inspector evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-automation-inspector-1.0.0-dev.303.json"


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
    expected = {"provenance.json", "run.json"}
    for scenario in ("malformed-en", "unsigned-en", "malformed-ru", "unsigned-ru"):
        expected.update({f"frames/{scenario}-a.png", f"frames/{scenario}-b.png"})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.automation_inspector_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-BUILD-206", "E-AUTO-181", "E-HIL-215", "E-UX-068",
             "E-STORAGE-039", "RB-M217"],
            "summary identity mismatch")
    require(failures, summary.get("firmware_source_commit") ==
            "ca5bf300289b310dd39845a530aa3fe7a2acd9c2" and
            summary.get("exact_cid") ==
            "FE343253440000002000000055019CB7",
            "source/media identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "1.0.0-dev.303" and
            candidate.get("firmware_bytes") == 3541952 and
            candidate.get("firmware_sha256") ==
            "0976943e76b5d03feefb9acda58d07301597175bc41e62183a1cbcff884e95a2" and
            candidate.get("app_elf_sha256") ==
            "28a67093c3bedf01cae20289fa7bc162f973f614dff43b549eacc82be6216125" and
            candidate.get("map_sha256") ==
            "f81d234557e19250b9fe99c7118942f2640108e6e66e1d0788d9e5a03b74979d" and
            summary.get("factory_sha256") ==
            "8fc16699e4383b6e31050671ac04e2774ac58dcc368065ef1e9f4727b3e2b9ce",
            "candidate identity mismatch")
    lineage = summary.get("lineage", {})
    require(failures,
            lineage.get("candidate_flashes") == 1 and
            lineage.get("accepted_run_flashes") == 0 and
            lineage.get("accepted_run_reused_installed_candidate") is True and
            len(lineage.get("precursors", [])) == 3,
            "single-flash lineage mismatch")
    fixture = summary.get("fixture", {})
    require(failures,
            fixture.get("scratch_path", "").startswith("/leshy-hil/") and
            fixture.get("bytes_written") == 159 and
            fixture.get("write_calls") == 2 and
            fixture.get("file_syncs") == 2 and
            fixture.get("directory_syncs") == 1 and
            fixture.get("exact_entries") is True and
            fixture.get("fingerprint_matched") is True,
            "physical scratch fixture mismatch")
    expected_inspection = {
        "malformed_en": ("en", "malformed.lhau", 12, "too_small",
                         "verifier_unavailable", 0),
        "malformed_ru": ("ru", "malformed.lhau", 12, "too_small",
                         "verifier_unavailable", 0),
        "unsigned_en": ("en", "unsigned.lhau", 147, "parsed",
                        "missing_signature", 1),
        "unsigned_ru": ("ru", "unsigned.lhau", 147, "parsed",
                        "missing_signature", 1),
    }
    for name, expected_values in expected_inspection.items():
        state = summary.get("inspection", {}).get(name, {})
        actual = tuple(state.get(key) for key in (
            "language", "source_name", "source_size", "parse_status",
            "trust_status", "observed_steps"))
        require(failures, actual == expected_values and
                state.get("execution_eligible") is False and
                state.get("zero_action_hid_resource_output") is True,
                f"inspection mismatch: {name}")
    for name, screen in summary.get("stable_screens", {}).items():
        pair = screen.get("pair", [])
        require(failures, len(pair) == 2 and
                all((ROOT / summary["bundle"] / path).is_file() for path in pair) and
                digest(ROOT / summary["bundle"] / pair[0]) ==
                digest(ROOT / summary["bundle"] / pair[1]) ==
                screen.get("png_sha256"),
                f"unstable retained screen pair: {name}")
    require(failures, len(summary.get("stable_screens", {})) == 4,
            "incomplete EN/RU stable screen set")
    require(failures, summary.get("safe") == {
        "action_invocations": 0, "hid_reports": 0,
        "resources_acquired": 0, "rf_transmit_attempts": 0,
        "product_namespace_written": False,
        "pin_or_digest_retained": False, "wifi_host_touched": False,
    }, "safe-output contract mismatch")
    require(failures, summary.get("cleanup") == {
        "scratch_files_removed": 2,
        "device_lock_product_restored": True,
        "language_restored": True,
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, "terminal cleanup mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Automation Inspector HIL acceptance passed: exact SD, stable EN/RU, zero output, clean lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
