#!/usr/bin/env python3
"""Verify a fresh physical 2.4 GHz signal-finder run."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


RUN_SCHEMA = "leshy.nrf24_signal_finder_hil.run.v1"
FINDER_SCHEMA = "leshy.nrf24.signal-finder.v1"
SCREEN_NAMES = {
    "modes", "finder_focus", "calibrating", "searching_first",
    "searching_second", "restarted", "stopped_menu", "home_after",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_report(report: dict[str, Any], *, active: bool,
                  state: str) -> None:
    require(report.get("schema") == FINDER_SCHEMA and
            report.get("view") ==
                ("nrf24_finder" if active else "nrf24_menu") and
            report.get("state") == state and
            report.get("modules") == 3 and
            report.get("active_slot_mask") == 7 and
            report.get("all_available_antennas") is True and
            report.get("rx_only") is True and
            report.get("adapter_active") is active and
            report.get("volatile") is True and
            report.get("current_owner") == "spectrum24" and
            report.get("current_lease_mask") == 9,
            f"finder {state} ownership/receiver contract mismatch")
    require(report.get("side_effects") == {
        "tx_mode_entries": 0, "tx_payload_commands": 0,
        "cc_command_strobes": 0, "storage_writes": 0,
    }, f"finder {state} side effects differ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    run_file = root / "run.json"
    require(run_file.is_file(), "run.json missing")
    run = json.loads(run_file.read_text(encoding="utf-8"))
    candidate = run.get("candidate", {})
    require(run.get("schema") == RUN_SCHEMA and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [], "run did not pass")
    require(candidate.get("version") == args.expected_version and
            candidate.get("source_commit") == args.source_commit and
            candidate.get("flashed") is True and
            candidate.get("flash_mode") == "fresh" and
            run.get("expected_cid") == args.expected_cid,
            "candidate identity mismatch")
    firmware = root / "firmware.bin"
    require(firmware.is_file() and
            digest(firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            "candidate bytes/hash mismatch")

    boot = run.get("boot", {})
    after = run.get("metrics_after", {})
    require(boot.get("version") == args.expected_version and
            boot.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            boot.get("heap_free") == after.get("heap_free") and
            boot.get("heap_min_free") == after.get("heap_min_free"),
            "boot identity or heap invariant mismatch")
    before_store = run.get("recovery_before", {})
    after_store = run.get("recovery_after", {})
    require(before_store.get("expected_fingerprint") == args.expected_cid and
            before_store.get("observed_fingerprint") == args.expected_cid and
            after_store.get("expected_fingerprint") == args.expected_cid and
            after_store.get("observed_fingerprint") == args.expected_cid and
            before_store.get("generation") == after_store.get("generation") and
            before_store.get("observations") == after_store.get("observations") and
            before_store.get("physical_write_calls") ==
                after_store.get("physical_write_calls") == 0,
            "exact-CID storage continuity mismatch")

    calibrated = run.get("calibrated", {})
    advanced = run.get("advanced", {})
    restarted = run.get("restarted", {})
    stopped = run.get("stopped", {})
    verify_report(calibrated, active=True, state="searching")
    verify_report(advanced, active=True, state="searching")
    verify_report(stopped, active=False, state="idle")
    require(calibrated.get("calibrated") is True and
            calibrated.get("calibration_windows") == 2 and
            calibrated.get("windows") == 2 and
            int(advanced.get("windows", 0)) > 2 and
            advanced.get("baseline_semantics") ==
                "minimum_of_two_ambient_windows" and
            advanced.get("response_semantics") ==
                "local_rise_above_baseline",
            "calibration/window progression mismatch")
    require(restarted.get("schema") == FINDER_SCHEMA and
            restarted.get("state") == "calibrating" and
            restarted.get("calibrated") is False and
            restarted.get("found") is False and
            restarted.get("windows") == 0 and
            restarted.get("calibration_windows") == 0 and
            restarted.get("adapter_active") is True,
            "Again did not reset ambient calibration")

    changes = run.get("pixel_changes", {})
    require(changes.get("graph_changed_pixels", 0) > 0 and
            changes.get("header_changed_pixels") == 0 and
            changes.get("legend_changed_pixels") == 0 and
            changes.get("axis_changed_pixels") == 0 and
            changes.get("footer_changed_pixels") == 0,
            "live redraw escaped dynamic result/graph regions")
    require(run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("cleanup_after", {}).get("complete") is True and
            run.get("cleanup_after", {}).get("final_state", {}).get(
                "lease_mask") == 0 and
            run.get("cleanup_after", {}).get("final_state", {}).get(
                "page") == "home",
            "input/safety/final cleanup mismatch")

    screens = run.get("screens", {})
    require(set(screens) == SCREEN_NAMES, "TFT state inventory mismatch")
    for metadata in screens.values():
        png_hash = metadata.get("png_sha256")
        matching = [path for path in (root / "frames").glob("*.png")
                    if digest(path) == png_hash]
        require(bool(matching), "TFT PNG hash binding mismatch")
        data = matching[0].read_bytes()
        require(len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and
                struct.unpack(">II", data[16:24]) == (240, 320),
                "TFT PNG dimensions differ")
    print("PASS: exact fresh-flash nRF24 signal-finder run is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
