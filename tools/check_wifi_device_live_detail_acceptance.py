#!/usr/bin/env python3
"""Verify retained board-01 integrated Wi-Fi device live-detail evidence."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import load, require


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-device-live-detail-0.117"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-device-live-detail-0.117.json"
VERSION = "0.117.0-wifi-device-live-detail"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "8cd1a0bf5e3114b796575e51c9864917f94dabff"
FIRMWARE_SHA256 = "ccda1a1e2009f4b5a6e81e04c3609865741b2002b6bc81e76830da8987535e8c"
FACTORY_SHA256 = "09e8485dd18c5630ac849aba8cd3650b1a9398d9b0c11d4976c38282dbbe7c53"
ELF_SHA256 = "eaed48330c34559c55e9040b76ddc58ca9b20aad98c2a36bbaec5c161230e824"
MAP_SHA256 = "08e46145d981e589efdd64aa5b1a23c72657c9651df7049109ba9ca115215511"
EVIDENCE_IDS = {"E-BUILD-117", "E-AUTO-081", "E-HIL-141", "E-UX-036"}
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
        "catalog_h": source / "WifiDeviceCatalog.h",
        "catalog_cpp": source / "WifiDeviceCatalog.cpp",
        "adapter_h": source / "BoardWifiPassiveCapture.h",
        "adapter_cpp": source / "BoardWifiPassiveCapture.cpp",
        "contract": source / "check_wifi_devices_contract.py",
    }
    for label, path in files.items():
        require(digest(path) == provenance["source_sha256"][label],
                f"source snapshot mismatch: {label}")
    renderer = files["renderer"].read_text(encoding="utf-8")
    for token in (
            "renderWifiDeviceDetailLiveData()",
            "wifiFrameCapture.lockDeviceChannel(",
            "wifiFrameCapture.unlockDeviceChannel(nowUs)",
            "wifi_device_detail_live",
            "integrated selected-channel radar updates in place"):
        require(token in renderer, f"integrated detail token missing: {token}")
    for token in ("WifiProductView::DeviceRadar", "renderWifiDeviceRadar("):
        require(token not in renderer, f"separate radar route remains: {token}")


def main() -> int:
    require(BUNDLE.is_dir() and SUMMARY.is_file(), "retained evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") ==
            "leshy.wifi_device_live_detail.acceptance.v1" and
            summary.get("status") ==
            "pass_integrated_wifi_device_live_detail",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == EVIDENCE_IDS,
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("schema") ==
            "leshy.wifi_device_live_detail_hil.provenance.v1" and
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
            provenance.get("app_image_bytes") == 2875360 and
            provenance.get("factory_image_bytes") == 2940896 and
            provenance.get("static_ram_bytes") == 198800 and
            provenance.get("linked_flash_bytes") == 2875204 and
            provenance.get("tft_states") == 6,
            "exact build/resource identity mismatch")
    require(summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    verify_source(provenance)

    run = load(BUNDLE / "run/run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_devices_hil.run.v3" and
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
    runner = BUNDLE / "tools/run_1x_wifi_devices_hil.py"
    checker = BUNDLE / "tools/check_wifi_devices_run.py"
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
    require(verified.get("fresh_flashes") == 1 and
            verified.get("manual_button_presses") == 0 and
            verified.get("selected_client_updates", 0) >= 1 and
            verified.get("selected_last_seen_advanced") is True and
            verified.get("channel_hops_during_detail") == 0 and
            verified.get("identity_changed_pixels") == 0 and
            verified.get("live_changed_pixels", 0) > 0 and
            verified.get("chrome_changed_pixels") == 0 and
            verified.get("zero_heap_drift_after_warmup") is True and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_lease_mask") == 0,
            "verified live-detail claims mismatch")
    print(
        "Wi-Fi device live-detail acceptance passed: direct locked-channel "
        "radar, stable identity/chrome, live-only TFT updates and final lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
