#!/usr/bin/env python3
"""Retain compact source-bound exact 0.150 Targets row-evidence HIL."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-evidence-0.150"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-evidence-0.150.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_SOURCE = "6ef57155b48be47fecfb6c8bb543886553009832"
EXPECTED_PRECURSOR_SOURCE = "a146b5961d80e5c6f61dd16ecf399359f50e36a9"
EXPECTED_VERSION = "0.150.0-targets-evidence"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/ui/UiStrings.def",
    "tests/hil/delta-scopes/targets-evidence-0.150.json",
    "tests/native/targets_controller_tests.cpp",
    "tools/check_targets_product_contract.py",
    "tools/check_targets_stack_elf_contract.py",
    "tools/run_1x_targets_evidence_hil.py",
)
FRAME_SOURCES = {
    "compare-first": "targets-evidence-compare-first",
    "compare-last": "targets-evidence-compare-last",
    "detail": "targets-evidence-detail",
    "list": "targets-evidence-list",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def representative_signal(row: dict[str, Any]) -> int:
    if row.get("current_evidence_present"):
        return int(row["current_rssi_dbm"])
    return int(row["baseline_rssi_dbm"])


def require_row_order(rows: list[dict[str, Any]]) -> None:
    rank = {"added": 0, "removed": 1, "changed": 2, "unchanged": 3}
    require(len(rows) == 16, "expected all 16 comparison rows")
    previous_rank = -1
    previous_signal = 0
    for index, row in enumerate(rows):
        require(row.get("comparison_selection") == index,
                "comparison selection sequence mismatch")
        change_class = row.get("selected_change_class")
        require(change_class in rank, "unknown comparison class")
        current_rank = rank[change_class]
        signal = representative_signal(row)
        require(current_rank >= previous_rank, "comparison class order mismatch")
        if current_rank == previous_rank:
            require(signal <= previous_signal,
                    "comparison signal order is not descending")
        previous_rank = current_rank
        previous_signal = signal
        baseline = row.get("baseline_evidence_present") is True
        current = row.get("current_evidence_present") is True
        require(baseline or current, "row has no exact source evidence")
        if baseline:
            require(row.get("baseline_evidence_generation") == 113 and
                    row.get("baseline_observation_sequence", 0) > 0,
                    "baseline evidence coordinate mismatch")
        if current:
            require(row.get("current_evidence_generation") == 114 and
                    row.get("current_observation_sequence", 0) > 0,
                    "current evidence coordinate mismatch")


def require_terminal(run: dict[str, Any]) -> None:
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
            final.get("library_generation") == 114,
            "final cleanup mismatch")
    released = run.get("targets", {}).get("released", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("page_open") is False and
            released.get("lease_mask") == 0 and
            released.get("heap_free_after_release", 0) >=
            released.get("heap_free_before", 0) - 512,
            "Targets workspace/heap not released")
    require(run.get("storage_write_calls") == 0 and
            run.get("radio_tx_commands") == 0,
            "unexpected write or radio TX")


def load_run(run_dir: Path, source: str) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    require(run_path.is_file(), f"missing {run_path}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    require(run.get("schema") == "leshy.targets_evidence_hil.run.v1" and
            run.get("status") == "pass", "passing Targets evidence run required")
    require(run.get("source_commit") == source, "exact source mismatch")
    require(run.get("exact_cid") == EXPECTED_CID, "exact CID mismatch")
    require(run.get("candidate", {}).get("version") == EXPECTED_VERSION,
            "candidate version mismatch")
    require(run.get("flash_count") == 1, "one exact flash required")
    require(run.get("generations") == [113, 114], "generation pair mismatch")
    firmware = run_dir / "firmware.bin"
    require(firmware.is_file() and
            digest(firmware) == run["candidate"].get("firmware_sha256"),
            "candidate firmware hash mismatch")
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--precursor", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    run_dir = args.run.resolve()
    precursor_dir = args.precursor.resolve()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        run = load_run(run_dir, EXPECTED_SOURCE)
        precursor = load_run(precursor_dir, EXPECTED_PRECURSOR_SOURCE)
        require_row_order(run["targets"]["rows"])
        detail = run["targets"]["detail"]
        returned = run["targets"]["returned"]
        first = run["targets"]["rows"][0]
        exact_fields = (
            "comparison_selection", "selected_change_class",
            "selected_change_mask", "baseline_evidence_present",
            "baseline_evidence_generation", "baseline_observation_sequence",
            "baseline_rssi_dbm", "baseline_channel",
            "current_evidence_present", "current_evidence_generation",
            "current_observation_sequence", "current_rssi_dbm",
            "current_channel",
        )
        require(detail.get("view") == "compare_detail" and
                all(detail.get(key) == first.get(key) for key in exact_fields),
                "detail does not match selected comparison row")
        require(returned.get("view") == "compare" and
                returned.get("comparison_selection") ==
                first.get("comparison_selection"),
                "detail back did not preserve comparison selection")
        require(run["targets"]["list"].get("view") == "list",
                "comparison back did not return to Targets list")
        require_terminal(run)
        require(precursor["candidate"] != run["candidate"],
                "precursor and accepted candidates unexpectedly match")
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_dir / "run.json", args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAME_SOURCES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{source}{suffix}",
                            frames / f"{retained}{suffix}")

    precursor_dir_out = args.bundle / "precursor"
    precursor_dir_out.mkdir()
    precursor_base = "targets-evidence-compare-last"
    for suffix in (".json", ".png"):
        shutil.copyfile(precursor_dir / "frames" / f"{precursor_base}{suffix}",
                        precursor_dir_out / f"compare-last{suffix}")
    precursor_record = {
        "schema": "leshy.targets_evidence_hil.visual_precursor.v1",
        "status": "rejected_after_manual_visual_review",
        "reason": "stale glyph pixels remained after scrolling a long Target name",
        "source_commit": EXPECTED_PRECURSOR_SOURCE,
        "candidate": precursor["candidate"],
        "run_sha256": digest(precursor_dir / "run.json"),
        "compare_last_png_sha256":
            digest(precursor_dir_out / "compare-last.png"),
    }
    write_json(precursor_dir_out / "record.json", precursor_record)

    provenance = {
        "schema": "leshy.targets_evidence_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256": digest(run_dir / "artifacts.sha256"),
    }
    write_json(args.bundle / "provenance.json", provenance)

    manifest: dict[str, str] = {}
    for path in sorted(args.bundle.rglob("*")):
        if path.is_file():
            manifest[str(path.relative_to(args.bundle))] = digest(path)
    write_json(args.bundle / "manifest.json", manifest)

    rows = run["targets"]["rows"]
    summary = {
        "schema": "leshy.targets_evidence_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-108", "E-HIL-168", "E-UX-045"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "exact_cid": EXPECTED_CID,
        "flash_count": 1,
        "generations": run["generations"],
        "comparison": {
            "count": len(rows),
            "classes": {key: run["targets"]["detail"][key] for key in
                        ("added", "removed", "changed", "unchanged")},
            "class_order": [row["selected_change_class"] for row in rows],
            "representative_signal_dbm": [representative_signal(row)
                                          for row in rows],
            "exact_evidence_rows": sum(
                row["baseline_evidence_present"] or
                row["current_evidence_present"] for row in rows),
        },
        "opened_evidence": {key: detail[key] for key in exact_fields},
        "navigation": {
            "detail_back_view": returned["view"],
            "detail_back_selection": returned["comparison_selection"],
            "compare_back_view": run["targets"]["list"]["view"],
        },
        "read_only": {
            "storage_write_calls": run["storage_write_calls"],
            "filesystem_mount_error": detail["filesystem_mount_error"],
            "write_enabled": detail["write_enabled"],
            "blocked_write_attempts": detail["blocked_write_attempts"],
        },
        "heap": {
            "before": run["targets"]["released"]["heap_free_before"],
            "after_release":
                run["targets"]["released"]["heap_free_after_release"],
        },
        "safe_outputs": {key: run["safe_outputs"][key] for key in
                         ("buzzer_inactive", "nrf_ce_inactive",
                          "software_quiesce_complete")},
        "input": {key: run["input"][key] for key in
                  ("status", "read_errors", "queue_drops",
                   "ambiguous_presses")},
        "final": {key: run["cleanup"]["final_state"][key] for key in
                  ("page", "runtime_owner", "lease_mask",
                   "library_generation")},
        "radio_tx_commands": run["radio_tx_commands"],
        "screens": {
            name: {
                "png": f"frames/{name}.png",
                "png_sha256": digest(frames / f"{name}.png"),
            } for name in FRAME_SOURCES
        },
        "visual_precursor": {
            "status": precursor_record["status"],
            "reason": precursor_record["reason"],
            "source_commit": EXPECTED_PRECURSOR_SOURCE,
            "record": "precursor/record.json",
            "compare_last_png": "precursor/compare-last.png",
            "compare_last_png_sha256":
                precursor_record["compare_last_png_sha256"],
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
