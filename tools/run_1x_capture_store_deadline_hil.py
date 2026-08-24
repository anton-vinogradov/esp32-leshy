#!/usr/bin/env python3
"""Prove Wi-Fi Capture Store deadline supervision on one enrolled board."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_boot_watchdog_hil import capture_until_ready, parse_ready
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
    reset_capture,
    resolve_expected_cid,
)
from run_1x_wifi_capture_product_hil import (
    CAPTURE_SCHEMA,
    open_product_capture,
    wait_capture,
)


RUN_SCHEMA = "leshy.capture_store_deadline_hil.run.v1"
INJECTION_SCHEMA = "leshy.safety.capture_store_deadline_test.v1"
SOFTWARE_RESET_REASON = 3


def wait_safety(
    device: PassiveSerial,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    message: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"safety.state", "leshy.safety.v1", "state")
        if predicate(last):
            return last
        time.sleep(0.15)
    raise RuntimeError(f"{message}: {last}")


def capture_to_confirmation(
    device: PassiveSerial, trace: list[dict[str, Any]],
) -> dict[str, Any]:
    trace.extend(open_product_capture(device))
    trace.append(action(device, "right"))
    wait_capture(
        device,
        lambda value: value.get("state") == "running" and
        int(value.get("frames_accepted", 0)) >= 1,
        5.0,
        "passive Wi-Fi capture received no frame",
    )
    trace.append(action(device, "right"))
    complete = wait_capture(
        device, lambda value: value.get("state") == "complete",
        5.0, "Wi-Fi capture did not stop",
    )
    accepted = int(complete.get("frames_accepted", 0))
    payload_bytes = int(complete.get("payload_bytes", 0))
    if not 1 <= accepted <= 16:
        raise RuntimeError(f"accepted frame bound invalid: {accepted}")
    if not accepted <= payload_bytes <= accepted * 256:
        raise RuntimeError(f"payload byte bound invalid: {payload_bytes}")
    trace.append(action(device, "right"))
    confirmed = query(device, b"capture.state", CAPTURE_SCHEMA, "state")
    failures = expect(confirmed, {
        "state": "complete", "persist_state": "confirm",
        "persist_status": "awaiting_confirmation",
        "storage_written": False,
    }, "capture_confirmation")
    if failures:
        raise RuntimeError("; ".join(failures))
    return confirmed


def close_capture_to_home(
    device: PassiveSerial, trace: list[dict[str, Any]],
) -> dict[str, Any]:
    trace.append(action(device, "left"))
    trace.append(action(device, "left"))
    home = query(device, b"ui.state", "leshy.ui.v1", "state")
    failures = expect(home, {
        "page": "home", "selected_id": "wifi",
        "runtime_owner": "none", "lease_mask": 0,
        "safety_latched": False,
    }, "capture_home")
    if failures:
        raise RuntimeError("; ".join(failures))
    return home


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    source_root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if args.source_commit != head:
        parser.error(
            f"--source-commit {args.source_commit} does not match HEAD {head}"
        )
    for diff_args in (["git", "diff", "--quiet"],
                      ["git", "diff", "--cached", "--quiet"]):
        if subprocess.run(diff_args, cwd=source_root, check=False).returncode != 0:
            parser.error("tracked source changes must be committed before exact HIL")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    runner_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected_cid = args.expected_cid or ""
    failures: list[str] = []
    records: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    restart_raw = b""
    clear_raw = b""

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)

        before_ready, before_recovery, before_timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds,
        )
        records["boot_before"] = {
            "ready": before_ready,
            "recovery": before_recovery,
            "timing": before_timing,
        }
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            before_recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            records["boot_before"]["recovery"] = before_recovery
            expected_cid = resolve_expected_cid(args.expected_cid, before_recovery)
            failures.extend(boot_failures(
                before_ready, before_recovery, args.expected_version,
                app_identity, expected_cid,
            ))
            records["safety_before"] = query(
                device, b"safety.state", "leshy.safety.v1", "state",
            )
            failures.extend(expect(records["safety_before"], {
                "state": "armed", "reason": "none", "latched": False,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": False, "worker_trip_count": 0,
            }, "safety_before"))
            if failures:
                raise RuntimeError("preflight contract failed")
            generation_before = int(before_recovery.get("generation", 0))

            # Calibrate the real write path first: the public privacy-confirmed
            # save must finish under the same deadline without a false trip.
            records["normal_confirm"] = capture_to_confirmation(device, trace)
            trace.append(action(device, "right"))
            records["normal_saved"] = wait_capture(
                device,
                lambda value: value.get("persist_state") in ("saved", "failed"),
                35.0,
                "normal Capture Store did not reach a terminal state",
            )
            failures.extend(expect(records["normal_saved"], {
                "persist_state": "saved", "persist_status": "saved",
                "storage_written": True,
            }, "normal_saved"))
            saved_generation = int(
                records["normal_saved"].get("persist_generation", 0))
            if saved_generation != generation_before + 1:
                failures.append(
                    f"normal save generation {saved_generation} != "
                    f"{generation_before + 1}"
                )
            records["safety_after_normal"] = query(
                device, b"safety.state", "leshy.safety.v1", "state",
            )
            failures.extend(expect(records["safety_after_normal"], {
                "state": "armed", "reason": "none", "latched": False,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": False, "worker_deadline_ms": 8000,
                "worker_arm_count": 1, "worker_trip_count": 0,
            }, "safety_after_normal"))
            normal_heartbeats = int(records["safety_after_normal"].get(
                "worker_heartbeat_count", 0))
            if normal_heartbeats < 8:
                failures.append("normal Capture Store heartbeat coverage is incomplete")
            records["home_after_normal"] = close_capture_to_home(device, trace)
            if failures:
                raise RuntimeError("normal Capture Store calibration failed")

            device.write(b"safety.capture-store-deadline-test confirm\n")
            device.flush()
            records["injection"] = read_json(
                device, INJECTION_SCHEMA, "armed", 5.0,
            )
            failures.extend(expect(records["injection"], {
                "worker": "wifi_capture_store", "deadline_ms": 8000,
                "injection_ms": 10000,
                "requires_public_capture_save": True,
                "before_storage_hardware": True,
                "outputs_inactive": True, "physical_write_calls": 0,
            }, "injection"))

            records["injected_confirm"] = capture_to_confirmation(device, trace)
            trace.append(action(device, "right"))
            records["saving"] = query(
                device, b"capture.state", CAPTURE_SCHEMA, "state",
            )
            failures.extend(expect(records["saving"], {
                "persist_state": "saving", "persist_status": "saving",
                "storage_written": False,
            }, "injected_saving"))
            if failures:
                raise RuntimeError("public injected save contract failed")

            records["safety_tripped"] = wait_safety(
                device,
                lambda state: state.get("latched") is True and
                state.get("reason") == "worker_deadline",
                15.0,
                "Capture Store deadline did not latch Safe Mode",
            )
            failures.extend(expect(records["safety_tripped"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "armed": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_last_expired": "wifi_capture_store",
                "worker_active": "wifi_capture_store",
                "worker_armed": True, "worker_expired": True,
                "worker_deadline_ms": 8000,
                "worker_arm_count": 2, "worker_trip_count": 1,
                "automatic_clear": False,
            }, "safety_tripped"))
            if int(records["safety_tripped"].get("worker_age_ms", 0)) < 8000:
                failures.append("Capture Store trip age is below its deadline")

            records["safety_cleanup"] = wait_safety(
                device,
                lambda state: state.get("latched") is True and
                state.get("worker_armed") is False and
                state.get("worker_active") == "none",
                6.0,
                "cancelled Capture Store did not reach terminal cleanup",
            )
            failures.extend(expect(records["safety_cleanup"], {
                "reason": "worker_deadline", "latched": True,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": True,
                "worker_last_expired": "wifi_capture_store",
                "worker_deadline_ms": 8000, "worker_trip_count": 1,
            }, "safety_cleanup"))
            records["ui_latched"] = query(
                device, b"ui.state", "leshy.ui.v1", "state",
            )
            records["outputs_latched"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state",
            )
            failures.extend(expect(records["ui_latched"], {
                "page": "safe_mode", "safety_latched": True,
                "runtime_owner": "none", "lease_mask": 0,
            }, "ui_latched"))
            failures.extend(expect(records["outputs_latched"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
            }, "outputs_latched"))
            records["frame_latched"] = capture(
                device, frames, "capture-store-deadline-latched",
            )

            device.write(b"safety.restart-test confirm\n")
            device.flush()
            records["restart_request"] = read_json(
                device, "leshy.safety.restart_test.v1", "restart", 5.0,
            )
            restart_raw, restart_ready_ms = capture_until_ready(
                device, args.boot_seconds,
            )
            records["restart_ready_marker_ms"] = restart_ready_ms

        (args.output / "latched-restart.ndjson").write_bytes(restart_raw)
        records["restart_ready"] = parse_ready(restart_raw)
        failures.extend(expect(records["restart_ready"], {
            "version": args.expected_version,
            "app_elf_sha256": app_identity,
            "reset_reason_code": SOFTWARE_RESET_REASON,
        }, "restart_ready"))

        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["safety_after_restart"] = query(
                device, b"safety.state", "leshy.safety.v1", "state",
            )
            records["recovery_after_restart"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            failures.extend(expect(records["safety_after_restart"], {
                "state": "latched", "reason": "worker_deadline",
                "latched": True, "clear_pending": False,
                "trip_count": 1, "emergency_quiesce_count": 1,
                "runtime_owner": "none", "lease_mask": 0,
                "worker_active": "none", "worker_armed": False,
                "worker_expired": False, "automatic_clear": False,
            }, "safety_after_restart"))
            failures.extend(expect(records["recovery_after_restart"], {
                "status": "safety_latched", "cleanup_complete": True,
                "physical_write_calls": 0, "owned_after": 0,
            }, "recovery_after_restart"))
            records["ui_clear_pending"] = action(device, "right")
            records["frame_clear_pending"] = capture(
                device, frames, "capture-store-deadline-clear-pending",
            )
            device.write(b"ui.key right\n")
            device.flush()
            clear_raw, clear_ready_ms = capture_until_ready(
                device, args.boot_seconds,
            )
            records["clear_ready_marker_ms"] = clear_ready_ms

        (args.output / "clear-restart.ndjson").write_bytes(clear_raw)
        records["clear_ready"] = parse_ready(clear_raw)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["recovery_final"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            records["safety_final"] = query(
                device, b"safety.state", "leshy.safety.v1", "state",
            )
            records["ui_final"] = query(
                device, b"ui.state", "leshy.ui.v1", "state",
            )
            records["frame_final"] = capture(device, frames, "home-final")
        failures.extend(boot_failures(
            records["clear_ready"], records["recovery_final"],
            args.expected_version, app_identity, expected_cid,
        ))
        failures.extend(expect(records["safety_final"], {
            "state": "armed", "reason": "none", "armed": True,
            "latched": False, "trip_count": 0,
            "emergency_quiesce_count": 0,
            "runtime_owner": "none", "lease_mask": 0,
            "worker_active": "none", "worker_armed": False,
            "worker_expired": False, "worker_trip_count": 0,
        }, "safety_final"))
        failures.extend(expect(records["ui_final"], {
            "page": "home", "safety_latched": False,
            "runtime_owner": "none", "lease_mask": 0,
        }, "ui_final"))
        if int(records["recovery_final"].get("generation", -1)) != saved_generation:
            failures.append("injected Capture Store changed product generation")
        if int(records["recovery_final"].get("observations", -1)) != 0:
            failures.append("saved Wi-Fi Capture has unexpected observations")
        if records["recovery_final"].get("physical_write_calls") != 0:
            failures.append("final read-only recovery performed a physical write")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "runner_sha256": runner_sha,
            "flashed": args.flash,
        },
        "expected_cid": expected_cid,
        "restart_raw": {
            "bytes": len(restart_raw),
            "sha256": hashlib.sha256(restart_raw).hexdigest(),
        },
        "clear_raw": {
            "bytes": len(clear_raw),
            "sha256": hashlib.sha256(clear_raw).hexdigest(),
        },
        "records": records,
        "trace": trace,
        "scope": {
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "normal_storage_write_authorized": True,
            "fault_injection_before_storage_hardware": True,
            "fault_injection_physical_write_calls": 0,
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "worker": "wifi_capture_store",
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
