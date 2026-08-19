#!/usr/bin/env python3
"""Fail closed unless the retained Sub-GHz RAW checkpoint remains intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-subghz-raw-0.102.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-subghz-raw-0.102"
VERSION = "0.102.0-subghz-raw-rx"
SOURCE = "d8c52f78ce3df81985b568e4f89ae74e098286e4"
RUNNER_COMMIT = "a553640e42f9568262e4082ac443020b4257bffb"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "6e5b858df967b93f8a534a90237a33a88eeb37405f88bf7996d35a8924813ed8"
APP = "a8792b4b13ff1b6e364dcd049f79f4e9398bec845d8aff6ab63ac8edd77cfd88"
FACTORY = "bb1de521040302dfc0fb9651e0b4f6eaa25995d2068144e7dbe5af31b4bd33c6"
MAP = "3e6979dc3c7dda68728b4ed5f6ef401bdbc3bb81aae78c2c6c412f1f1e7acb53"
FRAME_EVENTS = {
    "home": "subghz_home",
    "modes_spectrum": "subghz_modes",
    "modes_raw": "subghz_modes",
    "bands": "subghz_raw_band_menu",
    "waiting": "subghz_raw_waiting",
    "terminal": "subghz_raw_no_signal",
    "final_home": "subghz_home",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, relative: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24] if path.is_file() else b""
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def verify_manifest(failures: list[str]) -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifact index missing")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append("malformed artifact index line")
            continue
        expected, relative = parts
        indexed.add(relative)
        path = BUNDLE / relative
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, indexed == actual, "artifact index coverage mismatch")


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.102 Sub-GHz RAW evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    coverage = summary.get("coverage", {})
    require(failures,
            summary.get("schema") == "leshy.subghz_raw_acceptance.v1" and
            summary.get("status") ==
                "pass_physical_receive_no_signal_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-103", "E-AUTO-067", "E-HIL-127",
                "E-RADIO-012", "E-STORAGE-029"],
            "summary identity mismatch")
    require(failures,
            candidate.get("schema") == "leshy.subghz_raw.provenance.v1" and
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == RUNNER_COMMIT and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("map_sha256") == MAP and
            candidate.get("static_ram_bytes") == 171400 and
            candidate.get("linked_flash_bytes") == 1527836,
            "candidate identity/resource mismatch")
    require(failures,
            evidence.get("tft_states") == 7 and
            isinstance(evidence.get("files"), int) and
            evidence.get("files") == 27 and
            evidence.get("artifact_index_sha256") ==
                digest(BUNDLE / "artifacts.sha256") and
            evidence.get("provenance_sha256") ==
                digest(BUNDLE / "provenance.json") and
            evidence.get("run_sha256") == digest(BUNDLE / "run.json"),
            "evidence identity mismatch")
    require(failures,
            verified.get("checkpoint") == "physical_receive_path" and
            verified.get("frequency_khz") == 433920 and
            verified.get("modulation") == "ook_envelope" and
            verified.get("terminal_state") == "timed_out" and
            isinstance(verified.get("physical_rssi_samples"), int) and
            verified.get("physical_rssi_samples", 0) >= 100_000 and
            verified.get("wait_elapsed_us") == 10_000_007 and
            all(verified.get(key) == 0 for key in (
                "application_tx_calls", "tx_strobes", "pa_table_writes",
                "fifo_writes", "storage_physical_write_calls",
                "input_read_errors", "input_queue_drops")) and
            verified.get("storage_generation") == 95 and
            verified.get("storage_observations") == 0 and
            verified.get("heap") == [210308, 145076, 125848] and
            verified.get("buzzer_inactive") is True and
            verified.get("automatic_screenshots") is True and
            verified.get("manual_button_presses") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "physical checkpoint claims mismatch")
    require(failures, coverage == {
        "cap_030_complete": False,
        "host_capture_codec_store_csv": True,
        "physical_known_transmitter_used": False,
        "physical_persistence_and_library_export": False,
        "physical_receive_and_no_signal_timeout": True,
        "physical_successful_burst": False,
        "raw_rf_payload_retained": False,
        "tx_or_replay_in_scope": False,
    }, "coverage/limitations mismatch")

    verify_manifest(failures)
    require(failures,
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "runner.py") == candidate.get("runner_sha256"),
            "retained candidate/runner mismatch")
    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_subghz_raw_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() ==
                candidate.get("runner_sha256"),
            "runner commit/source mismatch")

    run = load(BUNDLE / "run.json")
    require(failures,
            run.get("schema") == "leshy.subghz_raw_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is False and
            run.get("checkpoint") == "physical_receive_path" and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("runner_source_sha256") == candidate.get("runner_sha256") and
            run.get("candidate") == {
                "app_elf_sha256": APP, "exact_flash_reused": True,
                "firmware_sha256": FIRMWARE, "flashed": False,
                "source_commit": SOURCE, "version": VERSION,
            }, "exact run identity mismatch")
    terminal = run.get("reports", {}).get("terminal", {})
    require(failures,
            terminal.get("state") == "timed_out" and
            terminal.get("samples") == verified.get("physical_rssi_samples") and
            terminal.get("signal_started_us") == 0 and
            terminal.get("pulses") == 0 and
            terminal.get("csv_available") is False and
            terminal.get("storage_written") is False and
            terminal.get("physical_no_tx_verified") is True and
            terminal.get("cleanup_complete") is True and
            terminal.get("driver_error") == 0 and
            all(terminal.get(key) == 0 for key in (
                "application_tx_calls", "tx_strobes", "pa_table_writes",
                "fifo_writes")),
            "terminal receive/no-side-effect contract mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures,
            before.get("expected_fingerprint") == CID and
            before.get("observed_fingerprint") == CID and
            before.get("generation") == after.get("generation") == 95 and
            before.get("observations") == after.get("observations") == 0 and
            before.get("physical_write_calls") ==
                after.get("physical_write_calls") == 0 and
            before.get("mounted_read_only") is True and
            after.get("mounted_read_only") is True,
            "storage/CID continuity mismatch")
    require(failures,
            run.get("boot", {}).get("app_elf_sha256") == APP and
            run.get("boot", {}).get("version") == VERSION and
            run.get("metrics_after", {}).get("heap_free") == 145076 and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("cleanup", {}).get("complete") is True and
            run.get("cleanup", {}).get("final_state", {}).get("page") == "home" and
            run.get("cleanup", {}).get("final_state", {}).get("lease_mask") == 0,
            "boot/input/safe-output/final cleanup mismatch")
    captures = run.get("captures", {})
    require(failures, set(captures) == set(FRAME_EVENTS),
            "TFT capture set mismatch")
    for key, event in FRAME_EVENTS.items():
        capture = captures.get(key, {})
        name = key.replace("_", "-")
        png = BUNDLE / "frames" / f"{name}.png"
        require(failures,
                capture.get("frame_begin", {}).get("width") == 240 and
                capture.get("frame_begin", {}).get("height") == 320 and
                capture.get("state", {}).get("runtime_event") == event and
                png_size(png) == (240, 320) and
                digest(png) == capture.get("png_sha256"),
                f"{key} TFT capture mismatch")

    source_platform = git_blob(SOURCE, "firmware/leshy1/platformio.ini")
    source_capture = git_blob(
        SOURCE, "firmware/leshy1/src/apps/capture/SubGhzRawCapture.cpp")
    source_radio = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp")
    require(failures, source_platform is not None and
            b'LESHY1_VERSION=\\"0.102.0-subghz-raw-rx\\"' in source_platform,
            "source version binding mismatch")
    require(failures, source_capture is not None and all(token in source_capture for token in (
        b"maximumPulses", b"SignalTooLong", b"TimedOut")),
        "bounded RAW state-machine source mismatch")
    require(failures, source_radio is not None and all(token in source_radio for token in (
        b"lockReceive", b"sampleRssi")),
        "physical receive adapter source mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION,
        "checkpoint": "physical_receive_path",
        "terminal_state": "timed_out",
        "samples": verified["physical_rssi_samples"],
        "tft_states": 7, "tx_calls": 0,
        "storage_generation": 95, "final_lease_mask": 0,
        "cap_030_complete": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
