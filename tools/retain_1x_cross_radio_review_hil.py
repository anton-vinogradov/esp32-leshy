#!/usr/bin/env python3
"""Retain privacy-minimal machine-checked evidence closing FF-1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.328"
SOURCE_COMMIT = "8b8ff984c8c881d13ca95abbbbb43f634747ffec"
TARGET_SOURCE_COMMIT = "b8b0daed3ef30854b8b8e607609774f71a24384b"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-AUTO-190", "E-HIL-223", "E-UX-074", "RB-M226"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run_checker(checker: Path, run_dir: Path) -> str:
    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(run_dir),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT],
        cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"{checker.name} rejected source run: {checked.stdout}")
    return checked.stdout.strip()


def verify_current_run(run: dict[str, Any], label: str) -> None:
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], f"{label} is not a clean pass")
    require(run.get("expected_cid") == CID, f"{label} CID mismatch")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") ==
                "a069ce661f56add492ece0d9f33df0343cfe7da20092048f9b315582e1a268c0" and
            candidate.get("app_elf_sha256") ==
                "e0d2d5acf53fa65f804e7866cab7f6fb20e52abd27a0f9864c21b04ce60a8306",
            f"{label} exact candidate mismatch")
    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    require(first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free"),
            f"{label} heap plateau mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(before.get("generation") == after.get("generation") and
            before.get("observations") == after.get("observations") and
            after.get("physical_write_calls") == 0,
            f"{label} storage continuity mismatch")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(run.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            f"{label} terminal cleanup mismatch")
    require(run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0,
            f"{label} input error/drop mismatch")
    require(run.get("safe_outputs", {}).get("buzzer_inactive") is True,
            f"{label} buzzer safe state missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wifi-run", required=True, type=Path)
    parser.add_argument("--ble-run", required=True, type=Path)
    parser.add_argument("--target-evidence", required=True, type=Path)
    parser.add_argument("--home-evidence", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    wifi_dir = args.wifi_run.resolve()
    ble_dir = args.ble_run.resolve()
    wifi_path = wifi_dir / "run.json"
    ble_path = ble_dir / "run.json"
    wifi_manifest = wifi_dir / "artifacts.sha256"
    ble_manifest = ble_dir / "artifacts.sha256"
    wifi_checker = ROOT / "tools/check_wifi_devices_run.py"
    ble_checker = ROOT / "tools/check_ble_nearby_run.py"
    required = (wifi_path, ble_path, wifi_manifest, ble_manifest,
                wifi_checker, ble_checker, args.target_evidence,
                args.home_evidence)
    require(all(path.resolve().is_file() for path in required),
            "input run, manifest, checker, or retained evidence missing")
    require(not args.destination.exists(), "destination already exists")

    wifi = load(wifi_path)
    ble = load(ble_path)
    target = load(args.target_evidence)
    home = load(args.home_evidence)
    verify_current_run(wifi, "wifi")
    verify_current_run(ble, "ble")
    wifi_output = run_checker(wifi_checker, wifi_dir)
    ble_output = run_checker(ble_checker, ble_dir)

    require(target.get("schema") == "leshy.target_radar.acceptance.v1" and
            target.get("status") == "pass" and target.get("cid") == CID,
            "Targets Radar retained evidence mismatch")
    require(target.get("candidate", {}).get("version") ==
                "1.0.0-dev.327" and
            target.get("candidate", {}).get("firmware_source_commit") ==
                TARGET_SOURCE_COMMIT and
            target.get("verified", {}).get("four_complete_lifecycles") is True and
            target.get("verified", {}).get("identity_stable") is True and
            target.get("verified", {}).get("atomic_live_region_only") is True and
            target.get("verified", {}).get("radio_tx_commands") == 0 and
            target.get("verified", {}).get("active_probe_commands") == 0 and
            target.get("verified", {}).get("final_lease_mask") == 0,
            "Targets Radar acceptance contract mismatch")
    require(home.get("schema") == "leshy.home_lab.acceptance.v1" and
            home.get("status") == "pass" and home.get("cid") == CID and
            home.get("candidate", {}).get("version") == VERSION and
            home.get("candidate", {}).get("source_commit") == SOURCE_COMMIT and
            home.get("verified", {}).get("direct_home_lab_entry") is True and
            home.get("verified", {}).get("lab_danger_text_and_color") is True and
            home.get("verified", {}).get("final_lease_mask") == 0,
            "Home hierarchy acceptance contract mismatch")

    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", TARGET_SOURCE_COMMIT,
         SOURCE_COMMIT], cwd=ROOT, check=False)
    require(ancestry.returncode == 0,
            "Targets source is not an ancestor of the reviewed candidate")
    changed = subprocess.run(
        ["git", "diff", "--name-only",
         f"{TARGET_SOURCE_COMMIT}..{SOURCE_COMMIT}", "--",
         "firmware/leshy1/src"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(changed.returncode == 0, "unable to inspect source delta")
    changed_files = sorted(filter(None, changed.stdout.splitlines()))
    require(changed_files == [
        "firmware/leshy1/src/domain/apps/AppCatalog.cpp",
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
        "firmware/leshy1/src/ui/UiStrings.def",
    ], f"unexpected dev.327 to dev.328 source delta: {changed_files!r}")

    wifi_detail_first = wifi["detail_oracle_first"]
    wifi_detail_second = wifi["detail_oracle_second"]
    ble_detail_first = ble["detail_oracle_first"]
    ble_detail_second = ble["detail_oracle_second"]
    evidence = {
        "schema": "leshy.cross_radio_review.acceptance.v1",
        "status": "pass",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            "version": VERSION,
            "firmware_source_commit": SOURCE_COMMIT,
            "firmware_sha256": wifi["candidate"]["firmware_sha256"],
            "app_elf_sha256": wifi["candidate"]["app_elf_sha256"],
            "target_source_commit": TARGET_SOURCE_COMMIT,
            "target_source_is_ancestor": True,
            "target_to_current_firmware_files": changed_files,
        },
        "automation": {
            "wifi_run_sha256": digest(wifi_path),
            "wifi_manifest_sha256": digest(wifi_manifest),
            "wifi_runner_sha256": wifi["runner_source_sha256"],
            "wifi_checker_sha256": digest(wifi_checker),
            "wifi_checker_output": wifi_output,
            "ble_run_sha256": digest(ble_path),
            "ble_manifest_sha256": digest(ble_manifest),
            "ble_runner_sha256": ble["runner_source_sha256"],
            "ble_checker_sha256": digest(ble_checker),
            "ble_checker_output": ble_output,
            "target_evidence_sha256": digest(args.target_evidence),
            "home_evidence_sha256": digest(args.home_evidence),
            "manual_button_presses": 0,
            "additional_flash_count": 0,
            "composition_inputs": 4,
        },
        "verified": {
            "home_task_first": True,
            "lab_direct_controlled_entry": True,
            "wifi_unique_devices": wifi["live_second"]["wifi_devices_unique"],
            "wifi_strongest_first": True,
            "wifi_identity_stable":
                wifi_detail_first["identity_hash"] ==
                wifi_detail_second["identity_hash"],
            "wifi_signal_samples": [wifi_detail_first["signal_samples"],
                                    wifi_detail_second["signal_samples"]],
            "wifi_live_pixels": wifi["detail_pixel_changes"][
                "live_changed_pixels"],
            "wifi_identity_pixels": wifi["detail_pixel_changes"][
                "identity_changed_pixels"],
            "wifi_chrome_pixels": wifi["detail_pixel_changes"][
                "chrome_changed_pixels"],
            "ble_unique_devices": ble["live_second"]["ble_devices_unique"],
            "ble_strongest_first": True,
            "ble_identity_stable":
                ble_detail_first["identity_hash"] ==
                ble_detail_second["identity_hash"],
            "ble_signal_samples": [ble_detail_first["signal_samples"],
                                   ble_detail_second["signal_samples"]],
            "ble_radar_pixels": ble["detail_pixel_changes"][
                "radar_changed_pixels"],
            "ble_static_pixels": ble["detail_pixel_changes"][
                "static_changed_pixels"],
            "ble_chrome_pixels": ble["detail_pixel_changes"][
                "chrome_changed_pixels"],
            "targets_radios": target["verified"]["radios"],
            "targets_identity_stable": True,
            "targets_live_region_only": True,
            "heap_stable_after_warmup": True,
            "generation_and_observations_unchanged": True,
            "physical_storage_writes": 0,
            "radio_tx_commands": 0,
            "active_probe_commands": 0,
            "input_read_errors": 0,
            "input_queue_drops": 0,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "privacy": {
            "raw_runs_retained": False,
            "frames_retained": False,
            "ambient_identifiers_retained": False,
            "note": "Only aggregate counts, invariant results and input hashes are committed.",
        },
        "scope": {
            "accepts": [
                "coherent task-first entry to passive Wi-Fi and BLE discovery",
                "identity-stable live Wi-Fi and BLE device cards with Radar",
                "retained Targets reopening both passive radio sources",
                "FF-1 cross-radio interaction review",
            ],
            "does_not_accept": [
                "calibrated distance or direction finding",
                "RF transmit or active probing",
                "periodic full HIL matrix",
                "device screenshot capture and export",
            ],
            "review_kind": "compositional focused deltas",
            "focused_cadence": "9/15",
            "next": "FF-2 on-device screenshot to Library to export",
        },
    }
    require(evidence["verified"]["wifi_identity_stable"] and
            evidence["verified"]["ble_identity_stable"] and
            evidence["verified"]["wifi_signal_samples"][1] >
                evidence["verified"]["wifi_signal_samples"][0] and
            evidence["verified"]["ble_signal_samples"][1] >
                evidence["verified"]["ble_signal_samples"][0] and
            evidence["verified"]["wifi_identity_pixels"] == 0 and
            evidence["verified"]["wifi_chrome_pixels"] == 0 and
            evidence["verified"]["ble_static_pixels"] == 0 and
            evidence["verified"]["ble_chrome_pixels"] == 0,
            "cross-radio identity/live-region invariant mismatch")

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": str(args.destination),
        "wifi_devices": evidence["verified"]["wifi_unique_devices"],
        "ble_devices": evidence["verified"]["ble_unique_devices"],
        "cadence": "9/15",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
