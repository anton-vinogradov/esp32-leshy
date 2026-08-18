#!/usr/bin/env python3
"""Validate durable source-timeline commit, cold reopen, UI and export."""

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


RUN_SCHEMA = "leshy.source_timeline_persistence_hil.run.v1"


def timeline_failures(state: dict[str, Any], terminal: bool) -> list[str]:
    failures = expect(state, {
        "survey_timeline_state": "stopped" if terminal else "running",
        "survey_timeline_healthy": True,
        "survey_timeline_selected_mask": 1,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_queue_high_water": 1,
        "survey_timeline_overflow": 0,
        "survey_timeline_ble_state": "unselected",
        "survey_timeline_ble_duty_permille": 0,
        "survey_timeline_ble_accepted": 0,
        "survey_timeline_ble_dropped": 0,
        "survey_timeline_wifi_dropped": 0,
        "survey_timeline_archive_status": "finalized" if terminal else "appended",
        "survey_timeline_persisted": terminal,
    }, "timeline")
    accepted = state.get("survey_timeline_wifi_accepted")
    forwarded = state.get("survey_forwarded")
    duty = state.get("survey_timeline_wifi_duty_permille")
    archived = state.get("survey_timeline_archived_windows")
    persisted = state.get("survey_timeline_persisted_windows")
    retained = state.get("survey_timeline_retained_windows")
    evicted = state.get("survey_timeline_evicted_windows")
    minimum_windows = 5 if terminal else 4
    if not isinstance(accepted, int) or accepted < 1 or accepted != forwarded:
        failures.append("timeline.wifi_accepted: expected exact forwarded count")
    if not isinstance(duty, int) or duty < 1 or duty > 1000:
        failures.append("timeline.wifi_duty_permille: expected 1..1000")
    if not isinstance(archived, int) or archived < minimum_windows:
        failures.append(f"timeline.archived_windows: expected >= {minimum_windows}")
    if terminal:
        if persisted != archived:
            failures.append("timeline.persisted_windows: expected exact archived count")
        if not isinstance(retained, int) or retained != min(archived, 16):
            failures.append("timeline.retained_windows: bounded history mismatch")
        if not isinstance(evicted, int) or evicted != archived - retained:
            failures.append("timeline.evicted_windows: explicit eviction mismatch")
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
    }, "library_export")
    session = artifact.get("session")
    if not isinstance(session, dict):
        return failures + ["library_export.session: missing"]
    failures.extend(expect(session, {
        "schema": "leshy.session.summary.v2",
        "id": "product-wifi-live",
        "observations": observations,
        "dropped": 0,
    }, "library_export.session"))
    timeline = session.get("timeline")
    if not isinstance(timeline, dict):
        return failures + ["library_export.session.timeline: missing"]
    failures.extend(expect(timeline, {
        "selected_mask": 1,
        "overflow": 0,
    }, "library_export.session.timeline"))
    windows = timeline.get("windows")
    retained = timeline.get("retained")
    evicted = timeline.get("evicted")
    if not isinstance(windows, int) or windows < 5:
        failures.append("library_export.timeline.windows: expected >= 5")
    elif retained != min(windows, 16) or evicted != windows - retained:
        failures.append("library_export.timeline: retained/evicted mismatch")
    wifi = timeline.get("wifi")
    ble = timeline.get("ble")
    if not isinstance(wifi, dict) or not isinstance(ble, dict):
        failures.append("library_export.timeline.sources: missing")
    else:
        failures.extend(expect(wifi, {
            "accepted": observations,
            "dropped": 0,
        }, "library_export.timeline.wifi"))
        duty = wifi.get("duty_permille")
        if not isinstance(duty, int) or duty < 1 or duty > 1000:
            failures.append("library_export.timeline.wifi.duty_permille: expected 1..1000")
        failures.extend(expect(ble, {
            "scheduled_us": 0,
            "active_us": 0,
            "unavailable_us": 0,
            "fault_us": 0,
            "duty_permille": 0,
            "accepted": 0,
            "dropped": 0,
        }, "library_export.timeline.ble"))
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
    run_id = secrets.token_hex(16)
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    timing_before: dict[str, Any] = {}
    running: dict[str, Any] = {}
    committed: dict[str, Any] = {}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    timing_after: dict[str, Any] = {}
    export: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
            time.sleep(1.0)
        boot_before, recovery_before, timing_before = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
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
                trace.append(action(device, "select"))
                start_row = action(device, "down")
                trace.append(start_row)
                failures.extend(expect(start_row, {
                    "page": "survey",
                    "survey_setup_view": "plan",
                    "survey_setup_selection": 1,
                    "survey_source_selected_mask": 1,
                    "survey_source_can_start": True,
                }, "start_row"))
                start_ack = action(device, "select")
                trace.append(start_ack)
                failures.extend(expect(start_ack, {
                    "survey_product_status": "preparing",
                    "survey_workflow_state": "setup",
                }, "start_ack"))
                if not failures:
                    running = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "running" and
                            state.get("survey_product_scan_cycles", 0) >= 2 and
                            state.get("survey_timeline_archived_windows", 0) >= 4
                        ),
                        30.0,
                        "durable timeline did not reach two scan cycles",
                    )
                    trace.append(running)
                    failures.extend(expect(running, {
                        "runtime_owner": "survey",
                        "lease_mask": 15,
                        "survey_workflow_state": "running",
                        "survey_product_backend_open": True,
                        "survey_scan_status": "valid",
                        "survey_scan_dropped": 0,
                        "survey_dropped": 0,
                    }, "running"))
                    failures.extend(timeline_failures(running, False))
                    captures["running"] = capture(device, frames, "running")
                if not failures:
                    trace.append(action(device, "select"))
                    stop_ack = action(device, "select")
                    trace.append(stop_ack)
                    failures.extend(expect(stop_ack, {
                        "survey_product_status": "stopping",
                        "survey_workflow_state": "running",
                    }, "stop_ack"))
                    committed = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "committed" and
                            state.get("survey_workflow_state") == "result"
                        ),
                        20.0,
                        "durable timeline candidate did not commit",
                    )
                    trace.append(committed)
                    failures.extend(expect(committed, {
                        "survey_generation": before_generation + 1,
                        "survey_product_cleanup_complete": True,
                        "survey_product_backend_open": False,
                        "survey_product_source_active": False,
                    }, "committed"))
                    failures.extend(timeline_failures(committed, True))
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
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
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
                    failures.extend(expect(library, {
                        "page": "library",
                        "runtime_owner": "library",
                        "lease_mask": 5,
                        "library_persistent": True,
                        "library_generation": generation,
                        "survey_timeline_persisted": True,
                    }, "library"))
                    detail = action(device, "select")
                    trace.append(detail)
                    captures["library_detail"] = capture(
                        device, frames, "library-detail"
                    )
                    trace.append(action(device, "right"))
                    captures["export"] = capture(device, frames, "export")
                    export = query(
                        device, b"library.export",
                        "leshy.library.export.v1", "artifact",
                    )
                    failures.extend(export_failures(
                        export, generation, observations
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
        "run_id": run_id,
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
        "library_export": export,
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
