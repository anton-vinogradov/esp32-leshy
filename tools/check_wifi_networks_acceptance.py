#!/usr/bin/env python3
"""Verify retained board-01 evidence for Wi-Fi nearby networks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-networks-0.107"
SUMMARY = ROOT / "tests/hil/evidence/board-01-wifi-networks-0.107.json"
VERSION = "0.107.0-wifi-networks"
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
    require(failures, BUNDLE.is_dir(), "Wi-Fi networks bundle missing")
    require(failures, SUMMARY.is_file(), "Wi-Fi networks summary missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    run = load(BUNDLE / "main/run.json")
    fresh = load(BUNDLE / "fresh-flash-diagnostic-run.json")
    manifest = BUNDLE / "artifacts.sha256"
    require(failures,
            summary.get("schema") == "leshy.wifi_networks.acceptance.v1" and
            summary.get("status") == "pass_wifi_networks_checkpoint" and
            summary.get("board") == "board-01",
            "summary identity mismatch")
    require(failures,
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            len(str(provenance.get("firmware_source_commit", ""))) == 40 and
            provenance.get("static_ram_bytes") == 175168 and
            provenance.get("linked_flash_bytes") == 1558808 and
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
            run.get("schema") == "leshy.wifi_networks_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("candidate", {}).get("version") == VERSION and
            run.get("candidate", {}).get("source_commit") ==
                provenance.get("firmware_source_commit") and
            run.get("candidate", {}).get("firmware_sha256") ==
                provenance.get("firmware_sha256") and
            run.get("candidate", {}).get("app_elf_sha256") ==
                provenance.get("app_elf_sha256") and
            run.get("expected_cid") == CID,
            "passing run identity mismatch")
    require(failures,
            fresh.get("passed") is False and
            fresh.get("failures") == ["heap free did not return to boot baseline"] and
            fresh.get("candidate", {}).get("flash_mode") == "fresh" and
            fresh.get("candidate", {}).get("firmware_sha256") ==
                provenance.get("firmware_sha256"),
            "fresh-flash diagnostic predecessor mismatch")
    verified = summary.get("verified", {})
    require(failures,
            verified.get("manual_button_presses") == 0 and
            verified.get("unique_networks_first", 0) >= 1 and
            verified.get("unique_networks_second", 0) >= 1 and
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
        "wifi-menu", "wifi-menu-after", "wifi-networks-first",
        "wifi-networks-second", "wifi-network-detail-first",
        "wifi-network-detail-second",
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
        "Wi-Fi networks acceptance passed: real unique APs, data-only live "
        "redraw, frozen detail screen, two stable lifecycles and final lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
