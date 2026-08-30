#!/usr/bin/env python3
"""Focused physical delta gate for exact, enumeration-only BLE GATT."""

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


RUN_SCHEMA = "leshy.ble_gatt_hil.run.v1"
SELECTOR_SCHEMA = "leshy.ble.device_hil_selector.v1"
DETAIL_SCHEMA = "leshy.ble.device_detail.v1"
GATT_SCHEMA = "leshy.ble.inspector.gatt.v1"
UI_SCHEMA = "leshy.ui.v1"


def fnv1a64(value: str) -> int:
    result = 14695981039346656037
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return result


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def wait_record(device: PassiveSerial, command: bytes, schema: str,
                predicate: Callable[[dict[str, Any]], bool], timeout: float,
                failure: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = query(device, command, schema, "state")
        if predicate(latest):
            return latest
        time.sleep(0.1)
    raise TimeoutError(f"{failure}: {latest!r}")


def select_exact_fixture(device: PassiveSerial, label: str,
                         timeout: float = 45.0) -> dict[str, Any]:
    label_hash = fnv1a64(label)
    command = (
        f"ble.device.hil-select-label-fnv1a64 {label_hash:016x}"
    ).encode("ascii")
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = query(device, command, SELECTOR_SCHEMA, "state")
        if (latest.get("selected") is True and
                latest.get("status") in ("selected", "already_selected")):
            require_exact(latest, {
                "match_count": 1,
                "strongest_match": True,
                "connectable": True,
                "hil_active": True,
                "navigation_locked": True,
                "rf_hardware_touched": False,
                "radio_started": False,
                "storage_mounted": False,
                "storage_written": False,
                "identifier_disclosed": False,
                "response_complete": True,
            }, "exact_fixture_selector")
            latest["requested_label_fnv1a64"] = f"{label_hash:016x}"
            return latest
        if latest.get("status") not in ("not_found", "runtime_not_ready"):
            raise RuntimeError(f"exact fixture selection rejected: {latest!r}")
        time.sleep(0.35)
    raise TimeoutError(f"exact connectable fixture was not observed: {latest!r}")


def gatt_failures(state: dict[str, Any], expected_state: str,
                  identity_hash: int, label: str) -> list[str]:
    failures = expect(state, {
        "view": "inspector_gatt",
        "state": expected_state,
        "failure": "none",
        "target_present": True,
        "selected_identity_hash": identity_hash,
        "confirmation_required": True,
        "enumeration_only": True,
        "pairing_allowed": False,
        "read_allowed": False,
        "write_allowed": False,
        "subscribe_allowed": False,
        "read_only_query": True,
        "gatt_owner": 6,
    }, label)
    if expected_state in ("permission_review", "awaiting_confirmation"):
        failures.extend(expect(state, {
            "permission_visible": True,
            "waiting_for_passive_stop": False,
            "services": 0,
            "characteristics": 0,
            "host_ready": False,
            "connected": False,
            # The selected permission flow is intentionally non-terminal even
            # though it has not acquired a radio or created a host yet.
            "cleanup_complete": False,
            "owns_radio": False,
            "esp_rf_owner": 1,
        }, label))
    return failures


def compare_complete_frames(frames: Path, before_name: str,
                            after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    if len(before) != 240 * 320 * 2 or len(after) != len(before):
        raise RuntimeError("TFT comparison requires complete 240x320 frames")
    changed = sum(
        before[index:index + 2] != after[index:index + 2]
        for index in range(0, len(before), 2)
    )
    return {"changed_pixels": changed, "total_pixels": 240 * 320}


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
    preflight: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery: dict[str, Any] = {}
    selector: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    permission: dict[str, Any] = {}
    confirmation: dict[str, Any] = {}
    ready: dict[str, Any] = {}
    terminal_gatt: dict[str, Any] = {}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    pixel_proof: dict[str, int] = {}
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
                query(device, b"ui.language ru", UI_SCHEMA, "state")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)

                home_ble(device)
                trace.append(action(device, "right"))
                trace.append(wait_stable_ble_entry(device)["final_state"])
                trace.append(wait_live(device))
                selector = select_exact_fixture(
                    device, args.external_ble_label)
                trace.append(selector)

                trace.append(action(device, "right"))
                detail = query(device, b"ble.device.detail", DETAIL_SCHEMA, "state")
                failures.extend(expect(detail, {
                    "active": True,
                    "passive": True,
                    "active_probe_allowed": False,
                    "label_known": True,
                    "connectable": True,
                }, "selected_connectable_detail"))
                identity_hash = int(detail.get("identity_hash", 0))
                if identity_hash == 0:
                    failures.append("selected_connectable_detail.identity_hash: zero")
                if failures:
                    raise RuntimeError("exact fixture detail contract failed")

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
                failures.extend(gatt_failures(
                    permission, "permission_review", identity_hash,
                    "permission_review"))
                if failures:
                    raise RuntimeError("permission review contract failed")
                screens["permission"] = capture(
                    device, frames, "ble-gatt-permission")

                trace.append(action(device, "right"))
                confirmation = query(
                    device, b"ble.inspector.gatt.state", GATT_SCHEMA, "state")
                failures.extend(gatt_failures(
                    confirmation, "awaiting_confirmation", identity_hash,
                    "awaiting_confirmation"))
                if failures:
                    raise RuntimeError("second-confirmation contract failed")

                trace.append(action(device, "right", timeout=20.0))
                ready = wait_record(
                    device, b"ble.inspector.gatt.state", GATT_SCHEMA,
                    lambda value: value.get("state") in ("ready", "failed") or
                    value.get("view") == "none",
                    35.0, "GATT connect/discovery did not terminate")
                if ready.get("state") != "ready":
                    raise RuntimeError(f"GATT enumeration failed closed: {ready!r}")
                failures.extend(expect(ready, {
                    "failure": "none",
                    "target_present": True,
                    "selected_identity_hash": identity_hash,
                    "permission_visible": False,
                    "waiting_for_passive_stop": False,
                    "host_ready": True,
                    "connected": True,
                    "cleanup_complete": False,
                    "owns_radio": True,
                    "esp_rf_owner": 6,
                    "gatt_owner": 6,
                    "enumeration_only": True,
                    "pairing_allowed": False,
                    "read_allowed": False,
                    "write_allowed": False,
                    "subscribe_allowed": False,
                }, "gatt_ready"))
                if int(ready.get("services", 0)) < 1:
                    failures.append("gatt_ready.services: expected >= 1")
                if int(ready.get("characteristics", 0)) < 1:
                    failures.append("gatt_ready.characteristics: expected >= 1")
                for key in ("heap_free_before", "heap_largest_before",
                            "heap_free_after_init", "heap_largest_after_init",
                            "heap_minimum"):
                    if int(ready.get(key, 0)) <= 0:
                        failures.append(f"gatt_ready.{key}: expected > 0")
                if int(ready.get("content_clears", -1)) != 1:
                    failures.append("gatt_ready.content_clears: expected exactly 1")
                if failures:
                    raise RuntimeError("GATT ready contract failed")

                screens["ready_first"] = capture(
                    device, frames, "ble-gatt-ready-first")
                time.sleep(0.75)
                screens["ready_second"] = capture(
                    device, frames, "ble-gatt-ready-second")
                pixel_proof = compare_complete_frames(
                    frames, "ble-gatt-ready-first", "ble-gatt-ready-second")
                if pixel_proof["changed_pixels"] != 0:
                    raise RuntimeError(
                        f"stable GATT card repainted: {pixel_proof}")

                trace.append(action(device, "left"))
                wait_record(
                    device, b"ui.state", UI_SCHEMA,
                    lambda value: value.get("page") == "home" and
                    value.get("runtime_owner") == "none" and
                    value.get("lease_mask") == 0,
                    15.0, "GATT Back did not return Home/zero lease")
                terminal_gatt = query(
                    device, b"ble.inspector.gatt.state", GATT_SCHEMA, "state")
                require_exact(terminal_gatt, {
                    "view": "none",
                    "state": "idle",
                    "target_present": False,
                    "host_ready": False,
                    "connected": False,
                    "cleanup_complete": True,
                    "owns_radio": False,
                    "esp_rf_owner": 0,
                    "read_allowed": False,
                    "write_allowed": False,
                    "subscribe_allowed": False,
                }, "gatt_terminal_cleanup")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
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
                        require_exact(hil_end, {"active": False}, "hil_session_end")
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

    passed = (
        candidate_verified and not failures and bool(ready) and
        bool(terminal_gatt) and
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
        "selector": selector,
        "detail": detail,
        "permission": permission,
        "confirmation": confirmation,
        "ready": ready,
        "terminal_gatt": terminal_gatt,
        "hil_session": {"begin": hil_begin, "end": hil_end},
        "external_ble_fixture": fixture,
        "pixel_proof": pixel_proof,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash_or_exact_reuse": candidate_verified,
            "manual_button_presses": 0,
            "screenshots_automatic": bool(screens),
            "exact_fixture_selected_without_identifier_disclosure": bool(selector),
            "active_connection_explicitly_confirmed_twice": bool(confirmation),
            "enumeration_only": ready.get("enumeration_only") is True,
            "characteristic_reads": 0,
            "characteristic_writes": 0,
            "subscriptions": 0,
            "pairings": 0,
            "host_wifi_control_calls": 0,
            "clone_touched": False,
            "cardputer_touched": False,
            "stable_ready_card_changed_pixels": pixel_proof.get("changed_pixels"),
            "terminal_zero_lease": terminal_gatt.get("esp_rf_owner") == 0,
            "storage_write_authorized": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if passed else "failed",
        "failures": failures,
        "output": str(args.output),
        "services": ready.get("services"),
        "characteristics": ready.get("characteristics"),
        "pixel_proof": pixel_proof,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
