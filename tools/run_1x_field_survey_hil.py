#!/usr/bin/env python3
"""Flash once and prove first/revisit Field Survey product behavior."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action as raw_action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    committed_failures,
    expect,
    focus_survey_start,
    open_product_survey_visit,
    paused_failures,
    query,
    reset_capture,
    return_home_after_commit,
    running_failures,
    setup_failures,
    valid_cid,
)


RUN_SCHEMA = "leshy.field_survey_hil.run.v1"
FIELD_SCHEMA = "leshy.survey.field_visit.v1"
HIL_SCHEMA = "leshy.hil.session.v1"


def require(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def synchronize_console(device: Any, timeout: float) -> None:
    from capture_1x_ui import synchronize_console as synchronize

    synchronize(device, timeout)


def read_only_query(device: Any, command: bytes, schema: str,
                    kind: str, maximum_attempts: int = 3) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = query(device, command, schema, kind)
            record["host_transport_attempts"] = attempt
            record["host_transport_transient_retries"] = attempt - 1
            record["host_transport_transient_errors"] = errors
            return record
        except TimeoutError as error:
            if attempt == maximum_attempts:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable read-only retry state")


def action(device: Any, name: str,
           timeout: float = 15.0) -> dict[str, Any]:
    """Never replay a navigation write after a lost acknowledgement."""
    try:
        state = raw_action(device, name, timeout=timeout)
        state["host_navigation_ack_received"] = True
    except TimeoutError as error:
        state = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state")
        state["host_navigation_ack_received"] = False
        state["host_navigation_ack_error"] = str(error)
    state["host_navigation_action_writes"] = 1
    state["host_navigation_action_replays"] = 0
    return state


def wait_state(device: Any,
               predicate: Callable[[dict[str, Any]], bool],
               timeout: float, description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last={last!r}")


def field_state(device: Any) -> dict[str, Any]:
    return read_only_query(
        device, b"survey.field-visit", FIELD_SCHEMA, "state")


def field_result_failures(record: dict[str, Any], status: str,
                          baseline_unique: int | None = None) -> list[str]:
    failures = expect(record, {
        "active": True,
        "status": status,
        "build_status": "complete",
        "complete": True,
        "session_id_exact": True,
        "session_stopped": True,
        "radio_touched": False,
        "storage_touched": False,
    }, status)
    current = record.get("current_unique")
    wifi_ap = record.get("wifi_access_points")
    wifi_sta = record.get("wifi_stations")
    ble = record.get("ble_devices")
    if not isinstance(current, int) or current < 1:
        failures.append(f"{status}.current_unique: expected >= 1")
        return failures
    if not all(isinstance(value, int) and value >= 0
               for value in (wifi_ap, wifi_sta, ble)):
        failures.append(f"{status}.radio_counts: invalid")
    elif wifi_ap + wifi_sta + ble != current:
        failures.append(f"{status}.radio_counts: do not total current_unique")
    if status == "first_visit":
        failures.extend(expect(record, {
            "compare_previous": False,
            "baseline_unique": 0,
            "seen_again": 0,
            "new_this_visit": current,
            "missing_this_visit": 0,
        }, status))
    elif status == "compared":
        if baseline_unique is None or baseline_unique < 1:
            failures.append("compared.baseline_unique: missing expected baseline")
        else:
            failures.extend(expect(record, {
                "previous_available": True,
                "compare_previous": True,
                "baseline_unique": baseline_unique,
            }, status))
            seen = record.get("seen_again")
            new = record.get("new_this_visit")
            missing = record.get("missing_this_visit")
            if not all(isinstance(value, int) and value >= 0
                       for value in (seen, new, missing)):
                failures.append("compared.delta_counts: invalid")
            elif seen + new != current or seen + missing != baseline_unique:
                failures.append("compared.delta_counts: inconsistent set arithmetic")
    return failures


def begin_hil(device: Any, run_id: str, app_sha: str,
              version: str) -> dict[str, Any]:
    try:
        begun = query(
            device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
            HIL_SCHEMA, "begun")
        begun["host_begin_ack_received"] = True
    except TimeoutError as error:
        begun = read_only_query(device, b"hil.state", HIL_SCHEMA, "state")
        begun["host_begin_ack_received"] = False
        begun["host_begin_ack_error"] = str(error)
    require(begun, {
        "session_id": run_id, "active": True,
        "app_elf_sha256": app_sha, "firmware_version": version,
    }, "hil_begin")
    begun["host_begin_action_writes"] = 1
    begun["host_begin_action_replays"] = 0
    return begun


def end_hil(device: Any, run_id: str, app_sha: str) -> dict[str, Any]:
    try:
        ended = query(
            device, f"hil.end {run_id}".encode("ascii"),
            HIL_SCHEMA, "ended")
        ended["host_end_ack_received"] = True
    except TimeoutError as error:
        ended = read_only_query(device, b"hil.state", HIL_SCHEMA, "state")
        ended["host_end_ack_received"] = False
        ended["host_end_ack_error"] = str(error)
    require(ended, {
        "active": False, "app_elf_sha256": app_sha,
    }, "hil_end")
    if ended.get("session_id") not in (None, "", run_id):
        raise RuntimeError("hil_end: unexpected terminal session id")
    ended["host_end_action_writes"] = 1
    ended["host_end_action_replays"] = 0
    ended["host_end_requested_session_id"] = run_id
    return ended


def run_visit(device: Any, frames: Path, name: str,
              before_generation: int, first: bool,
              trace: list[dict[str, Any]], expected_cid: str,
              baseline_unique: int | None = None,
              run_incomplete_negative: bool = False) -> dict[str, Any]:
    setup = open_product_survey_visit(device, trace)
    failures = setup_failures(setup, "wifi")
    failures.extend(expect(setup, {
        "survey_source_selected_mask": 3,
        "survey_source_selected_count": 2,
        "survey_source_can_start": True,
    }, f"{name}.all_receivers"))
    if failures:
        raise RuntimeError("; ".join(failures))

    setup_field = field_state(device)
    require(setup_field, {"active": True}, f"{name}.field_setup")
    if first and setup_field.get("compare_previous") is True:
        selection = action(device, "down")
        trace.append(selection)
        require(selection, {"survey_setup_selection": 1},
                f"{name}.compare_row")
        toggled = action(device, "select")
        trace.append(toggled)
        setup_field = field_state(device)
    comparison_expected: dict[str, Any] = {
        "compare_previous": not first,
        "status": "empty",
    }
    if not first:
        comparison_expected["previous_available"] = True
    require(setup_field, comparison_expected, f"{name}.comparison_mode")
    setup_capture = capture(device, frames, f"{name}-setup")

    start = focus_survey_start(device)
    trace.append(start)
    started = action(device, "select")
    trace.append(started)
    require(started, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_status": "preparing",
    }, f"{name}.start_ack")
    running = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "running" and
            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
            state.get("survey_observations", 0) >= 1
        ), 35.0, f"{name}: both receive sources did not complete one cycle")
    trace.append(running)
    failures = running_failures(running, expected_cid, "wifi")
    failures.extend(expect(running, {
        "survey_product_selected_source_mask": 3,
        "survey_product_active_source_mask": 3,
        "survey_scan_dropped": 0,
        "survey_ble_scan_dropped": 0,
    }, f"{name}.running_sources"))
    if failures:
        raise RuntimeError("; ".join(failures))

    incomplete: dict[str, Any] = {}
    if run_incomplete_negative:
        incomplete = query(
            device, b"survey.field-visit.test-incomplete once",
            FIELD_SCHEMA, "state")
        require(incomplete, {
            "active": True,
            "status": "incomplete",
            "build_status": "session_not_stopped",
            "complete": False,
            "session_id_exact": True,
            "session_stopped": False,
            "radio_touched": False,
            "storage_touched": False,
        }, f"{name}.incomplete_negative")

    pause_ack = action(device, "up")
    trace.append(pause_ack)
    paused = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False
    ), 20.0, f"{name}: did not pause")
    trace.append(paused)
    paused_observations = int(paused["survey_observations"])
    paused_cycles = int(paused["survey_product_scan_cycles"])
    failures = paused_failures(
        paused, paused_observations, paused_cycles, "wifi")
    time.sleep(0.25)
    paused_stable = read_only_query(
        device, b"ui.state", "leshy.ui.v1", "state")
    failures.extend(expect(paused_stable, {
        "survey_product_status": "paused",
        "survey_product_source_active": False,
        "survey_observations": paused_observations,
        "survey_product_scan_cycles": paused_cycles,
    }, f"{name}.paused_stable"))
    if failures:
        raise RuntimeError("; ".join(failures))

    trace.append(action(device, "down"))
    trace.append(action(device, "right"))
    committed = action(device, "select", timeout=40.0)
    trace.append(committed)
    if committed.get("survey_product_status") != "committed":
        committed = wait_state(
            device,
            lambda state: state.get("survey_product_status") == "committed",
            20.0, f"{name}: did not commit")
        trace.append(committed)
    failures = committed_failures(committed, before_generation, "wifi")
    if failures:
        raise RuntimeError("; ".join(failures))

    result = field_state(device)
    result_failures = field_result_failures(
        result, "first_visit" if first else "compared",
        None if first else baseline_unique)
    if result_failures:
        raise RuntimeError("; ".join(result_failures))
    result_capture = capture(device, frames, f"{name}-result")
    home = return_home_after_commit(device, trace)
    require(home, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_source_active": False,
    }, f"{name}.home")
    return {
        "setup": setup,
        "setup_field": setup_field,
        "setup_capture": setup_capture,
        "running": running,
        "incomplete_negative": incomplete,
        "paused": paused,
        "committed": committed,
        "result": result,
        "result_capture": result_capture,
        "home": home,
    }


def main() -> int:
    from capture_1x_ui import PassiveSerial

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hex characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_sha = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    begun: dict[str, Any] = {}
    ended: dict[str, Any] = {}
    first: dict[str, Any] = {}
    revisit: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    boot: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    boot_timing: dict[str, Any] = {}
    flashed = False
    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "run_id": run_id,
        "source_commit": args.source_commit,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_sha,
        },
    }
    write_json(args.output / "run.json", record)

    try:
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        flashed = True
        time.sleep(0.75)
        boot, recovery, boot_timing = reset_capture(
            args.port, args.output, "boot", 20.0, maximum_attempts=2)
        failures.extend(boot_failures(
            boot, recovery, args.expected_version, app_sha,
            args.expected_cid))
        if failures:
            raise RuntimeError("; ".join(failures))

        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 20.0)
            try:
                begun = begin_hil(device, run_id, app_sha,
                                  args.expected_version)
                generation = int(recovery["generation"])
                first = run_visit(
                    device, frames, "first", generation, True, trace,
                    args.expected_cid,
                    run_incomplete_negative=True)
                first_result = first["result"]
                first_unique = int(first_result["current_unique"])
                generation += 1
                revisit = run_visit(
                    device, frames, "revisit", generation, False, trace,
                    args.expected_cid, baseline_unique=first_unique)
                ended = end_hil(device, run_id, app_sha)
            finally:
                cleanup = best_effort_cleanup(device)
                if not ended:
                    try:
                        hil_state = read_only_query(
                            device, b"hil.state", HIL_SCHEMA, "state")
                        if (hil_state.get("active") is True and
                                hil_state.get("session_id") == run_id):
                            ended = end_hil(device, run_id, app_sha)
                        elif hil_state.get("active") is True:
                            failures.append(
                                "hil_cleanup: another session is active")
                        else:
                            ended = hil_state
                    except Exception as error:
                        failures.append(f"hil_cleanup: {type(error).__name__}: {error}")
                if not cleanup.get("complete"):
                    failures.append("cleanup: terminal Home/none/lease0 unproven")
    except Exception as error:
        message = f"workflow: {type(error).__name__}: {error}"
        if message not in failures:
            failures.append(message)

    record.update({
        "status": "pass" if not failures else "failed",
        "passed": not failures,
        "gate_eligible": flashed and not failures,
        "failures": failures,
        "flashed": flashed,
        "boot": {"ready": boot, "recovery": recovery,
                 "timing": boot_timing},
        "hil_begin": begun,
        "first_visit": first,
        "revisit": revisit,
        "hil_end": ended,
        "cleanup": cleanup,
        "trace": trace,
    })
    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "status": record["status"],
        "passed": record["passed"], "failures": failures,
        "output": str(args.output),
    }, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
