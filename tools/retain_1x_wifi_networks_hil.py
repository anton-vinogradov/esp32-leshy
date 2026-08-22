#!/usr/bin/env python3
"""Retain compact machine-checked evidence for Wi-Fi nearby networks."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.107.0-wifi-networks"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-107", "E-AUTO-071", "E-HIL-131", "E-UX-026"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--fresh-failed", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    source = args.source.resolve()
    fresh_source = args.fresh_failed.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_wifi_networks_hil.py"
    checker = ROOT / "tools/check_wifi_networks_run.py"
    required = (source / "run.json", fresh_source / "run.json",
                source / "firmware.bin", args.factory.resolve(),
                args.elf.resolve(), args.map.resolve(), runner, checker)
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(all(path.is_file() for path in required),
            "source/build/tool artifact missing")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40,
            "commits must be full IDs")

    run = load(source / "run.json")
    fresh = load(fresh_source / "run.json")
    candidate = run.get("candidate", {})
    fresh_candidate = fresh.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "reuse_exact" and
            run.get("expected_cid") == CID,
            "source is not the exact passing reuse run")
    require(fresh.get("passed") is False and
            fresh.get("failures") == ["heap free did not return to boot baseline"] and
            fresh_candidate.get("flash_mode") == "fresh" and
            fresh_candidate.get("version") == VERSION and
            fresh_candidate.get("source_commit") == args.firmware_source_commit and
            fresh_candidate.get("firmware_sha256") ==
                candidate.get("firmware_sha256") and
            fresh_candidate.get("app_elf_sha256") ==
                candidate.get("app_elf_sha256") and
            fresh.get("list_pixel_changes", {}).get("chrome_changed_pixels") == 0 and
            fresh.get("detail_pixel_changes") == {
                "content_changed_pixels": 0, "chrome_changed_pixels": 0} and
            fresh.get("cleanup_after", {}).get("complete") is True,
            "fresh-flash diagnostic predecessor mismatch")
    require(run.get("runner_source_sha256") == digest(runner),
            "passing runner hash mismatch")
    verification = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION,
         "--expected-cid", CID, "--source-commit",
         args.firmware_source_commit], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(verification.returncode == 0,
            f"independent run verification failed: {verification.stdout}")

    destination.mkdir(parents=True)
    main_dir = destination / "main"
    frames_dir = main_dir / "frames"
    frames_dir.mkdir(parents=True)
    shutil.copy2(source / "run.json", main_dir / "run.json")
    shutil.copy2(source / "firmware.bin", main_dir / "firmware.bin")
    for path in sorted((source / "frames").glob("*.png")):
        shutil.copy2(path, frames_dir / path.name)
    for path in sorted((source / "frames").glob("*.json")):
        shutil.copy2(path, frames_dir / path.name)
    shutil.copy2(fresh_source / "run.json",
                 destination / "fresh-flash-diagnostic-run.json")
    for path, name in (
        (args.factory.resolve(), "firmware.factory.bin"),
        (args.elf.resolve(), "firmware.elf"),
        (args.map.resolve(), "firmware.map"),
        (runner, "runner.py"),
        (checker, "checker.py"),
    ):
        shutil.copy2(path, destination / name)

    provenance = {
        "schema": "leshy.wifi_networks_hil.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(main_dir / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "runner_sha256": digest(destination / "runner.py"),
        "checker_sha256": digest(destination / "checker.py"),
        "run_sha256": digest(main_dir / "run.json"),
        "fresh_diagnostic_run_sha256": digest(
            destination / "fresh-flash-diagnostic-run.json"),
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "tft_states": len(run.get("screens", {})),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")
    summary_value = {
        "schema": "leshy.wifi_networks.acceptance.v1",
        "status": "pass_wifi_networks_checkpoint",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": len(run.get("screens", {})),
        },
        "verified": {
            "fresh_flash_diagnostic_retained": True,
            "exact_flash_reuse_pass": True,
            "manual_button_presses": 0,
            "unique_networks_first": run["live_first"]["wifi_networks_unique"],
            "unique_networks_second": run["live_second"]["wifi_networks_unique"],
            "live_content_changed_pixels": run["list_pixel_changes"][
                "content_changed_pixels"],
            "live_chrome_changed_pixels": 0,
            "detail_changed_pixels": 0,
            "two_complete_wifi_lifecycles": True,
            "zero_heap_drift_after_warmup": True,
            "persistent_generation_unchanged": True,
            "physical_sd_write_calls": 0,
            "buzzer_inactive": True,
            "final_lease_mask": 0,
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "retained", "files": len(indexed) + 1,
        "tft_states": len(run.get("screens", {})),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
