#!/usr/bin/env python3
"""Retain exact 0.92 nRF24/CC1101 spectrum-view HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.92.0-spectrum-views"
CID = "FE343253440000002000000055019CB7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rewrite_paths(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: rewrite_paths(item, old, new)
                for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_paths(item, old, new) for item in value]
    if isinstance(value, str) and value.startswith(old):
        return new + value[len(old):]
    return value


def canonicalize(directory: Path, old: str, new: str) -> None:
    for path in sorted(directory.rglob("*.json")):
        write(path, rewrite_paths(load(path), old, new))


def passing_run(run: dict[str, Any], source_commit: str,
                firmware_hash: str, app_identity: str,
                runner_hash: str) -> bool:
    candidate = run.get("candidate", {})
    final = run.get("cleanup_after", {}).get("final_state", {})
    return (
        run.get("passed") is True and run.get("gate_eligible") is True and
        run.get("failures") == [] and run.get("expected_cid") == CID and
        run.get("runner_source_sha256") == runner_hash and
        candidate == {
            "version": VERSION,
            "source_commit": source_commit,
            "firmware_sha256": firmware_hash,
            "app_elf_sha256": app_identity,
            "flashed": True,
        } and run.get("cleanup_after", {}).get("complete") is True and
        [final.get("page"), final.get("runtime_owner"),
         final.get("lease_mask")] == ["home", "none", 0]
    )


def zero_continuity(run: dict[str, Any]) -> bool:
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    boot = run.get("boot", {})
    final = run.get("metrics_after", {})
    input_state = run.get("input", {})
    return (
        [before.get("generation"), before.get("observations")] == [95, 0] and
        [after.get("generation"), after.get("observations")] == [95, 0] and
        before.get("physical_write_calls") ==
            after.get("physical_write_calls") == 0 and
        [boot.get("heap_total"), boot.get("heap_free"),
         boot.get("heap_min_free")] ==
        [final.get("heap_total"), final.get("heap_free"),
         final.get("heap_min_free")] == [221876, 156916, 137564] and
        input_state.get("read_errors") == 0 and
        input_state.get("queue_drops") == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nrf-source", required=True, type=Path)
    parser.add_argument("--cc-source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    nrf_source = args.nrf_source.resolve()
    cc_source = args.cc_source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    firmware = args.firmware.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    nrf_runner = ROOT / "tools/run_1x_nrf24_spectrum_hil.py"
    cc_runner = ROOT / "tools/run_1x_cc1101_spectrum_hil.py"
    required = (firmware, factory, elf, nrf_runner, cc_runner)
    if not nrf_source.is_dir() or not cc_source.is_dir() or \
            destination.exists() or summary.exists() or \
            not all(path.is_file() for path in required):
        parser.error("sources/artifacts must exist and outputs must not exist")
    if len(args.source_commit) != 40 or len(args.runner_commit) != 40:
        parser.error("commits must be full 40-character IDs")

    nrf = load(nrf_source / "run.json")
    cc = load(cc_source / "run.json")
    firmware_hash = digest(firmware)
    app_identity = app_elf_sha256(firmware)
    nrf_runner_hash = digest(nrf_runner)
    cc_runner_hash = digest(cc_runner)
    if not passing_run(nrf, args.source_commit, firmware_hash, app_identity,
                       nrf_runner_hash):
        parser.error("nRF24 source is not an exact passing run")
    if not passing_run(cc, args.source_commit, firmware_hash, app_identity,
                       cc_runner_hash):
        parser.error("CC1101 source is not an exact passing run")
    if not zero_continuity(nrf) or not zero_continuity(cc):
        parser.error("heap/storage/input continuity differs")

    nrf_reports = nrf.get("reports", {})
    cc_reports = cc.get("reports", {})
    nrf_zero = {"cc_command_strobes": 0, "storage_writes": 0,
                "tx_mode_entries": 0, "tx_payload_commands": 0}
    cc_zero = {"fifo_writes": 0, "pa_table_writes": 0,
               "rejected_strobes": 0, "storage_writes": 0,
               "tx_strobes": 0}
    if nrf_reports.get("waterfall", {}).get("history_rows", 0) < 32 or \
            nrf_reports.get("waterfall", {}).get("display_mode") != "waterfall" or \
            nrf_reports.get("paused_before", {}).get("sweeps") != \
            nrf_reports.get("paused_after", {}).get("sweeps") or \
            not all(report.get("side_effects") == nrf_zero
                    for report in nrf_reports.values()):
        parser.error("nRF24 lifecycle/history/side-effect contract differs")
    bands = {cc_reports.get(f"band_{band}", {}).get("band")
             for band in ("315", "433", "868", "915")}
    if bands != {"315", "433", "868", "915"} or \
            cc_reports.get("waterfall_433", {}).get("history_rows", 0) < 16 or \
            cc_reports.get("waterfall_433", {}).get("display_mode") != "waterfall" or \
            cc_reports.get("paused_before", {}).get("adapter_samples") != \
            cc_reports.get("paused_after", {}).get("adapter_samples") or \
            not all(report.get("side_effects") == cc_zero
                    for report in cc_reports.values()):
        parser.error("CC1101 bands/lifecycle/history/side-effect contract differs")

    destination.mkdir(parents=True)
    nrf_destination = destination / "nrf24"
    cc_destination = destination / "cc1101"
    shutil.copytree(nrf_source, nrf_destination)
    shutil.copytree(cc_source, cc_destination)
    canonicalize(nrf_destination, str(nrf_source.relative_to(ROOT)),
                 str(nrf_destination.relative_to(ROOT)))
    canonicalize(cc_destination, str(cc_source.relative_to(ROOT)),
                 str(cc_destination.relative_to(ROOT)))
    for source, name in (
        (firmware, "firmware.bin"),
        (factory, "firmware.factory.bin"),
        (elf, "firmware.elf"),
        (nrf_runner, "nrf24-spectrum-runner.py"),
        (cc_runner, "cc1101-spectrum-runner.py"),
    ):
        shutil.copy2(source, destination / name)

    provenance = {
        "schema": "leshy.spectrum_views_hil.provenance.v1",
        "version": VERSION,
        "source_commit": args.source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": firmware_hash,
        "factory_sha256": digest(factory),
        "elf_file_sha256": digest(elf),
        "app_elf_sha256": app_identity,
        "nrf_runner_sha256": nrf_runner_hash,
        "cc_runner_sha256": cc_runner_hash,
        "firmware_bytes": firmware.stat().st_size,
        "factory_bytes": factory.stat().st_size,
        "elf_bytes": elf.stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "nrf_run_sha256": digest(nrf_destination / "run.json"),
        "cc_run_sha256": digest(cc_destination / "run.json"),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path != destination / "artifacts.sha256")
    index = "".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed)
    (destination / "artifacts.sha256").write_text(index, encoding="utf-8")

    evidence = {
        "files": len(indexed) + 1,
        "artifact_index_sha256": digest(destination / "artifacts.sha256"),
        "provenance_sha256": digest(destination / "provenance.json"),
        "nrf_run_sha256": digest(nrf_destination / "run.json"),
        "cc_run_sha256": digest(cc_destination / "run.json"),
        "nrf_tft_states": len(nrf.get("captures", {})),
        "cc_tft_states": len(cc.get("captures", {})),
    }
    result = {
        "schema": "leshy.spectrum_views_acceptance.v1",
        "status": "pass_spectrum_views_checkpoint",
        "board": "board-01",
        "evidence_ids": ["E-BUILD-093", "E-AUTO-057", "E-HIL-117",
                         "E-UX-016", "E-RADIO-005"],
        "candidate": provenance,
        "evidence": evidence,
        "verified": {
            "viewport": [0, 62, 240, 216],
            "footer_divider_y": 293,
            "nrf_history_rows": nrf_reports["waterfall"]["history_rows"],
            "cc_history_rows": cc_reports["waterfall_433"]["history_rows"],
            "cc_bands": sorted(bands),
            "storage_generation": 95,
            "storage_observations": 0,
            "heap": [221876, 156916, 137564],
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
