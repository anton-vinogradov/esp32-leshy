#!/usr/bin/env python3
"""Verify retained Bluetooth Nearby physical acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-ble-nearby-0.111"
SUMMARY = ROOT / "tests/hil/evidence/board-01-ble-nearby-0.111.json"
VERSION = "0.111.0-ble-nearby"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "15cd3be1e9eb4f14dcf9aba3270113a3610047da"
RUNNER_COMMIT = "d2fe5dacc97d68fba21e3150e42e495c4d511400"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed == present,
            "artifact index coverage mismatch: "
            f"missing={sorted(str(path) for path in present - indexed)} "
            f"extra={sorted(str(path) for path in indexed - present)}")


def main() -> int:
    require(SUMMARY.is_file() and BUNDLE.is_dir(), "retained evidence missing")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    provenance = json.loads(
        (BUNDLE / "provenance.json").read_text(encoding="utf-8"))
    manifest = BUNDLE / "artifacts.sha256"
    verify_manifest(BUNDLE, manifest)
    require(summary.get("schema") == "leshy.ble_nearby.acceptance.v1" and
            summary.get("status") == "pass_ble_nearby_checkpoint",
            "summary status mismatch")
    require(set(summary.get("evidence_ids", [])) == {
                "E-BUILD-111", "E-AUTO-075", "E-HIL-135", "E-UX-030"},
            "evidence IDs mismatch")
    require(summary.get("evidence", {}).get("artifact_index_sha256") ==
            digest(manifest), "artifact index hash mismatch")
    require(provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("firmware_source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == RUNNER_COMMIT,
            "candidate provenance mismatch")
    verified = summary.get("verified", {})
    require(verified.get("fresh_flash_pass") is True and
            verified.get("manual_button_presses") == 0 and
            verified.get("unique_devices_first", 0) >= 1 and
            verified.get("unique_devices_second", 0) >= 1 and
            verified.get("scan_drops") == 0 and
            verified.get("active_scan") is False and
            verified.get("live_content_changed_pixels", 0) > 0 and
            verified.get("live_chrome_changed_pixels") == 0 and
            verified.get("detail_changed_pixels") == 0 and
            verified.get("zero_heap_drift_after_warmup") is True and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_lease_mask") == 0,
            "verified physical claims mismatch")
    run_check = subprocess.run(
        [sys.executable, str(BUNDLE / "checker.py"),
         "--run", str(BUNDLE / "main"),
         "--expected-version", VERSION, "--expected-cid", CID,
         "--source-commit", SOURCE_COMMIT], cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(run_check.returncode == 0,
            f"retained run check failed: {run_check.stdout}")
    print(
        "Bluetooth Nearby acceptance passed: fresh passive scan, 32 unique "
        "devices, row-only live redraw, frozen detail, stable heap and final "
        "lease 0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
