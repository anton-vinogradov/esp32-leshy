#!/usr/bin/env python3
"""Flash once and physically prove four fail-closed BLE GATT paths."""

from __future__ import annotations

import argparse
import json
import secrets
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    MACOS_BLE_FIXTURE_SCHEMA,
    action,
    begin_hil_session,
    deterministic_ble_fixture_succeeded,
    end_hil_session,
    robust_cleanup,
)
from run_1x_ble_gatt_hil import (
    DETAIL_SCHEMA,
    GATT_SCHEMA,
    SELECTOR_SCHEMA,
    UI_SCHEMA,
    gatt_failures,
    require_exact,
    select_exact_fixture,
)
from run_1x_ble_inspector_hil import preflight_exact_board
from run_1x_ble_nearby_hil import home_ble, wait_live, wait_stable_ble_entry
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.ble_gatt_negative_hil.run.v1"
FAULT_SCHEMA = "leshy.ble.inspector.gatt_hil_fault.v1"


def wait_record(device: PassiveSerial, command: bytes, schema: str,
                predicate: Callable[[dict[str, Any]], bool], timeout: float,
                failure: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = query(device, command, schema, "state")
        if predicate(latest):
            return latest
        time.sleep(0.05)
    raise TimeoutError(f"{failure}: {latest!r}")


def fault_state(device: PassiveSerial, request: str) -> dict[str, Any]:
    return query(
        device,
        f"ble.inspector.gatt.hil-fault {request}".encode("ascii"),
        FAULT_SCHEMA,
        "state",
    )


def enter_permission(device: PassiveSerial, fixture_label: str,
                     trace: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    home_ble(device)
    trace.append(action(device, "right"))
    # The positive dev.272 gate already proves the full entry dwell. Negative
    # delta scenarios need only a bounded bounce check before exact selection.
    trace.append(wait_stable_ble_entry(device, duration_seconds=1.0)[
        "final_state"])
    trace.append(wait_live(device))
    selector = select_exact_fixture(device, fixture_label)
    trace.append(selector)
    trace.append(action(device, "right"))
    detail = query(device, b"ble.device.detail", DETAIL_SCHEMA, "state")
    require_exact(detail, {
        "active": True,
        "passive": True,
        "active_probe_allowed": False,
        "label_known": True,
        "connectable": True,
    }, "selected_connectable_detail")
    identity_hash = int(detail.get("identity_hash", 0))
    if identity_hash == 0:
        raise RuntimeError("selected_connectable_detail.identity_hash: zero")
    modes = action(device, "right")
    trace.append(modes)
    require_exact(modes, {"ble_product_view": "inspector_menu"},
                  "inspector_mode_menu")
    trace.append(action(device, "down"))
    review_ui = action(device, "right")
    trace.append(review_ui)
    require_exact(review_ui, {
        "ble_product_view": "inspector_gatt",
        "runtime_owner": "ble",
        "lease_mask": 15,
    }, "gatt_permission_ui")
    permission = query(
        device, b"ble.inspector.gatt.state", GATT_SCHEMA, "state")
    failures = gatt_failures(
        permission, "permission_review", identity_hash, "permission_review")
    if failures:
        raise RuntimeError("; ".join(failures))
    return identity_hash, permission


def arm_fault(device: PassiveSerial, request: str, canonical: str,
              consumed_before: int) -> dict[str, Any]:
    armed = fault_state(device, request)
    require_exact(armed, {
        "status": "armed",
        "requested": request,
        "armed": canonical,
        "consumed_count": consumed_before,
        "hil_active": True,
        "one_shot": True,
        "enumeration_only": True,
        "pairing_allowed": False,
        "read_allowed": False,
        "write_allowed": False,
        "subscribe_allowed": False,
        "storage_mounted": False,
        "storage_written": False,
        "physical_write_calls": 0,
    }, f"arm_{request}")
    return armed


def confirm_permission(device: PassiveSerial, identity_hash: int,
                       trace: list[dict[str, Any]]) -> None:
    trace.append(action(device, "right"))
    confirmation = query(
        device, b"ble.inspector.gatt.state", GATT_SCHEMA, "state")
    failures = gatt_failures(
        confirmation, "awaiting_confirmation", identity_hash,
        "awaiting_confirmation")
    if failures:
        raise RuntimeError("; ".join(failures))
    trace.append(action(device, "right", timeout=20.0))


def terminal_failure(device: PassiveSerial, expected_failure: str,
                     expected_cleanup_cause: str) -> dict[str, Any]:
    terminal = wait_record(
        device, b"ble.inspector.gatt.state", GATT_SCHEMA,
        lambda value: value.get("state") == "failed" and
        value.get("cleanup_complete") is True,
        20.0, f"GATT {expected_failure} did not clean up")
    require_exact(terminal, {
        "view": "inspector_gatt",
        "state": "failed",
        "failure": expected_failure,
        "cleanup_cause": expected_cleanup_cause,
        "target_present": True,
        "host_ready": False,
        "connected": False,
        "transport_connecting": False,
        "transport_disconnected": True,
        "cleanup_requested": False,
        "cleanup_complete": True,
        "owns_radio": False,
        "esp_rf_owner": 0,
        "gatt_owner": 6,
        "enumeration_only": True,
        "pairing_allowed": False,
        "read_allowed": False,
        "write_allowed": False,
        "subscribe_allowed": False,
    }, f"terminal_{expected_failure}")
    return terminal


def return_home(device: PassiveSerial, trace: list[dict[str, Any]]) -> dict[str, Any]:
    trace.append(action(device, "left"))
    return wait_record(
        device, b"ui.state", UI_SCHEMA,
        lambda value: value.get("page") == "home" and
        value.get("runtime_owner") == "none" and
        value.get("lease_mask") == 0,
        15.0, "GATT failure Back did not return Home/zero lease")


def run_preconnect_fault(
        device: PassiveSerial, fixture_label: str, request: str,
        canonical: str, expected_failure: str, expected_cleanup_cause: str,
        consumed_before: int, frames: Path, trace: list[dict[str, Any]],
        screens: dict[str, Any]) -> dict[str, Any]:
    identity_hash, permission = enter_permission(
        device, fixture_label, trace)
    armed = arm_fault(device, request, canonical, consumed_before)
    confirm_permission(device, identity_hash, trace)
    terminal = terminal_failure(
        device, expected_failure, expected_cleanup_cause)
    consumed = fault_state(device, "state")
    require_exact(consumed, {
        "status": "state",
        "armed": "none",
        "last_consumed": canonical,
        "consumed_count": consumed_before + 1,
        "hil_active": True,
    }, f"consumed_{request}")
    screens[request] = capture(device, frames, f"ble-gatt-{request}")
    home = return_home(device, trace)
    return {
        "request": request,
        "canonical": canonical,
        "permission": permission,
        "armed": armed,
        "terminal": terminal,
        "consumed": consumed,
        "home": home,
    }


def run_failed_cleanup(
        device: PassiveSerial, fixture_label: str, consumed_before: int,
        frames: Path, trace: list[dict[str, Any]],
        screens: dict[str, Any]) -> dict[str, Any]:
    identity_hash, permission = enter_permission(
        device, fixture_label, trace)
    confirm_permission(device, identity_hash, trace)
    ready = wait_record(
        device, b"ble.inspector.gatt.state", GATT_SCHEMA,
        lambda value: value.get("state") in ("ready", "failed"),
        35.0, "GATT setup for failed cleanup did not terminate")
    require_exact(ready, {
        "state": "ready",
        "failure": "none",
        "host_ready": True,
        "connected": True,
        "transport_connecting": False,
        "transport_disconnected": False,
        "cleanup_requested": False,
        "cleanup_complete": False,
        "owns_radio": True,
        "esp_rf_owner": 6,
    }, "failed_cleanup_ready")
    armed = arm_fault(
        device, "failed-cleanup", "disconnect_failure", consumed_before)
    trace.append(action(device, "left"))
    terminal = terminal_failure(device, "disconnect_failed", "none")
    require_exact(terminal, {"return_after_cleanup": False},
                  "failed_cleanup_visible")
    consumed = fault_state(device, "state")
    require_exact(consumed, {
        "status": "state",
        "armed": "none",
        "last_consumed": "disconnect_failure",
        "consumed_count": consumed_before + 1,
        "hil_active": True,
    }, "consumed_failed_cleanup")
    screens["failed-cleanup"] = capture(
        device, frames, "ble-gatt-failed-cleanup")
    home = return_home(device, trace)
    return {
        "request": "failed-cleanup",
        "canonical": "disconnect_failure",
        "permission": permission,
        "ready": ready,
        "armed": armed,
        "terminal": terminal,
        "consumed": consumed,
        "home": home,
    }


def run_recovery_success(device: PassiveSerial, fixture_label: str,
                         consumed_count: int,
                         trace: list[dict[str, Any]]) -> dict[str, Any]:
    identity_hash, permission = enter_permission(
        device, fixture_label, trace)
    confirm_permission(device, identity_hash, trace)
    ready = wait_record(
        device, b"ble.inspector.gatt.state", GATT_SCHEMA,
        lambda value: value.get("state") in ("ready", "failed"),
        35.0, "post-negative GATT recovery did not terminate")
    require_exact(ready, {
        "state": "ready",
        "failure": "none",
        "host_ready": True,
        "connected": True,
        "cleanup_complete": False,
        "owns_radio": True,
        "esp_rf_owner": 6,
        "hil_fault_armed": "none",
        "hil_fault_consumed_count": consumed_count,
    }, "post_negative_ready")
    if int(ready.get("services", 0)) < 1 or \
            int(ready.get("characteristics", 0)) < 1:
        raise RuntimeError("post-negative recovery enumerated no GATT facts")
    trace.append(action(device, "left"))
    home = wait_record(
        device, b"ui.state", UI_SCHEMA,
        lambda value: value.get("page") == "home" and
        value.get("runtime_owner") == "none" and
        value.get("lease_mask") == 0,
        15.0, "post-negative success did not disconnect to Home")
    return {"permission": permission, "ready": ready, "home": home}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--external-ble-label", required=True)
    parser.add_argument("--external-ble-executable", required=True, type=Path)
    parser.add_argument(
        "--only", choices=("all", "timeout"), default="all",
        help="run the complete matrix or the focused timeout regression")
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if not args.external_ble_executable.is_file():
        parser.error("external BLE fixture executable is missing")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    if not 1 <= len(args.external_ble_label.encode("utf-8")) <= 29:
        parser.error("external BLE label must occupy 1..29 UTF-8 bytes")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    scenarios: list[dict[str, Any]] = []
    preflight: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery: dict[str, Any] = {}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    final_fault_clear: dict[str, Any] = {}
    recovery_success: dict[str, Any] = {}
    candidate_verified = False
    fixture_process: subprocess.Popen[str] | None = None
    fixture_states: list[dict[str, Any]] = []
    fixture = {
        "kind": "macos_corebluetooth",
        "label": args.external_ble_label,
        "states": fixture_states,
        "host_wifi_control_calls": 0,
        "terminated": False,
        "executable_sha256": sha256_file(args.external_ble_executable),
    }

    try:
        preflight = preflight_exact_board(args.port, args.expected_cid)
        fixture_process = subprocess.Popen(
            [str(args.external_ble_executable.resolve()),
             args.external_ble_label],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if fixture_process.stdout is None:
            raise RuntimeError("external BLE fixture has no stdout")
        readable, _, _ = select.select([fixture_process.stdout], [], [], 10.0)
        if not readable:
            raise RuntimeError("external BLE fixture did not become ready")
        fixture_state = json.loads(fixture_process.stdout.readline())
        fixture_states.append(fixture_state)
        if (fixture_state.get("schema") != MACOS_BLE_FIXTURE_SCHEMA or
                fixture_state.get("state") != "advertising" or
                fixture_state.get("label") != args.external_ble_label):
            raise RuntimeError(f"external BLE fixture start failed: {fixture_state}")

        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                candidate_verified = True
                cleanup_before = robust_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)
                initial_fault = fault_state(device, "state")
                require_exact(initial_fault, {
                    "status": "state", "armed": "none",
                    "last_consumed": "none", "hil_active": True,
                }, "initial_fault_state")
                consumed = int(initial_fault.get("consumed_count", -1))
                if consumed < 0:
                    raise RuntimeError("negative initial fault counter")

                definitions = (
                    ("wrong-peer", "unexpected_peer", "unexpected_peer",
                     "unexpected_peer"),
                    ("timeout", "timeout", "timeout", "timeout"),
                    ("resource-conflict", "resource_conflict",
                     "resource_busy", "none"),
                )
                if args.only == "timeout":
                    definitions = (definitions[1],)
                for request, canonical, failure, cleanup_cause in definitions:
                    scenarios.append(run_preconnect_fault(
                        device, args.external_ble_label, request, canonical,
                        failure, cleanup_cause, consumed, frames, trace,
                        screens))
                    consumed += 1
                if args.only == "all":
                    scenarios.append(run_failed_cleanup(
                        device, args.external_ble_label, consumed, frames,
                        trace, screens))
                    consumed += 1
                recovery_success = run_recovery_success(
                    device, args.external_ble_label, consumed, trace)
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                try:
                    final_fault_clear = fault_state(device, "clear")
                    require_exact(final_fault_clear, {
                        "status": "cleared", "armed": "none",
                        "hil_active": True,
                    }, "final_fault_clear")
                except Exception as error:
                    failures.append(
                        f"fault_clear: {type(error).__name__}: {error}")
                try:
                    cleanup_after = robust_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("cleanup_after: Home/zero lease unproven")
                except Exception as error:
                    failures.append(
                        f"cleanup_after: {type(error).__name__}: {error}")
                if hil_begin:
                    try:
                        hil_end = end_hil_session(device, run_id, app_identity)
                        require_exact(hil_end, {"active": False},
                                      "hil_session_end")
                    except Exception as error:
                        failures.append(
                            f"hil_session_end: {type(error).__name__}: {error}")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")
    finally:
        if fixture_process is not None:
            fixture_process.terminate()
            try:
                fixture_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                fixture_process.kill()
                fixture_process.wait(timeout=5.0)
            fixture["terminated"] = True
            fixture["returncode"] = fixture_process.returncode
            if fixture_process.stderr is not None:
                stderr = fixture_process.stderr.read().strip()
                if stderr:
                    fixture["stderr"] = stderr

    expected_scenarios = 4 if args.only == "all" else 1
    passed = (
        candidate_verified and not failures and
        len(scenarios) == expected_scenarios and
        bool(recovery_success) and bool(hil_end) and
        deterministic_ble_fixture_succeeded(fixture)
    )
    if not deterministic_ble_fixture_succeeded(fixture):
        failures.append("deterministic external BLE fixture was not proved")
        passed = False
    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": passed,
        "gate_eligible": passed,
        "failures": failures,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash and candidate_verified,
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "preflight": preflight,
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery": recovery,
        "scenarios": scenarios,
        "recovery_success": recovery_success,
        "hil_session": {"begin": hil_begin, "end": hil_end},
        "external_ble_fixture": fixture,
        "screens": screens,
        "trace": trace,
        "final_fault_clear": final_fault_clear,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "run_mode": args.only,
            "single_flash_or_exact_reuse": candidate_verified,
            "scenario_order": (
                ["wrong-peer", "timeout", "resource-conflict",
                 "failed-cleanup", "recovery-success"]
                if args.only == "all" else
                ["timeout", "recovery-success"]
            ),
            "manual_button_presses": 0,
            "screenshots_automatic": len(screens) == expected_scenarios,
            "enumeration_only": True,
            "characteristic_reads": 0,
            "characteristic_writes": 0,
            "subscriptions": 0,
            "pairings": 0,
            "host_wifi_control_calls": 0,
            "clone_touched": False,
            "cardputer_touched": False,
            "storage_write_authorized": False,
            "terminal_zero_lease": cleanup_after.get("complete") is True,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if passed else "failed",
        "failures": failures,
        "output": str(args.output),
        "scenarios": len(scenarios),
        "recovery_services": recovery_success.get("ready", {}).get("services"),
        "recovery_characteristics": recovery_success.get(
            "ready", {}).get("characteristics"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
