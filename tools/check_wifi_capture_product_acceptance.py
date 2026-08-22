#!/usr/bin/env python3
"""Verify retained board-01 evidence for Wi-Fi packet recording."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-capture-product-0.110"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-capture-product-0.110.json"
VERSION = "0.110.0-wifi-capture"
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
    require(failures, BUNDLE.is_dir(), "Wi-Fi packet recorder bundle missing")
    require(failures, SUMMARY.is_file(), "Wi-Fi packet recorder summary missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    run = load(BUNDLE / "main/run.json")
    manifest = BUNDLE / "artifacts.sha256"
    require(failures,
            summary.get("schema") ==
                "leshy.wifi_capture_product.acceptance.v1" and
            summary.get("status") ==
                "pass_wifi_capture_product_checkpoint" and
            summary.get("board") == "board-01",
            "summary identity mismatch")
    require(failures,
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            len(str(provenance.get("firmware_source_commit", ""))) == 40 and
            provenance.get("static_ram_bytes") == 179680 and
            provenance.get("linked_flash_bytes") == 1571740 and
            provenance.get("tft_states") == 7,
            "candidate provenance mismatch")
    require(failures, summary.get("candidate") == provenance,
            "summary/provenance mismatch")
    require(failures,
            summary.get("evidence", {}).get("artifact_index_sha256") ==
                digest(manifest), "artifact index hash mismatch")
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
            run.get("schema") == "leshy.wifi_capture_product_hil.run.v1" and
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
            verified.get("first_frames_reported", 0) >=
                verified.get("first_frames_retained", 0) >= 1 and
            verified.get("first_frames_retained", 0) <= 16 and
            verified.get("second_frames_reported", 0) >=
                verified.get("second_frames_retained", 0) >= 1 and
            verified.get("invalid_frames") == 0 and
            verified.get("first_pcap_records") ==
                verified.get("first_frames_retained") and
            verified.get("second_pcap_records") ==
                verified.get("second_frames_retained") and
            verified.get("first_pcap_bytes", 0) >= 24 and
            verified.get("live_changed_pixels", 0) > 0 and
            verified.get("static_changed_pixels") == 0 and
            verified.get("passive_receive_only") is True and
            verified.get("bounded_ram_capture") is True and
            verified.get("privacy_confirmation_and_cancel") is True and
            verified.get("raw_payload_retained_in_repository") is False and
            verified.get("two_complete_wifi_lifecycles") is True and
            verified.get("zero_post_warm_heap_drift") is True and
            verified.get("heap_minimum_floor_bytes", 0) >= 70000 and
            verified.get("persistent_generation_unchanged") is True and
            verified.get("physical_sd_write_calls") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("final_safety_latched") is False and
            verified.get("final_lease_mask") == 0,
            "verified physical outcome mismatch")
    screen_names = {
        "wifi-capture-setup", "wifi-capture-running-first",
        "wifi-capture-running-second", "wifi-capture-result",
        "wifi-capture-confirm", "wifi-menu-after-capture", "home-final",
    }
    require(failures,
            {path.stem for path in (BUNDLE / "main/frames").glob("*.png")} ==
                screen_names, "retained TFT screen set mismatch")
    require(failures,
            not any((BUNDLE / "main").rglob("*.pcap")) and
            provenance.get("runner_sha256") == digest(BUNDLE / "runner.py") and
            provenance.get("checker_sha256") == digest(BUNDLE / "checker.py") and
            provenance.get("run_sha256") == digest(BUNDLE / "main/run.json"),
            "privacy or retained tool/run hash mismatch")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(
        "Wi-Fi packet recorder acceptance passed: direct passive bounded "
        "PCAP, privacy confirmation, changed-metric-only redraw, stable heap "
        "and final lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
