#!/usr/bin/env python3
"""Canonicalize the first physical Sub-GHz RAW receive-only checkpoint."""

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
VERSION = "0.102.0-subghz-raw-rx"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = [
    "E-BUILD-103", "E-AUTO-067", "E-HIL-127", "E-RADIO-012",
    "E-STORAGE-029",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--factory-sha256", required=True)
    parser.add_argument("--map-sha256", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_subghz_raw_hil.py"
    required = (source / "run.json", source / "firmware.bin", runner,
                args.factory.resolve())
    if not source.is_dir() or destination.exists() or summary.exists() or \
            not all(path.is_file() for path in required):
        parser.error("source/artifacts must exist and outputs must not exist")
    if len(args.source_commit) != 40 or len(args.runner_commit) != 40:
        parser.error("source and runner commits must be full IDs")
    if len(args.factory_sha256) != 64 or len(args.map_sha256) != 64:
        parser.error("factory/map hashes must be SHA-256 values")

    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    terminal = run.get("reports", {}).get("terminal", {})
    if run.get("passed") is not True or run.get("gate_eligible") is not False or \
            run.get("checkpoint") != "physical_receive_path" or \
            run.get("failures") != [] or run.get("expected_cid") != CID or \
            candidate.get("version") != VERSION or \
            candidate.get("source_commit") != args.source_commit or \
            candidate.get("flashed") is not False or \
            candidate.get("exact_flash_reused") is not True or \
            candidate.get("firmware_sha256") != digest(source / "firmware.bin") or \
            candidate.get("app_elf_sha256") != app_elf_sha256(
                source / "firmware.bin") or \
            run.get("runner_source_sha256") != digest(runner) or \
            terminal.get("state") != "timed_out" or \
            terminal.get("samples", 0) < 100_000:
        parser.error("source is not the exact passing no-signal checkpoint")
    runner_blob = git_blob(
        args.runner_commit, "tools/run_1x_subghz_raw_hil.py")
    if hashlib.sha256(runner_blob).hexdigest() != digest(runner):
        parser.error("runner commit does not bind the executed runner")
    if digest(args.factory.resolve()) != args.factory_sha256:
        parser.error("factory image hash mismatch")

    shutil.copytree(source, destination)
    shutil.copy2(runner, destination / "runner.py")
    shutil.copy2(args.factory.resolve(), destination / "firmware.factory.bin")
    manifest = destination / "artifacts.sha256"
    if manifest.exists():
        manifest.unlink()

    provenance = {
        "schema": "leshy.subghz_raw.provenance.v1",
        "version": VERSION,
        "source_commit": args.source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(destination / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "app_elf_sha256": app_elf_sha256(destination / "firmware.bin"),
        "map_sha256": args.map_sha256,
        "runner_sha256": digest(destination / "runner.py"),
        "run_sha256": digest(destination / "run.json"),
        "firmware_bytes": (destination / "firmware.bin").stat().st_size,
        "factory_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    recovery = run["recovery_before"]
    frames = run["captures"]
    result = {
        "schema": "leshy.subghz_raw_acceptance.v1",
        "status": "pass_physical_receive_no_signal_checkpoint",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "files": len(indexed) + 1,
            "artifact_index_sha256": digest(manifest),
            "provenance_sha256": digest(destination / "provenance.json"),
            "run_sha256": digest(destination / "run.json"),
            "tft_states": len(frames),
        },
        "verified": {
            "checkpoint": "physical_receive_path",
            "frequency_khz": terminal["frequency_khz"],
            "modulation": terminal["modulation"],
            "terminal_state": terminal["state"],
            "physical_rssi_samples": terminal["samples"],
            "wait_elapsed_us": terminal["ended_us"] - terminal["started_us"],
            "application_tx_calls": terminal["application_tx_calls"],
            "tx_strobes": terminal["tx_strobes"],
            "pa_table_writes": terminal["pa_table_writes"],
            "fifo_writes": terminal["fifo_writes"],
            "storage_generation": recovery["generation"],
            "storage_observations": recovery["observations"],
            "storage_physical_write_calls": recovery["physical_write_calls"],
            "heap": [run["boot"]["heap_total"], run["boot"]["heap_free"],
                     run["boot"]["heap_min_free"]],
            "input_read_errors": run["input"]["read_errors"],
            "input_queue_drops": run["input"]["queue_drops"],
            "buzzer_inactive": run["safe_outputs"]["buzzer_inactive"],
            "automatic_screenshots": True,
            "manual_button_presses": 0,
            "final_owner": run["reports"]["final"]["runtime_owner"],
            "final_lease_mask": run["reports"]["final"]["lease_mask"],
        },
        "coverage": {
            "physical_receive_and_no_signal_timeout": True,
            "host_capture_codec_store_csv": True,
            "physical_known_transmitter_used": False,
            "physical_successful_burst": False,
            "physical_persistence_and_library_export": False,
            "raw_rf_payload_retained": False,
            "tx_or_replay_in_scope": False,
            "cap_030_complete": False,
        },
    }
    write(summary, result)
    print(json.dumps({
        "status": "retained", "summary": str(summary.relative_to(ROOT)),
        "destination": str(destination.relative_to(ROOT)),
        **result["evidence"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
