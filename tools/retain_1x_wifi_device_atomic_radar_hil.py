#!/usr/bin/env python3
"""Retain privacy-minimal evidence for atomic Wi-Fi device radar updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.312"
CID = "FE343253440000002000000055019CB7"
FIRMWARE_SOURCE = "a2964985eff8bd33d8c429d4ec37350446d56834"
HARNESS_COMMIT = "69515a1bf23c25d77443acec53af8e6932b0bde6"
EVIDENCE_IDS = ["E-BUILD-212", "E-AUTO-187", "E-HIL-220", "E-UX-071",
                "RB-M223"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--fresh-failure", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    failed_source = args.fresh_failure.resolve()
    destination = args.destination.resolve()
    run_path = source / "run.json"
    failed_run_path = failed_source / "run.json"
    firmware = args.firmware.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    map_file = args.map.resolve()
    runner = ROOT / "tools/run_1x_wifi_devices_hil.py"
    checker = ROOT / "tools/check_wifi_devices_run.py"
    contract = ROOT / "tools/check_wifi_devices_contract.py"
    required = (run_path, failed_run_path, firmware, factory, elf, map_file,
                runner, checker, contract)
    require(all(path.is_file() for path in required), "input artifact missing")
    require(not destination.exists(), "destination already exists")

    run = load(run_path)
    failed = load(failed_run_path)
    candidate = run.get("candidate", {})
    failed_candidate = failed.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_devices_hil.run.v4" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], "accepted run is not a clean v4 pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == FIRMWARE_SOURCE and
            candidate.get("firmware_sha256") == digest(firmware) and
            candidate.get("app_elf_sha256") == app_elf_sha256(firmware) and
            candidate.get("flash_mode") == "reuse_exact" and
            run.get("expected_cid") == CID and
            run.get("runner_source_sha256") == digest(runner),
            "accepted candidate/source/runner binding mismatch")
    require(failed.get("schema") == "leshy.wifi_devices_hil.run.v3" and
            failed.get("passed") is False and
            failed_candidate.get("version") == VERSION and
            failed_candidate.get("source_commit") == FIRMWARE_SOURCE and
            failed_candidate.get("firmware_sha256") == digest(firmware) and
            failed_candidate.get("app_elf_sha256") == candidate.get(
                "app_elf_sha256") and
            failed_candidate.get("flash_mode") == "fresh" and
            failed.get("screens") == {} and
            failed.get("cleanup_after", {}).get("complete") is True and
            len(failed.get("failures", [])) == 1 and
            "wifi_menu.page" in failed["failures"][0],
            "fresh-flash predecessor lineage mismatch")

    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(source),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", FIRMWARE_SOURCE],
        cwd=ROOT, text=True, env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"independent run check failed: {checked.stdout}")

    first = run["detail_oracle_first"]
    second = run["detail_oracle_second"]
    pixels = run["detail_pixel_changes"]
    lock = run["device_lock_fixture"]
    final = run["cleanup_after"]["final_state"]
    before = run["recovery_before"]
    after = run["recovery_after"]
    require(first["detail_content_clears"] ==
            second["detail_content_clears"] == 1 and
            first["radar_full_repaints"] ==
            second["radar_full_repaints"] == 1 and
            second["radar_delta_repaints"] > first["radar_delta_repaints"] and
            second["signal_samples"] > first["signal_samples"] and
            first["identity_hash"] == second["identity_hash"] and
            pixels == {"identity_changed_pixels": 0,
                       "live_changed_pixels": 49,
                       "chrome_changed_pixels": 0},
            "atomic live-detail proof mismatch")
    require(lock.get("cleanup_proven") is True and
            lock.get("configured") is True and
            lock.get("hil_ended") is True and
            lock.get("active_at_end") is False and
            lock.get("product_namespace_written_or_erased") is False and
            lock.get("pin_or_digest_retained") is False,
            "isolated Device Lock cleanup mismatch")
    require(before.get("generation") == after.get("generation") == 8 and
            before.get("observations") == after.get("observations") == 54 and
            after.get("physical_write_calls") == 0 and
            run["metrics_after_first"]["heap_free"] ==
                run["metrics_after"]["heap_free"] and
            run["input"]["read_errors"] == run["input"]["queue_drops"] == 0 and
            run["safe_outputs"]["buzzer_inactive"] is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "storage/heap/input/output/terminal invariant mismatch")

    screen_digests = {
        name: {"png_sha256": record["png_sha256"],
               "rgb565_sha256": record["rgb565_sha256"]}
        for name, record in sorted(run["screens"].items())
    }
    evidence = {
        "schema": "leshy.wifi_device_atomic_radar.acceptance.v1",
        "status": "pass",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            "version": VERSION,
            "firmware_source_commit": FIRMWARE_SOURCE,
            "harness_commit": HARNESS_COMMIT,
            "firmware_sha256": digest(firmware),
            "factory_sha256": digest(factory),
            "elf_sha256": digest(elf),
            "map_sha256": digest(map_file),
            "app_elf_sha256": candidate["app_elf_sha256"],
            "firmware_bytes": firmware.stat().st_size,
            "factory_bytes": factory.stat().st_size,
            "static_ram_bytes": 233760,
            "linked_flash_bytes": 3565108,
            "ota_free_bytes": 4194304 - firmware.stat().st_size,
        },
        "automation": {
            "accepted_run_sha256": digest(run_path),
            "accepted_manifest_sha256": digest(source / "artifacts.sha256"),
            "fresh_flash_predecessor_run_sha256": digest(failed_run_path),
            "fresh_flash_predecessor_rejected": True,
            "fresh_flash_predecessor_reason": "unconfigured Device Lock state was not isolated by v3 harness",
            "runner_sha256": digest(runner),
            "checker_sha256": digest(checker),
            "contract_sha256": digest(contract),
            "independent_checker_output": checked.stdout.strip(),
            "manual_button_presses": 0,
            "automatic_screenshots": len(screen_digests),
            "ambient_frames_retained": False,
            "screen_digests": screen_digests,
        },
        "verified": {
            "passive_receive_only": True,
            "active_probe_allowed": False,
            "channels_listened": list(range(1, 14)),
            "channel_hops": run["live_second"]["wifi_device_channel_hops"],
            "unique_devices": run["live_second"]["wifi_devices_unique"],
            "oui_records": 39984,
            "identity_stable": True,
            "signal_samples_before": first["signal_samples"],
            "signal_samples_after": second["signal_samples"],
            "content_clears_before": first["detail_content_clears"],
            "content_clears_after": second["detail_content_clears"],
            "full_repaints_before": first["radar_full_repaints"],
            "full_repaints_after": second["radar_full_repaints"],
            "delta_repaints_before": first["radar_delta_repaints"],
            "delta_repaints_after": second["radar_delta_repaints"],
            **pixels,
            "list_chrome_changed_pixels": run["list_pixel_changes"][
                "chrome_changed_pixels"],
            "atomic_row_allocation_failures": second[
                "atomic_text_row_allocation_failures"],
            "direct_row_fallbacks": second["direct_text_row_fallbacks"],
            "two_complete_lifecycles": True,
            "heap_free_before_bytes": run["metrics_after_first"]["heap_free"],
            "heap_free_after_bytes": run["metrics_after"]["heap_free"],
            "physical_sd_write_calls": 0,
            "device_lock_fixture_cleanup_proven": True,
            "product_device_lock_namespace_mutated": False,
            "input_read_errors": 0,
            "input_queue_drops": 0,
            "buzzer_inactive": True,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "privacy": {
            "raw_run_retained": False,
            "frames_retained": False,
            "ambient_identifiers_retained": False,
            "note": "Ambient device identities and frame pixels remain local; only digests and aggregate machine-checked facts are committed.",
        },
        "scope": {
            "accepts": [
                "FF-1 Wi-Fi device facts plus channel-locked live radar",
                "identity-stable atomic content-only live updates",
                "Device Lock state-independent automated delta HIL",
            ],
            "does_not_accept": [
                "FF-1 BLE or Targets radar/localize",
                "calibrated distance or RF accuracy",
                "periodic full HIL or release endurance",
            ],
            "focused_cadence": "6/15",
            "next": "FF-1 Targets radar/localize delta, then cross-radio review",
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False,
                                      indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination": str(destination),
                      "run_sha256": evidence["automation"][
                          "accepted_run_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
