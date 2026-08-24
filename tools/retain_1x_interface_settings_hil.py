#!/usr/bin/env python3
"""Retain a compact, source-bound exact 0.145 Settings delta."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-interface-settings-0.145"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-interface-settings-0.145.json"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/ui/InterfaceSettingsController.cpp",
    "firmware/leshy1/src/ui/InterfaceSettingsController.h",
    "firmware/leshy1/src/ui/UiStrings.def",
    "firmware/leshy1/src/ui/VisualTheme.h",
    "tests/hil/delta-scopes/interface-settings-0.145.json",
    "tools/check_interface_settings_contract.py",
    "tools/run_1x_interface_settings_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    run_dir = args.run.resolve()
    run_path = run_dir / "run.json"
    if not run_path.is_file():
        parser.error("run.json is missing")
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("schema") != "leshy.interface_settings_hil.run.v1" or \
            run.get("status") != "pass":
        parser.error("only a passing interface-settings run can be retained")
    firmware = run_dir / "firmware.bin"
    if not firmware.is_file() or digest(firmware) != run["candidate"]["firmware_sha256"]:
        parser.error("candidate firmware hash mismatch")

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_path, args.bundle / "run.json")
    for name in ("persistence-reset.json", "persistence-reset.ndjson",
                 "restore-reset.json", "restore-reset.ndjson"):
        shutil.copyfile(run_dir / name, args.bundle / name)
    frames = args.bundle / "frames"
    frames.mkdir()
    for name in ("settings-initial", "settings-changed", "home-restored"):
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{name}{suffix}",
                            frames / f"{name}{suffix}")

    source_hashes = {path: digest(ROOT / path) for path in SOURCE_PATHS}
    provenance = {
        "schema": "leshy.interface_settings_hil.provenance.v1",
        "source_commit": run["source_commit"],
        "candidate": run["candidate"],
        "source_sha256": source_hashes,
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
    }
    write_json(args.bundle / "provenance.json", provenance)

    manifest: dict[str, str] = {}
    for path in sorted(args.bundle.rglob("*")):
        if path.is_file():
            manifest[str(path.relative_to(args.bundle))] = digest(path)
    write_json(args.bundle / "manifest.json", manifest)
    summary = {
        "schema": "leshy.interface_settings_hil.summary.v1",
        "status": "pass",
        "evidence_id": "E-HIL-163",
        "source_commit": run["source_commit"],
        "candidate": run["candidate"],
        "initial": run["initial"],
        "persisted": run["persisted"],
        "final": run["final"],
        "safe_outputs": {
            key: run["safe_outputs"][key] for key in (
                "buzzer_inactive", "buzzer_level", "nrf_ce_inactive",
                "software_quiesce_complete")
        },
        "input": {key: run["input"][key] for key in (
            "status", "read_errors", "queue_drops")},
        "flash_count": run["flash_count"],
        "hardware_reset_count": run["hardware_reset_count"],
        "radio_tx_commands": run["radio_tx_commands"],
        "screens": {
            name: {
                "png": f"frames/{name.replace('_', '-')}.png",
                "png_sha256": run["screens"][name]["png_sha256"],
            } for name in run["screens"]
        },
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
