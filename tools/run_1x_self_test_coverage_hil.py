#!/usr/bin/env python3
"""Prove the plan-v4 read-only shield receiver Self-Test on the real device."""

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
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.shield_receiver_self_test_hil.run.v1"
REPORT_SCHEMA = "leshy.self_test.report.v1"
QUICK_IDS = [
    "quick.build.identity",
    "quick.board.profile",
    "quick.runtime.heap",
    "quick.display.ready",
    "quick.input.frontend",
    "quick.input.queue",
    "quick.output.buzzer",
    "quick.resource.scope",
]
FULL_CHECKS = [
    *[(check_id, "pass") for check_id in QUICK_IDS],
    ("full.ui.common_states", "pass"),
    ("full.s3.survey.persistence", "pass"),
    ("full.s4.radio.ble.passive", "pass"),
    ("full.s4.capture.wifi.passive", "pass"),
    ("full.s4.storage.enrolled", "pass"),
    ("full.s4.library.recovery", "pass"),
    ("full.s4.capture.persistence", "pass"),
    ("full.assembly.gps", "not_applicable"),
    ("full.assembly.pn532", "not_applicable"),
    ("full.shield.ir", "not_applicable"),
    ("full.s4.shield.receivers", "pass"),
    ("full.capability.coverage", "blocked"),
]


def report_failures(report: dict[str, Any], *, full: bool) -> list[str]:
    failures = expect(report, {
        "schema_version": 1,
        "plan_version": 4,
        "mode": "full_guided" if full else "quick",
        "status": "blocked" if full else "pass",
        "read_only": True,
        "cancelled": False,
        "passed": 16 if full else 8,
        "failed": 0,
        "blocked": 1 if full else 0,
        "not_applicable": 3 if full else 0,
        "current_owner": "self-test",
        "current_lease_mask": 1,
    }, "full_report" if full else "quick_report")
    expected = FULL_CHECKS if full else [(check_id, "pass") for check_id in QUICK_IDS]
    actual = [(item.get("id"), item.get("status"))
              for item in report.get("checks", [])]
    if actual != expected:
        failures.append(f"report checks differ: {actual!r}")
    side_effects = report.get("side_effects", {})
    if side_effects != {
        "radio_tx_commands": 0,
        "storage_write_commands": 0,
        "buzzer_activations": 0,
    }:
        failures.append(f"unexpected Self-Test side effects: {side_effects!r}")
    facts = report.get("facts", {})
    for key in (
        "build_identity_present", "profile_matched", "display_ready",
        "input_frontend_ready", "input_queue_healthy", "buzzer_inactive",
        "resource_scope_clean", "persistent_survey_ready", "passive_ble_ready",
        "passive_wifi_capture_ready", "enrolled_storage_ready",
        "persistent_library_ready", "persistent_wifi_capture_ready",
    ):
        if facts.get(key) is not True:
            failures.append(f"report fact is not ready: {key}")
    for key in ("gps_declared", "pn532_declared", "ir_declared"):
        if facts.get(key) is not False:
            failures.append(f"absent assembly is not explicit: {key}")
    if facts.get("run_resource_mask") != 1:
        failures.append("Self-Test report was not scoped to UI-only lease 1")
    if full:
        for key in (
            "shield_receivers_applicable", "shield_receiver_probe_complete",
            "shield_receiver_probe_passed",
        ):
            if facts.get(key) is not True:
                failures.append(f"shield receiver fact is not true: {key}")
    return failures


def shield_probe_failures(report: dict[str, Any]) -> list[str]:
    failures = expect(report, {
        "schema_version": 1, "status": "pass", "read_only": True,
        "profile_declared": True, "gps_excluded_by_profile": True,
        "pn532_excluded_by_profile": True, "nrf_slot3_gated": True,
        "gpio21_stable_high": True, "resource_acquired": True,
        "resource_released": True, "cleanup_complete": True,
        "detected_receivers": 3, "current_owner": "self-test",
        "current_lease_mask": 1,
    }, "shield_receiver_probe")
    nrf = report.get("nrf", [])
    if len(nrf) != 2:
        failures.append(f"shield probe NRF count differs: {len(nrf)}")
    else:
        for slot, item in enumerate(nrf, 1):
            if (item.get("slot") != slot or item.get("detected") is not True or
                    not isinstance(item.get("status"), int) or
                    item.get("status") & 0x80 or
                    not isinstance(item.get("channel"), int) or
                    not 0 <= item.get("channel") <= 125):
                failures.append(f"NRF slot {slot} identity is implausible: {item!r}")
    cc1101 = report.get("cc1101", {})
    if (cc1101.get("detected") is not True or cc1101.get("ready") is not True or
            not isinstance(cc1101.get("status"), int) or
            cc1101.get("status") == 0xFF or cc1101.get("partnum") != 0 or
            cc1101.get("version") != 0x14):
        failures.append(f"CC1101 identity differs: {cc1101!r}")
    if report.get("wire") != {
        "nrf_register_reads": 8, "cc_status_reads": 2,
        "spi_bytes_clocked": 20,
    }:
        failures.append(f"shield probe wire bounds differ: {report.get('wire')!r}")
    if report.get("side_effects") != {
        "nrf_ce_high_events": 0, "cc_command_strobes": 0,
        "radio_tx_commands": 0,
    }:
        failures.append(f"shield probe side effects differ: {report.get('side_effects')!r}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
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
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    quick: dict[str, Any] = {}
    full: dict[str, Any] = {}
    shield_probe: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot = query(device, b"metrics", "leshy.boot.v1", "ready")
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid,
                ))
                if failures:
                    raise RuntimeError("boot contract failed")
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial cleanup did not reach Home/lease 0")
                state = query(device, b"ui.state", "leshy.ui.v1", "state")
                for _ in range(8):
                    if int(state.get("selection", -1)) == 0:
                        break
                    state = action(device, "up")
                    trace.append(state)
                if int(state.get("selection", -1)) != 0:
                    raise RuntimeError("could not normalize Home selection")
                state = query(device, b"ui.language ru", "leshy.ui.v1", "state")
                for _ in range(5):
                    state = action(device, "down")
                    trace.append(state)
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "self_test", "self_test_view": "mode_menu",
                    "self_test_mode": "quick", "lease_mask": 1,
                }, "mode_menu"))
                captures["modes"] = capture(device, frames, "modes")

                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "self_test_view": "result", "self_test_status": "pass",
                    "self_test_checks": 8, "self_test_passed": 8,
                    "self_test_failed": 0, "self_test_blocked": 0,
                    "self_test_not_applicable": 0, "lease_mask": 1,
                }, "quick_result"))
                captures["quick_result"] = capture(device, frames, "quick-result")
                quick = query(device, b"self-test.report", REPORT_SCHEMA, "report")
                failures.extend(report_failures(quick, full=False))

                trace.append(action(device, "left"))
                trace.append(action(device, "down"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "self_test_view": "preflight", "self_test_mode": "full_guided",
                    "lease_mask": 1,
                }, "preflight"))
                captures["preflight"] = capture(device, frames, "preflight")

                visual_states = [
                    "dialog_confirm", "unavailable", "degraded", "error", "running",
                ]
                state = action(device, "right")
                trace.append(state)
                for index, visual in enumerate(visual_states):
                    failures.extend(expect(state, {
                        "self_test_view": "visual_check",
                        "self_test_visual_state": visual,
                        "self_test_mode": "full_guided", "lease_mask": 1,
                    }, f"visual_{visual}"))
                    captures[f"visual_{visual}"] = capture(
                        device, frames, f"visual-{visual.replace('_', '-')}")
                    if index + 1 < len(visual_states):
                        state = action(device, "right")
                        trace.append(state)
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "self_test_view": "result", "self_test_status": "blocked",
                    "self_test_checks": 20, "self_test_passed": 16,
                    "self_test_failed": 0, "self_test_blocked": 1,
                    "self_test_not_applicable": 3, "lease_mask": 1,
                }, "full_result"))
                captures["full_result"] = capture(device, frames, "full-result")
                full = query(device, b"self-test.report", REPORT_SCHEMA, "report")
                failures.extend(report_failures(full, full=True))
                shield_probe = query(
                    device, b"hardware.shield.receivers",
                    "leshy.shield.receiver_probe.v1", "report",
                )
                failures.extend(shield_probe_failures(shield_probe))

                trace.append(action(device, "left"))
                state = action(device, "left")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final"))
                captures["home"] = capture(device, frames, "home")
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                input_state = query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
                if (recovery_after.get("generation") != recovery_before.get("generation") or
                        recovery_after.get("observations") !=
                        recovery_before.get("observations") or
                        recovery_after.get("physical_write_calls") != 0):
                    failures.append("Self-Test changed the recovered product artifact")
            except Exception as error:
                failures.append(f"self_test_phase: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: terminal zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "recovery_before": recovery_before,
        "quick_report": quick,
        "full_report": full,
        "shield_receiver_probe": shield_probe,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "recovery_after": recovery_after,
        "final": final,
        "captures": captures,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "privacy": {
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "self_test_report_contains_nearby_identifiers": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "failures": failures, "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
