#!/usr/bin/env python3
"""Verify retained board-01 evidence for passive Wi-Fi devices."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-devices-0.108"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-devices-0.108.json"
VERSION = "0.108.0-wifi-devices"
CID = "FE343253440000002000000055019CB7"
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    require(failures, BUNDLE.is_dir(), "Wi-Fi devices bundle missing")
    require(failures, SUMMARY.is_file(), "Wi-Fi devices summary missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    run = load(BUNDLE / "main/run.json")
    manifest = BUNDLE / "artifacts.sha256"
    require(failures,
            summary.get("schema") == "leshy.wifi_devices.acceptance.v1" and
            summary.get("status") == "pass_wifi_devices_checkpoint" and
            summary.get("board") == "board-01",
            "summary identity mismatch")
    require(failures,
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            len(str(provenance.get("firmware_source_commit", ""))) == 40 and
            provenance.get("static_ram_bytes") == 178360 and
            provenance.get("linked_flash_bytes") == 1566368 and
            provenance.get("tft_states") == 6,
            "candidate provenance mismatch")
    require(failures, summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    require(failures,
            summary.get("evidence", {}).get("artifact_index_sha256") ==
                digest(manifest),
            "artifact index hash mismatch")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"malformed artifact line: {line!r}")
            continue
        expected, relative = parts
        path = BUNDLE / relative
        if not path.is_file():
            require(failures, relative.endswith(OPAQUE_SUFFIXES),
                    f"tracked artifact missing: {relative}")
            continue
        require(failures, digest(path) == expected,
                f"artifact hash mismatch: {relative}")
    require(failures,
            run.get("schema") == "leshy.wifi_devices_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("candidate", {}).get("version") == VERSION and
            run.get("candidate", {}).get("source_commit") ==
                provenance.get("firmware_source_commit") and
            run.get("candidate", {}).get("flash_mode") == "fresh" and
            run.get("candidate", {}).get("firmware_sha256") ==
                provenance.get("firmware_sha256") and
            run.get("candidate", {}).get("app_elf_sha256") ==
                provenance.get("app_elf_sha256") and
            run.get("expected_cid") == CID,
            "passing run identity mismatch")
    verified = summary.get("verified", {})
    require(failures,
            verified.get("fresh_exact_flash_pass") is True and
            verified.get("manual_button_presses") == 0 and
            verified.get("unique_devices_first", 0) >= 1 and
            verified.get("unique_devices_second", 0) >= 1 and
            verified.get("client_frames_accepted_second", 0) >= 1 and
            verified.get("channel_hops_second", 0) >= 13 and
            verified.get("client_frames_dropped") == 0 and
            verified.get("access_point_beacons_excluded") is True and
            verified.get("passive_client_inference_only") is True and
            verified.get("live_content_changed_pixels", 0) > 0 and
            verified.get("live_chrome_changed_pixels") == 0 and
            verified.get("detail_changed_pixels") == 0 and
            verified.get("two_complete_wifi_lifecycles") is True and
            verified.get("zero_heap_drift_after_warmup") is True and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_lease_mask") == 0,
            "verified physical outcome mismatch")
    screen_names = {
        "wifi-menu", "wifi-menu-after", "wifi-devices-first",
        "wifi-devices-second", "wifi-device-detail-first",
        "wifi-device-detail-second",
    }
    require(failures,
            {path.stem for path in (BUNDLE / "main/frames").glob("*.png")} ==
                screen_names,
            "retained TFT screen set mismatch")
    require(failures,
            provenance.get("runner_sha256") == digest(BUNDLE / "runner.py") and
            provenance.get("checker_sha256") == digest(BUNDLE / "checker.py") and
            provenance.get("run_sha256") == digest(BUNDLE / "main/run.json"),
            "retained tool/run hash mismatch")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(
        "Wi-Fi devices acceptance passed: real passive clients, 13-channel "
        "coverage, data-only redraw, frozen detail and final lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
