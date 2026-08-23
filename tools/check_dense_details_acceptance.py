#!/usr/bin/env python3
"""Verify retained user-facing radio-detail density evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-dense-details-0.113"
SUMMARY = ROOT / "tests/hil/evidence/board-01-dense-details-0.113.json"
VERSION = "0.113.0-dense-details"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "69c347f28b50cd5392b899d10508ca655c03e0b0"
FIRMWARE_SHA256 = "083b55a2da40d4deab616b7f8147857c58c564144bb29dfc68814f5068491693"
FACTORY_SHA256 = "ae8e7a0c45697d96e0690503c0b0e53936fc2af5dc4cfabf9864e571bb0209dc"
ELF_SHA256 = "55980a31da74c458ef47c1c86ab2ee364390327d80c4b9496cec408ba29895a8"
MAP_SHA256 = "a691b37cacce1b41298fd8f5a0240548b56053ca788300de68a449ad66421f60"
EVIDENCE_IDS = {"E-BUILD-113", "E-AUTO-077", "E-HIL-137", "E-UX-032"}
RADIOS = {
    "ble": ("run_1x_ble_nearby_hil.py", "check_ble_nearby_run.py"),
    "wifi-networks": (
        "run_1x_wifi_networks_hil.py", "check_wifi_networks_run.py"),
    "wifi-devices": (
        "run_1x_wifi_devices_hil.py", "check_wifi_devices_run.py"),
}
DETAIL_FRAMES = {
    "ble": ("ble-detail-first.png", "ble-detail-second.png"),
    "wifi-networks": (
        "wifi-network-detail-first.png", "wifi-network-detail-second.png"),
    "wifi-devices": (
        "wifi-device-detail-first.png", "wifi-device-detail-second.png"),
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


def verify_source_contract(provenance: dict[str, Any]) -> None:
    source = BUNDLE / "source"
    renderer = (source / "ArduinoEntry.cpp").read_text(encoding="utf-8")
    strings = (source / "UiStrings.def").read_text(encoding="utf-8")
    source_files = {
        "renderer": source / "ArduinoEntry.cpp",
        "strings": source / "UiStrings.def",
        "content_guard": source / "check_product_ui_content.py",
        "ble_guard": source / "check_ble_nearby_contract.py",
        "wifi_networks_guard": source / "check_wifi_networks_contract.py",
        "wifi_devices_guard": source / "check_wifi_devices_contract.py",
    }
    for label, path in source_files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    require(renderer.count("renderRadioSignalCard(") == 4,
            "shared signal card definition/use count mismatch")
    for use in (
        "renderRadioSignalCard(bleDeviceDetail.rssiDbm)",
        "renderRadioSignalCard(wifiNetworkDetail.rssiDbm)",
        "renderRadioSignalCard(wifiDeviceDetail.rssiDbm)",
    ):
        require(use in renderer, f"dense detail use missing: {use}")
    for identifier in (
        "RadioSignalLabel", "RadioSignalExcellent", "RadioSignalGood",
        "RadioSignalWeak", "RadioSignalVeryWeak", "RadioSignalDbmFormat",
        "RadioSignalScaleWeak", "RadioSignalScaleStrong",
        "RadioChannelFormat",
    ):
        require(f"LESHY_UI_TEXT({identifier}," in strings,
                f"user-facing detail string missing: {identifier}")
    for identifier in (
        "BleDeviceSeenFormat", "WifiNetworkSamplesFormat",
        "WifiDeviceFramesFormat",
    ):
        require(identifier not in strings and f"UiTextId::{identifier}" not in renderer,
                f"implementation counter remains visible: {identifier}")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") == "leshy.dense_details.acceptance.v1" and
            summary.get("status") == "pass_dense_radio_details_checkpoint",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.dense_details_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == SOURCE_COMMIT,
            "candidate provenance mismatch")
    require(provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("elf_file_sha256") == ELF_SHA256 and
            provenance.get("app_elf_sha256") == ELF_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("app_image_bytes") == 1579120 and
            provenance.get("factory_image_bytes") == 1644656 and
            provenance.get("static_ram_bytes") == 182080 and
            provenance.get("linked_flash_bytes") == 1578716,
            "exact build identity/resource mismatch")
    verify_source_contract(provenance)

    expected_modes = {
        "ble": "fresh", "wifi-networks": "reuse_exact",
        "wifi-devices": "reuse_exact",
    }
    for radio, (runner_name, checker_name) in RADIOS.items():
        run = load(BUNDLE / radio / "run.json")
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
        require(digest(BUNDLE / "tools" / runner_name) ==
                provenance["runner_sha256"][radio] ==
                run.get("runner_source_sha256"),
                f"{radio}: runner hash mismatch")
        require(digest(BUNDLE / "tools" / checker_name) ==
                provenance["checker_sha256"][radio],
                f"{radio}: checker hash mismatch")
        require(digest(BUNDLE / radio / "firmware.bin") == FIRMWARE_SHA256,
                f"{radio}: retained firmware mismatch")
        first, second = DETAIL_FRAMES[radio]
        require(digest(BUNDLE / radio / "frames" / first) ==
                digest(BUNDLE / radio / "frames" / second),
                f"{radio}: detail screenshots are not byte-identical")
        require(run.get("detail_pixel_changes") == {
            "content_changed_pixels": 0, "chrome_changed_pixels": 0},
            f"{radio}: open detail changed")
        require(run.get("list_pixel_changes", {}).get("chrome_changed_pixels") == 0,
                f"{radio}: live redraw touched chrome")
        require(run.get("metrics_after_first", {}).get("heap_total") ==
                run.get("metrics_after", {}).get("heap_total") and
                run.get("metrics_after_first", {}).get("heap_free") ==
                run.get("metrics_after", {}).get("heap_free"),
                f"{radio}: warm heap drift")
        require(run.get("metrics_after", {}).get("buzzer_inactive") is True,
                f"{radio}: buzzer is not inactive")
        final = run.get("cleanup_after", {}).get("final_state", {})
        require(run.get("cleanup_after", {}).get("complete") is True and
                final.get("runtime_owner") == "none" and
                final.get("lease_mask") == 0 and
                final.get("survey_product_store_bytes_written") == 0,
                f"{radio}: final cleanup/write mismatch")
        run_checker(radio, checker_name)

    ble = load(BUNDLE / "ble/run.json")
    networks = load(BUNDLE / "wifi-networks/run.json")
    devices = load(BUNDLE / "wifi-devices/run.json")
    require(ble["live_first"].get("survey_ble_scan_dropped") == 0 and
            ble["live_second"].get("survey_ble_scan_dropped") == 0 and
            networks["live_first"].get("survey_scan_dropped") == 0 and
            networks["live_second"].get("survey_scan_dropped") == 0 and
            devices["live_first"].get("wifi_device_clients_dropped") == 0 and
            devices["live_second"].get("wifi_device_clients_dropped") == 0,
            "radio drops observed")
    verified = summary.get("verified", {})
    require(verified == {
        "buzzer_inactive": True,
        "channel_or_passive_context": True,
        "dense_detail_screens": 3,
        "detail_changed_pixels": 0,
        "exact_flash_reuse_runs": 2,
        "final_lease_mask": 0,
        "fresh_flashes": 1,
        "implementation_counters_visible": 0,
        "live_chrome_changed_pixels": 0,
        "manual_button_presses": 0,
        "numeric_dbm": True,
        "physical_sd_write_calls": 0,
        "qualitative_signal": True,
        "radio_drops": 0,
        "shared_signal_card": True,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Dense-detail acceptance passed: three radio details use compact facts "
        "plus one shared signal meter on one exact flash, with zero detail "
        "changes/drops/heap drift/writes and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
