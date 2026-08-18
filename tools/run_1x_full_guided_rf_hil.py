#!/usr/bin/env python3
"""Prove plan-v6 active RF and read-only artifact checks on the real device."""

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


RUN_SCHEMA = "leshy.full_guided_artifact_self_test_hil.run.v1"
REPORT_SCHEMA = "leshy.self_test.report.v1"
ACTIVE_RF_SCHEMA = "leshy.self_test.active_rf.v1"
ACTIVE_ARTIFACT_SCHEMA = "leshy.self_test.active_artifact.v1"
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
    ("full.s4.spectrum.nrf24.receive", "pass"),
    ("full.s4.spectrum.cc1101.receive", "pass"),
    ("full.s4.storage.recovery.audit", "pass"),
    ("full.s4.library.export.audit", "pass"),
    ("full.s4.capture.pcap.audit", "pass"),
    ("full.capability.coverage", "blocked"),
]


def report_failures(report: dict[str, Any], *, full: bool) -> list[str]:
    failures = expect(report, {
        "schema_version": 1,
        "plan_version": 6,
        "mode": "full_guided" if full else "quick",
        "status": "blocked" if full else "pass",
        "read_only": not full,
        "cancelled": False,
        "passed": 21 if full else 8,
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
            "nrf24_spectrum_exercise_complete",
            "nrf24_spectrum_exercise_passed",
            "cc1101_spectrum_exercise_complete",
            "cc1101_spectrum_exercise_passed",
            "persistent_recovery_audit_complete",
            "persistent_recovery_audit_passed",
            "library_export_audit_complete",
            "library_export_audit_passed",
            "capture_pcap_audit_complete",
            "capture_pcap_audit_applicable",
            "capture_pcap_audit_passed",
        ):
            if facts.get(key) is not True:
                failures.append(f"shield receiver fact is not true: {key}")
    return failures


def active_rf_failures(report: dict[str, Any]) -> list[str]:
    failures = expect(report, {
        "plan_version": 6, "step": "complete", "rx_only": True,
        "resource_acquired": True, "resource_released": True,
        "cleanup_complete": True, "current_owner": "self-test",
        "current_lease_mask": 1,
    }, "active_rf")
    nrf = report.get("nrf24", {})
    failures.extend(expect(nrf, {
        "complete": True, "passed": True, "sweeps": 1,
        "channels": 83, "modules": 2, "cleanup_complete": True,
    }, "active_rf.nrf24"))
    if nrf.get("wire") != {
        "register_reads": 93, "register_writes": 95,
        "spi_bytes_clocked": 376, "receive_ce_high_events": 83,
    }:
        failures.append(f"nRF24 active wire differs: {nrf.get('wire')!r}")
    cc = report.get("cc1101", {})
    failures.extend(expect(cc, {
        "complete": True, "passed": True, "band": "433", "bins": 64,
        "cleanup_complete": True,
    }, "active_rf.cc1101"))
    wire = cc.get("wire", {})
    reads = wire.get("register_reads")
    if not isinstance(reads, int) or reads < 130:
        failures.append(f"CC1101 active reads are implausible: {reads!r}")
    # begin() contributes one reset strobe. Each bin is explicitly bounded by
    # SIDLE -> tune -> SRX -> RSSI read -> SIDLE, and end() adds one SIDLE.
    # Therefore 64 bins produce 1 + (3 * 64) + 1 = 194 command strobes,
    # including 2 * 64 + 1 = 129 idle strobes.
    if (wire.get("register_writes") != 208 or
            wire.get("command_strobes") != 194 or
            wire.get("reset_strobes") != 1 or
            wire.get("receive_strobes") != 64 or
            wire.get("idle_strobes") != 129 or
            isinstance(reads, int) and
            wire.get("spi_bytes_clocked") != 2 * (reads + 208) + 194):
        failures.append(f"CC1101 active wire differs: {wire!r}")
    expected_effects = {
        "radio_tx_commands": 0, "nrf_tx_mode_entries": 0,
        "nrf_tx_payload_commands": 0, "cc_tx_strobes": 0,
        "cc_pa_table_writes": 0, "cc_fifo_writes": 0,
        "cc_rejected_strobes": 0, "storage_write_commands": 0,
    }
    if report.get("side_effects") != expected_effects:
        failures.append(
            f"active RF side effects differ: {report.get('side_effects')!r}")
    return failures


def active_artifact_failures(report: dict[str, Any],
                             recovery: dict[str, Any]) -> list[str]:
    failures = expect(report, {
        "plan_version": 6, "step": "complete", "read_only": True,
        "expected_cid": recovery.get("expected_fingerprint"),
        "cleanup_complete": True, "current_owner": "self-test",
        "current_lease_mask": 1,
    }, "active_artifact")
    recovered = report.get("recovery", {})
    failures.extend(expect(recovered, {
        "complete": True, "passed": True, "status": "admitted",
        "generation_before": recovery.get("generation"),
        "generation_after": recovery.get("generation"),
        "observations_before": recovery.get("observations"),
        "observations_after": recovery.get("observations"),
        "mounted_read_only": True, "cleanup_complete": True,
    }, "active_artifact.recovery"))
    library = report.get("library", {})
    failures.extend(expect(library, {
        "complete": True, "passed": True,
        "csv_records": recovery.get("observations"),
    }, "active_artifact.library"))
    for field in ("json_bytes", "metadata_bytes", "csv_bytes"):
        value = library.get(field)
        if not isinstance(value, int) or value <= 0:
            failures.append(f"artifact library {field} is invalid: {value!r}")
    capture = report.get("capture", {})
    failures.extend(expect(capture, {
        "complete": True, "applicable": True, "passed": True,
        "pcap_frames": 16, "pcap_bytes": 2773,
    }, "active_artifact.capture"))
    if not isinstance(capture.get("pcap_fnv1a"), int) or not capture.get(
            "pcap_fnv1a"):
        failures.append("artifact PCAP digest is absent")
    if report.get("side_effects") != {
        "radio_tx_commands": 0, "storage_write_commands": 0,
        "blocked_write_attempts": 0,
    }:
        failures.append(
            f"artifact side effects differ: {report.get('side_effects')!r}")
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
    active_rf: dict[str, Any] = {}
    active_artifact: dict[str, Any] = {}
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
                    "self_test_view": "active_checks",
                    "self_test_active_step": "idle", "lease_mask": 1,
                }, "active_checks"))
                captures["active_checks"] = capture(
                    device, frames, "active-checks")
                artifact_captured = False
                deadline = time.monotonic() + 30.0
                while time.monotonic() < deadline:
                    state = query(device, b"ui.state", "leshy.ui.v1", "state")
                    trace.append(state)
                    if state.get("self_test_view") == "result":
                        break
                    if (not artifact_captured and
                            state.get("self_test_active_step") == "complete" and
                            state.get("self_test_artifact_step") in {
                                "recover", "library_json", "library_csv",
                                "capture_pcap",
                            }):
                        captures["active_artifacts"] = capture(
                            device, frames, "active-artifacts")
                        artifact_captured = True
                    time.sleep(0.05)
                if not artifact_captured:
                    failures.append("active artifact UI phase was not captured")
                failures.extend(expect(state, {
                    "self_test_view": "result", "self_test_status": "blocked",
                    "self_test_checks": 25, "self_test_passed": 21,
                    "self_test_failed": 0, "self_test_blocked": 1,
                    "self_test_not_applicable": 3, "lease_mask": 1,
                }, "full_result"))
                captures["full_result"] = capture(device, frames, "full-result")
                full = query(device, b"self-test.report", REPORT_SCHEMA, "report")
                failures.extend(report_failures(full, full=True))
                active_rf = query(
                    device, b"self-test.active-rf", ACTIVE_RF_SCHEMA, "report")
                failures.extend(active_rf_failures(active_rf))
                active_artifact = query(
                    device, b"self-test.active-artifact",
                    ACTIVE_ARTIFACT_SCHEMA, "report")
                failures.extend(active_artifact_failures(
                    active_artifact, recovery_before))
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
        "active_rf": active_rf,
        "active_artifact": active_artifact,
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
