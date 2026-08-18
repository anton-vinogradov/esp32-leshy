#!/usr/bin/env python3
"""Validate exact one-source degradation and continued Survey on real hardware."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

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
    recovered_failures,
    reset_capture,
    valid_cid,
    wait_ui_state,
)


RUN_SCHEMA = "leshy.runtime_degradation_hil.run.v1"
INJECTION_SCHEMA = "leshy.survey.runtime_unavailable_test.v1"
WIFI_MASK = 1
BLE_MASK = 2
DUAL_MASK = WIFI_MASK | BLE_MASK


def injection_failures(state: dict[str, Any]) -> list[str]:
    return expect(state, {
        "status": "armed",
        "one_shot": True,
        "armed_mask": BLE_MASK,
        "worker_idle": True,
        "ui_home": True,
        "runtime_owner": "none",
        "lease_mask": 0,
        "hardware_touched": False,
        "storage_mounted": False,
        "storage_written": False,
    }, "injection")


def degraded_failures(state: dict[str, Any]) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "running",
        "survey_product_status": "running_degraded",
        "survey_product_backend_open": True,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": True,
        "survey_product_selected_source_mask": DUAL_MASK,
        "survey_product_active_source_mask": WIFI_MASK,
        "survey_product_unavailable_source_mask": BLE_MASK,
        "survey_product_source_failure_injected": False,
        "survey_product_runtime_source_failure_injected": True,
        "survey_product_runtime_source_failure_injected_mask": BLE_MASK,
        "survey_product_runtime_source_injection_armed_mask": 0,
        "survey_scan_status": "valid",
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_ble_scan_status": "not_started",
        "survey_ble_scan_reported": 0,
        "survey_ble_scan_read": 0,
        "survey_ble_scan_accepted": 0,
        "survey_ble_scan_rejected": 0,
        "survey_ble_scan_dropped": 0,
        "survey_product_ble_scan_cycles": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_timeline_state": "running",
        "survey_timeline_healthy": True,
        "survey_timeline_failure_status": "none",
        "survey_timeline_selected_mask": DUAL_MASK,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_ble_state": "unavailable",
        "survey_timeline_ble_accepted": 0,
        "survey_timeline_ble_dropped": 0,
        "survey_timeline_wifi_dropped": 0,
    }, "degraded")
    wifi_cycles = state.get("survey_product_wifi_scan_cycles")
    scan_cycles = state.get("survey_product_scan_cycles")
    if not isinstance(wifi_cycles, int) or wifi_cycles < 2:
        failures.append("degraded.wifi_cycles: expected continuation after BLE loss")
    if scan_cycles != wifi_cycles:
        failures.append("degraded.scan_cycles: active-source progress mismatch")
    wifi = state.get("survey_scan_accepted")
    observations = state.get("survey_observations")
    forwarded = state.get("survey_forwarded")
    if not isinstance(wifi, int) or wifi < 1:
        failures.append("degraded.wifi_accepted: expected >= 1")
    if observations != wifi or forwarded != observations:
        failures.append("degraded.observations: surviving-source accounting mismatch")
    if state.get("survey_timeline_wifi_accepted") != wifi:
        failures.append("degraded.timeline_wifi: accepted mismatch")
    archived = state.get("survey_timeline_archived_windows")
    if not isinstance(archived, int) or archived < 6:
        failures.append("degraded.timeline: expected >= 6 archived windows")
    return failures


def committed_failures(state: dict[str, Any], generation: int) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "result",
        "survey_product_status": "committed",
        "survey_generation": generation,
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
        "survey_product_selected_source_mask": DUAL_MASK,
        "survey_product_active_source_mask": WIFI_MASK,
        "survey_product_unavailable_source_mask": BLE_MASK,
        "survey_product_runtime_source_failure_injected": True,
        "survey_product_runtime_source_failure_injected_mask": BLE_MASK,
        "survey_product_ble_scan_cycles": 0,
        "survey_dropped": 0,
        "survey_timeline_state": "stopped",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": DUAL_MASK,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_archive_status": "finalized",
        "survey_timeline_persisted": True,
    }, "committed")
    observations = state.get("survey_observations")
    if not isinstance(observations, int) or observations < 1:
        failures.append("committed.observations: expected surviving Wi-Fi records")
    if state.get("survey_scan_accepted") != observations or \
            state.get("survey_ble_scan_accepted") != 0:
        failures.append("committed.observations: per-source mismatch")
    archived = state.get("survey_timeline_archived_windows")
    persisted = state.get("survey_timeline_persisted_windows")
    retained = state.get("survey_timeline_retained_windows")
    evicted = state.get("survey_timeline_evicted_windows")
    if not isinstance(archived, int) or archived < 8 or persisted != archived:
        failures.append("committed.timeline: incomplete persisted window count")
    elif retained != min(archived, 16) or evicted != archived - retained:
        failures.append("committed.timeline: retained/evicted mismatch")
    return failures


def export_failures(artifact: dict[str, Any], generation: int,
                    observations: int) -> list[str]:
    failures = expect(artifact, {
        "status": "valid",
        "generation": generation,
        "integrity": "valid",
        "persistent": True,
        "simulated": False,
        "storage_backend": "persistent_media",
        "radio_touched": False,
    }, "export")
    session = artifact.get("session")
    if not isinstance(session, dict):
        return failures + ["export.session: missing"]
    failures.extend(expect(session, {
        "schema": "leshy.session.summary.v2",
        "id": "product-passive-live",
        "observations": observations,
        "dropped": 0,
        "sources": {"wifi": observations, "ble": 0},
    }, "export.session"))
    timeline = session.get("timeline")
    if not isinstance(timeline, dict):
        return failures + ["export.timeline: missing"]
    failures.extend(expect(timeline, {
        "selected_mask": DUAL_MASK,
        "overflow": 0,
    }, "export.timeline"))
    started = timeline.get("started_us")
    stopped = timeline.get("stopped_us")
    if not isinstance(started, int) or not isinstance(stopped, int) or stopped < started:
        failures.append("export.timeline: invalid time bounds")
        elapsed = None
    else:
        elapsed = stopped - started
    windows = timeline.get("windows")
    retained = timeline.get("retained")
    evicted = timeline.get("evicted")
    if not isinstance(windows, int) or windows < 8:
        failures.append("export.timeline: expected >= 8 windows")
    elif retained != min(windows, 16) or evicted != windows - retained:
        failures.append("export.timeline: retained/evicted mismatch")
    wifi = timeline.get("wifi")
    ble = timeline.get("ble")
    if not isinstance(wifi, dict) or not isinstance(ble, dict):
        return failures + ["export.timeline: per-source summary missing"]
    failures.extend(expect(wifi, {
        "accepted": observations,
        "dropped": 0,
        "unavailable_us": 0,
        "fault_us": 0,
    }, "export.timeline.wifi"))
    failures.extend(expect(ble, {
        "accepted": 0,
        "dropped": 0,
        "fault_us": 0,
    }, "export.timeline.ble"))
    if not isinstance(ble.get("unavailable_us"), int) or \
            ble.get("unavailable_us", 0) < 1:
        failures.append("export.timeline.ble: unavailable duration missing")
    if elapsed is not None:
        for source, summary in (("wifi", wifi), ("ble", ble)):
            duration = sum(summary.get(field, 0) for field in (
                "scheduled_us", "active_us", "unavailable_us", "fault_us"
            ))
            if duration != elapsed:
                failures.append(f"export.timeline.{source}: duration mismatch")
    retained_windows = artifact.get("timeline_windows")
    if not isinstance(retained_windows, list) or len(retained_windows) != retained:
        failures.append("export.timeline_windows: retained list mismatch")
    elif not any(
        isinstance(window, dict) and
        window.get("source") == "ble" and
        window.get("state") == "unavailable" and
        window.get("reason") == "driver_unavailable"
        for window in retained_windows
    ):
        failures.append("export.timeline_windows: BLE unavailability not retained")
    return failures


def main() -> int:
    from capture_1x_ui import PassiveSerial, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be exactly 32 uppercase hexadecimal characters")

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
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    injection: dict[str, Any] = {}
    degraded: dict[str, Any] = {}
    committed: dict[str, Any] = {}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    exported: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    timing_before: dict[str, Any] = {}
    timing_after: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
            time.sleep(1.0)
        boot_before, recovery_before, timing_before = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                failures.extend(boot_failures(
                    boot_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid,
                ))
                before_generation = int(recovery_before.get("generation", 0))
                if failures:
                    raise RuntimeError("preflight boot contract failed")
                injection = query(
                    device, b"survey.product.test-runtime-unavailable ble",
                    INJECTION_SCHEMA, "state",
                )
                failures.extend(injection_failures(injection))
                trace.append(action(device, "down"))
                setup = action(device, "select")
                trace.append(setup)
                failures.extend(expect(setup, {
                    "page": "survey",
                    "survey_setup_view": "plan",
                    "survey_source_selected_mask": DUAL_MASK,
                    "survey_source_selected_count": 2,
                    "survey_source_can_start": True,
                    "survey_source_wifi_state": "available",
                    "survey_source_ble_state": "available",
                }, "setup"))
                captures["setup"] = capture(device, frames, "setup")
                trace.append(action(device, "down"))
                trace.append(action(device, "select"))
                if not failures:
                    degraded = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") ==
                                "running_degraded" and
                            state.get("survey_product_active_source_mask") ==
                                WIFI_MASK and
                            state.get("survey_product_unavailable_source_mask") ==
                                BLE_MASK and
                            state.get("survey_product_wifi_scan_cycles", 0) >= 2 and
                            state.get("survey_timeline_ble_state") == "unavailable"
                        ),
                        45.0,
                        "Survey did not continue on Wi-Fi after injected BLE loss",
                    )
                    trace.append(degraded)
                    failures.extend(degraded_failures(degraded))
                    captures["degraded"] = capture(device, frames, "degraded")
                if not failures:
                    trace.append(action(device, "select"))
                    trace.append(action(device, "select"))
                    committed = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "committed" and
                            state.get("survey_workflow_state") == "result"
                        ),
                        25.0,
                        "degraded Survey did not commit",
                    )
                    trace.append(committed)
                    failures.extend(committed_failures(
                        committed, before_generation + 1
                    ))
                    captures["committed"] = capture(device, frames, "committed")
                    trace.append(action(device, "back"))
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    failures.append("cleanup_before: terminal zero-lease state unproven")

        if committed and not failures:
            boot_after, recovery_after, timing_after = reset_capture(
                args.port, args.output, "boot-after", args.boot_seconds
            )
            generation = int(committed["survey_generation"])
            observations = int(committed["survey_observations"])
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                try:
                    synchronize_console(device)
                    recovery_after = query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state",
                    )
                    failures.extend(boot_failures(
                        boot_after, recovery_after, args.expected_version,
                        app_identity, args.expected_cid,
                    ))
                    failures.extend(recovered_failures(
                        recovery_after, generation, observations,
                        args.expected_cid,
                    ))
                    trace.append(action(device, "down"))
                    trace.append(action(device, "down"))
                    trace.append(action(device, "select"))
                    trace.append(action(device, "select"))
                    captures["library_detail"] = capture(
                        device, frames, "library-detail"
                    )
                    trace.append(action(device, "right"))
                    captures["export"] = capture(device, frames, "export")
                    exported = query(
                        device, b"library.export",
                        "leshy.library.export.v1", "artifact",
                    )
                    failures.extend(export_failures(
                        exported, generation, observations
                    ))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    final = query(device, b"ui.state", "leshy.ui.v1", "state")
                    failures.extend(expect(final, {
                        "page": "home",
                        "runtime_owner": "none",
                        "lease_mask": 0,
                        "survey_product_runtime_source_injection_armed_mask": 0,
                    }, "final"))
                except Exception as error:
                    failures.append(f"post_boot: {type(error).__name__}: {error}")
                finally:
                    cleanup_after = best_effort_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("cleanup_after: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "boot_before": {"ready": boot_before, "recovery": recovery_before,
                        "timing": timing_before},
        "injection": injection,
        "degraded": degraded,
        "committed": committed,
        "cleanup_before": cleanup_before,
        "boot_after": {"ready": boot_after, "recovery": recovery_after,
                       "timing": timing_after},
        "library_export": exported,
        "final": final,
        "cleanup_after": cleanup_after,
        "captures": captures,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": result["failures"],
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
