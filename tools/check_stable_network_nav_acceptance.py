#!/usr/bin/env python3
"""Verify retained identity-stable Wi-Fi navigation evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-stable-network-nav-0.114"
SUMMARY = ROOT / "tests/hil/evidence/board-01-stable-network-nav-0.114.json"
VERSION = "0.114.0-stable-network-nav"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "8ec3d36906eba766f5652d807d1c556d66755eea"
FIRMWARE_SHA256 = "913b17dbb231a0586ec86e2bb75869420eb4fbcdfd215633921fd878debfae3c"
FACTORY_SHA256 = "87ebe3e91e05d6afbef2462436d63c48acd9209c6b94b9a3a1dcb278975473a4"
ELF_SHA256 = "59f70c3b802ff2184dbebfc385e1d6d8c306d6820829de7d9013d7ebbe78ec65"
MAP_SHA256 = "1069ee2f5047f2c22738035a7ff58f52ea0305e12fa04629f1d0ca91173ead62"
EVIDENCE_IDS = {"E-BUILD-114", "E-AUTO-078", "E-HIL-138", "E-UX-033"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def verify_source(provenance: dict[str, Any]) -> None:
    source = BUNDLE / "source"
    files = {
        "renderer": source / "ArduinoEntry.cpp",
        "catalog_h": source / "WifiNetworkCatalog.h",
        "catalog_cpp": source / "WifiNetworkCatalog.cpp",
        "navigation": source / "WifiNetworkNavigationOrder.h",
        "native_tests": source / "clean_target_tests.cpp",
        "contract": source / "check_wifi_networks_contract.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    renderer = files["renderer"].read_text(encoding="utf-8")
    navigation = files["navigation"].read_text(encoding="utf-8")
    native_tests = files["native_tests"].read_text(encoding="utf-8")
    for token in (
        "wifiNetworkNavigationOrder.lock(wifiNetworkCatalog)",
        "wifiNetworkCatalog.upsert(",
        "!wifiNetworkNavigationOrder.locked()",
        "wifi_network_order_hash",
        "wifi_network_selected_identity_hash",
    ):
        require(token in renderer, f"renderer contract missing: {token}")
    for token in (
        "class WifiNetworkNavigationOrder final",
        "catalog.indexOfIdentity(identity)",
        "std::uint32_t orderHash",
        "std::uint32_t identityHash",
    ):
        require(token in navigation, f"navigation contract missing: {token}")
    require("testWifiNetworkNavigationLocksIdentityOrder" in native_tests and
            "CHECK(navigation.orderHash(catalog) == lockedOrder)" in native_tests,
            "native RSSI-reorder regression coverage missing")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.stable_network_nav.acceptance.v1" and
            summary.get("status") ==
            "pass_identity_stable_network_navigation",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.stable_network_nav_hil.provenance.v1" and
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
            provenance.get("app_image_bytes") == 1579904 and
            provenance.get("factory_image_bytes") == 1645440 and
            provenance.get("static_ram_bytes") == 182312 and
            provenance.get("linked_flash_bytes") == 1579500 and
            provenance.get("tft_states") == 6,
            "exact build identity/resource mismatch")
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
    require(digest(BUNDLE / "run/firmware.bin") == FIRMWARE_SHA256,
            "retained firmware mismatch")
    runner = BUNDLE / "tools/run_1x_wifi_networks_hil.py"
    checker = BUNDLE / "tools/check_wifi_networks_run.py"
    require(digest(runner) == provenance["runner_sha256"] ==
            run.get("runner_source_sha256"), "runner hash mismatch")
    require(digest(checker) == provenance["checker_sha256"],
            "checker hash mismatch")
    checked = subprocess.run(
        [sys.executable, str(checker), "--run", str(BUNDLE / "run"),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0,
            f"independent retained run check failed: {checked.stdout}")

    first = run["navigation_first"]
    second = run["navigation_second"]
    require(second["survey_product_wifi_scan_cycles"] >=
            first["survey_product_wifi_scan_cycles"] + 2 and
            second["wifi_network_catalog_revision"] >
            first["wifi_network_catalog_revision"],
            "live scans did not advance under lock")
    for field in (
            "wifi_network_selection", "wifi_network_visible_size",
            "wifi_network_order_hash", "wifi_network_selected_identity_hash"):
        require(first.get(field) == second.get(field),
                f"locked navigation changed: {field}")
    require(run.get("metrics_after_first", {}).get("heap_total") ==
            run.get("metrics_after", {}).get("heap_total") and
            run.get("metrics_after_first", {}).get("heap_free") ==
            run.get("metrics_after", {}).get("heap_free"),
            "post-warm heap drift")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(run.get("cleanup_after", {}).get("complete") is True and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("survey_product_store_bytes_written") == 0,
            "final cleanup/write mismatch")
    verified = summary.get("verified", {})
    require(verified == {
        "automated_navigation_actions": 8,
        "bssid_order_stable": True,
        "buzzer_inactive": True,
        "catalog_revision_delta_under_lock": 28,
        "detail_changed_pixels": 0,
        "final_lease_mask": 0,
        "fresh_flashes": 1,
        "live_chrome_changed_pixels": 0,
        "live_values_update_in_place": True,
        "manual_button_presses": 0,
        "physical_sd_write_calls": 0,
        "scan_cycles_under_lock": 2,
        "selected_bssid_stable": True,
        "selection_stable": True,
        "visible_networks_locked": 23,
        "visible_size_stable": True,
        "zero_heap_drift_after_warmup": True,
    }, "verified claims mismatch")
    print(
        "Stable network navigation acceptance passed: 8 automated actions, "
        "23 locked BSSIDs, 2 additional live scans, unchanged cursor/order/"
        "selected identity, zero chrome/detail changes and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
