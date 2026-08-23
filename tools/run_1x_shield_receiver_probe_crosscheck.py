#!/usr/bin/env python3
"""Cross-check one DIV RF shield with an exact known-positive product image."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    expect,
    query,
)


RUN_SCHEMA = "leshy.shield_receiver_crosscheck.run.v1"
PROBE_SCHEMA = "leshy.shield.receiver_probe.v1"


def probe_contract_failures(report: dict[str, Any]) -> list[str]:
    failures = expect(report, {
        "schema_version": 1,
        "read_only": True,
        "profile_declared": True,
        "gps_excluded_by_profile": True,
        "pn532_excluded_by_profile": True,
        "nrf_slot3_gated": True,
        "gpio21_stable_high": True,
        "resource_acquired": True,
        "resource_released": True,
        "cleanup_complete": True,
        "current_owner": "self-test",
        "current_lease_mask": 1,
    }, "shield_receiver_probe")
    if report.get("wire") != {
        "nrf_register_reads": 8,
        "cc_status_reads": 2,
        "spi_bytes_clocked": 20,
    }:
        failures.append(f"unexpected wire bounds: {report.get('wire')!r}")
    if report.get("side_effects") != {
        "nrf_ce_high_events": 0,
        "cc_command_strobes": 0,
        "radio_tx_commands": 0,
    }:
        failures.append(
            f"unexpected probe side effects: {report.get('side_effects')!r}")
    return failures


def normalize_home(device: Any) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            return trace
        state = action(device, "up")
        trace.append(state)
    raise RuntimeError("could not normalize Home selection")


def cleanup_reached_legacy_home(cleanup: dict[str, Any]) -> bool:
    state = cleanup.get("final_state", {})
    return (
        state.get("page") == "home" and
        state.get("runtime_owner") == "none" and
        state.get("lease_mask") == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    probe: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if not args.flash:
            raise RuntimeError("cross-check requires a fresh exact-image flash")
        flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
        time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot = query(device, b"metrics", "leshy.boot.v1", "ready")
                failures.extend(expect(boot, {
                    "version": args.expected_version,
                    "app_elf_sha256": app_identity,
                }, "boot"))
                if failures:
                    raise RuntimeError("boot identity differs")
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_reached_legacy_home(cleanup_before):
                    raise RuntimeError("initial cleanup did not reach Home/lease 0")

                trace.extend(normalize_home(device))
                for _ in range(5):
                    trace.append(action(device, "down"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "self_test",
                    "self_test_view": "mode_menu",
                    "self_test_mode": "quick",
                    "lease_mask": 1,
                }, "mode_menu"))
                trace.append(action(device, "down"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "self_test_view": "preflight",
                    "self_test_mode": "full_guided",
                    "lease_mask": 1,
                }, "preflight"))

                for expected_visual in (
                    "dialog_confirm", "unavailable", "degraded", "error",
                    "running",
                ):
                    state = action(device, "right")
                    trace.append(state)
                    failures.extend(expect(state, {
                        "self_test_view": "visual_check",
                        "self_test_visual_state": expected_visual,
                        "self_test_mode": "full_guided",
                        "lease_mask": 1,
                    }, f"visual_{expected_visual}"))

                # The next public action synchronously runs only the guarded
                # receiver-identity probe in plan v4, then enters its result.
                state = action(device, "right")
                trace.append(state)
                probe = query(
                    device, b"hardware.shield.receivers",
                    PROBE_SCHEMA, "report",
                )
                failures.extend(probe_contract_failures(probe))
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state",
                )
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True,
                    "buzzer_level": "low",
                }, "safe_outputs"))
            except Exception as error:
                failures.append(
                    f"probe_phase: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_reached_legacy_home(cleanup_after):
                    failures.append("cleanup_after: terminal Home/lease 0 unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    detected = int(probe.get("detected_receivers", 0))
    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "failures": failures,
        "outcome": (
            "all_receivers_detected" if detected == 3 else
            "partial_receivers_detected" if detected > 0 else
            "no_receivers_detected"
        ),
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "boot": boot,
        "shield_receiver_probe": probe,
        "safe_outputs": safe_outputs,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "limits": {
            "read_only_identity": True,
            "rf_transmission_authorized": False,
            "storage_required": False,
            "stage_or_phase_promotion": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "outcome": result["outcome"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
