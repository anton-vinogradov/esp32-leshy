#!/usr/bin/env python3
"""Fail closed unless compact exact 0.149 Targets evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-0.149.json"


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
    if not manifest_path.is_file():
        failures.append("retained manifest missing")
        manifest = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(failures, digest(manifest_path) == summary.get("manifest_sha256"),
                "manifest hash mismatch")
    require(failures, set(manifest) == {
        "frames/full-compare.json", "frames/full-compare.png",
        "frames/full-detail.json", "frames/full-detail.png",
        "frames/full-list.json", "frames/full-list.png",
        "frames/short-compare.json", "frames/short-compare.png",
        "frames/short-list.json", "frames/short-list.png",
        "full-run.json", "provenance.json", "short-run.json",
    }, "unexpected retained artifact set")
    for relative, expected in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.targets_product_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-107", "E-HIL-167", "E-UX-044"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "8d4a2e86d88807f0de21d5afd9680912d8b7797f",
            "exact source mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "0.149.0-targets-inplace-reset" and
            candidate.get("firmware_sha256") ==
            "743f31614df8891667293fdf755c7e53b9b4fc6ce105bc48d8a84a76d1e9c653" and
            candidate.get("app_elf_sha256") ==
            "3293c8328bf946843c0035df7516fa47b8363d207acface51416967d51be62e9" and
            candidate.get("map_sha256") ==
            "8fef982fadc2253d7a64ae01d272965d8bd29c701654d95b128c552f8c202051",
            "exact candidate hashes mismatch")
    require(failures, candidate.get("checked_stack_frames") == {
        "TargetsController::loadBindings(": 416,
        "TargetsController::reset()": 256,
        "buildSide(": 1104,
        "compareTargetSessionsInto(": 80,
        "resetTargetComparisonResult(": 32,
    }, "exact ELF stack frames mismatch")
    require(failures,
            summary.get("exact_cid") == "FE343253440000002000000055019CB7" and
            summary.get("flash_sequence") ==
            {"short": 1, "full_reuse": 0, "total": 1},
            "CID or one-flash sequence mismatch")

    short = summary.get("short_regression", {})
    require(failures,
            short.get("generations") == [111, 112] and
            short.get("target_count") == 16 and
            short.get("comparison") ==
            {"added": 7, "removed": 0, "changed": 0, "unchanged": 9} and
            short.get("storage_write_calls") == 0 and
            short.get("heap_free_after_release") >=
            short.get("heap_free_before", 0) - 512,
            "short read-only regression mismatch")
    full = summary.get("full_delta", {})
    require(failures,
            full.get("generation_before") == 112 and
            full.get("survey_generations") == [113, 114] and
            full.get("survey_observations") == [21, 18] and
            full.get("target_count") == 16 and
            full.get("comparison") ==
            {"added": 2, "removed": 0, "changed": 0, "unchanged": 14} and
            full.get("heap_free_after_release") >=
            full.get("heap_free_before", 0) - 512,
            "full Targets delta mismatch")
    require(failures, summary.get("read_only_targets") == {
        "filesystem_mount_error": 0,
        "write_enabled": False,
        "blocked_write_attempts": 0,
    }, "read-only Targets invariant mismatch")
    require(failures, summary.get("safe_outputs") == {
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "safe outputs mismatch")
    require(failures, summary.get("input") == {
        "status": "ready", "read_errors": 0, "queue_drops": 0,
        "ambiguous_presses": 0,
    }, "input integrity mismatch")
    require(failures, summary.get("final") == {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_generation": 114,
    }, "final cleanup mismatch")
    require(failures, summary.get("radio_tx_commands") == 0,
            "radio TX observed")

    raw_hashes = summary.get("raw_run_sha256", {})
    for name in ("short", "full"):
        path = bundle / f"{name}-run.json"
        require(failures, path.is_file() and digest(path) == raw_hashes.get(name),
                f"raw {name} run mismatch")
    screens = summary.get("screens", {})
    require(failures, set(screens) == {
        "short-list", "short-compare", "full-list", "full-compare",
        "full-detail",
    }, "screenshot set mismatch")
    for record in screens.values():
        path = bundle / record.get("png", "missing")
        require(failures,
                path.is_file() and digest(path) == record.get("png_sha256"),
                f"screenshot mismatch: {record.get('png')}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets HIL acceptance passed: one flash, generations 111..114, List/Compare/Detail, zero TX/drops/leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
