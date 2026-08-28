#!/usr/bin/env python3
"""Verify one bounded Airspace Guard delta before a full lifecycle HIL."""

from __future__ import annotations

import argparse
import json
import secrets
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    action,
    artifact_manifest,
    candidate_verification_succeeded,
    cancel_to_menu,
    deterministic_ble_fixture_succeeded,
    finish_to_home,
    MACOS_BLE_FIXTURE_SCHEMA,
    open_guard,
    query,
    require_exact,
    result_failures,
    robust_cleanup,
    running_failures,
    valid_cid,
    wait_guard_state,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import boot_failures, expect


RUN_SCHEMA = "leshy.airspace_guard_start_regression_hil.run.v1"


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
    parser.add_argument(
        "--wait-for-ble-handoff", action="store_true",
        help="wait for terminal Wi-Fi evidence and prove BLE handoff",
    )
    parser.add_argument(
        "--wait-for-ble-result", action="store_true",
        help="wait for one complete Wi-Fi plus BLE result",
    )
    parser.add_argument(
        "--external-ble-label",
        help="BLE local name advertised by --external-ble-executable",
    )
    parser.add_argument(
        "--external-ble-executable", type=Path,
        help="bounded macOS CoreBluetooth fixture executable",
    )
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    if args.wait_for_ble_handoff and args.wait_for_ble_result:
        parser.error("choose at most one BLE terminal mode")
    if ((args.external_ble_label is None) !=
            (args.external_ble_executable is None)):
        parser.error(
            "--external-ble-label and --external-ble-executable are a pair")
    if args.external_ble_executable is not None and not (
            args.external_ble_executable.is_file()):
        parser.error("external BLE fixture executable is missing")
    if args.external_ble_label is not None and not (
            1 <= len(args.external_ble_label.encode("utf-8")) <= 29):
        parser.error("external BLE label must occupy 1..29 UTF-8 bytes")
    if args.wait_for_ble_result and args.external_ble_executable is None:
        parser.error("--wait-for-ble-result requires deterministic BLE fixture")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    wifi_running: dict[str, Any] = {}
    wifi_cancelled: dict[str, Any] = {}
    ble_handoff: dict[str, Any] = {}
    ble_result: dict[str, Any] = {}
    ble_cancelled: dict[str, Any] = {}
    final_home: dict[str, Any] = {}
    final_metrics: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    flash_completed = False
    candidate_verified = False
    fixture_process: subprocess.Popen[str] | None = None
    fixture_states: list[dict[str, Any]] = []
    external_ble_fixture: dict[str, Any] = {
        "kind": ("macos_corebluetooth"
                 if args.external_ble_executable is not None else "none"),
        "label": args.external_ble_label,
        "states": fixture_states,
        "host_wifi_control_calls": 0,
        "terminated": args.external_ble_executable is None,
    }
    if args.external_ble_executable is not None:
        external_ble_fixture["executable_sha256"] = sha256_file(
            args.external_ble_executable)

    try:
        if args.external_ble_executable is not None:
            fixture_process = subprocess.Popen(
                [str(args.external_ble_executable.resolve()),
                 str(args.external_ble_label)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if fixture_process.stdout is None:
                raise RuntimeError("external BLE fixture has no stdout")
            readable, _, _ = select.select(
                [fixture_process.stdout], [], [], 10.0)
            if not readable:
                raise RuntimeError("external BLE fixture did not become ready")
            fixture_state = json.loads(fixture_process.stdout.readline())
            fixture_states.append(fixture_state)
            if (fixture_state.get("schema") != MACOS_BLE_FIXTURE_SCHEMA or
                    fixture_state.get("state") != "advertising" or
                    fixture_state.get("label") != args.external_ble_label):
                raise RuntimeError(
                    f"external BLE fixture start failed: {fixture_state}")
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flash_completed = True
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                candidate_verified = candidate_verification_succeeded(
                    fresh_flash_requested=args.flash,
                    reuse_exact_requested=args.reuse_exact_flash,
                    flash_completed=flash_completed,
                    exact_boot_verified=True)
                cleanup_before = robust_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                wifi_running = open_guard(device, trace)
                failures.extend(running_failures(
                    wifi_running, "wifi_running"))
                if failures:
                    raise RuntimeError("Wi-Fi monitor admission failed")
                if args.wait_for_ble_result:
                    ble_result = wait_guard_state(
                        device,
                        lambda value: value.get("capture_state") in
                        ("result", "failed"),
                        35.0, "complete Guard lifecycle did not finish")
                    failures.extend(result_failures(
                        ble_result, "ble_result"))
                    if failures:
                        raise RuntimeError("complete BLE result contract failed")
                    finish_to_home(device, trace, "ble_result")
                    final_home = query(
                        device, b"ui.state", "leshy.ui.v1", "state")
                elif args.wait_for_ble_handoff:
                    ble_handoff = wait_guard_state(
                        device,
                        lambda value: value.get("capture_state") in
                        ("ble_running", "failed"),
                        18.0, "Wi-Fi terminal handoff did not finish")
                    if ble_handoff.get("capture_state") != "ble_running":
                        raise RuntimeError(
                            f"Wi-Fi evidence did not admit BLE: {ble_handoff!r}")
                    failures.extend(running_failures(
                        ble_handoff, "ble_running"))
                    if failures:
                        raise RuntimeError("BLE handoff contract failed")
                    ble_cancelled = cancel_to_menu(
                        device, trace, "ble_cancelled")
                else:
                    wifi_cancelled = cancel_to_menu(
                        device, trace, "wifi_cancelled")
                if not args.wait_for_ble_result:
                    final_home = action(device, "left")
                    trace.append(final_home)
                require_exact(final_home, {
                    "page": "home", "runtime_owner": "none",
                    "lease_mask": 0,
                }, "final_home")

                final_metrics = query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                input_state = query(
                    device, b"input.state",
                    "leshy.input.frontend.v1", "state")
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
                for key in ("generation", "observations"):
                    if recovery_after.get(key) != recovery_before.get(key):
                        failures.append(f"persistent {key} changed")
                if recovery_after.get("physical_write_calls") != 0:
                    failures.append("physical SD write observed")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = robust_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
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
            external_ble_fixture["terminated"] = True
            external_ble_fixture["returncode"] = fixture_process.returncode
            if fixture_process.stderr is not None:
                fixture_stderr = fixture_process.stderr.read().strip()
                if fixture_stderr:
                    external_ble_fixture["stderr"] = fixture_stderr

    passed = candidate_verified and not failures
    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": passed,
        "gate_eligible": False,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": candidate_verified,
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "wifi_running": wifi_running,
        "wifi_cancelled": wifi_cancelled,
        "ble_handoff": ble_handoff,
        "ble_result": ble_result,
        "ble_cancelled": ble_cancelled,
        "final_home": final_home,
        "final_metrics": final_metrics,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "external_ble_fixture": external_ble_fixture,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "start_regression_only": True,
            "full_lifecycle_gate": False,
            "single_flash": candidate_verified,
            "manual_button_presses": 0,
            "passive_receive_only": passed,
            "application_wifi_connect_calls": 0 if passed else None,
            "application_raw_tx_calls": 0 if passed else None,
            "wifi_cancel_cleanup_proved": bool(wifi_cancelled),
            "terminal_wifi_to_ble_handoff": bool(ble_handoff),
            "complete_wifi_plus_ble_result": bool(ble_result),
            "deterministic_ble_fixture": (
                deterministic_ble_fixture_succeeded(external_ble_fixture)
            ),
            "host_wifi_control_calls": 0,
            "ble_cancel_cleanup_proved": bool(ble_cancelled),
            "storage_write_authorized": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if passed else "failed",
        "failures": failures,
        "output": str(args.output),
        "wifi_driver_error": wifi_running.get("wifi_driver_error"),
        "final_lease_mask": final_home.get("lease_mask"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
