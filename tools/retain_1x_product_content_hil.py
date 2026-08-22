#!/usr/bin/env python3
"""Retain compact physical evidence for outcome-first product screens."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.106.0-product-content"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-106", "E-AUTO-070", "E-HIL-130", "E-UX-025"]
RUNNERS = {
    "main": ROOT / "tools/run_1x_product_home_hil.py",
    "infrared": ROOT / "tools/run_1x_infrared_capture_hil.py",
    "subghz": ROOT / "tools/run_1x_subghz_raw_hil.py",
    "wifi_capture": ROOT / "tools/run_1x_wifi_frame_capture_hil.py",
}


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


def frames(run: dict[str, Any]) -> dict[str, Any]:
    value = run.get("screens", run.get("captures", {}))
    return value if isinstance(value, dict) else {}


def retain_run(label: str, source: Path,
               destination: Path) -> dict[str, Any]:
    run_file = source / "run.json"
    require(run_file.is_file(), f"{label}: run.json missing")
    run = load(run_file)
    target = destination / label
    (target / "frames").mkdir(parents=True)
    shutil.copy2(run_file, target / "run.json")
    pngs = sorted((source / "frames").glob("*.png"))
    require(len(pngs) == len(frames(run)), f"{label}: frame count mismatch")
    for png in pngs:
        shutil.copy2(png, target / "frames" / png.name)
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", required=True, type=Path)
    parser.add_argument("--infrared", required=True, type=Path)
    parser.add_argument("--subghz", required=True, type=Path)
    parser.add_argument("--wifi-capture", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--supplementary-source-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(len(args.firmware_source_commit) == 40 and
            len(args.supplementary_source_commit) == 40,
            "commits must be full IDs")
    destination.mkdir(parents=True)
    sources = {
        "main": args.main.resolve(),
        "infrared": args.infrared.resolve(),
        "subghz": args.subghz.resolve(),
        "wifi_capture": args.wifi_capture.resolve(),
    }
    runs = {label: retain_run(label, source, destination)
            for label, source in sources.items()}
    primary = runs["main"]
    candidate = primary.get("candidate", {})
    firmware_sha = candidate.get("firmware_sha256")
    app_sha = candidate.get("app_elf_sha256")
    require(primary.get("passed") is True and
            primary.get("gate_eligible") is True and
            primary.get("failures") == [] and
            primary.get("expected_cid") == CID and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flashed") is True and
            candidate.get("flash_mode") == "fresh",
            "main run is not the exact fresh flashed pass")
    verification = subprocess.run(
        [str(ROOT / "tools/check_product_home_run.py"), "--run",
         str(sources["main"]), "--expected-version", VERSION,
         "--expected-cid", CID, "--source-commit",
         args.firmware_source_commit], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(verification.returncode == 0,
            f"main verification failed: {verification.stdout}")
    for label in ("infrared", "subghz", "wifi_capture"):
        run = runs[label]
        current = run.get("candidate", {})
        require(run.get("passed") is True and run.get("failures") == [] and
                run.get("expected_cid") == CID and
                current.get("version") == VERSION and
                current.get("source_commit") ==
                    args.supplementary_source_commit and
                current.get("flashed") is False and
                current.get("exact_flash_reused") is True and
                current.get("firmware_sha256") == firmware_sha and
                current.get("app_elf_sha256") == app_sha,
                f"{label}: exact-flash binding mismatch")
    require(runs["infrared"]["reports"]["terminal"]["state"] == "timed_out",
            "infrared terminal mismatch")
    require(runs["subghz"]["reports"]["terminal"]["state"] == "timed_out",
            "Sub-GHz terminal mismatch")
    wifi = runs["wifi_capture"]
    require(wifi["privacy"]["visual_only"] is True and
            wifi["privacy"]["pcap_exported_to_host"] is False and
            wifi["complete"]["storage_written"] is False and
            wifi["scrubbed"]["state"] == "idle",
            "Wi-Fi privacy-safe run mismatch")

    tools_dir = destination / "tools"
    tools_dir.mkdir()
    tool_hashes: dict[str, str] = {}
    for label, runner in RUNNERS.items():
        require(runs[label].get("runner_source_sha256") == digest(runner),
                f"{label}: runner hash mismatch")
        shutil.copy2(runner, tools_dir / runner.name)
        tool_hashes[runner.name] = digest(tools_dir / runner.name)
    checker = ROOT / "tools/check_product_home_run.py"
    shutil.copy2(checker, tools_dir / checker.name)
    tool_hashes[checker.name] = digest(tools_dir / checker.name)
    frame_counts = {label: len(frames(run)) for label, run in runs.items()}
    require(sum(frame_counts.values()) == 37, "expected 37 TFT states")
    provenance = {
        "schema": "leshy.product_content.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "supplementary_source_commit": args.supplementary_source_commit,
        "firmware_sha256": firmware_sha,
        "app_elf_sha256": app_sha,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "run_sha256": {label: digest(destination / label / "run.json")
                       for label in runs},
        "tool_sha256": tool_hashes,
        "tft_states": frame_counts,
    }
    write(destination / "provenance.json", provenance)
    retained = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in retained), encoding="utf-8")
    result = {
        "schema": "leshy.product_content.acceptance.v1",
        "status": "pass_outcome_first_product_content",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {"artifact_index_sha256": digest(manifest),
                     "files": len(retained) + 1, "tft_states": 37},
        "verified": {
            "developer_telemetry_on_product_screens": False,
            "exact_flash_reuse_runs": 3,
            "final_lease_mask": 0,
            "manual_button_presses": 0,
            "one_fresh_flash": True,
            "pcap_exported_to_host": False,
            "storage_written": False,
        },
    }
    write(summary, result)
    print(json.dumps({"status": "retained", "files": len(retained) + 1,
                      "tft_states": 37}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
