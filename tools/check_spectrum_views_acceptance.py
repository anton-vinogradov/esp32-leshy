#!/usr/bin/env python3
"""Fail closed unless the exact 0.92 spectrum-view proof is intact."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-spectrum-views-0.92.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-spectrum-views-0.92"
VERSION = "0.92.0-spectrum-views"
SOURCE = "89f185f5309495d27918eaeb16490cfa8f8ce9ac"
RUNNERS = "9499a1978a0bddb0b4cae8e5d28f03222299bf00"
FIRMWARE = "e5fded9b4bf7781bb8424d34fd1af874db242d3c13c33446785387e6557f5e62"
FACTORY = "a2fdd200363f139cd79e58b14fb08be6fa2860c95f343f6ffa65cb0d9d650446"
APP = "99982fa6f3b2adc25fbe24d2d13d7fe9a390f51f918d2061c192c8262601b4d4"
NRF_RUNNER = "496eff33eb8b9bf0fc6feb6a219e5ad949c8678777e5d359bde4fba216f4740e"
CC_RUNNER = "cb1e06d1d3128245b01e0cd63e2b66cafae63c2080614fd21ea65aa6a46acf54"
INDEX = "26746ac656288aad0cfba5fb2a901704dfe0c6c7a500ac39ab74a5938c432789"
CID = "FE343253440000002000000055019CB7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_index(failures: list[str]) -> int:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX,
            "artifact index hash mismatch")
    if not manifest.is_file():
        return 0
    entries: dict[str, str] = {}
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"malformed artifact-index line {number}")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in entries:
            failures.append(f"unsafe/duplicate artifact path: {name}")
            continue
        path = BUNDLE / relative
        require(failures, path.is_file() and digest(path) == expected,
                f"artifact mismatch: {name}")
        entries[name] = expected
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, set(entries) == actual,
            "artifact index does not exactly cover bundle")
    return len(actual) + 1


def dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes() if path.is_file() else b""
    return struct.unpack(">II", data[16:24]) if len(data) >= 24 else None


def verify_captures(failures: list[str], directory: str,
                    run: dict[str, Any]) -> int:
    captures = run.get("captures", {})
    for key, record in captures.items():
        basename = key.replace("_", "-")
        png = BUNDLE / directory / "frames" / f"{basename}.png"
        raw = BUNDLE / directory / "frames" / f"{basename}.rgb565"
        require(failures,
                dimensions(png) == (240, 320) and
                raw.is_file() and raw.stat().st_size == 153600 and
                digest(png) == record.get("png_sha256") and
                digest(raw) == record.get("rgb565_sha256"),
                f"{directory} TFT binding mismatch: {key}")
    return len(captures)


def verify_common_run(failures: list[str], run: dict[str, Any],
                      runner_hash: str, label: str) -> None:
    candidate = run.get("candidate", {})
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    boot = run.get("boot", {})
    metrics = run.get("metrics_after", {})
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures,
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("runner_source_sha256") == runner_hash and
            candidate == {"version": VERSION, "source_commit": SOURCE,
                          "firmware_sha256": FIRMWARE,
                          "app_elf_sha256": APP, "flashed": True},
            f"{label} run identity mismatch")
    require(failures,
            [before.get("generation"), before.get("observations"),
             before.get("physical_write_calls")] == [95, 0, 0] and
            [after.get("generation"), after.get("observations"),
             after.get("physical_write_calls")] == [95, 0, 0] and
            [boot.get("heap_total"), boot.get("heap_free"),
             boot.get("heap_min_free")] ==
            [metrics.get("heap_total"), metrics.get("heap_free"),
             metrics.get("heap_min_free")] == [221876, 156916, 137564] and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("cleanup_after", {}).get("complete") is True and
            [final.get("page"), final.get("runtime_owner"),
             final.get("lease_mask")] == ["home", "none", 0],
            f"{label} continuity/final cleanup mismatch")


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.92 spectrum-view evidence is missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.spectrum_views_acceptance.v1" and
            summary.get("status") == "pass_spectrum_views_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-093", "E-AUTO-057", "E-HIL-117",
                 "E-UX-016", "E-RADIO-005"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == RUNNERS and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("nrf_runner_sha256") == NRF_RUNNER and
            candidate.get("cc_runner_sha256") == CC_RUNNER and
            [candidate.get("firmware_bytes"), candidate.get("factory_bytes"),
             candidate.get("static_ram_bytes"),
             candidate.get("linked_flash_bytes")] ==
                [1504912, 1570448, 159832, 1504500],
            "candidate identity/size mismatch")
    require(failures, verify_index(failures) == evidence.get("files") == 79,
            "retained file count mismatch")
    require(failures,
            digest(BUNDLE / "provenance.json") ==
                evidence.get("provenance_sha256") and
            digest(BUNDLE / "nrf24/run.json") ==
                evidence.get("nrf_run_sha256") and
            digest(BUNDLE / "cc1101/run.json") ==
                evidence.get("cc_run_sha256") and
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "firmware.elf") == APP and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "nrf24-spectrum-runner.py") == NRF_RUNNER and
            digest(BUNDLE / "cc1101-spectrum-runner.py") == CC_RUNNER,
            "summary/binary/runner bundle binding mismatch")

    entry = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    viewport = git_blob(
        SOURCE, "firmware/leshy1/src/apps/spectrum/SpectrumViewport.h")
    theme = git_blob(SOURCE, "firmware/leshy1/src/ui/VisualTheme.h")
    nrf_runner = git_blob(RUNNERS, "tools/run_1x_nrf24_spectrum_hil.py")
    cc_runner = git_blob(RUNNERS, "tools/run_1x_cc1101_spectrum_hil.py")
    require(failures, entry is not None and all(token in entry for token in (
        b"kSpectrumOverlayHeight = 28", b"kSpectrumAxisHeight = 15",
        b"display.fillRect(0, kSpectrumGraphY, Layout::ScreenWidth",
        b"renderLatestWaterfallRow()", b"RfSpectrumView::CcBandMenu",
        b"UiTextId::Brand")),
        "full-width/header/band-menu source contract mismatch")
    require(failures, viewport is not None and all(token in viewport for token in (
        b"kHistoryRows = 112", b"enum class SpectrumDisplayMode",
        b"Spectrum", b"Waterfall")),
        "bounded spectrum history source contract mismatch")
    require(failures, theme is not None and b"FooterDividerY = 293" in theme,
            "expanded viewport geometry source contract mismatch")
    require(failures,
            nrf_runner is not None and
            hashlib.sha256(nrf_runner).hexdigest() == NRF_RUNNER and
            cc_runner is not None and
            hashlib.sha256(cc_runner).hexdigest() == CC_RUNNER,
            "runner Git source binding mismatch")

    nrf = load(BUNDLE / "nrf24/run.json")
    cc = load(BUNDLE / "cc1101/run.json")
    verify_common_run(failures, nrf, NRF_RUNNER, "nRF24")
    verify_common_run(failures, cc, CC_RUNNER, "CC1101")
    require(failures,
            verify_captures(failures, "nrf24", nrf) ==
                evidence.get("nrf_tft_states") == 8 and
            verify_captures(failures, "cc1101", cc) ==
                evidence.get("cc_tft_states") == 14,
            "TFT state count mismatch")

    nrf_reports = nrf.get("reports", {})
    nrf_zero = {"cc_command_strobes": 0, "storage_writes": 0,
                "tx_mode_entries": 0, "tx_payload_commands": 0}
    require(failures,
            nrf_reports.get("waterfall", {}).get("display_mode") == "waterfall" and
            nrf_reports.get("waterfall", {}).get("history_rows") == 32 and
            nrf_reports.get("paused_before", {}).get("sweeps") ==
                nrf_reports.get("paused_after", {}).get("sweeps") == 34 and
            nrf_reports.get("resumed", {}).get("sweeps", 0) > 34 and
            nrf_reports.get("stopped", {}).get("cleanup_complete") is True and
            all(report.get("side_effects") == nrf_zero
                for report in nrf_reports.values()),
            "nRF24 views/pause/receive-only contract mismatch")
    cc_reports = cc.get("reports", {})
    cc_zero = {"fifo_writes": 0, "pa_table_writes": 0,
               "rejected_strobes": 0, "storage_writes": 0,
               "tx_strobes": 0}
    require(failures,
            {cc_reports.get(f"band_{band}", {}).get("band")
             for band in ("315", "433", "868", "915")} ==
                {"315", "433", "868", "915"} and
            cc_reports.get("waterfall_433", {}).get("display_mode") ==
                "waterfall" and
            cc_reports.get("waterfall_433", {}).get("history_rows") == 16 and
            cc_reports.get("paused_before", {}).get("adapter_samples") ==
                cc_reports.get("paused_after", {}).get("adapter_samples") == 1034 and
            all(report.get("side_effects") == cc_zero
                for report in cc_reports.values()),
            "CC1101 bands/views/pause/receive-only contract mismatch")
    require(failures,
            verified == {
                "cc_bands": ["315", "433", "868", "915"],
                "cc_history_rows": 16,
                "final_lease_mask": 0,
                "final_owner": "none",
                "footer_divider_y": 293,
                "heap": [221876, 156916, 137564],
                "nrf_history_rows": 32,
                "physical_rf_silence_measured": False,
                "software_rx_only": True,
                "storage_generation": 95,
                "storage_observations": 0,
                "viewport": [0, 62, 240, 216],
            }, "verified claims mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "files": 79,
        "nrf_tft_states": 8, "cc_tft_states": 14,
        "nrf_history_rows": 32, "cc_history_rows": 16,
        "cc_bands": ["315", "433", "868", "915"],
        "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
