#!/usr/bin/env python3
"""Retain privacy-minimal machine-checked dev.328 Home/Lab evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from check_home_lab_run import analyze


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.328"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "8b8ff984c8c881d13ca95abbbbb43f634747ffec"
SOURCE_FILES = {
    "catalog": "firmware/leshy1/src/domain/apps/AppCatalog.cpp",
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "checker": "tools/check_home_lab_run.py",
    "runner": "tools/run_1x_top_level_menu_smoke_hil.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--home-png", required=True, type=Path)
    parser.add_argument("--home-trace", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    required = (args.run / "run.json", args.home_png, args.home_trace,
                args.firmware, args.factory, args.elf, args.map,
                *(ROOT / path for path in SOURCE_FILES.values()))
    if not all(path.is_file() for path in required):
        raise ValueError("run, build, screenshot, or source artifact missing")
    if args.destination.exists():
        raise ValueError("destination already exists")
    checked = analyze(args.run, args.home_png, args.home_trace,
                      version=VERSION, cid=CID, source_commit=SOURCE_COMMIT)
    if checked["firmware_sha256"] != digest(args.firmware):
        raise ValueError("firmware hash mismatch")

    retained_dir = args.destination.with_suffix("")
    retained_dir.mkdir(parents=True, exist_ok=True)
    retained_png = retained_dir / "home-lab-selected.png"
    shutil.copyfile(args.home_png, retained_png)
    evidence = {
        "schema": "leshy.home_lab.acceptance.v1",
        "status": "pass",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": [
            "E-BUILD-214", "E-AUTO-189", "E-HIL-222", "E-UX-073",
            "RB-M225",
        ],
        "candidate": {
            "version": VERSION,
            "source_commit": SOURCE_COMMIT,
            "firmware_sha256": digest(args.firmware),
            "factory_sha256": digest(args.factory),
            "elf_sha256": digest(args.elf),
            "map_sha256": digest(args.map),
            "firmware_bytes": args.firmware.stat().st_size,
            "factory_bytes": args.factory.stat().st_size,
            "static_ram_bytes": args.static_ram_bytes,
            "linked_flash_bytes": args.linked_flash_bytes,
            "ota_free_bytes": 4194304 - args.firmware.stat().st_size,
        },
        "automation": {
            **checked,
            "manual_button_presses": 0,
            "flash_count": 1,
            "source_sha256": {
                label: digest(ROOT / path)
                for label, path in SOURCE_FILES.items()
            },
        },
        "verified": {
            "direct_home_lab_entry": True,
            "lab_danger_text_and_color": True,
            "independent_selection_focus": True,
            "stable_lab_owner_and_lease": True,
            "clean_home_return": True,
            "input_read_errors": 0,
            "input_queue_drops": 0,
            "buzzer_inactive": True,
            "nrf_ce_inactive": True,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "retained": {
            "home_png": str(retained_png.resolve().relative_to(ROOT)),
            "home_png_sha256": digest(retained_png),
            "ambient_identifiers": False,
            "raw_run": False,
        },
        "scope": {
            "accepts": [
                "task-first Home wording and stable route identities",
                "direct red controlled-zone Lab entry",
                "focused Home to Lab to Home lifecycle",
            ],
            "does_not_accept": [
                "Lab execution or RF transmit",
                "full top-level menu matrix",
                "periodic full HIL matrix",
            ],
            "focused_cadence": "8/15",
        },
    }
    args.destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
