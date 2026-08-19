#!/usr/bin/env python3
"""Fail closed unless the exact board-01 physical power-cut proof is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-sd-power-cut-0.101.json"
SOURCE = "aa188baa1d055f15de2a14a027d09de5766a77b7"
VERSION = "0.101.0-power-cut-harness"
CID = "FE343253440000002000000055019CB7"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def all_equal(values: Any, expected: Any, count: int = 6) -> bool:
    return isinstance(values, list) and len(values) == count and all(
        value == expected for value in values)


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "0.101 power-cut evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    candidate = record.get("candidate", {})
    tools = record.get("tool_binding", {})
    media = record.get("media", {})
    preflight = record.get("software_reset_preflight", {})
    matrix = record.get("physical_matrix", {})
    product = record.get("product_regression", {})
    gate = record.get("gate", {})

    require(failures,
            record.get("schema") ==
                "leshy.storage.sd.physical_power_cut_acceptance.v1" and
            record.get("status") == "pass_demo_s4_gate" and
            record.get("board") == "board-01" and
            record.get("evidence_ids") == [
                "E-BUILD-102", "E-AUTO-066", "E-HIL-126",
                "E-STORAGE-028", "E-GATE-005"],
            "evidence identity mismatch")
    require(failures, candidate == {
        "version": VERSION,
        "source_commit": SOURCE,
        "firmware_sha256":
            "beee8ab472412ad0cec135a887236bb6094f3a89b4da0144e77b241614310fe7",
        "app_elf_sha256":
            "f5d343497b12b8fdb98c1b69bd1ce731958cc8663a078d3f495137304e1adb90",
        "firmware_bytes": 1512848,
        "factory_bytes": 1578384,
        "linked_flash_bytes": 1512700,
        "static_ram_bytes": 170128,
    }, "candidate identity or build budget mismatch")
    require(failures,
            media.get("cid") == CID and
            media.get("usb_serial") == "1C:DB:D4:87:90:D4" and
            media.get("same_usb_identity_all_cycles") is True and
            media.get("format_allowed") is False and
            media.get("scratch_prefix") == "/leshy-hil/s4pc101-b",
            "media identity or scratch policy mismatch")

    require(failures,
            preflight.get("status") == "valid" and
            preflight.get("boundaries_completed") == 1 and
            preflight.get("software_reset") is True and
            preflight.get("physical_power_cut") is False and
            preflight.get("opened_read_only") is True and
            preflight.get("recovered_generation") == 1 and
            preflight.get("reopened_observations") == 3 and
            preflight.get("prior_unchanged") is True and
            all(preflight.get(key) == 0 for key in (
                "recovery_bytes_written", "recovery_file_syncs",
                "recovery_directory_syncs", "final_lease_mask")) and
            preflight.get("cleanup_complete") is True,
            "software-reset preflight mismatch")

    expected_boundaries = [1, 2, 3, 4, 5, 6]
    expected_names = [
        "write_payloads", "sync_payloads", "write_manifest",
        "sync_manifest", "write_head", "sync_head"]
    require(failures,
            matrix.get("status") == "valid" and
            matrix.get("physical_power_cut") is True and
            matrix.get("manual_power_cycles") == 6 and
            matrix.get("boundaries") == expected_boundaries and
            matrix.get("boundary_names") == expected_names and
            matrix.get("recovered_generations") == [1, 1, 1, 1, 1, 2] and
            matrix.get("reopened_observations") == [3, 3, 3, 3, 3, 3] and
            matrix.get("reset_reason_codes") == [1, 1, 1, 1, 1, 1],
            "six-boundary recovery result mismatch")
    blackouts = matrix.get("blackout_seconds", [])
    floor = matrix.get("minimum_blackout_seconds")
    require(failures,
            isinstance(floor, (int, float)) and floor >= 3.0 and
            isinstance(blackouts, list) and len(blackouts) == 6 and
            all(isinstance(value, (int, float)) and value >= floor
                for value in blackouts),
            "physical blackout floor not proven")
    for key in (
            "disconnect_observed", "reconnect_observed", "same_usb_identity",
            "power_on_reset", "opened_read_only", "prior_unchanged",
            "cleanup_complete"):
        require(failures, all_equal(matrix.get(key), True),
                f"matrix {key} mismatch")
    for key in ("software_reset", "reset_injection",
                "session_store_io_writable", "user_file_names_listed",
                "user_file_data_read"):
        require(failures, all_equal(matrix.get(key), False),
                f"matrix {key} mismatch")
    for key in ("recovery_bytes_written", "recovery_file_syncs",
                "recovery_directory_syncs", "final_lease_masks",
                "radio_tx_commands"):
        require(failures, all_equal(matrix.get(key), 0),
                f"matrix {key} not zero")
    require(failures,
            matrix.get("initial_generations") == [1] * 6 and
            matrix.get("recovery_attempt_counts") == [1] * 6 and
            matrix.get("mismatches") == [{}, {}, {}, {}, {}, {}],
            "matrix continuity/retry/mismatch contract failed")

    require(failures,
            product.get("status") == "pass" and
            product.get("flashed_exact_candidate") is True and
            product.get("tft_states") == 17 and
            product.get("failures") == [] and
            product.get("generation_before") == 95 and
            product.get("generation_after") == 95 and
            product.get("observations_before") == 0 and
            product.get("observations_after") == 0 and
            product.get("physical_write_calls_before") == 0 and
            product.get("physical_write_calls_after") == 0 and
            product.get("heap_total") == 211580 and
            product.get("heap_free") == 146472 and
            product.get("heap_min_free") == 127120 and
            product.get("final_page") == "home" and
            product.get("final_owner") == "none" and
            product.get("final_lease_mask") == 0,
            "exact product regression or continuity mismatch")
    require(failures,
            gate.get("st_hil_a08") == "verified" and
            gate.get("demo_s4") == "pass" and
            gate.get("s4_status") == "done" and
            gate.get("next_stage") == "S5" and
            gate.get("release_endurance_seconds") >= 2700 and
            gate.get("release_endurance_cycles") >= 8,
            "DEMO-S4 gate closure mismatch")

    runner = git_blob("tools/run_1x_sd_power_cut_matrix.py")
    runner_tests = git_blob("tools/test_sd_power_cut_runner.py")
    firmware = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    platformio = git_blob("firmware/leshy1/platformio.ini")
    require(failures,
            runner is not None and digest(runner) == tools.get("runner_sha256") and
            runner_tests is not None and
                digest(runner_tests) == tools.get("runner_tests_sha256") and
            firmware is not None and
                digest(firmware) == tools.get("firmware_protocol_source_sha256") and
            platformio is not None and
                digest(platformio) == tools.get("platformio_sha256"),
            "exact source/tool binding mismatch")
    require(failures,
            firmware is not None and all(token in firmware for token in (
                b"power-cut disposable-write",
                b"power-cut-recover disposable-read-only",
                b"physical_power_cut", b"ESP_RST_POWERON")) and
            platformio is not None and
                b'LESHY1_VERSION=\\"0.101.0-power-cut-harness\\"' in platformio,
            "firmware protocol/version source contract mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "physical_power_cuts": 6,
        "boundaries": expected_boundaries,
        "recovered_generations": [1, 1, 1, 1, 1, 2],
        "recovery_writes": 0, "final_lease_mask": 0,
        "demo_s4": "pass", "next_stage": "S5",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
