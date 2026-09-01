#!/usr/bin/env python3
"""Verify Airspace Guard profile UX on one exact, already-flashed board.

This is deliberately a delta HIL, not the full Airspace Guard release gate.
It proves the task-first selector, all exact policies, passive start/cancel,
bounded selector repaint, and final cleanup without depending on ambient RF
frames being syntactically perfect.
"""

from __future__ import annotations

import argparse
import secrets
import shutil
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    STATE_SCHEMA,
    action,
    begin_hil_session,
    cancel_to_menu,
    end_hil_session,
    guard_state,
    open_guard_profile,
    robust_cleanup,
    running_failures,
    start_guard_from_profile,
    wait_guard_state,
)
from run_1x_prerelease_hil import sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.airspace_guard_profiles_hil.run.v1"
WIDTH = 240
HEIGHT = 320
PROFILE_MUTABLE_TOP = 28
PROFILE_MUTABLE_BOTTOM = 280
PROFILES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("everyday", {
        "profile_selection": 0,
        "disconnect_threshold": 4,
        "churn_threshold": 4,
        "noise_floor_dbm": -75,
        "noise_threshold": 4,
        "ble_tracker_threshold": 3,
    }),
    ("quiet_place", {
        "profile_selection": 1,
        "disconnect_threshold": 3,
        "churn_threshold": 3,
        "noise_floor_dbm": -80,
        "noise_threshold": 3,
        "ble_tracker_threshold": 3,
    }),
    ("busy_place", {
        "profile_selection": 2,
        "disconnect_threshold": 6,
        "churn_threshold": 6,
        "noise_floor_dbm": -70,
        "noise_threshold": 6,
        "ble_tracker_threshold": 5,
    }),
)


def profile_failures(state: dict[str, Any], name: str,
                     policy: dict[str, Any], label: str) -> list[str]:
    return expect(state, {
        "schema": STATE_SCHEMA,
        "kind": "state",
        "profile": name,
        "profile_version": 1,
        **policy,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
    }, label)


def pixel_region_delta(frames: Path, before: str, after: str) -> dict[str, Any]:
    before_bytes = (frames / f"{before}.rgb565").read_bytes()
    after_bytes = (frames / f"{after}.rgb565").read_bytes()
    expected_size = WIDTH * HEIGHT * 2
    if len(before_bytes) != expected_size or len(after_bytes) != expected_size:
        raise RuntimeError("profile repaint proof requires complete TFT frames")
    mutable = 0
    static = 0
    xs: list[int] = []
    ys: list[int] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            offset = (y * WIDTH + x) * 2
            if before_bytes[offset:offset + 2] == after_bytes[offset:offset + 2]:
                continue
            xs.append(x)
            ys.append(y)
            if PROFILE_MUTABLE_TOP <= y < PROFILE_MUTABLE_BOTTOM:
                mutable += 1
            else:
                static += 1
    return {
        "changed_pixels": mutable + static,
        "mutable_changed_pixels": mutable,
        "static_changed_pixels": static,
        "bounds": ({
            "left": min(xs), "top": min(ys),
            "right": max(xs), "bottom": max(ys),
        } if xs else None),
        "mutable_top": PROFILE_MUTABLE_TOP,
        "mutable_bottom": PROFILE_MUTABLE_BOTTOM,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-exact-flash", action="store_true")
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not args.reuse_exact_flash:
        parser.error("profile delta HIL requires --reuse-exact-flash")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

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
    selected: list[dict[str, Any]] = []
    started: list[dict[str, Any]] = []
    stopped: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    capacity_drop_clear: dict[str, Any] = {}
    repaint: dict[str, Any] = {}
    candidate_verified = False

    try:
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
                query(device, b"ui.language ru", "leshy.ui.v1", "state")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)
                capacity_drop_clear = query(
                    device, b"airspace-guard.test-capacity-drop clear",
                    "leshy.airspace_guard.capacity_drop_test.v1", "state")
                failures.extend(expect(capacity_drop_clear, {
                    "status": "cleared", "armed": False,
                    "one_shot": False, "hil_active": True,
                    "worker_idle": True, "ui_home": True,
                    "runtime_owner": "none", "lease_mask": 0,
                    "hardware_touched": False, "radio_started": False,
                    "storage_mounted": False, "storage_written": False,
                }, "capacity_drop_clear"))

                for name, policy in PROFILES:
                    open_guard_profile(device, trace)
                    initial_name = f"guard-profile-{name}-initial"
                    screens[f"{name}_initial"] = capture(
                        device, frames, initial_name)
                    for _ in range(policy["profile_selection"]):
                        trace.append(action(device, "down"))
                    profile = query(
                        device, b"ui.state", "leshy.ui.v1", "state")
                    selected.append(profile)
                    failures.extend(expect(profile, {
                        "page": "survey",
                        "wifi_product_view": "airspace_guard_profile",
                        "wifi_product_selection": policy["profile_selection"],
                        "runtime_owner": "wifi", "lease_mask": 15,
                    }, f"selected.{name}"))
                    selected_name = f"guard-profile-{name}-selected"
                    screens[f"{name}_selected"] = capture(
                        device, frames, selected_name)
                    if name == "quiet_place":
                        repaint = pixel_region_delta(
                            frames, initial_name, selected_name)
                        if repaint["changed_pixels"] <= 0:
                            failures.append("profile selector did not repaint")
                        if repaint["static_changed_pixels"] != 0:
                            failures.append(
                                "profile selector repaint escaped content region")

                    start = start_guard_from_profile(device, trace)
                    start = wait_guard_state(
                        device,
                        lambda value: value.get("capture_state") in
                        ("wifi_running", "failed"),
                        5.0, f"{name} did not start")
                    started.append(start)
                    failures.extend(profile_failures(
                        start, name, policy, f"started.{name}"))
                    failures.extend(running_failures(start, "wifi_running"))
                    stop = cancel_to_menu(device, trace, f"stopped.{name}")
                    stopped.append(stop)
                    home = action(device, "left")
                    trace.append(home)
                    failures.extend(expect(home, {
                        "page": "home", "runtime_owner": "none",
                        "lease_mask": 0,
                    }, f"home.{name}"))
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                try:
                    cleanup_after = robust_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("final Home/zero-lease cleanup failed")
                except Exception as error:
                    failures.append(
                        f"cleanup_after: {type(error).__name__}: {error}")
                if hil_begin:
                    try:
                        hil_end = end_hil_session(device, run_id, app_identity)
                    except Exception as error:
                        failures.append(
                            f"hil_end: {type(error).__name__}: {error}")
    except Exception as error:
        failures.append(f"serial: {type(error).__name__}: {error}")

    passed = not failures and candidate_verified
    result = {
        "schema": RUN_SCHEMA,
        "status": "pass" if passed else "failed",
        "gate_eligible": passed,
        "failures": failures,
        "run_id": run_id,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "runner_sha256": sha256_file(Path(__file__)),
            "cid": args.expected_cid,
            "reuse_exact_flash": True,
            "verified": candidate_verified,
        },
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery": recovery,
        "profiles": {
            "selected": selected,
            "started": started,
            "stopped": stopped,
        },
        "profile_repaint": repaint,
        "screens": screens,
        "trace": trace,
        "hil_session": {"begin": hil_begin, "end": hil_end},
        "capacity_drop_clear": capacity_drop_clear,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "delta_only": True,
            "full_airspace_guard_release_gate": False,
            "ambient_rf_conclusion_required": False,
            "profiles_checked": len(selected),
            "profile_starts_checked": len(started),
            "manual_button_presses": 0,
            "screenshots_automatic": bool(screens),
            "passive_receive_only": passed,
            "host_wifi_control_calls": 0,
            "application_wifi_connect_calls": 0 if passed else None,
            "application_raw_tx_calls": 0 if passed else None,
            "static_pixels_unchanged_during_profile_selection": (
                repaint.get("static_changed_pixels") == 0),
            "storage_write_authorized": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print({
        "schema": RUN_SCHEMA,
        "status": result["status"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    })
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
