#!/usr/bin/env python3
"""Fail closed unless the exact 0.83 CC1101 spectrum proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-cc1101-spectrum-0.83.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-cc1101-spectrum-0.83"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "b3c97d7417143fb7d4015dd4b8bfe742f035b879"
RUNNER_COMMIT = "7f6cf77f6e43453c1badbc13f0b9e05cf5367bef"
CAPTURES = {
    "plan", "source_menu", "band_433", "band_868", "band_915",
    "band_315", "paused", "stopped", "home",
}
BANDS = {
    "band_315": ("315", [300000, 348000]),
    "band_433": ("433", [433050, 434790]),
    "band_868": ("868", [863000, 870000]),
    "band_915": ("915", [902000, 928000]),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


def verify_index(failures: list[str], index: Path) -> None:
    require(failures, index.is_file(), "artifact index missing")
    if not index.is_file():
        return
    expected: dict[str, str] = {}
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
            continue
        expected[parts[1]] = parts[0]
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual,
            "artifact index is not an exact bundle inventory")
    for relative, expected_hash in expected.items():
        path = BUNDLE / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"indexed artifact mismatch: {relative}")


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    require(failures, BUNDLE.is_dir(), "retained bundle missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    candidate = evidence.get("candidate", {})
    retained = evidence.get("evidence", {})
    verified = evidence.get("verified", {})
    limits = evidence.get("limits", {})
    require(failures,
            evidence.get("schema") == "leshy.cc1101_spectrum_acceptance.v1" and
            evidence.get("status") == "pass_receive_only_user_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.83.0-cc1101-spectrum" and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")

    run_path = BUNDLE / "run.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures, run_path.is_file() and
            digest(run_path) == retained.get("run_sha256"), "run binding mismatch")
    require(failures, index_path.is_file() and
            digest(index_path) == retained.get("artifact_index_sha256"),
            "artifact-index binding mismatch")
    verify_index(failures, index_path)
    require(failures, retained.get("files") == 33 and
            retained.get("tft_states") == 9, "retained inventory/count mismatch")

    for field, filename in (
        ("firmware_sha256", "firmware.bin"),
        ("factory_sha256", "firmware.factory.bin"),
        ("app_elf_sha256", "firmware.elf"),
        ("map_sha256", "firmware.map"),
    ):
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == candidate.get(field),
                f"retained {filename} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures, app_elf_sha256(BUNDLE / "firmware.bin") ==
                candidate.get("app_elf_sha256"), "embedded app identity mismatch")
    require(failures,
            (BUNDLE / "firmware.bin").stat().st_size == candidate.get("app_bytes") and
            (BUNDLE / "firmware.factory.bin").stat().st_size ==
                candidate.get("factory_bytes"), "candidate size mismatch")

    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_cc1101_spectrum_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures, hashlib.sha256(runner_blob).hexdigest() ==
                retained.get("runner_sha256"), "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.cc1101_spectrum_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
                run.get("runner_source_sha256") == retained.get("runner_sha256") and
                run.get("candidate") == {
                    "version": candidate.get("version"),
                    "source_commit": SOURCE_COMMIT,
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "flashed": True,
                }, "physical run identity mismatch")
        boot = run.get("boot", {})
        after = run.get("metrics_after", {})
        require(failures,
                boot.get("version") == candidate.get("version") and
                boot.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                boot.get("heap_free") == after.get("heap_free") == 164036 and
                boot.get("heap_min_free") == after.get("heap_min_free") == 144640,
                "boot identity or heap invariant mismatch")
        for label in ("recovery_before", "recovery_after"):
            recovery = run.get(label, {})
            require(failures,
                    recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == CID and
                    recovery.get("observed_fingerprint") == CID and
                    recovery.get("generation") == 83 and
                    recovery.get("observations") == 0 and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"{label} continuity mismatch")

        reports = run.get("reports", {})
        require(failures, set(reports) == set(BANDS) | {
            "paused_before", "paused_after", "resumed", "stopped"},
            "spectrum report set mismatch")
        for label, (band, range_khz) in BANDS.items():
            report = reports.get(label, {})
            require(failures,
                    report.get("band") == band and
                    report.get("range_khz") == range_khz and
                    report.get("sweeps") == 1 and report.get("samples") >= 64,
                    f"{label} range/progression mismatch")
        for label, expected_state, active, cleanup in (
            ("paused_before", "paused", True, False),
            ("paused_after", "paused", True, False),
            ("resumed", "running", True, False),
            ("stopped", "idle", False, True),
        ):
            report = reports.get(label, {})
            require(failures,
                    report.get("schema") == "leshy.cc1101.spectrum.v1" and
                    report.get("state") == expected_state and
                    report.get("status") == "ready" and
                    report.get("adapter_active") is active and
                    report.get("cleanup_complete") is cleanup and
                    report.get("bins") == 64 and report.get("settle_us") == 500 and
                    report.get("ready_timeout_us") == 3000 and
                    report.get("rx_only") is True and
                    report.get("nrf_slot3_gated") is True and
                    report.get("gpio21_stable_high") is True and
                    report.get("current_owner") == "survey" and
                    report.get("current_lease_mask") == 15 and
                    report.get("side_effects") == {
                        "rejected_strobes": 0, "tx_strobes": 0,
                        "pa_table_writes": 0, "fifo_writes": 0,
                        "storage_writes": 0,
                    }, f"{label} receive-only contract mismatch")
        pause_before = reports.get("paused_before", {})
        pause_after = reports.get("paused_after", {})
        stopped = reports.get("stopped", {})
        require(failures,
                pause_before.get("adapter_samples") ==
                    pause_after.get("adapter_samples") == 351 and
                reports.get("resumed", {}).get("adapter_samples") == 353 and
                stopped.get("adapter_samples") == 354,
                "pause/resume/result progression mismatch")
        wire = stopped.get("wire", {})
        samples = stopped.get("adapter_samples", -1)
        require(failures,
                wire == {
                    "register_reads": 11443, "register_writes": 1078,
                    "spi_bytes_clocked": 26110, "command_strobes": 1068,
                    "reset_strobes": 1, "receive_strobes": 354,
                    "idle_strobes": 713,
                } and
                wire.get("command_strobes") == wire.get("reset_strobes") +
                    wire.get("receive_strobes") + wire.get("idle_strobes") and
                samples == wire.get("receive_strobes"),
                "final wire accounting mismatch")
        require(failures,
                run.get("input", {}).get("read_errors") == 0 and
                run.get("input", {}).get("queue_drops") == 0 and
                run.get("safe_outputs", {}).get("buzzer_inactive") is True and
                run.get("cleanup_after", {}).get("complete") is True and
                run.get("cleanup_after", {}).get("final_state", {}).get(
                    "runtime_owner") == "none" and
                run.get("cleanup_after", {}).get("final_state", {}).get(
                    "lease_mask") == 0,
                "input/safe-output/final cleanup mismatch")
        require(failures, set(run.get("captures", {})) == CAPTURES,
                "capture set mismatch")

    for label in CAPTURES:
        stem = label.replace("_", "-")
        png = BUNDLE / "frames" / f"{stem}.png"
        rgb = BUNDLE / "frames" / f"{stem}.rgb565"
        metadata = BUNDLE / "frames" / f"{stem}.json"
        require(failures, png.is_file() and png_dimensions(png) == (240, 320),
                f"invalid {label} PNG")
        require(failures, rgb.is_file() and rgb.stat().st_size == 240 * 320 * 2,
                f"invalid {label} RGB frame")
        require(failures, metadata.is_file(), f"missing {label} metadata")

    require(failures,
            verified.get("final_samples") == 354 and
            verified.get("paused_samples_before") ==
                verified.get("paused_samples_after_400ms") == 351 and
            verified.get("tx_strobes") == 0 and
            verified.get("pa_table_writes") == 0 and
            verified.get("fifo_writes") == 0 and
            limits.get("physical_rf_silence_measured") is False and
            limits.get("rf_instrument_available") is False and
            limits.get("rssi_calibrated") is False and
            limits.get("frequency_accuracy_calibrated") is False and
            limits.get("active_full_guided_execution") == "next_checkpoint" and
            limits.get("demo_s4_closed") is False and
            limits.get("release_promoted") is False,
            "accepted facts or scope limits were weakened")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.83 receive-only CC1101 spectrum evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
