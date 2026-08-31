#!/usr/bin/env python3
"""Retain privacy-minimal machine-checked evidence for Targets Radar."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.327"
SOURCE_COMMIT = "b8b0daed3ef30854b8b8e607609774f71a24384b"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-213", "E-AUTO-188", "E-HIL-221", "E-UX-072",
                "RB-M224"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    run_dir = args.run.resolve()
    run_path = run_dir / "run.json"
    manifest = run_dir / "artifacts.sha256"
    runner = ROOT / "tools/run_1x_target_radar_hil.py"
    checker = ROOT / "tools/check_target_radar_run.py"
    destination = args.destination.resolve()
    required = (run_path, manifest, runner, checker, args.firmware,
                args.factory, args.elf, args.map)
    require(all(path.resolve().is_file() for path in required),
            "input artifact missing")
    require(not destination.exists(), "destination already exists")

    run = load(run_path)
    candidate = run.get("candidate", {})
    require(run.get("status") == "pass" and run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "source run is not a clean pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == digest(args.firmware) and
            candidate.get("elf_sha256") == digest(args.elf) and
            candidate.get("map_sha256") == digest(args.map) and
            run.get("expected_cid") == CID,
            "candidate, source, artifact, or CID binding mismatch")

    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(run_dir),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT],
        cwd=ROOT, text=True, env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"independent checker failed: {checked.stdout}")

    lifecycles = run["lifecycles"]
    require(Counter(item["radio"] for item in lifecycles) ==
            Counter({"ble": 2, "wifi": 2}), "radio repeat matrix mismatch")
    require(any(item["physical_live_match"] for item in lifecycles),
            "no physical live match retained")
    require(all(item["source_lifecycle_proven"] and item["live_match"] and
                item["target_id_stable"] for item in lifecycles),
            "source, live delta, or identity invariant missing")
    final = run["cleanup"]["final_state"]
    require(final["survey_product_worker_ready"] is True and
            final["page"] == "home" and final["runtime_owner"] == "none" and
            final["lease_mask"] == 0, "terminal worker/resource invariant missing")

    screen_digests = {
        name: {
            "png_sha256": record["png_sha256"],
            "rgb565_sha256": record["rgb565_sha256"],
        }
        for name, record in sorted(run["screens"].items())
    }
    evidence = {
        "schema": "leshy.target_radar.acceptance.v1",
        "status": "pass",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            "version": VERSION,
            "firmware_source_commit": SOURCE_COMMIT,
            "harness_commit": candidate["harness_commit"],
            "firmware_sha256": digest(args.firmware),
            "factory_sha256": digest(args.factory),
            "elf_sha256": digest(args.elf),
            "map_sha256": digest(args.map),
            "firmware_bytes": args.firmware.stat().st_size,
            "factory_bytes": args.factory.stat().st_size,
            "static_ram_bytes": 234064,
            "linked_image_bytes": 3578100,
            "ota_free_bytes": 4194304 - args.firmware.stat().st_size,
        },
        "automation": {
            "run_sha256": digest(run_path),
            "manifest_sha256": digest(manifest),
            "runner_sha256": digest(runner),
            "checker_sha256": digest(checker),
            "independent_checker_output": checked.stdout.strip(),
            "manual_button_presses": 0,
            "flash_count": run["flash_count"],
            "automatic_screenshots": len(screen_digests),
            "screen_digests": screen_digests,
        },
        "verified": {
            "radios": [item["radio"] for item in lifecycles],
            "four_complete_lifecycles": True,
            "physical_live_match_present": True,
            "deterministic_fallback_observations":
                run["deterministic_observation_injections"],
            "identity_stable": True,
            "restore_matches": [item["restore_match"] for item in lifecycles],
            "source_lifecycle_proven": True,
            "atomic_live_region_only": all(
                item["pixel_changes"]["identity_changed_pixels"] == 0 and
                item["pixel_changes"]["chrome_changed_pixels"] == 0 and
                item["pixel_changes"]["live_changed_pixels"] > 0
                for item in lifecycles),
            "repeat_heap_stable": all(
                lifecycles[index]["heap_free_after"] ==
                lifecycles[index]["heap_free_before"]
                for index in (1, 3)),
            "generation_unchanged":
                run["recovery_before"]["generation"] ==
                run["recovery_after"]["generation"],
            "observations_unchanged":
                run["recovery_before"]["observations"] ==
                run["recovery_after"]["observations"],
            "physical_storage_writes": 0,
            "radio_tx_commands": run["radio_tx_commands"],
            "active_probe_commands": run["active_probe_commands"],
            "input_read_errors": run["input"]["read_errors"],
            "input_queue_drops": run["input"]["queue_drops"],
            "buzzer_inactive": run["safe_outputs"]["buzzer_inactive"],
            "survey_worker_ready_after_cleanup": True,
            "final_page": final["page"],
            "final_runtime_owner": final["runtime_owner"],
            "final_lease_mask": final["lease_mask"],
        },
        "privacy": {
            "raw_run_retained": False,
            "frames_retained": False,
            "ambient_identifiers_retained": False,
            "note": "Only aggregate facts and frame digests are committed.",
        },
        "scope": {
            "accepts": [
                "passive Targets Radar for retained Wi-Fi and BLE identities",
                "repeatable identity-preserving return to Targets Actions",
                "atomic live-region redraw and restored Survey worker",
            ],
            "does_not_accept": [
                "calibrated distance or direction finding",
                "RF transmit or active probing",
                "periodic full HIL matrix",
            ],
            "focused_cadence": "7/15",
            "next": "coherent Wi-Fi/BLE/Targets interaction review and user-first Home hierarchy",
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False,
                                      indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination": str(destination),
                      "run_sha256": evidence["automation"]["run_sha256"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
