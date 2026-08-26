#!/usr/bin/env python3
"""Retain compact exact 0.160 post-Survey Targets load evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE = "3846afbcae14dda8d2f5656da3a08c8a46c1c94d"
EXPECTED_VERSION = "0.160.0-targets-load-memory"
EXPECTED_CID = "FE343253440000002000000055019CB7"
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-load-memory-0.160"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-load-memory-0.160.json"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "tools/check_targets_product_contract.py",
    "tools/check_targets_stack_elf_contract.py",
    "tools/run_1x_targets_hil.py",
    "tools/retain_1x_targets_load_memory_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    run_dir = args.run.resolve()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        candidate = run["candidate"]
        targets = run["targets"]
        listed = targets["list"]
        compared = targets["compare"]
        detail = targets["detail"]
        released = targets["released"]
        final = run["cleanup"]["final_state"]
        require(run["schema"] == "leshy.targets_product_hil.run.v1" and
                run["status"] == "pass", "passing Targets run required")
        require(run["source_commit"] == EXPECTED_SOURCE,
                "exact source mismatch")
        require(candidate["version"] == EXPECTED_VERSION and
                run["exact_cid"] == EXPECTED_CID,
                "candidate identity mismatch")
        require(digest(run_dir / "firmware.bin") ==
                candidate["firmware_sha256"], "firmware hash mismatch")
        require(run["flash_count"] == 0 and
                run["survey_cycles_executed"] == 0 and
                run["survey_generations"] == [160, 161] and
                run["radio_tx_commands"] == 0,
                "focused zero-flash/no-scan contract mismatch")
        require(listed["status"] == "ready" and
                listed["workspace_allocated"] is True and
                listed["view"] == "list" and
                listed["target_count"] == 7 and
                listed["catalog_count"] == 16 and
                listed["baseline_generation"] == 160 and
                listed["current_generation"] == 161 and
                listed["heap_free_before"] == 67436 and
                listed["heap_free_now"] >= 40000 and
                listed["blocked_write_attempts"] == 0 and
                listed["lease_mask"] == 13,
                "post-Survey Targets load mismatch")
        require(compared["view"] == "compare" and
                sum(int(compared[key]) for key in
                    ("added", "removed", "changed", "unchanged")) == 7,
                "comparison classification mismatch")
        require(detail["view"] == "detail" and
                detail["selected_target_present"] is True and
                detail["lease_mask"] == 13,
                "detail drilldown mismatch")
        require(released["status"] == "not_loaded" and
                released["lease_mask"] == 0 and
                released["heap_free_after_release"] >=
                released["heap_free_before"] - 512,
                "Targets heap/lease release mismatch")
        require(run["cleanup"]["complete"] is True and
                final["page"] == "home" and
                final["runtime_owner"] == "none" and
                final["lease_mask"] == 0,
                "terminal cleanup mismatch")
        require(run["safe_outputs"]["buzzer_inactive"] is True and
                run["safe_outputs"]["nrf_ce_inactive"] is True and
                run["safe_outputs"]["software_quiesce_complete"] is True,
                "safe outputs mismatch")
        require(run["input"]["read_errors"] == 0 and
                run["input"]["queue_drops"] == 0 and
                run["input"]["ambiguous_presses"] == 0,
                "input integrity mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_dir / "run.json", args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for name in ("targets-list", "targets-compare", "targets-detail"):
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{name}{suffix}",
                            frames / f"{name}{suffix}")
    provenance = {
        "schema": "leshy.targets_load_memory_hil.provenance.v1",
        "source_commit": EXPECTED_SOURCE,
        "candidate": candidate,
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256": digest(run_dir / "artifacts.sha256"),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)
    summary = {
        "schema": "leshy.targets_load_memory_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-115", "E-HIL-175"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "source_commit": EXPECTED_SOURCE,
        "candidate": candidate,
        "exact_cid": EXPECTED_CID,
        "session_generations": [160, 161],
        "flash_count": 0,
        "survey_cycles_executed": 0,
        "targets": {
            "visible": listed["target_count"],
            "catalog": listed["catalog_count"],
            "classification": {key: compared[key] for key in
                               ("added", "removed", "changed", "unchanged")},
            "heap_free_before": listed["heap_free_before"],
            "heap_free_loaded": listed["heap_free_now"],
            "heap_free_after_release": released["heap_free_after_release"],
            "load_elapsed_us": listed["load_elapsed_us"],
            "load_watchdog_feeds": listed["load_watchdog_feeds"],
            "load_maximum_phase_us": listed["load_maximum_phase_us"],
            "blocked_write_attempts": listed["blocked_write_attempts"],
        },
        "safe_outputs": {key: run["safe_outputs"][key] for key in
                         ("buzzer_inactive", "nrf_ce_inactive",
                          "software_quiesce_complete")},
        "input": {key: run["input"][key] for key in
                  ("status", "read_errors", "queue_drops",
                   "ambiguous_presses")},
        "final": {key: final[key] for key in
                  ("page", "runtime_owner", "lease_mask",
                   "library_generation")},
        "radio_tx_commands": 0,
        "screens": {
            name: {
                "png": f"frames/{name}.png",
                "png_sha256": digest(frames / f"{name}.png"),
            } for name in ("targets-list", "targets-compare", "targets-detail")
        },
        "raw_run_sha256": provenance["raw_run_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(json.dumps({"schema": summary["schema"], "status": "pass",
                      "summary": str(args.summary.relative_to(ROOT))},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
