#!/usr/bin/env python3
"""Validate and retain exact Bluetooth repaint HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.250"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "bfe646e4d9408b4cd0ec1dc58c7c4e9c38a4ac0d"
FIRMWARE_SHA256 = (
    "4c82162eab199532fba475df8341c520d43bce8bf4ab04bc31f930bf5f310bce")
APP_ELF_SHA256 = (
    "3c401f5b1a7ffb9e15298b6716506ec9475e7d4c980aa5adc0ddbd756d08b750")
FACTORY_SHA256 = (
    "0b6c24cdc3ac4a90e7e2725be18bb62ca6d9a30c5eabb5f490f112782006a923")
MAP_SHA256 = (
    "614a52bc07636efd0279ab4f100e7dfc78cd58c292a11de41c4a68cb05142e3f")
EVIDENCE_IDS = ["E-BUILD-178", "E-AUTO-152", "E-HIL-193", "E-UX-057"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    factory = args.factory.resolve()
    map_file = args.map.resolve()
    checker = ROOT / "tools/check_ble_nearby_run.py"
    source_guard = ROOT / "tools/check_ble_nearby_contract.py"
    runner = ROOT / "tools/run_1x_ble_nearby_hil.py"
    require(source.is_dir() and not source.is_symlink(),
            "regular source directory required")
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(destination.parent == summary.parent,
            "destination and summary must share a parent")
    for item in source.rglob("*"):
        require(not item.is_symlink(), f"symlink rejected: {item}")
    for required in (source / "run.json", source / "firmware.bin",
                     source / "artifacts.sha256", factory, map_file,
                     checker, source_guard, runner):
        require(required.is_file(), f"missing artifact: {required}")
    require(digest(source / "firmware.bin") == FIRMWARE_SHA256,
            "firmware hash mismatch")
    require(digest(factory) == FACTORY_SHA256, "factory hash mismatch")
    require(digest(map_file) == MAP_SHA256, "map hash mismatch")
    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.ble_nearby_hil.run.v2" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean HIL pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == APP_ELF_SHA256 and
            candidate.get("flashed") is True and
            candidate.get("flash_mode") in ("fresh", "reuse_exact") and
            run.get("expected_cid") == CID,
            "exact candidate binding mismatch")

    env = {"PYTHONPATH": str(ROOT / "tools")}
    for command in (
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT],
        [sys.executable, str(source_guard)],
    ):
        result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        require(result.returncode == 0, result.stdout.strip())

    first_list = run["list_render_first"]
    second_list = run["list_render_second"]
    first_detail = run["detail_oracle_first"]
    second_detail = run["detail_oracle_second"]
    final_state = run["cleanup_after"]["final_state"]
    row_delta = (second_list["list_row_repaints"] -
                 first_list["list_row_repaints"])
    delta_repaints = (second_detail["radar_delta_repaints"] -
                      first_detail["radar_delta_repaints"])
    require(row_delta == 2 and
            second_list["list_content_clears"] ==
            first_list["list_content_clears"],
            "expected exact bounded list repaint proof")
    require(delta_repaints == 1 and
            second_detail["radar_full_repaints"] ==
            first_detail["radar_full_repaints"] and
            second_detail["detail_content_clears"] ==
            first_detail["detail_content_clears"],
            "expected exact delta-only detail repaint proof")
    require(final_state["page"] == "home" and
            final_state["runtime_owner"] == "none" and
            final_state["lease_mask"] == 0,
            "final cleanup mismatch")

    parent = destination.parent
    staging = Path(tempfile.mkdtemp(prefix=".ble-repaint-retain-", dir=parent))
    staged_bundle = staging / destination.name
    staged_summary = staging / summary.name
    try:
        shutil.copytree(source, staged_bundle, copy_function=shutil.copy2)
        shutil.copy2(runner, staged_bundle / "runner.py")
        shutil.copy2(checker, staged_bundle / "checker.py")
        shutil.copy2(source_guard, staged_bundle / "source-guard.py")
        shutil.copy2(factory, staged_bundle / "firmware.factory.bin")
        shutil.copy2(map_file, staged_bundle / "firmware.map")
        indexed = sorted(path for path in staged_bundle.rglob("*")
                         if path.is_file() and
                         path.name != "artifacts.sha256")
        manifest = staged_bundle / "artifacts.sha256"
        manifest.write_text("".join(
            f"{digest(path)}  {path.relative_to(staged_bundle)}\n"
            for path in indexed), encoding="utf-8")
        summary_value = {
            "schema": "leshy.ble_repaint_hil.acceptance.v1",
            "status": "pass_bluetooth_bounded_repaint",
            "board": "board-01",
            "evidence_ids": EVIDENCE_IDS,
            "exact_cid": CID,
            "candidate": {
                "version": VERSION,
                "source_commit": SOURCE_COMMIT,
                "firmware_sha256": FIRMWARE_SHA256,
                "app_elf_sha256": APP_ELF_SHA256,
                "factory_sha256": FACTORY_SHA256,
                "map_sha256": MAP_SHA256,
            },
            "evidence": {
                "run_id": run["run_id"],
                "run_sha256": digest(staged_bundle / "run.json"),
                "artifact_index_sha256": digest(manifest),
                "runner_sha256": digest(staged_bundle / "runner.py"),
                "checker_sha256": digest(staged_bundle / "checker.py"),
                "source_guard_sha256": digest(
                    staged_bundle / "source-guard.py"),
            },
            "verified": {
                "list_changed_rows": row_delta,
                "list_visible_rows": 4,
                "list_content_changed_pixels":
                    run["list_pixel_changes"]["content_changed_pixels"],
                "list_chrome_changed_pixels": 0,
                "list_full_content_clears": 0,
                "detail_radar_changed_pixels":
                    run["detail_pixel_changes"]["radar_changed_pixels"],
                "detail_static_changed_pixels": 0,
                "detail_chrome_changed_pixels": 0,
                "detail_delta_repaints": delta_repaints,
                "detail_full_repaints": 0,
                "detail_full_content_clears": 0,
                "passive_only": True,
                "active_probe_allowed": False,
                "driver_scan_drops": 0,
                "manual_button_presses": 0,
                "final_page": "home",
                "final_runtime_owner": "none",
                "final_lease_mask": 0,
            },
        }
        write(staged_summary, summary_value)
        staged_bundle.replace(destination)
        staged_summary.replace(summary)
        shutil.rmtree(staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"status": "retained", "destination": str(destination),
                      "summary": str(summary)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
