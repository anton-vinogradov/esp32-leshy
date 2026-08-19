#!/usr/bin/env python3
"""Canonicalize the exact receiver-paced one-pixel waterfall HIL run."""

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
VERSION = "0.99.0-wifi-spectrum-modes"
EVIDENCE_IDS = [
    "E-BUILD-100", "E-AUTO-064", "E-HIL-124", "E-UX-023",
    "E-RADIO-010",
]
WATERFALL_REPORTS = (
    ("nrf_signal", "nrf_waterfall"),
    ("nrf_traffic", "nrf_traffic"),
    ("cc315", "cc_fill_315"),
    ("cc433", "cc_waterfall"),
    ("cc868", "cc_fill_868"),
    ("cc915", "cc_fill_915"),
)


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
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_product_home_hil.py"
    checker = ROOT / "tools/check_product_home_run.py"
    gate = ROOT / "tools/verify_connected_candidate.sh"
    required = (source / "run.json", source / "firmware.bin", runner, checker, gate)
    if not source.is_dir() or destination.exists() or summary.exists() or \
            not all(path.is_file() for path in required):
        parser.error("source/artifacts must exist and outputs must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be a full 40-character ID")

    run = load(source / "run.json")
    firmware = source / "firmware.bin"
    candidate = run.get("candidate", {})
    if run.get("passed") is not True or run.get("gate_eligible") is not True or \
            run.get("failures") != [] or candidate.get("version") != VERSION or \
            candidate.get("source_commit") != args.source_commit or \
            candidate.get("firmware_sha256") != digest(firmware) or \
            candidate.get("app_elf_sha256") != app_elf_sha256(firmware) or \
            run.get("runner_source_sha256") != digest(runner):
        parser.error("source is not the exact passing receiver-paced run")

    verification = subprocess.run(
        [str(checker), "--run", str(source), "--expected-version", VERSION,
         "--expected-cid", str(run.get("expected_cid", "")),
         "--source-commit", args.source_commit],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    if verification.returncode != 0:
        parser.error(f"independent source verification failed: {verification.stdout}")

    reports = run["reports"]
    for label, key in WATERFALL_REPORTS:
        report = reports[key]
        if report.get("waterfall_cadence") != "receiver_sweep" or \
                report.get("history_rows") != 224 or \
                report.get("waterfall_full") is not True or \
                report.get("waterfall_measurements_consumed") != \
                report.get("waterfall_source_sweeps") or \
                report.get("waterfall_measurements_skipped") != 0:
            parser.error(f"{label} is not exact one-sweep-per-pixel evidence")

    shutil.copytree(source, destination)
    for path, name in (
        (runner, "runner.py"),
        (checker, "checker.py"),
        (gate, "connected-candidate-gate.sh"),
    ):
        shutil.copy2(path, destination / name)
    manifest = destination / "artifacts.sha256"
    if manifest.exists():
        manifest.unlink()

    provenance = {
        "schema": "leshy.receiver_paced_waterfall.provenance.v1",
        "version": VERSION,
        "source_commit": args.source_commit,
        "firmware_sha256": digest(destination / "firmware.bin"),
        "app_elf_sha256": app_elf_sha256(destination / "firmware.bin"),
        "runner_sha256": digest(destination / "runner.py"),
        "checker_sha256": digest(destination / "checker.py"),
        "gate_sha256": digest(destination / "connected-candidate-gate.sh"),
        "firmware_bytes": (destination / "firmware.bin").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "run_sha256": digest(destination / "run.json"),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    timings = {
        label: {
            "device_us": reports[key]["waterfall_fill_elapsed_us"],
            "host_ms": reports[key]["host_fill_elapsed_ms"],
            "measurements": reports[key]["waterfall_measurements_consumed"],
            "skipped": reports[key]["waterfall_measurements_skipped"],
        }
        for label, key in WATERFALL_REPORTS
    }
    wires = {
        label: reports[key]["wire"] for label, key in WATERFALL_REPORTS
    }
    evidence = {
        "files": len(indexed) + 1,
        "artifact_index_sha256": digest(manifest),
        "provenance_sha256": digest(destination / "provenance.json"),
        "run_sha256": digest(destination / "run.json"),
        "tft_states": len(run["screens"]),
    }
    result = {
        "schema": "leshy.receiver_paced_waterfall_acceptance.v1",
        "status": "pass_receiver_paced_waterfall_checkpoint",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": evidence,
        "verified": {
            "cadence": "one_complete_receiver_sweep_per_physical_row",
            "physical_row_height_px": 1,
            "history_rows": 224,
            "graph_width_px": 240,
            "nrf_source_bins": 83,
            "cc_source_bins": 64,
            "horizontal_interpolation": False,
            "nrf_metrics": ["signal", "traffic"],
            "nrf_modules": 3,
            "nrf_active_slot_mask": 7,
            "all_available_nrf_antennas": True,
            "waterfall_timings": timings,
            "wire": wires,
            "waterfall_pixel_changes": run["waterfall_pixel_changes"],
            "diagnostic_heap_stabilized": run["boot_metrics_stabilized"],
            "heap": [run["boot"]["heap_total"], run["boot"]["heap_free"],
                     run["boot"]["heap_min_free"]],
            "storage_generation": run["recovery_before"]["generation"],
            "storage_observations": run["recovery_before"]["observations"],
            "software_rx_only": True,
            "physical_rf_silence_measured": False,
            "manual_button_presses": 0,
            "automatic_screenshots": True,
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
