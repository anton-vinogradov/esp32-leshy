#!/usr/bin/env python3
"""Fail closed unless the compact exact 0.140 FSK delta proof is intact."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-subghz-fsk-delta-0.140"
SUMMARY = ROOT / "tests/hil/evidence/board-01-subghz-fsk-delta-0.140.json"
VERSION = "0.140.0-subghz-fsk-rx"
CID = "FE343253440000002000000055019CB7"
SOURCE = "ed820b8e61026e5feb37d0284508808e964bd55a"
BASE = "0b0f0cf341fa53311b517abeb93025cd79a1de0a"
RUN_SHA256 = "7d009827f3deafe7d149bc22867598266c6ccd8f34ebecadb5d9db2d0ca0a2c3"
PROVENANCE_SHA256 = "992efda185679122ab6d04edff7689653489acd7eb8190488e8dbcdcb56ea2e6"
INDEX_SHA256 = "1acfebff4be73a99ca1dbf01e1011c1a9c3605d8401a84fadb1011a1743b547f"
FIRMWARE_SHA256 = "cc4dbfe5df747968cb618845c4bfee28eefc37208a79c79f0dd584713a7059b9"
ELF_SHA256 = "5647c991098f395470996a1b4a43070d9cc1760d02039a3250e2cc2b00fdff40"
RUNNER_SHA256 = "9172aa55ed36a32859c5b414cd09a41158aa845d7bdac0644c1137d90b93ae1b"
RETAINER_SHA256 = "85ac62d96a45332abd55d0492cbb9deba2198394054aa72742bf41bc4f4a3adf"
RETAINER_SOURCE = "f7304c74d898db6d5cd74278dfaa6800c3aec3d7"
CAPTURES = {
    "fsk_async-band-433", "fsk_async-no-signal",
    "fsk_async-type-ook", "fsk_async-type-selected",
    "fsk_async-waiting", "home-final", "ook_envelope-band-433",
    "ook_envelope-no-signal", "ook_envelope-type-ook",
    "ook_envelope-waiting",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, relative: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24] if path.is_file() else b""
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def verify_manifest(failures: list[str]) -> int:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX_SHA256,
            "compact artifact index identity mismatch")
    if not manifest.is_file():
        return 0
    indexed: set[str] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"malformed compact artifact line {number}")
            continue
        expected, relative = match.groups()
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in indexed:
            failures.append(f"unsafe or duplicate compact artifact: {relative}")
            continue
        artifact = BUNDLE / path
        require(failures, artifact.is_file() and digest(artifact) == expected,
                f"compact artifact mismatch: {relative}")
        indexed.add(relative)
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, indexed == actual,
            "compact artifact index does not exactly cover bundle")
    return len(actual) + 1


def receive_terminal_ok(record: dict[str, Any], modulation: str,
                        register_writes: int, samples: int) -> bool:
    return (
        record.get("schema") == "leshy.capture.subghz_raw.v1" and
        record.get("state") == "timed_out" and
        record.get("modulation") == modulation and
        record.get("frequency_khz") == 433920 and
        record.get("gdo0_gpio") == 6 and
        record.get("samples") == samples and
        record.get("pulses") == 0 and
        record.get("storage_written") is False and
        record.get("receiver_register_writes") == register_writes and
        record.get("receiver_command_strobes") == 4 and
        record.get("receiver_reset_strobes") == 1 and
        record.get("receiver_receive_strobes") == 1 and
        record.get("receiver_idle_strobes") == 2 and
        record.get("receiver_rejected_strobes") == 0 and
        record.get("application_tx_calls") == 0 and
        record.get("tx_strobes") == 0 and
        record.get("pa_table_writes") == 0 and
        record.get("fifo_writes") == 0 and
        record.get("physical_no_tx_verified") is True and
        record.get("cleanup_complete") is True
    )


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "compact FSK delta evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    run = load(BUNDLE / "run.json")
    require(failures,
            summary.get("schema") == "leshy.subghz_fsk_delta.acceptance.v1" and
            summary.get("status") ==
                "pass_software_and_no_signal_delta_physical_positive_open" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-140", "E-AUTO-101", "E-HIL-161", "E-RADIO-019"],
            "acceptance summary contract mismatch")
    cadence = summary.get("cadence", {})
    require(failures,
            cadence.get("scope") == "delta" and
            cadence.get("full_matrix_run") is False and
            cadence.get("accepted_delta_ordinal") == 1 and
            cadence.get("full_after_accepted_deltas") == 15,
            "HIL cadence claim mismatch")
    evidence = summary.get("evidence", {})
    require(failures,
            digest(BUNDLE / "provenance.json") == PROVENANCE_SHA256 and
            verify_manifest(failures) == evidence.get("compact_files") == 14 and
            evidence.get("compact_artifact_manifest_sha256") == INDEX_SHA256 and
            evidence.get("compact_provenance_sha256") == PROVENANCE_SHA256 and
            evidence.get("run_sha256") == RUN_SHA256 and
            sum(path.stat().st_size for path in BUNDLE.rglob("*")
                if path.is_file()) <= evidence.get("retained_bytes_max", 0),
            "compact evidence identity or size mismatch")
    require(failures,
            provenance.get("schema") ==
                "leshy.compact_delta_hil.provenance.v1" and
            provenance.get("base_commit") == BASE and
            provenance.get("run_sha256") == RUN_SHA256 and
            provenance.get("runner_sha256") == RUNNER_SHA256 and
            provenance.get("candidate") == run.get("candidate") and
            provenance.get("original_bundle") == {
                "artifact_manifest_sha256":
                    "4ef54f836289bdea1787b02345e8bf674905d8f241dfe9a15f9a8ffa2d870224",
                "bytes": 45818642,
                "files": 36,
            } and
            provenance.get("retention", {}).get("policy") ==
                "compact_delta_no_duplicate_build_binaries" and
            provenance.get("retention", {}).get("png_frames") == 10,
            "compact provenance mismatch")
    for relative, expected in provenance.get("source_sha256", {}).items():
        blob = git_blob(SOURCE, relative)
        require(failures, blob is not None and
                hashlib.sha256(blob).hexdigest() == expected,
                f"candidate source binding mismatch: {relative}")
    require(failures,
            digest(BUNDLE / "run.json") == RUN_SHA256 and
            digest(BUNDLE / "runner.py") == RUNNER_SHA256 and
            hashlib.sha256(git_blob(
                RETAINER_SOURCE,
                "tools/retain_compact_delta_hil.py") or b"").hexdigest() ==
                RETAINER_SHA256 and
            git_blob(SOURCE, "tools/run_1x_subghz_fsk_delta_hil.py") ==
                (BUNDLE / "runner.py").read_bytes(),
            "run/runner/retainer identity mismatch")
    candidate = run.get("candidate", {})
    records = run.get("records", {})
    ready = records.get("ready", {})
    after = records.get("metrics_after", {})
    before_storage = records.get("recovery_before", {})
    after_storage = records.get("recovery_after", {})
    require(failures,
            run.get("schema") == "leshy.subghz_fsk_delta_hil.run.v1" and
            run.get("passed") is True and run.get("failures") == [] and
            run.get("scope") == "delta" and
            run.get("full_matrix_run") is False and
            run.get("gate_eligible") is True and
            run.get("board") == "board-01" and
            run.get("expected_cid") == CID and
            candidate == {
                "app_elf_sha256": ELF_SHA256,
                "exact_flash_reused": False,
                "firmware_sha256": FIRMWARE_SHA256,
                "flashed": True,
                "source_commit": SOURCE,
                "version": VERSION,
            }, "exact delta run identity mismatch")
    require(failures,
            ready.get("heap_total") == after.get("heap_total") == 168076 and
            ready.get("heap_free") == after.get("heap_free") == 97800 and
            ready.get("heap_min_free") == after.get("heap_min_free") == 83612 and
            before_storage.get("generation") ==
                after_storage.get("generation") == 110 and
            before_storage.get("observations") ==
                after_storage.get("observations") == 0 and
            before_storage.get("physical_write_calls") ==
                after_storage.get("physical_write_calls") == 0 and
            before_storage.get("observed_fingerprint") ==
                after_storage.get("observed_fingerprint") == CID and
            before_storage.get("cleanup_complete") is True and
            after_storage.get("cleanup_complete") is True,
            "heap/storage continuity mismatch")
    fsk = records.get("fsk", {}).get("terminal", {})
    ook = records.get("ook", {}).get("terminal", {})
    require(failures, receive_terminal_ok(fsk, "fsk_async", 42, 143724),
            "FSK receive/no-signal contract mismatch")
    require(failures, receive_terminal_ok(ook, "ook_envelope", 35, 143061),
            "adjacent OOK receive/no-signal contract mismatch")
    require(failures,
            fsk.get("minimum_fsk_pulse_us") == 4 and
            fsk.get("maximum_pulses") == 512 and
            fsk.get("fsk_edges_drained") == 0 and
            fsk.get("fsk_transport_overflows") == 0 and
            run.get("coverage") == {
                "fsk_menu_and_no_signal_cleanup": True,
                "ook_adjacent_no_signal_cleanup": True,
                "physical_fsk_edge_capture_proven": False,
                "physical_fsk_positive_source_used": False,
                "tx_or_replay_in_scope": False,
            }, "FSK bounds or claim boundary mismatch")
    captures = run.get("captures", {})
    require(failures, set(captures) == CAPTURES,
            "automatic TFT capture inventory mismatch")
    for name in CAPTURES:
        png = BUNDLE / "frames" / f"{name}.png"
        require(failures,
                png_size(png) == (240, 320) and
                digest(png) == captures.get(name, {}).get("png_sha256"),
                f"automatic TFT frame mismatch: {name}")
    final = run.get("cleanup", {}).get("final_state", {})
    require(failures,
            records.get("input", {}).get("read_errors") == 0 and
            records.get("input", {}).get("queue_drops") == 0 and
            records.get("outputs", {}).get("buzzer_inactive") is True and
            records.get("outputs", {}).get("nrf_ce_inactive") is True and
            records.get("outputs", {}).get("software_quiesce_complete") is True and
            records.get("hil_begin", {}).get("active") is True and
            records.get("hil_end", {}).get("active") is False and
            records.get("hil_begin", {}).get("session_id") ==
                records.get("hil_end", {}).get("session_id") and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "input/output/session/final cleanup mismatch")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Sub-GHz FSK compact delta acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
