#!/usr/bin/env python3
"""Verify an exact fresh physical Sub-GHz frequency-finder run."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


RUN_SCHEMA = "leshy.cc1101_signal_finder_hil.run.v1"
FINDER_SCHEMA = "leshy.cc1101.signal-finder.v1"
SCREEN_NAMES = {
    "modes", "finder_focus", "calibrating", "searching_first",
    "searching_second", "restarted", "stopped_menu", "home_after",
}
WINDOWS = [[300000, 348000], [387000, 464000], [779000, 928000]]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_report(report: dict[str, Any], *, active: bool,
                  state: str) -> None:
    require(report.get("schema") == FINDER_SCHEMA and
            report.get("view") ==
                ("cc1101_finder" if active else "subghz_menu") and
            report.get("state") == state and
            report.get("bins") == 1099 and
            report.get("step_khz") == 250 and
            report.get("tuning_windows_khz") == WINDOWS and
            report.get("baseline_semantics") ==
                "median_of_three_ambient_sweeps" and
            report.get("response_semantics") ==
                "local_rssi_rise_after_common_drift" and
            report.get("rx_only") is True and
            report.get("adapter_active") is active and
            report.get("volatile") is True and
            report.get("current_owner") == "subghz" and
            report.get("current_lease_mask") == 9,
            f"finder {state} ownership/receiver contract mismatch")
    require(report.get("side_effects") == {
        "rejected_strobes": 0, "tx_strobes": 0,
        "pa_table_writes": 0, "fifo_writes": 0,
        "storage_writes": 0,
    }, f"finder {state} side effects differ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--require-ambient-below-threshold",
                        action="store_true")
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
            calibrated.get("calibration_passes") == 3 and
            calibrated.get("sweeps") == 3 and
            int(advanced.get("sweeps", 0)) > 3,
            "median calibration/search progression mismatch")
    if args.require_ambient_below_threshold:
        require(advanced.get("found") is False and
                advanced.get("frequency_khz") == 0 and
                isinstance(advanced.get("response_db"), int) and
                advanced.get("response_db") <
                    advanced.get("response_threshold_db"),
                "ambient run crossed the signal threshold")
    require(restarted.get("schema") == FINDER_SCHEMA and
            restarted.get("state") == "calibrating" and
            restarted.get("calibrated") is False and
            restarted.get("found") is False and
            restarted.get("sweeps") == 0 and
            restarted.get("calibration_passes") == 0 and
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
        matching = [path for path in (root / "frames").glob("*.png")
                    if digest(path) == metadata.get("png_sha256")]
        require(bool(matching), "TFT PNG hash binding mismatch")
        data = matching[0].read_bytes()
        require(len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and
                struct.unpack(">II", data[16:24]) == (240, 320),
                "TFT PNG dimensions differ")
    print("PASS: exact fresh-flash CC1101 signal-finder run is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
