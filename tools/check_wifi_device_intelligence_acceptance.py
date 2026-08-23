#!/usr/bin/env python3
"""Verify retained board-01 Wi-Fi device-intelligence evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-device-intelligence-0.115"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-device-intelligence-0.115.json"
VERSION = "0.115.0-wifi-device-intelligence"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "b2ea80493ecc17f96f735f159306e6711b753654"
FIRMWARE_SHA256 = "1ee8fe748d7ca455df2f7495effc244ba0968907cb5bf8283cbceccbfb98c2d9"
FACTORY_SHA256 = "dda0513137fd4841a21533099e9705995301f375c0acea534a86e7971b3de5c1"
ELF_SHA256 = "8c6928d2574ef3a98ee06f1211eb3307dc42da0b2491e2fcffd96775f097c236"
MAP_SHA256 = "26f41dc2f7ca4a196613a5cd404161267aae7e1390d9ffb17cc5dc13c5ef1290"
EVIDENCE_IDS = {"E-BUILD-115", "E-AUTO-079", "E-HIL-139", "E-UX-034"}
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path, manifest: Path) -> None:
    indexed_present: set[Path] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        artifact = root / relative
        if not artifact.is_file():
            require(relative.endswith(OPAQUE_SUFFIXES),
                    f"tracked artifact missing: {relative}")
            continue
        require(digest(artifact) == expected,
                f"artifact hash mismatch: {relative}")
        indexed_present.add(Path(relative))
    present = {
        path.relative_to(root) for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed_present == present, "artifact index coverage mismatch")


def verify_source(provenance: dict[str, Any]) -> None:
    source = BUNDLE / "source"
    files = {
        "renderer": source / "ArduinoEntry.cpp",
        "catalog_h": source / "WifiDeviceCatalog.h",
        "catalog_cpp": source / "WifiDeviceCatalog.cpp",
        "navigation": source / "WifiDeviceNavigationOrder.h",
        "oui_h": source / "WifiOuiDatabase.h",
        "oui_cpp": source / "WifiOuiDatabase.cpp",
        "oui_metadata": source / "oui.json",
        "oui_generator": source / "make_wifi_oui_asset.py",
        "native_tests": source / "clean_target_tests.cpp",
        "contract": source / "check_wifi_devices_contract.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    renderer = files["renderer"].read_text(encoding="utf-8")
    catalog = files["catalog_cpp"].read_text(encoding="utf-8")
    navigation = files["navigation"].read_text(encoding="utf-8")
    oui = files["oui_cpp"].read_text(encoding="utf-8")
    native_tests = files["native_tests"].read_text(encoding="utf-8")
    for token in (
            "wifiFrameCapture.lockDeviceChannel(",
            "wifiDeviceNavigationOrder.lock(wifiDeviceCatalog)",
            "wifi_device_detail_wps_identity_known",
            "wifi_device_oui_records",
            "renderWifiDeviceRadar",
    ):
        require(token in renderer, f"renderer contract missing: {token}")
    for token in ("0x1011U", "0x1021U", "0x1023U", "WifiDeviceGeneration::Wifi6"):
        require(token in catalog, f"passive fingerprint contract missing: {token}")
    require("class WifiDeviceNavigationOrder final" in navigation and
            "std::uint32_t orderHash" in navigation,
            "identity-stable navigation source missing")
    require("WifiOuiDatabase::lookup" in oui and
            "(mac[0] & 0x03U) != 0U" in oui,
            "OUI/private-MAC source contract missing")
    require("testWifiDevicePassiveFingerprintAndOuiLookup" in native_tests,
            "native passive fingerprint regression missing")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_device_intelligence.acceptance.v1" and
            summary.get("status") ==
            "pass_passive_wifi_device_intelligence",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_device_intelligence_hil.provenance.v1" and
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
            provenance.get("app_image_bytes") == 2875280 and
            provenance.get("factory_image_bytes") == 2940816 and
            provenance.get("static_ram_bytes") == 198568 and
            provenance.get("linked_flash_bytes") == 2874880 and
            provenance.get("oui_records") == 39984 and
            provenance.get("tft_states") == 8,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)

    run = load(BUNDLE / "run/run.json")
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID,
            "run status mismatch")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == ELF_SHA256 and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flashed") is True,
            "exact fresh-flash binding mismatch")
    firmware = BUNDLE / "run/firmware.bin"
    if firmware.is_file():
        require(digest(firmware) == FIRMWARE_SHA256,
                "retained firmware mismatch")
    runner = BUNDLE / "tools/run_1x_wifi_devices_hil.py"
    checker = BUNDLE / "tools/check_wifi_devices_run.py"
    require(digest(runner) == provenance["runner_sha256"] ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance["checker_sha256"],
            "checker hash mismatch")
    if firmware.is_file():
        checked = subprocess.run(
            [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        require(checked.returncode == 0,
                f"independent retained run check failed: {checked.stdout}")

    verified = summary.get("verified", {})
    require(verified == {
        "buzzer_inactive": True,
        "channel_hops_second": 39,
        "channel_locked_radar": True,
        "client_frames_accepted_second": 3,
        "client_frames_dropped": 0,
        "detail_changed_pixels": 0,
        "embedded_ieee_oui_records": 39984,
        "final_lease_mask": 0,
        "fresh_flashes": 1,
        "identity_stable_navigation": True,
        "list_content_changed_pixels": 38143,
        "live_chrome_changed_pixels": 0,
        "manual_button_presses": 0,
        "passive_probe_association_wps_fingerprint": True,
        "physical_sd_write_calls": 0,
        "private_mac_reported_honestly": True,
        "radar_channel": 4,
        "radar_client_updates": 1,
        "radar_content_changed_pixels": 827,
        "radar_last_seen_advanced": True,
        "selected_index_stable": True,
        "selected_order_hash_stable": True,
        "two_complete_wifi_lifecycles": True,
        "unique_devices_first": 2,
        "unique_devices_second": 3,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Wi-Fi device intelligence acceptance passed: 39,984 OUI makers, "
        "passive fingerprint passport, identity-stable list, channel-locked "
        "live radar, zero chrome changes and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
