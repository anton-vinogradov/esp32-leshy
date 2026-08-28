#!/usr/bin/env python3
"""Validate the exact receive-only Wi-Fi + BLE Survey on real hardware."""

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


RUN_SCHEMA = "leshy.passive_ble_hil.run.v1"
WIFI_MASK = 1
BLE_MASK = 2
DUAL_MASK = WIFI_MASK | BLE_MASK


def running_failures(state: dict[str, Any]) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "running",
        "survey_product_status": "running",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": True,
        "survey_product_selected_source_mask": DUAL_MASK,
        "survey_product_active_source_mask": DUAL_MASK,
        "survey_product_unavailable_source_mask": 0,
        "survey_scan_status": "valid",
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_ble_scan_status": "valid",
        "survey_ble_scan_rejected": 0,
        "survey_ble_scan_dropped": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_timeline_state": "running",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": DUAL_MASK,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_wifi_dropped": 0,
        "survey_timeline_ble_dropped": 0,
    }, "running")
    wifi_cycles = state.get("survey_product_wifi_scan_cycles")
    ble_cycles = state.get("survey_product_ble_scan_cycles")
    cycles = state.get("survey_product_scan_cycles")
    if not all(isinstance(value, int) and value >= 1
               for value in (wifi_cycles, ble_cycles, cycles)):
        failures.append("running.scan_cycles: expected one complete dual-source cycle")
    wifi = state.get("survey_scan_accepted")
    ble = state.get("survey_ble_scan_accepted")
    observations = state.get("survey_observations")
    forwarded = state.get("survey_forwarded")
    if not isinstance(wifi, int) or wifi < 1:
        failures.append("running.wifi_accepted: expected >= 1")
    if not isinstance(ble, int) or ble < 1:
        failures.append("running.ble_accepted: expected >= 1")
    if not isinstance(wifi, int) or not isinstance(ble, int) or \
            observations != wifi + ble or forwarded != observations:
        failures.append("running.observations: source accounting mismatch")
    for prefix in ("survey_scan", "survey_ble_scan"):
        reported = state.get(f"{prefix}_reported")
        read = state.get(f"{prefix}_read")
        accepted = state.get(f"{prefix}_accepted")
        if reported != read or read != accepted:
            failures.append(f"running.{prefix}: reported/read/accepted mismatch")
    for source in ("wifi", "ble"):
        accepted = state.get(f"survey_timeline_{source}_accepted")
        scan_accepted = state.get(
            "survey_scan_accepted" if source == "wifi"
            else "survey_ble_scan_accepted"
        )
        duty = state.get(f"survey_timeline_{source}_duty_permille")
        if accepted != scan_accepted:
            failures.append(f"running.timeline_{source}: accepted mismatch")
        if not isinstance(duty, int) or duty < 1 or duty > 1000:
            failures.append(f"running.timeline_{source}: invalid duty")
    archived = state.get("survey_timeline_archived_windows")
    if not isinstance(archived, int) or archived < 4:
        failures.append("running.timeline: expected >= 4 archived windows")
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
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
        "survey_product_selected_source_mask": DUAL_MASK,
        "survey_product_unavailable_source_mask": 0,
        "survey_dropped": 0,
        "survey_timeline_state": "stopped",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": DUAL_MASK,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_archive_status": "finalized",
        "survey_timeline_persisted": True,
    }, "committed")
    archived = state.get("survey_timeline_archived_windows")
    persisted = state.get("survey_timeline_persisted_windows")
    retained = state.get("survey_timeline_retained_windows")
    evicted = state.get("survey_timeline_evicted_windows")
    if not isinstance(archived, int) or archived < 6 or persisted != archived:
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
    }, "export.session"))
    sources = session.get("sources")
    if not isinstance(sources, dict):
        failures.append("export.sources: missing")
    else:
        wifi_observations = sources.get("wifi")
        ble_observations = sources.get("ble")
        if not isinstance(wifi_observations, int) or wifi_observations < 1:
            failures.append("export.sources.wifi: expected >= 1")
        if not isinstance(ble_observations, int) or ble_observations < 1:
            failures.append("export.sources.ble: expected >= 1")
        if (isinstance(wifi_observations, int) and
                isinstance(ble_observations, int) and
                wifi_observations + ble_observations != observations):
            failures.append("export.sources: observation accounting mismatch")
    timeline = session.get("timeline")
    if not isinstance(timeline, dict):
        return failures + ["export.timeline: missing"]
    failures.extend(expect(timeline, {
        "selected_mask": DUAL_MASK,
        "overflow": 0,
    }, "export.timeline"))
    started = timeline.get("started_us")
    stopped = timeline.get("stopped_us")
    windows = timeline.get("windows")
    retained = timeline.get("retained")
    evicted = timeline.get("evicted")
    if not isinstance(started, int) or not isinstance(stopped, int) or stopped < started:
        failures.append("export.timeline: invalid time bounds")
        elapsed = None
    else:
        elapsed = stopped - started
    if not isinstance(windows, int) or windows < 6:
        failures.append("export.timeline: expected >= 6 windows")
    elif retained != min(windows, 16) or evicted != windows - retained:
        failures.append("export.timeline: retained/evicted mismatch")
    source_total = 0
    for source in ("wifi", "ble"):
        summary = timeline.get(source)
        if not isinstance(summary, dict):
            failures.append(f"export.timeline.{source}: missing")
            continue
        accepted = summary.get("accepted")
        source_total += accepted if isinstance(accepted, int) else 0
        if not isinstance(accepted, int) or accepted < 1:
            failures.append(f"export.timeline.{source}: expected accepted >= 1")
        if summary.get("dropped") != 0:
            failures.append(f"export.timeline.{source}: expected zero drops")
        duty = summary.get("duty_permille")
        if not isinstance(duty, int) or duty < 1 or duty > 1000:
            failures.append(f"export.timeline.{source}: invalid duty")
        if elapsed is not None:
            duration = sum(summary.get(field, 0) for field in (
                "scheduled_us", "active_us", "unavailable_us", "fault_us"
            ))
            if duration != elapsed:
                failures.append(f"export.timeline.{source}: duration mismatch")
    if source_total != observations:
        failures.append("export.timeline: source observations mismatch")
    retained_windows = artifact.get("timeline_windows")
    if not isinstance(retained_windows, list) or len(retained_windows) != retained:
        failures.append("export.timeline_windows: retained list mismatch")
    else:
        seen = {window.get("source") for window in retained_windows
                if isinstance(window, dict)}
        if not {"wifi", "ble"}.issubset(seen):
            failures.append("export.timeline_windows: both sources not retained")
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
    running: dict[str, Any] = {}
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
                start_row = action(device, "down")
                trace.append(start_row)
                start_ack = action(device, "select")
                trace.append(start_ack)
                if not failures:
                    running = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "running" and
                            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
                            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
                            state.get("survey_timeline_archived_windows", 0) >= 4
                        ),
                        45.0,
                        "dual passive Survey did not reach one complete cycle",
                    )
                    trace.append(running)
                    failures.extend(running_failures(running))
                    captures["running"] = capture(device, frames, "running")
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
                        "dual passive Survey did not commit",
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
                    library = action(device, "select")
                    trace.append(library)
                    detail = action(device, "select")
                    trace.append(detail)
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
        "running": running,
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
