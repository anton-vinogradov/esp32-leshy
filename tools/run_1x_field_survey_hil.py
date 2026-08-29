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
               timeout: float, description: str,
               trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state")
        if last.get("safety_latched") is True:
            safety = read_only_query(
                device, b"safety.state", "leshy.safety.v1", "state")
            if trace is not None:
                trace.append({
                    "checkpoint": "safety_latched",
                    "ui": last,
                    "safety": safety,
                })
            raise RuntimeError(
                f"{description}: safety latch: "
                f"worker={safety.get('worker_last_expired')!r} "
                f"stage={safety.get('product_survey_preparation_stage')!r} "
                f"age_ms={safety.get('worker_age_ms')!r}")
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


def auto_paused_failures(state: dict[str, Any], expected_cid: str,
                         label: str) -> list[str]:
    observations = state.get("survey_observations")
    scan_cycles = state.get("survey_product_scan_cycles")
    failures: list[str] = []
    if not isinstance(observations, int) or observations < 1:
        failures.append(f"{label}.survey_observations: expected >= 1")
        return failures
    if not isinstance(scan_cycles, int) or scan_cycles != 1:
        failures.append(f"{label}.survey_product_scan_cycles: expected 1")
        return failures
    failures.extend(paused_failures(
        state, observations, scan_cycles, "wifi"))
    failures.extend(expect(state, {
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_product_identity_status": "valid",
        "survey_product_selected_source_mask": 3,
        "survey_product_active_source_mask": 3,
        "survey_product_wifi_scan_cycles": 1,
        "survey_product_ble_scan_cycles": 1,
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_ble_scan_rejected": 0,
        "survey_ble_scan_dropped": 0,
        "survey_dropped": 0,
    }, label))
    wifi_accepted = state.get("survey_scan_accepted")
    ble_accepted = state.get("survey_ble_scan_accepted")
    forwarded = state.get("survey_forwarded")
    if (not isinstance(wifi_accepted, int) or
            not isinstance(ble_accepted, int) or
            wifi_accepted + ble_accepted != observations or
            forwarded != observations):
        failures.append(
            f"{label}.observation_accounting: "
            "wifi+ble accepted/forwarded/observations differ")
    return failures


def post_commit_recovery_failures(record: dict[str, Any], expected_cid: str,
                                  expected_generation: int,
                                  label: str) -> list[str]:
    failures = expect(record, {
        "status": "admitted",
        "catalog_admitted": True,
        "integrity": "valid",
        "expected_fingerprint": expected_cid,
        "observed_fingerprint": expected_cid,
        "fingerprint_matched": True,
        "generation": expected_generation,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
        "owned_after": 0,
    }, label)
    observations = record.get("observations")
    if not isinstance(observations, int) or observations < 1:
        failures.append(f"{label}.observations: expected >= 1")
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
    paused = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False and
            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
            state.get("survey_observations", 0) >= 1
        ), 35.0, f"{name}: one receive pass did not auto-pause",
        trace)
    trace.append(paused)
    failures = auto_paused_failures(
        paused, expected_cid, f"{name}.auto_paused")
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
            20.0, f"{name}: did not commit", trace)
        trace.append(committed)
    failures = committed_failures(
        committed, before_generation, "wifi", automatic_pause=True)
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
        "auto_paused": paused,
        "incomplete_negative": incomplete,
        "paused": paused,
        "committed": committed,
        "result": result,
        "result_capture": result_capture,
        "home": home,
    }


def run_preflight(device: Any, frames: Path,
                  trace: list[dict[str, Any]],
                  expected_cid: str) -> dict[str, Any]:
    """Prove one live Wi-Fi+BLE cycle without committing a field visit."""
    setup = open_product_survey_visit(device, trace)
    failures = setup_failures(setup, "wifi")
    failures.extend(expect(setup, {
        "survey_source_selected_mask": 3,
        "survey_source_selected_count": 2,
        "survey_source_can_start": True,
    }, "preflight.all_receivers"))
    if failures:
        raise RuntimeError("; ".join(failures))
    setup_capture = capture(device, frames, "preflight-setup")

    start = focus_survey_start(device)
    trace.append(start)
    started = action(device, "select")
    trace.append(started)
    require(started, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_status": "preparing",
    }, "preflight.start_ack")
    paused = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False and
            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
            state.get("survey_observations", 0) >= 1
        ), 35.0, "preflight: one receive pass did not auto-pause",
        trace)
    trace.append(paused)
    failures = auto_paused_failures(
        paused, expected_cid, "preflight.auto_paused")
    if failures:
        raise RuntimeError("; ".join(failures))
    paused_capture = capture(device, frames, "preflight-auto-paused")
    return {
        "setup": setup,
        "setup_capture": setup_capture,
        "start": start,
        "started": started,
        "auto_paused": paused,
        "auto_paused_capture": paused_capture,
        "writes_committed": 0,
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
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="reuse the already-flashed exact candidate after boot identity proof",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only", action="store_true",
        help=("run one live Wi-Fi+BLE cycle, cancel to Home, and never commit "
              "a field visit"),
    )
    mode.add_argument(
        "--recovery-only", action="store_true",
        help=("cold-reset and prove the already-committed exact generation "
              "read-only without scanning or writing"),
    )
    parser.add_argument(
        "--expected-generation", type=int,
        help="exact retained generation required by --recovery-only",
    )
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
    if args.recovery_only and args.expected_generation is None:
        parser.error("--recovery-only requires --expected-generation")
    if not args.recovery_only and args.expected_generation is not None:
        parser.error("--expected-generation is valid only with --recovery-only")

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
    preflight: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    boot: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    boot_timing: dict[str, Any] = {}
    post_commit_boot: dict[str, Any] = {}
    post_commit_recovery: dict[str, Any] = {}
    post_commit_boot_timing: dict[str, Any] = {}
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
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flashed = True
            time.sleep(0.75)
        boot, recovery, boot_timing = reset_capture(
            args.port, args.output, "boot", 20.0, maximum_attempts=1)

        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 20.0)
            try:
                recovery = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery, args.expected_version, app_sha,
                    args.expected_cid))
                if failures:
                    raise RuntimeError("; ".join(failures))
                if args.recovery_only:
                    failures.extend(post_commit_recovery_failures(
                        recovery, args.expected_cid,
                        int(args.expected_generation), "post_commit_recovery"))
                    if failures:
                        raise RuntimeError("; ".join(failures))
                    cleanup = best_effort_cleanup(device)
                    if not cleanup.get("complete"):
                        raise RuntimeError(
                            "recovery cleanup: terminal Home/none/lease0 unproven")
                else:
                    begun = begin_hil(device, run_id, app_sha,
                                      args.expected_version)
                    generation = int(recovery["generation"])
                if args.preflight_only:
                    preflight = run_preflight(
                        device, frames, trace, args.expected_cid)
                    cleanup = best_effort_cleanup(device)
                    if not cleanup.get("complete"):
                        raise RuntimeError(
                            "preflight cleanup: terminal Home/none/lease0 unproven")
                elif not args.recovery_only:
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
                if not args.recovery_only:
                    ended = end_hil(device, run_id, app_sha)
            finally:
                if not cleanup.get("complete"):
                    cleanup = best_effort_cleanup(device)
                if not ended and not args.recovery_only:
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
        if not args.preflight_only and not args.recovery_only and not failures:
            expected_generation = int(revisit["committed"]["library_generation"])
            post_commit_boot, post_commit_recovery, post_commit_boot_timing = (
                reset_capture(
                    args.port, args.output, "post-commit-cold", 20.0,
                    maximum_attempts=1))
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                synchronize_console(device, 20.0)
                post_commit_recovery = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    post_commit_boot, post_commit_recovery,
                    args.expected_version, app_sha, args.expected_cid))
                failures.extend(post_commit_recovery_failures(
                    post_commit_recovery, args.expected_cid,
                    expected_generation, "post_commit_recovery"))
                cleanup = best_effort_cleanup(device)
                if not cleanup.get("complete"):
                    failures.append(
                        "post_commit_cleanup: terminal Home/none/lease0 unproven")
    except Exception as error:
        message = f"workflow: {type(error).__name__}: {error}"
        if message not in failures:
            failures.append(message)

    record.update({
        "status": "pass" if not failures else "failed",
        "passed": not failures,
        "mode": ("preflight" if args.preflight_only else
                 "recovery" if args.recovery_only else "full"),
        "gate_eligible": (
            not args.preflight_only and
            not args.recovery_only and
            (flashed or args.reuse_exact_flash) and
            bool(post_commit_recovery) and
            not failures
        ),
        "failures": failures,
        "flashed": flashed,
        "reused_exact_flash": args.reuse_exact_flash,
        "boot": {"ready": boot, "recovery": recovery,
                 "timing": boot_timing},
        "post_commit_boot": {
            "ready": post_commit_boot,
            "recovery": post_commit_recovery,
            "timing": post_commit_boot_timing,
        },
        "hil_begin": begun,
        "preflight": preflight,
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
