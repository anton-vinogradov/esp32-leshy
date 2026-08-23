#!/usr/bin/env python3
"""Verify retained cross-radio descending-signal physical evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-signal-order-0.112"
SUMMARY = ROOT / "tests/hil/evidence/board-01-signal-order-0.112.json"
VERSION = "0.112.0-signal-order"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "1ff10d2438bfe17d92e4d7face11670d494641ef"
RUNNER_COMMIT = SOURCE_COMMIT
FIRMWARE_SHA256 = "b48e006dfa2563b98dad29d89b376ac0c0f53b8df02fdca9c9b2e0427926dd4f"
FACTORY_SHA256 = "d1586eeb731ad0081100d190eefce55ff887a6ab2c83c8f3f0194c5329fe6958"
ELF_SHA256 = "260ec5cd4c4326c3981241eb8aad28d0c1d532a260306bc46c953196b7bf1fc2"
MAP_SHA256 = "754b908f88d3ae35d87d10427fbca2675b855bad5c45aaaa5908268dfbd92782"
EVIDENCE_IDS = {"E-BUILD-112", "E-AUTO-076", "E-HIL-136", "E-UX-031"}
RADIOS = {
    "ble": ("run_1x_ble_nearby_hil.py", "check_ble_nearby_run.py"),
    "wifi-networks": (
        "run_1x_wifi_networks_hil.py", "check_wifi_networks_run.py"),
    "wifi-devices": (
        "run_1x_wifi_devices_hil.py", "check_wifi_devices_run.py"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_manifest(root: Path, manifest: Path) -> None:
    indexed: set[Path] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        artifact = root / relative
        require(artifact.is_file(), f"indexed artifact missing: {relative}")
        require(digest(artifact) == expected,
                f"artifact hash mismatch: {relative}")
        indexed.add(Path(relative))
    present = {
        path.relative_to(root) for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed == present, "artifact index coverage mismatch")


def run_checker(radio: str, checker_name: str) -> None:
    checked = subprocess.run(
        [sys.executable, str(BUNDLE / "tools" / checker_name),
         "--run", str(BUNDLE / radio), "--expected-version", VERSION,
         "--expected-cid", CID, "--source-commit", SOURCE_COMMIT],
        cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"{radio} retained run check failed: {checked.stdout}")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") == "leshy.signal_order.acceptance.v1" and
            summary.get("status") == "pass_descending_signal_checkpoint",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.signal_order_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == RUNNER_COMMIT,
            "candidate provenance mismatch")
    require(provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("app_image_bytes") == 1578720 and
            provenance.get("factory_image_bytes") == 1644256 and
            provenance.get("static_ram_bytes") == 182080 and
            provenance.get("linked_flash_bytes") == 1578308,
            "exact build identity/resource mismatch")

    runs: dict[str, dict[str, Any]] = {}
    expected_modes = {
        "ble": "fresh", "wifi-networks": "reuse_exact",
        "wifi-devices": "reuse_exact",
    }
    for radio, (runner_name, checker_name) in RADIOS.items():
        run = load(BUNDLE / radio / "run.json")
        runs[radio] = run
        candidate = run.get("candidate", {})
        require(run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID,
                f"{radio}: run status mismatch")
        require(candidate.get("version") == VERSION and
                candidate.get("source_commit") == SOURCE_COMMIT and
                candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
                candidate.get("app_elf_sha256") == ELF_SHA256 and
                candidate.get("flash_mode") == expected_modes[radio] and
                candidate.get("flashed") is True,
                f"{radio}: exact-flash binding mismatch")
        runner = BUNDLE / "tools" / runner_name
        checker = BUNDLE / "tools" / checker_name
        require(digest(runner) == provenance["runner_sha256"][radio] ==
                run.get("runner_source_sha256"),
                f"{radio}: runner hash mismatch")
        require(digest(checker) == provenance["checker_sha256"][radio],
                f"{radio}: checker hash mismatch")
        require(digest(BUNDLE / radio / "firmware.bin") == FIRMWARE_SHA256,
                f"{radio}: retained firmware mismatch")
        run_checker(radio, checker_name)

    ble = runs["ble"]
    networks = runs["wifi-networks"]
    devices = runs["wifi-devices"]
    require(ble["live_first"].get("ble_devices_strongest_first") is True and
            ble["live_second"].get("ble_devices_strongest_first") is True and
            networks["live_first"].get("wifi_networks_strongest_first") is True and
            networks["live_second"].get("wifi_networks_strongest_first") is True and
            devices["live_first"].get("wifi_devices_strongest_first") is True and
            devices["live_second"].get("wifi_devices_strongest_first") is True,
            "a live catalog is not strongest-first")
    require(ble["live_first"].get("survey_ble_scan_dropped") == 0 and
            ble["live_second"].get("survey_ble_scan_dropped") == 0 and
            networks["live_first"].get("survey_scan_dropped") == 0 and
            networks["live_second"].get("survey_scan_dropped") == 0 and
            devices["live_first"].get("wifi_device_clients_dropped") == 0 and
            devices["live_second"].get("wifi_device_clients_dropped") == 0,
            "radio drops observed")
    for radio, run in runs.items():
        require(run.get("list_pixel_changes", {}).get("chrome_changed_pixels") == 0 and
                run.get("detail_pixel_changes") == {
                    "content_changed_pixels": 0, "chrome_changed_pixels": 0},
                f"{radio}: redraw escaped live data")
        require(run.get("metrics_after_first", {}).get("heap_total") ==
                run.get("metrics_after", {}).get("heap_total") and
                run.get("metrics_after_first", {}).get("heap_free") ==
                run.get("metrics_after", {}).get("heap_free"),
                f"{radio}: warm heap drift")
        final = run.get("cleanup_after", {}).get("final_state", {})
        require(run.get("cleanup_after", {}).get("complete") is True and
                final.get("runtime_owner") == "none" and
                final.get("lease_mask") == 0,
                f"{radio}: final cleanup mismatch")

    verified = summary.get("verified", {})
    require(verified.get("fresh_flashes") == 1 and
            verified.get("exact_flash_reuse_runs") == 2 and
            verified.get("manual_button_presses") == 0 and
            verified.get("ble_strongest_first") is True and
            verified.get("wifi_networks_strongest_first") is True and
            verified.get("wifi_devices_strongest_first") is True and
            verified.get("stable_equal_signal_order") is True and
            verified.get("selection_anchored_to_identity") is True and
            verified.get("radio_drops") == 0 and
            verified.get("live_chrome_changed_pixels") == 0 and
            verified.get("detail_changed_pixels") == 0 and
            verified.get("zero_heap_drift_after_warmup") is True and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_lease_mask") == 0,
            "verified claims mismatch")
    require(verified.get("ble_unique_first") ==
            ble["live_first"]["ble_devices_unique"] and
            verified.get("ble_unique_second") ==
            ble["live_second"]["ble_devices_unique"] and
            verified.get("wifi_networks_unique_first") ==
            networks["live_first"]["wifi_networks_unique"] and
            verified.get("wifi_networks_unique_second") ==
            networks["live_second"]["wifi_networks_unique"] and
            verified.get("wifi_devices_unique_first") ==
            devices["live_first"]["wifi_devices_unique"] and
            verified.get("wifi_devices_unique_second") ==
            devices["live_second"]["wifi_devices_unique"],
            "summary live counts mismatch")
    print(
        "Signal-order acceptance passed: BLE, Wi-Fi networks and Wi-Fi devices "
        "are strongest-first on one exact flash, with zero drops/chrome redraw/"
        "heap drift and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
