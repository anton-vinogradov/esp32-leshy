#!/usr/bin/env python3
"""Fail closed unless the exact compact-UI/three-second-waterfall proof remains intact."""

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
SUMMARY = ROOT / "tests/hil/evidence/board-01-compact-ui-waterfall-0.96.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-compact-ui-waterfall-0.96"
VERSION = "0.96.0-compact-ui-waterfall"
SOURCE = "4603340d187e27c8ef3b150a02bf70a3bbb4a267"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "341f4df3ef54fa139a8e63d71464c7c03f0ecad7d1a5d44f59193e1446f0c4b6"
FACTORY = "77cf489d3e5872387128665fcc808dbf86ea982a7975e24a9cdbb48ad212953d"
APP = "c6227edde37fbbe175214ee0b2be17aa4411fa1319a6eb4dd26d96d884df6e66"
MAP = "3fcc57b5b51dc6040d185162960a9bc99d464fdea0d082b616218ffe6d58a1a8"
RUNNER = "d065f8ca7b6e54231e95f0da5bb596ded57855dd6f688ab3e6e1fbfbde9868d1"
CHECKER = "c2fca705ee189ce661747a6ec8a065b298dc6d05cb980f9391fd9e59f819e618"
GATE = "990f8deb3857ae0b700c0dee7b2fc7edbaeaf3a5ea239fcdcd1e0a3c1be86caa"
INDEX = "a036a4009e2bb1735005f7ed6f205b2d4cc03aa68ba51b3ffe7ea237e8402d8e"
PROVENANCE = "9e0234cfc970281833d321e087e2d1a714f26e4947268fb33470684d82f847f2"
RUN = "b59b7f58f44f47a5c490283e708e7d5b16e46c88bb0349c64d5f4269ced34328"
OPAQUE = {"firmware.bin", "firmware.factory.bin", "firmware.elf", "firmware.map"}
FRAME_HASHES = {
    "frames/home-top.png": "6f4dacde54beb4745c90afd6a16c5f465eef6262ce0bf35f2e996292c8472920",
    "frames/home-en.png": "53b72994fab1f5adf6c3a05f9a128ea43d8fb962e68fdda93559dd8b69a4c3ed",
    "frames/device.png": "1a58a881856f60d3f751b2cb47de58a4cf61ca1e6147e27f2b780b88f18d672f",
    "frames/cc-band-menu.png": "bd5a7c6eee5ee0037abcf5880173393bb09aadb7cb0e8e877a81d55a86d5b277",
    "frames/nrf-waterfall.png": "b86dca61075142a1698a5ee5d87c668577926a1518be5347a81edd38d06b99e4",
    "frames/cc-waterfall.png": "70ad1ca3a21dc3319de0458f96e948b61ad79fac6a99a072bfc75c3bd77bcf19",
}


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
        path = BUNDLE / relative
        if tracked_only and relative in OPAQUE:
            continue
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    require(failures, OPAQUE <= indexed, "opaque candidate bindings missing")


def verify_waterfall(failures: list[str], label: str,
                     report: dict[str, Any], band: str | None) -> None:
    require(failures,
            report.get("history_rows") == 112 and
            report.get("waterfall_fill_target_us") == 3_000_000 and
            report.get("waterfall_row_period_us") == 26_785 and
            report.get("waterfall_full") is True and
            int(report.get("waterfall_rows_emitted", 0)) >= 112 and
            report.get("state") == "running" and
            report.get("rx_only") is True,
            f"{label} waterfall/RX contract mismatch")
    elapsed = report.get("waterfall_fill_elapsed_us")
    host = report.get("host_fill_elapsed_ms")
    require(failures, isinstance(elapsed, int) and 2_700_000 <= elapsed <= 3_000_000,
            f"{label} device fill time outside 2.7..3.0 s")
    require(failures, isinstance(host, (int, float)) and 2700.0 <= host <= 3100.0,
            f"{label} host fill time outside 2.7..3.1 s")
    if band is not None:
        require(failures, report.get("band") == band,
                f"{label} band mismatch")
    side_effects = report.get("side_effects", {})
    require(failures,
            isinstance(side_effects, dict) and
            all(value == 0 for value in side_effects.values()),
            f"{label} side effect detected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.96 compact UI/waterfall evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.product_home_acceptance.v1" and
            summary.get("status") == "pass_compact_ui_waterfall_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-097", "E-AUTO-061", "E-HIL-121", "E-UX-020",
                "E-RADIO-007"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("checker_sha256") == CHECKER and
            candidate.get("gate_sha256") == GATE and
            [candidate.get("firmware_bytes"), candidate.get("factory_bytes"),
             candidate.get("static_ram_bytes"), candidate.get("linked_flash_bytes")] ==
                [1507408, 1572944, 159888, 1507264],
            "candidate identity/size mismatch")
    require(failures, evidence == {
        "artifact_index_sha256": INDEX, "files": 52,
        "provenance_sha256": PROVENANCE, "run_sha256": RUN,
        "tft_states": 14,
    }, "evidence summary mismatch")
    require(failures, verified.get("compact_navigation") == {
        "content_top_px": 32, "header_height_px": 26,
        "menu_row_gap_px": 5, "menu_row_height_px": 60,
        "menu_row_width_px": 216, "nested_title_inside_header": True,
        "row_text_inset_px": 12, "row_text_vertically_centered": True,
        "touch_geometry_shared": True, "visible_menu_rows": 4,
    }, "compact navigation contract mismatch")
    require(failures,
            verified.get("waterfall_timing", {}).get("fill_target_us") == 3_000_000 and
            verified.get("waterfall_timing", {}).get("history_rows") == 112 and
            verified.get("waterfall_timing", {}).get("row_period_us") == 26_785 and
            verified.get("diagnostic_heap_stabilized") is True and
            verified.get("diagnostic_heap_samples") == 2 and
            verified.get("heap") == [221820, 156712, 137360] and
            verified.get("software_rx_only") is True and
            verified.get("manual_button_presses") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified runtime claims mismatch")

    verify_manifest(failures, args.tracked_only)
    for relative, expected in FRAME_HASHES.items():
        require(failures, (BUNDLE / relative).is_file() and
                digest(BUNDLE / relative) == expected,
                f"exact TFT frame mismatch: {relative}")

    run = load(BUNDLE / "run.json")
    reports = run.get("reports", {})
    require(failures,
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            len(run.get("screens", {})) == 14 and
            run.get("candidate", {}).get("source_commit") == SOURCE and
            run.get("cleanup_after", {}).get("complete") is True and
            run.get("cleanup_after", {}).get("final_state", {}).get("page") == "home" and
            run.get("cleanup_after", {}).get("final_state", {}).get("runtime_owner") == "none" and
            run.get("cleanup_after", {}).get("final_state", {}).get("lease_mask") == 0,
            "physical route/final cleanup mismatch")
    samples = run.get("boot_metrics_samples", [])
    require(failures, len(samples) == 2 and all(
        [sample.get("heap_total"), sample.get("heap_free"),
         sample.get("heap_min_free")] == [221820, 156712, 137360]
        for sample in samples), "stabilized diagnostic heap mismatch")
    verify_waterfall(failures, "nRF24", reports.get("nrf_spectrum", {}), None)
    for band, key in (("315", "cc_fill_315"), ("433", "cc_spectrum"),
                      ("868", "cc_fill_868"), ("915", "cc_fill_915")):
        verify_waterfall(failures, f"CC{band}", reports.get(key, {}), band)

    theme = git_blob("firmware/leshy1/src/ui/VisualTheme.h")
    components = git_blob("firmware/leshy1/src/ui/UiComponents.h")
    viewport = git_blob("firmware/leshy1/src/apps/spectrum/SpectrumViewport.h")
    renderer = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    platform = git_blob("firmware/leshy1/platformio.ini")
    runner = git_blob("tools/run_1x_product_home_hil.py")
    require(failures, theme is not None and all(token in theme for token in (
        b"HeaderHeight = 26", b"TitleY = 5", b"ContentTop = 32",
        b"HomeRowHeight = 60", b"HomeRowGap = 5")),
        "compact theme source mismatch")
    require(failures, components is not None and all(token in components for token in (
        b"Layout::TitleY", b"Layout::ContentTop", b"Layout::HomeRowHeight")),
        "shared geometry source mismatch")
    require(failures, viewport is not None and all(token in viewport for token in (
        b"kHistoryRows = 112", b"kWaterfallFillUs = 3000000ULL",
        b"kWaterfallFillUs / kHistoryRows")),
        "three-second viewport source mismatch")
    require(failures, renderer is not None and all(token in renderer for token in (
        b"kInteractiveRowTextInset = 12", b"menuRowTextTop(Rect bounds)",
        b"void serviceSpectrumWaterfallCadence()",
        b"SpectrumViewport::kWaterfallRowPeriodUs",
        b"waterfall_fill_target_us", b"waterfall_full",
        b"serviceSpectrumWaterfallCadence();")),
        "compact renderer/waterfall cadence source mismatch")
    require(failures, platform is not None and
            b'LESHY1_VERSION=\\"0.96.0-compact-ui-waterfall\\"' in platform,
            "exact build version source mismatch")
    require(failures, runner is not None and all(token in runner for token in (
        b"WATERFALL_ROWS = 112", b"WATERFALL_FILL_US = 3_000_000",
        b"host_fill_elapsed_ms", b'("315", ("up", "up", "up"))')),
        "physical runner timing/band coverage mismatch")

    if not args.tracked_only:
        for name, expected in (("firmware.bin", FIRMWARE),
                               ("firmware.factory.bin", FACTORY),
                               ("firmware.elf", APP), ("firmware.map", MAP)):
            require(failures, (BUNDLE / name).is_file() and
                    digest(BUNDLE / name) == expected,
                    f"opaque candidate mismatch: {name}")
        if (BUNDLE / "firmware.bin").is_file():
            require(failures, app_elf_sha256(BUNDLE / "firmware.bin") == APP,
                    "embedded ELF identity mismatch")
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
        "status": "pass", "version": VERSION, "tft_states": 14,
        "waterfall_rows": 112, "fill_target_ms": 3000,
        "cc_bands": ["315", "433", "868", "915"],
        "manual_button_presses": 0, "final_lease_mask": 0,
        "evidence_mode": "tracked" if args.tracked_only else "full",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
