#!/usr/bin/env python3
"""Fail closed unless the exact receiver-paced waterfall proof remains intact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-receiver-paced-waterfall-0.99.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-receiver-paced-waterfall-0.99"
VERSION = "0.99.0-wifi-spectrum-modes"
SOURCE = "9d8fbca486eef3df1885c1ff036400db9db9d388"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "461aa64ae8f5d3e420ed8768e6a2dfa7ba238b1f9715c71f68489c4bd10f6876"
APP = "8aea18ed91079f773c8999e25ee2be5fc322d4893c048718a5f8bf450c159cda"
RUNNER = "387aca38519942b0196b8208de46870664dc34a00590f985dcc2e522247344e0"
CHECKER = "953104a99c0df70849dfcf5f9178c90483b94614efa39c56f133291a933d94ca"
GATE = "990f8deb3857ae0b700c0dee7b2fc7edbaeaf3a5ea239fcdcd1e0a3c1be86caa"
INDEX = "4e244091103de56241ad863cc61112b04f1fef34f7f36c6c450140ffd8f08235"
PROVENANCE = "58492624e29cd415036d47da8d0227368aae6c24f2f83b7b0a6ceb43e26a9012"
RUN = "128e27e37daae7784f41fcda5001218990a5629ce3e21680c6ea1aef004eb021"
OPAQUE = {"firmware.bin"}
FRAME_HASHES = {
    "frames/nrf-waterfall.png": "0690e361b249cbcf4891a7bd68ff5f6df366abe71af0e39929d0cf2ecab42269",
    "frames/nrf-waterfall-next.png": "df7e229a244b6f6ddde37a0103daf7a6125b321e7633b55f476b5912c4a3ca67",
    "frames/nrf-traffic-waterfall.png": "965f0ae24079ba6e2594bde821e8dea1d6ba7b4d279020f304fad52fda494ce9",
    "frames/cc-waterfall.png": "713ed3c7b60f1f001d99aec0c5017cbc9d16595ef194ba2f4cc971383f735ee1",
    "frames/cc-waterfall-next.png": "6a92a0073056f54243dbc4f7079495fc8da609cc328cf99673fb805420656923",
}
REPORTS = (
    ("nrf_signal", "nrf_waterfall", None),
    ("nrf_traffic", "nrf_traffic", None),
    ("cc315", "cc_fill_315", "315"),
    ("cc433", "cc_waterfall", "433"),
    ("cc868", "cc_fill_868", "868"),
    ("cc915", "cc_fill_915", "915"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_manifest(failures: list[str], tracked_only: bool) -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX,
            "artifact index mismatch")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        indexed.add(relative)
        if tracked_only and relative in OPAQUE:
            continue
        path = BUNDLE / relative
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    require(failures, OPAQUE <= indexed, "opaque candidate binding missing")


def verify_report(failures: list[str], label: str,
                  report: dict[str, Any], band: str | None) -> None:
    consumed = report.get("waterfall_measurements_consumed")
    require(failures,
            report.get("waterfall_cadence") == "receiver_sweep" and
            report.get("history_rows") == 224 and
            report.get("waterfall_full") is True and
            isinstance(consumed, int) and consumed >= 224 and
            report.get("waterfall_rows_emitted") == consumed and
            report.get("waterfall_source_sweeps") == consumed and
            report.get("waterfall_measurements_skipped") == 0 and
            report.get("waterfall_fill_target_us") == 0 and
            report.get("waterfall_row_period_us") == 0 and
            report.get("state") == "running" and
            report.get("rx_only") is True,
            f"{label} one-sweep-per-pixel contract mismatch")
    if band is not None:
        require(failures, report.get("band") == band and report.get("bins") == 64,
                f"{label} band/bin contract mismatch")
        wire = report.get("wire", {})
        require(failures, all(wire.get(key) == 0 for key in (
            "receive_ready_timeouts", "transient_retries",
            "select_ready_timeouts", "recovery_attempts", "recoveries")),
            f"{label} exact run unexpectedly used retry/recovery")
    side_effects = report.get("side_effects", {})
    require(failures, isinstance(side_effects, dict) and
            all(value == 0 for value in side_effects.values()),
            f"{label} side effect detected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.99 receiver-paced waterfall evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.receiver_paced_waterfall_acceptance.v1" and
            summary.get("status") == "pass_receiver_paced_waterfall_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-100", "E-AUTO-064", "E-HIL-124", "E-UX-023",
                "E-RADIO-010"],
            "summary identity mismatch")
    require(failures,
            candidate == {
                "app_elf_sha256": APP,
                "checker_sha256": CHECKER,
                "firmware_bytes": 1511360,
                "firmware_sha256": FIRMWARE,
                "gate_sha256": GATE,
                "linked_flash_bytes": 1510960,
                "run_sha256": RUN,
                "runner_sha256": RUNNER,
                "schema": "leshy.receiver_paced_waterfall.provenance.v1",
                "source_commit": SOURCE,
                "static_ram_bytes": 205296,
                "version": VERSION,
            }, "candidate identity/size mismatch")
    require(failures, evidence == {
        "artifact_index_sha256": INDEX, "files": 58,
        "provenance_sha256": PROVENANCE, "run_sha256": RUN,
        "tft_states": 17,
    }, "evidence summary mismatch")
    require(failures,
            verified.get("cadence") ==
                "one_complete_receiver_sweep_per_physical_row" and
            verified.get("physical_row_height_px") == 1 and
            verified.get("history_rows") == 224 and
            verified.get("graph_width_px") == 240 and
            verified.get("nrf_source_bins") == 83 and
            verified.get("cc_source_bins") == 64 and
            verified.get("horizontal_interpolation") is False and
            verified.get("nrf_metrics") == ["signal", "traffic"] and
            verified.get("nrf_modules") == 3 and
            verified.get("nrf_active_slot_mask") == 7 and
            verified.get("all_available_nrf_antennas") is True and
            verified.get("diagnostic_heap_stabilized") is True and
            verified.get("heap") == [176412, 111372, 92020] and
            verified.get("storage_generation") == 95 and
            verified.get("storage_observations") == 0 and
            verified.get("software_rx_only") is True and
            verified.get("physical_rf_silence_measured") is False and
            verified.get("manual_button_presses") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified receiver/display/runtime claims mismatch")

    verify_manifest(failures, args.tracked_only)
    require(failures, digest(BUNDLE / "provenance.json") == PROVENANCE and
            digest(BUNDLE / "run.json") == RUN and
            digest(BUNDLE / "runner.py") == RUNNER and
            digest(BUNDLE / "checker.py") == CHECKER and
            digest(BUNDLE / "connected-candidate-gate.sh") == GATE,
            "retained provenance/run/tool binding mismatch")
    for relative, expected in FRAME_HASHES.items():
        require(failures, (BUNDLE / relative).is_file() and
                digest(BUNDLE / relative) == expected,
                f"exact TFT frame mismatch: {relative}")

    run = load(BUNDLE / "run.json")
    require(failures,
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            len(run.get("screens", {})) == 17 and
            run.get("candidate", {}).get("source_commit") == SOURCE and
            run.get("recovery_before", {}).get("generation") == 95 and
            run.get("recovery_after", {}).get("generation") == 95 and
            run.get("cleanup_after", {}).get("complete") is True and
            run.get("cleanup_after", {}).get("final_state", {}).get("page") == "home" and
            run.get("cleanup_after", {}).get("final_state", {}).get("runtime_owner") == "none" and
            run.get("cleanup_after", {}).get("final_state", {}).get("lease_mask") == 0 and
            run.get("waterfall_pixel_changes") == {
                "cc": {"chrome_changed_pixels": 0, "graph_changed_pixels": 480},
                "nrf": {"chrome_changed_pixels": 0, "graph_changed_pixels": 2621},
            }, "physical route/pixel/final cleanup mismatch")
    reports = run.get("reports", {})
    for label, key, band in REPORTS:
        verify_report(failures, label, reports.get(key, {}), band)
    require(failures,
            reports.get("nrf_waterfall", {}).get("modules") == 3 and
            reports.get("nrf_waterfall", {}).get("active_slot_mask") == 7 and
            reports.get("nrf_waterfall", {}).get("all_available_antennas") is True and
            reports.get("nrf_waterfall", {}).get("channels") == 83,
            "all-available nRF antenna contract mismatch")

    viewport = git_blob("firmware/leshy1/src/apps/spectrum/SpectrumViewport.h")
    renderer = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    touch = git_blob("firmware/leshy1/src/platform/arduino/BoardTouchInput.cpp")
    cc_adapter = git_blob(
        "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp")
    platform = git_blob("firmware/leshy1/platformio.ini")
    runner = git_blob("tools/run_1x_product_home_hil.py")
    checker = git_blob("tools/check_product_home_run.py")
    require(failures, viewport is not None and all(token in viewport for token in (
        b"kDisplayColumns = 240", b"kHistoryRows = 224")),
        "one-pixel viewport source mismatch")
    require(failures, renderer is not None and all(token in renderer for token in (
        b"spectrumWaterfallLastSourceSweep", b"newlyCompleted > 1U",
        b"spectrumWaterfallMeasurementsSkipped", b"receiver_sweep",
        b"wifiChannelGridTone", b"Nrf24SpectrumMetric::Traffic")),
        "receiver-paced renderer/source semantics mismatch")
    require(failures, touch is not None and all(token in touch for token in (
        b"getTouchRawZ", b"getTouch(&x, &y")),
        "non-blocking idle touch source mismatch")
    require(failures, cc_adapter is not None and all(token in cc_adapter for token in (
        b"kSpectrumSpiHz = 4000000", b"recoverReceive()")),
        "CC1101 4 MHz/bounded recovery source mismatch")
    require(failures, platform is not None and
            b'LESHY1_VERSION=\\"0.99.0-wifi-spectrum-modes\\"' in platform,
            "exact build version source mismatch")
    require(failures, runner is not None and checker is not None and all(
        token in runner and token in checker for token in (
            b"waterfall_measurements_consumed",
            b"waterfall_measurements_skipped", b"receiver_sweep")),
        "runner/checker receiver-paced source mismatch")

    if not args.tracked_only:
        require(failures, (BUNDLE / "firmware.bin").is_file() and
                digest(BUNDLE / "firmware.bin") == FIRMWARE and
                app_elf_sha256(BUNDLE / "firmware.bin") == APP,
                "opaque exact candidate mismatch")
        check = subprocess.run(
            [str(BUNDLE / "checker.py"), "--run", str(BUNDLE),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")})
        require(failures, check.returncode == 0,
                f"retained independent checker failed: {check.stdout}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "tft_states": 17,
        "waterfall_rows": 224, "row_height_px": 1,
        "cadence": "receiver_sweep", "skipped_measurements": 0,
        "nrf_modules": 3, "cc_bands": ["315", "433", "868", "915"],
        "final_lease_mask": 0,
        "evidence_mode": "tracked" if args.tracked_only else "full",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
