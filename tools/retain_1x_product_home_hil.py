#!/usr/bin/env python3
"""Canonicalize a passing 0.93 one-command board gate into retained evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.93.0-product-menu"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    map_file = args.map.resolve()
    runner = ROOT / "tools/run_1x_product_home_hil.py"
    checker = ROOT / "tools/check_product_home_run.py"
    gate = ROOT / "tools/verify_connected_candidate.sh"
    required = (factory, elf, map_file, runner, checker, gate)
    if not source.is_dir() or destination.exists() or summary.exists() or \
            not all(path.is_file() for path in required):
        parser.error("source/artifacts must exist and outputs must not exist")
    if len(args.source_commit) != 40 or len(args.runner_commit) != 40:
        parser.error("commits must be full 40-character IDs")

    run = load(source / "run.json")
    firmware = source / "firmware.bin"
    candidate = run.get("candidate", {})
    if run.get("passed") is not True or run.get("gate_eligible") is not True or \
            run.get("failures") != [] or candidate.get("version") != VERSION or \
            candidate.get("source_commit") != args.source_commit or \
            candidate.get("firmware_sha256") != digest(firmware) or \
            candidate.get("app_elf_sha256") != app_elf_sha256(firmware) or \
            run.get("runner_source_sha256") != digest(runner):
        parser.error("source is not an exact passing product-Home run")

    verification = subprocess.run(
        [str(checker), "--run", str(source), "--expected-version", VERSION,
         "--expected-cid", str(run.get("expected_cid", "")),
         "--source-commit", args.source_commit],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    if verification.returncode != 0:
        parser.error(f"independent source verification failed: {verification.stdout}")

    shutil.copytree(source, destination)
    for path, name in (
        (factory, "firmware.factory.bin"),
        (elf, "firmware.elf"),
        (map_file, "firmware.map"),
        (runner, "runner.py"),
        (checker, "checker.py"),
        (gate, "connected-candidate-gate.sh"),
    ):
        shutil.copy2(path, destination / name)
    manifest = destination / "artifacts.sha256"
    if manifest.exists():
        manifest.unlink()

    provenance = {
        "schema": "leshy.product_home_hil.provenance.v1",
        "version": VERSION,
        "source_commit": args.source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(destination / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": app_elf_sha256(destination / "firmware.bin"),
        "runner_sha256": digest(destination / "runner.py"),
        "checker_sha256": digest(destination / "checker.py"),
        "gate_sha256": digest(destination / "connected-candidate-gate.sh"),
        "firmware_bytes": (destination / "firmware.bin").stat().st_size,
        "factory_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "elf_bytes": (destination / "firmware.elf").stat().st_size,
        "map_bytes": (destination / "firmware.map").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "run_sha256": digest(destination / "run.json"),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    before = run["recovery_before"]
    reports = run["reports"]
    evidence = {
        "files": len(indexed) + 1,
        "artifact_index_sha256": digest(manifest),
        "provenance_sha256": digest(destination / "provenance.json"),
        "run_sha256": digest(destination / "run.json"),
        "tft_states": len(run["screens"]),
    }
    result = {
        "schema": "leshy.product_home_acceptance.v1",
        "status": "pass_product_home_checkpoint",
        "board": "board-01",
        "evidence_ids": ["E-BUILD-094", "E-AUTO-058", "E-HIL-118",
                         "E-UX-017", "E-RADIO-006"],
        "candidate": provenance,
        "evidence": evidence,
        "verified": {
            "home_items": run["home_items"],
            "single_flash": True,
            "manual_button_presses": 0,
            "automatic_screenshots": True,
            "nrf_history_rows": reports["nrf_waterfall"]["history_rows"],
            "cc_history_rows": reports["cc_waterfall"]["history_rows"],
            "storage_generation": before["generation"],
            "storage_observations": before["observations"],
            "heap": [run["boot"]["heap_total"], run["boot"]["heap_free"],
                     run["boot"]["heap_min_free"]],
            "software_rx_only": True,
            "physical_rf_silence_measured": False,
            "final_owner": "none",
            "final_lease_mask": 0,
        },
    }
    write(summary, result)
    print(json.dumps({
        "status": "retained",
        "destination": str(destination.relative_to(ROOT)),
        "summary": str(summary.relative_to(ROOT)),
        **evidence,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
