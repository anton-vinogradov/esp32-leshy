#!/usr/bin/env python3
"""Retain compact machine-checked evidence for Wi-Fi packet recording."""

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
VERSION = "0.110.0-wifi-capture"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = [
    "E-BUILD-110", "E-AUTO-074", "E-HIL-134", "E-UX-029",
    "E-CAPTURE-004",
]


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
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_wifi_capture_product_hil.py"
    checker = ROOT / "tools/check_wifi_capture_product_run.py"
    required = (source / "run.json", source / "firmware.bin",
                args.factory.resolve(), args.elf.resolve(), args.map.resolve(),
                runner, checker)
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(all(path.is_file() for path in required),
            "source/build/tool artifact missing")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40, "commits must be full IDs")

    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "fresh" and
            run.get("expected_cid") == CID,
            "source is not the exact fresh-flash passing run")
    require(run.get("runner_source_sha256") == digest(runner),
            "passing runner hash mismatch")
    verification = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", args.firmware_source_commit], cwd=ROOT, text=True,
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
    for path, name in (
        (args.factory.resolve(), "firmware.factory.bin"),
        (args.elf.resolve(), "firmware.elf"),
        (args.map.resolve(), "firmware.map"),
        (runner, "runner.py"), (checker, "checker.py"),
    ):
        shutil.copy2(path, destination / name)

    provenance = {
        "schema": "leshy.wifi_capture_product_hil.provenance.v1",
        "version": VERSION, "cid": CID,
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

    first = run["first"]
    second = run["second"]
    summary_value = {
        "schema": "leshy.wifi_capture_product.acceptance.v1",
        "status": "pass_wifi_capture_product_checkpoint",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": len(run.get("screens", {})),
        },
        "verified": {
            "fresh_exact_flash_pass": True,
            "manual_button_presses": 0,
            "first_frames_reported": first["complete"]["frames_reported"],
            "first_frames_retained": first["complete"]["frames_accepted"],
            "first_capacity_drops": first["complete"][
                "frames_dropped_capacity"],
            "second_frames_reported": second["complete"]["frames_reported"],
            "second_frames_retained": second["complete"]["frames_accepted"],
            "invalid_frames": 0,
            "first_pcap_records": first["pcap"]["summary"]["records"],
            "first_pcap_bytes": first["pcap"]["summary"]["bytes"],
            "second_pcap_records": second["pcap"]["summary"]["records"],
            "live_changed_pixels": first["pixel_changes"][
                "live_changed_pixels"],
            "static_changed_pixels": 0,
            "passive_receive_only": True,
            "bounded_ram_capture": True,
            "privacy_confirmation_and_cancel": True,
            "raw_payload_retained_in_repository": False,
            "two_complete_wifi_lifecycles": True,
            "zero_post_warm_heap_drift": True,
            "heap_minimum_floor_bytes": min(
                run["metrics_after_first"]["heap_min_free"],
                run["metrics_after_second"]["heap_min_free"]),
            "persistent_generation_unchanged": True,
            "physical_sd_write_calls": 0,
            "buzzer_inactive": True,
            "final_safety_latched": False,
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
