#!/usr/bin/env python3
"""Retain machine-checked Sub-GHz frequency-finder evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.124.1-cc1101-frequency-finder"
FAILED_VERSION = "0.124.0-cc1101-frequency-finder"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-124", "E-AUTO-088", "E-HIL-148", "E-UX-043"]
SOURCE_FILES = {
    "finder_h": "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.h",
    "finder_cpp": "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.cpp",
    "adapter_h": "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.h",
    "adapter_cpp": "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp",
    "passive_h": "firmware/leshy1/src/drivers/radio/Cc1101PassiveSpectrum.h",
    "passive_cpp": "firmware/leshy1/src/drivers/radio/Cc1101PassiveSpectrum.cpp",
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "catalog": "firmware/leshy1/src/domain/apps/AppCatalog.cpp",
    "platform": "firmware/leshy1/platformio.ini",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "source_contract": "tools/check_cc1101_signal_finder_contract.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_quiet_reuse(run: dict, firmware_sha: str,
                       source_commit: str) -> None:
    candidate = run.get("candidate", {})
    advanced = run.get("advanced", {})
    require(run.get("schema") ==
                "leshy.cc1101_signal_finder_hil.run.v1" and
            run.get("failures") == [] and
            run.get("passed") is False and
            run.get("gate_eligible") is False and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == source_commit and
            candidate.get("firmware_sha256") == firmware_sha and
            candidate.get("flashed") is False and
            advanced.get("found") is False and
            advanced.get("frequency_khz") == 0 and
            advanced.get("response_db", 999) <
                advanced.get("response_threshold_db", 0) and
            run.get("cleanup_after", {}).get("complete") is True and
            run.get("cleanup_after", {}).get("final_state", {}).get(
                "lease_mask") == 0,
            "quiet reuse regression is not a clean non-gating pass")


def verify_failed_predecessor(run: dict, *, fresh: bool,
                              source_commit: str) -> None:
    candidate = run.get("candidate", {})
    advanced = run.get("advanced", {})
    require(candidate.get("version") == FAILED_VERSION and
            candidate.get("source_commit") == source_commit and
            candidate.get("flashed") is fresh and
            advanced.get("found") is True and
            advanced.get("frequency_khz", 0) > 0 and
            advanced.get("response_db", 0) >=
                advanced.get("response_threshold_db", 255),
            "failed predecessor does not retain the false-positive symptom")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--quiet-regression", required=True, type=Path)
    parser.add_argument("--failed-fresh", required=True, type=Path)
    parser.add_argument("--failed-reuse", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--failed-source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    source = args.source.resolve()
    quiet = args.quiet_regression.resolve()
    failed_fresh = args.failed_fresh.resolve()
    failed_reuse = args.failed_reuse.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_cc1101_signal_finder_hil.py"
    checker = ROOT / "tools/check_cc1101_signal_finder_run.py"
    contract = ROOT / "tools/check_cc1101_signal_finder_contract.py"
    required = (
        source / "run.json", source / "firmware.bin",
        source / "artifacts.sha256", quiet / "run.json",
        failed_fresh / "run.json", failed_reuse / "run.json",
        args.factory.resolve(), args.elf.resolve(), args.map.resolve(),
        runner, checker, contract,
    )
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(all(path.is_file() for path in required),
            "required artifact missing")
    require(all(len(value) == 40 for value in (
        args.firmware_source_commit, args.failed_source_commit,
        args.runner_commit)), "commits must be full IDs")
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "fresh" and
            run.get("expected_cid") == CID,
            "source is not the exact fresh-flash pass")
    require(run.get("runner_source_sha256") == digest(runner),
            "runner hash mismatch")
    verify_quiet_reuse(load(quiet / "run.json"),
                       candidate["firmware_sha256"],
                       args.firmware_source_commit)
    failed_fresh_run = load(failed_fresh / "run.json")
    failed_reuse_run = load(failed_reuse / "run.json")
    verify_failed_predecessor(
        failed_fresh_run, fresh=True,
        source_commit=args.failed_source_commit)
    verify_failed_predecessor(
        failed_reuse_run, fresh=False,
        source_commit=args.failed_source_commit)
    verification = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", args.firmware_source_commit,
         "--require-ambient-below-threshold"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    require(verification.returncode == 0,
            f"run verification failed: {verification.stdout}")
    source_check = subprocess.run(
        [sys.executable, str(contract)], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(source_check.returncode == 0,
            f"source contract failed: {source_check.stdout}")

    destination.mkdir(parents=True)
    shutil.copytree(source, destination / "run")
    shutil.copytree(quiet, destination / "quiet-regression")
    predecessor = destination / "failed-predecessor"
    predecessor.mkdir()
    shutil.copytree(failed_fresh, predecessor / "fresh")
    shutil.copytree(failed_reuse, predecessor / "reuse")
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    for tool in (runner, checker, contract):
        shutil.copy2(tool, tools_dir / tool.name)
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        original = ROOT / relative
        target = source_dir / Path(relative).name
        shutil.copy2(original, target)
        source_hashes[label] = digest(target)
    for path, name in (
        (args.factory.resolve(), "firmware.factory.bin"),
        (args.elf.resolve(), "firmware.elf"),
        (args.map.resolve(), "firmware.map"),
    ):
        shutil.copy2(path, destination / name)

    provenance = {
        "schema": "leshy.cc1101_signal_finder_hil.provenance.v1",
        "version": VERSION, "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "failed_source_commit": args.failed_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(destination / "run/firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "app_image_bytes":
            (destination / "run/firmware.bin").stat().st_size,
        "factory_image_bytes":
            (destination / "firmware.factory.bin").stat().st_size,
        "runner_sha256": digest(tools_dir / runner.name),
        "checker_sha256": digest(tools_dir / checker.name),
        "source_guard_sha256": digest(tools_dir / contract.name),
        "source_sha256": source_hashes,
        "run_sha256": digest(destination / "run/run.json"),
        "quiet_regression_run_sha256":
            digest(destination / "quiet-regression/run.json"),
        "failed_fresh_run_sha256":
            digest(destination / "failed-predecessor/fresh/run.json"),
        "failed_reuse_run_sha256":
            digest(destination / "failed-predecessor/reuse/run.json"),
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
    quiet_run = load(quiet / "run.json")
    summary_value = {
        "schema": "leshy.cc1101_signal_finder.acceptance.v1",
        "status": "pass_after_false_positive_regression",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": len(run.get("screens", {})),
        },
        "verified": {
            "bins": run["advanced"]["bins"],
            "step_khz": run["advanced"]["step_khz"],
            "calibration_passes": run["calibrated"]["calibration_passes"],
            "fresh_ambient_found": run["advanced"]["found"],
            "fresh_ambient_response_db": run["advanced"]["response_db"],
            "reuse_ambient_found": quiet_run["advanced"]["found"],
            "reuse_ambient_response_db":
                quiet_run["advanced"]["response_db"],
            "response_threshold_db":
                run["advanced"]["response_threshold_db"],
            "failed_fresh_frequency_khz":
                failed_fresh_run["advanced"]["frequency_khz"],
            "failed_fresh_response_db":
                failed_fresh_run["advanced"]["response_db"],
            "failed_reuse_frequency_khz":
                failed_reuse_run["advanced"]["frequency_khz"],
            "failed_reuse_response_db":
                failed_reuse_run["advanced"]["response_db"],
            "graph_changed_pixels":
                run["pixel_changes"]["graph_changed_pixels"],
            "static_changed_pixels": sum(
                run["pixel_changes"][name] for name in (
                    "header_changed_pixels", "legend_changed_pixels",
                    "axis_changed_pixels", "footer_changed_pixels")),
            "generation": run["recovery_after"]["generation"],
            "observations": run["recovery_after"]["observations"],
            "physical_write_calls":
                run["recovery_after"]["physical_write_calls"],
            "heap_free_after": run["metrics_after"]["heap_free"],
            "heap_min_after": run["metrics_after"]["heap_min_free"],
            "final_lease_mask":
                run["cleanup_after"]["final_state"]["lease_mask"],
        },
        "regression": {
            "failed_version": FAILED_VERSION,
            "symptom": "nonrepeatable ambient false frequency",
            "root_cause": "two-pass minimum biased the per-bin floor low",
            "fix": "three-pass median plus 26/40 MHz harmonic exclusion",
        },
        "limits": {
            "known_signal_physical_source": False,
            "found_branch": "deterministic native injection",
            "physical_rf_silence": False,
            "calibrated_power_or_distance": False,
            "ambient_environment": "one board and one location",
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "pass", "destination": str(destination),
        "summary": str(summary), "files": len(indexed) + 1,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
