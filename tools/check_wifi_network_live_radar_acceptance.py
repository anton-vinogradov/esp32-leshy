#!/usr/bin/env python3
"""Verify retained board-01 Wi-Fi network live-radar evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-network-live-radar-0.119"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-network-live-radar-0.119.json"
VERSION = "0.119.0-wifi-network-live-radar"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "f2da0b89a51d380d949aab8be81e283c05c34794"
FAILED_SOURCE_COMMIT = "c6947120f2adf8862e49ac5c6aaef96309e89c57"
FIRMWARE_SHA256 = "241b7f3bcac75a48b63e98b1ddfa13492b7d422539fa8b8d84333872717d69aa"
FACTORY_SHA256 = "b18e6b406c4fdab87cd6e5ff4a5999ab2d65edfa878574552a7984b6b92b7e6b"
ELF_SHA256 = "666907c065ec810c5df14e1e0154683cd9b637bce7d7d457b518276cc2524a77"
MAP_SHA256 = "2e259ff733fcb7f920e028750ba988166427ba03b6b8e08674cecde40f200df5"
EVIDENCE_IDS = {"E-BUILD-119", "E-AUTO-083", "E-HIL-143", "E-UX-038"}
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
        "strings": source / "UiStrings.def",
        "catalog_h": source / "WifiNetworkCatalog.h",
        "catalog_cpp": source / "WifiNetworkCatalog.cpp",
        "navigation": source / "WifiNetworkNavigationOrder.h",
        "native_tests": source / "clean_target_tests.cpp",
        "source_guard": source / "check_wifi_networks_contract.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    renderer = files["renderer"].read_text(encoding="utf-8")
    catalog_h = files["catalog_h"].read_text(encoding="utf-8")
    catalog_cpp = files["catalog_cpp"].read_text(encoding="utf-8")
    native_tests = files["native_tests"].read_text(encoding="utf-8")
    for token in (
            "renderWifiNetworkRadar(live, signal)",
            "liveWifiNetworkSignal()",
            "integrated radar must follow passive scan",
            "detail_live_radar_only"):
        require(token in renderer or token in (BUNDLE / "tools/run_1x_wifi_networks_hil.py").read_text(encoding="utf-8"),
                f"live-radar source token missing: {token}")
    require("struct WifiNetworkSignalStats final" in catalog_h and
            "minimumRssiDbm" in catalog_h and "maximumRssiDbm" in catalog_h and
            "rssiTrendDb" in catalog_h and "signals_[position]" in catalog_cpp,
            "identity-bound signal history source missing")
    require("testWifiNetworkCatalogKeepsStrongestUniqueRows" in native_tests and
            "signalAt(0)->rssiTrendDb" in native_tests,
            "network-radar native regression missing")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_network_live_radar.acceptance.v1" and
            summary.get("status") == "pass_wifi_network_live_radar",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_network_live_radar_hil.provenance.v1" and
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
            provenance.get("app_image_bytes") == 2891840 and
            provenance.get("factory_image_bytes") == 2957376 and
            provenance.get("static_ram_bytes") == 209464 and
            provenance.get("linked_flash_bytes") == 2891428 and
            provenance.get("tft_states") == 6,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)

    run = load(BUNDLE / "run/run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_networks_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID,
            "run status mismatch")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE_SHA256 and
            candidate.get("app_elf_sha256") == ELF_SHA256 and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flashed") is True,
            "exact fresh-flash binding mismatch")
    failed = load(BUNDLE / "failed-predecessor/run.json")
    require(failed.get("passed") is False and
            failed.get("gate_eligible") is False and
            failed.get("candidate", {}).get("source_commit") ==
                FAILED_SOURCE_COMMIT and
            "redrew outside its card" in "\n".join(
                failed.get("failures", [])) and
            failed.get("cleanup_after", {}).get("complete") is True,
            "fail-closed frozen-detail predecessor mismatch")

    runner = BUNDLE / "tools/run_1x_wifi_networks_hil.py"
    checker = BUNDLE / "tools/check_wifi_networks_run.py"
    require(digest(runner) == provenance["runner_sha256"] ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance["checker_sha256"],
            "checker hash mismatch")
    if (BUNDLE / "run/firmware.bin").is_file():
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
        "active_probe_allowed": False,
        "buzzer_inactive": True,
        "channel": 8,
        "chrome_changed_pixels": 0,
        "detail_changed_pixels": 86,
        "detail_outside_radar_changed_pixels": 0,
        "final_lease_mask": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "fresh_flashes": 1,
        "heap_free_bytes": 104256,
        "heap_min_free_bytes": 40540,
        "heap_total_bytes": 171988,
        "library_generation": 95,
        "library_observations": 0,
        "manual_button_presses": 0,
        "maximum_rssi_dbm": -70,
        "minimum_rssi_dbm": -72,
        "network_facts_stable": True,
        "network_identity_hash": 3304241313,
        "passive_only": True,
        "physical_sd_write_calls": 0,
        "rssi_first_dbm": -71,
        "rssi_second_dbm": -70,
        "rssi_trend_db": 1,
        "signal_samples_first": 4,
        "signal_samples_second": 5,
        "ssid_known": True,
        "two_complete_wifi_lifecycles": True,
        "vendor": "Keenetic",
        "zero_heap_drift_after_warmup": True,
    }, "verified live-radar claims mismatch")
    print(
        "Wi-Fi network live-radar acceptance passed: passive BSSID-bound "
        "range/trend, stable passport, radar-only TFT update and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
