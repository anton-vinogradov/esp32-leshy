#!/usr/bin/env python3
"""Fail closed unless compact exact 0.150 Targets evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-evidence-0.150.json"


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
    expected_files = {
        "frames/compare-first.json", "frames/compare-first.png",
        "frames/compare-last.json", "frames/compare-last.png",
        "frames/detail.json", "frames/detail.png",
        "frames/list.json", "frames/list.png",
        "precursor/compare-last.json", "precursor/compare-last.png",
        "precursor/record.json", "provenance.json", "run.json",
    }
    require(failures, set(manifest) == expected_files,
            "unexpected retained artifact set")
    for relative, expected in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.targets_evidence_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-AUTO-108", "E-HIL-168", "E-UX-045"],
            "summary identity mismatch")
    require(failures, summary.get("source_commit") ==
            "6ef57155b48be47fecfb6c8bb543886553009832",
            "exact source mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") == "0.150.0-targets-evidence" and
            candidate.get("firmware_bytes") == 3113168 and
            candidate.get("firmware_sha256") ==
            "bbb200a5a9ca4b8c1cd60dcdd665ec64eea70ecb2a4d0244ff642df240268e65" and
            candidate.get("app_elf_sha256") ==
            "e91cad765c55c08dc317e4099e173423a18af4aeba323f824b1759e3b8caae56" and
            candidate.get("map_sha256") ==
            "5599e1d0835f81458d1647b31ed3a40d0fe5e67d55bab7d47f95a50a0516ae9c",
            "exact candidate identity mismatch")
    require(failures, candidate.get("checked_stack_frames") == {
        "TargetsController::comparisonItemBefore(": 480,
        "TargetsController::loadBindings(": 416,
        "TargetsController::loadComparisonSide(": 272,
        "TargetsController::rebuildComparisonOrder()": 32,
        "TargetsController::reset()": 256,
        "buildSide(": 1104,
        "compareTargetSessionsInto(": 80,
        "resetTargetComparisonResult(": 32,
    }, "exact ELF stack frames mismatch")
    require(failures,
            summary.get("exact_cid") == "FE343253440000002000000055019CB7" and
            summary.get("flash_count") == 1 and
            summary.get("generations") == [113, 114],
            "CID, flash count or generation pair mismatch")

    comparison = summary.get("comparison", {})
    require(failures,
            comparison.get("count") == 16 and
            comparison.get("classes") ==
            {"added": 2, "removed": 0, "changed": 0, "unchanged": 14} and
            comparison.get("class_order") ==
            ["added", "added"] + ["unchanged"] * 14 and
            comparison.get("representative_signal_dbm") ==
            [-73, -88, -70, -70, -70, -71, -75, -75,
             -76, -77, -78, -78, -79, -80, -87, -87] and
            comparison.get("exact_evidence_rows") == 16,
            "comparison row order/evidence mismatch")
    opened = summary.get("opened_evidence", {})
    require(failures,
            opened.get("comparison_selection") == 0 and
            opened.get("selected_change_class") == "added" and
            opened.get("selected_change_mask") == 0 and
            opened.get("baseline_evidence_present") is False and
            opened.get("current_evidence_present") is True and
            opened.get("current_evidence_generation") == 114 and
            opened.get("current_observation_sequence") == 16 and
            opened.get("current_rssi_dbm") == -73 and
            opened.get("current_channel") == 9,
            "opened exact evidence mismatch")
    require(failures, summary.get("navigation") == {
        "detail_back_view": "compare", "detail_back_selection": 0,
        "compare_back_view": "list",
    }, "navigation return mismatch")
    require(failures, summary.get("read_only") == {
        "storage_write_calls": 0, "filesystem_mount_error": 0,
        "write_enabled": False, "blocked_write_attempts": 0,
    }, "read-only invariant mismatch")
    heap = summary.get("heap", {})
    require(failures, heap.get("after_release", 0) >= heap.get("before", 0) - 512,
            "Targets heap did not return after release")
    require(failures, summary.get("safe_outputs") == {
        "buzzer_inactive": True, "nrf_ce_inactive": True,
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

    screens = summary.get("screens", {})
    require(failures, set(screens) ==
            {"compare-first", "compare-last", "detail", "list"},
            "screenshot set mismatch")
    for record in screens.values():
        path = bundle / record.get("png", "missing")
        require(failures,
                path.is_file() and digest(path) == record.get("png_sha256"),
                f"screenshot mismatch: {record.get('png')}")
    require(failures,
            screens.get("compare-last", {}).get("png_sha256") ==
            "9d628070c8fbb26174cc0acd0261928c1817cdc525f3da04fc15463024632791",
            "accepted scrolled-frame hash mismatch")
    precursor = summary.get("visual_precursor", {})
    require(failures,
            precursor.get("status") == "rejected_after_manual_visual_review" and
            precursor.get("source_commit") ==
            "a146b5961d80e5c6f61dd16ecf399359f50e36a9" and
            precursor.get("compare_last_png_sha256") ==
            "5d7d1f8a870ec2142747a71a61f07ef818f5911e180ab05bf00fff1d61dd9f03" and
            precursor.get("compare_last_png_sha256") !=
            screens.get("compare-last", {}).get("png_sha256"),
            "visual precursor/fix boundary mismatch")

    run_path = bundle / "run.json"
    require(failures,
            run_path.is_file() and digest(run_path) == summary.get("raw_run_sha256"),
            "raw run mismatch")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets evidence HIL acceptance passed: 16 sorted rows, exact evidence, clean scrolling, zero writes/TX/drops/leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
