#!/usr/bin/env python3
"""Prove that the exact app fails safe before Arduino app startup."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_boot_watchdog_hil import capture_until_ready, parse_ready
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    boot_ready_failures,
    expect,
    query,
    reset_capture,
    resolve_expected_cid,
)


RUN_SCHEMA = "leshy.early_boot_watchdog_hil.run.v1"
WATCHDOG_RESET_REASONS = {4, 5, 6, 7}
SOFTWARE_RESET_REASON = 3


def early_boot_injection_failures(
        armed: dict[str, Any], ready: dict[str, Any],
        safety: dict[str, Any], ui: dict[str, Any],
        outputs: dict[str, Any], recovery: dict[str, Any],
        expected_version: str, app_identity: str) -> list[str]:
    failures = boot_ready_failures(ready, expected_version, app_identity)
    if ready.get("reset_reason_code") not in WATCHDOG_RESET_REASONS:
        failures.append(
            "watchdog_boot.reset_reason_code: expected panic/watchdog reset"
        )
    failures.extend(expect(armed, {
        "status": "ready", "stage": "before_setup",
        "watchdog_timeout_ms": 5000, "outputs_inactive": True,
        "filesystem_write_attempted": False, "physical_write_calls": 0,
    }, "injection"))
    failures.extend(expect(safety, {
        "state": "latched", "reason": "runtime_watchdog",
        "armed": True, "latched": True, "clear_pending": False,
        "trip_count": 1, "emergency_quiesce_count": 1,
        "startup_guard_tripped": True,
        "buzzer_inactive": True, "nrf_ce_inactive": True,
        "runtime_owner": "none", "lease_mask": 0,
        "automatic_clear": False,
    }, "safety_latched"))
    failures.extend(expect(ui, {
        "page": "safe_mode", "safety_latched": True,
        "runtime_owner": "none", "lease_mask": 0,
    }, "ui_latched"))
    failures.extend(expect(outputs, {
        "buzzer_inactive": True, "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
        "physical_rail_kill_available": False,
        "cc1101_hard_kill_available": False,
    }, "outputs_latched"))
    failures.extend(expect(recovery, {
        "status": "safety_latched", "cleanup_complete": True,
        "physical_write_calls": 0, "owned_after": 0,
    }, "recovery_latched"))
    return failures


def final_failures(
        ready: dict[str, Any], recovery: dict[str, Any],
        safety: dict[str, Any], ui: dict[str, Any],
        outputs: dict[str, Any], before_recovery: dict[str, Any],
        expected_version: str, app_identity: str,
        expected_cid: str) -> list[str]:
    failures = boot_failures(
        ready, recovery, expected_version, app_identity, expected_cid
    )
    if ready.get("reset_reason_code") != SOFTWARE_RESET_REASON:
        failures.append("final_boot.reset_reason_code: expected software reset")
    failures.extend(expect(safety, {
        "state": "armed", "reason": "none", "armed": True,
        "latched": False, "clear_pending": False,
        "trip_count": 0, "emergency_quiesce_count": 0,
        "startup_guard_tripped": False,
        "buzzer_inactive": True, "nrf_ce_inactive": True,
        "runtime_owner": "none", "lease_mask": 0,
    }, "safety_final"))
    failures.extend(expect(ui, {
        "page": "home", "safety_latched": False,
        "runtime_owner": "none", "lease_mask": 0,
    }, "ui_final"))
    failures.extend(expect(outputs, {
        "buzzer_inactive": True, "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "outputs_final"))
    for key in ("generation", "observations"):
        if recovery.get(key) != before_recovery.get(key):
            failures.append(
                f"final_recovery.{key}: {recovery.get(key)!r} != "
                f"{before_recovery.get(key)!r}"
            )
    return failures


def require_exact_source(source_root: Path, source_commit: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if source_commit != head:
        raise ValueError(
            f"--source-commit {source_commit} does not match HEAD {head}"
        )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if status:
        raise ValueError("source tree must be clean before exact HIL")


def main() -> int:
    from capture_1x_ui import PassiveSerial, read_json, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--flash", action="store_true")
    mode.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=30.0)
    parser.add_argument("--watchdog-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")
    source_root = Path(__file__).resolve().parents[1]
    try:
        require_exact_source(source_root, args.source_commit)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    runner_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected_cid = args.expected_cid or ""
    failures: list[str] = []
    records: dict[str, Any] = {}
    watchdog_raw = b""
    clear_raw = b""
    flash_completed = False

    try:
        if args.flash:
            flash_candidate(
                args.port, candidate, args.flash_offset, args.flash_baud
            )
            flash_completed = True
            time.sleep(0.5)

        ready, recovery, timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        records["boot_before"] = {
            "ready": ready, "recovery": recovery, "timing": timing,
        }
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
            records["boot_before"]["recovery"] = recovery
            expected_cid = resolve_expected_cid(args.expected_cid, recovery)
            failures.extend(boot_failures(
                ready, recovery, args.expected_version,
                app_identity, expected_cid,
            ))
            records["safety_before"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["ui_before"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["outputs_before"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state",
            )
            failures.extend(expect(records["safety_before"], {
                "state": "armed", "reason": "none", "armed": True,
                "latched": False, "clear_pending": False,
                "runtime_owner": "none", "lease_mask": 0,
                "buzzer_inactive": True, "nrf_ce_inactive": True,
            }, "safety_before"))
            failures.extend(expect(records["ui_before"], {
                "page": "home", "safety_latched": False,
                "runtime_owner": "none", "lease_mask": 0,
            }, "ui_before"))
            failures.extend(expect(records["outputs_before"], {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True,
            }, "outputs_before"))
            if not failures:
                device.write(b"safety.early-boot-watchdog-test confirm\n")
                device.flush()
                records["injection"] = read_json(
                    device, "leshy.safety.early_boot_watchdog_test.v1",
                    "armed", 5.0,
                )
                watchdog_raw, ready_ms = capture_until_ready(
                    device, args.watchdog_seconds
                )
                records["watchdog_ready_marker_ms"] = ready_ms

        (args.output / "watchdog-reset.ndjson").write_bytes(watchdog_raw)
        if "injection" not in records:
            raise RuntimeError(
                "initial admission failed; early-boot injection was not started"
            )
        records["watchdog_ready"] = parse_ready(watchdog_raw)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 15.0)
            records["safety_latched"] = query(
                device, b"safety.state", "leshy.safety.v1", "state"
            )
            records["ui_latched"] = query(
                device, b"ui.state", "leshy.ui.v1", "state"
            )
            records["outputs_latched"] = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state",
            )
            records["recovery_latched"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state",
            )
        failures.extend(early_boot_injection_failures(
            records.get("injection", {}), records["watchdog_ready"],
            records["safety_latched"], records["ui_latched"],
            records["outputs_latched"], records["recovery_latched"],
            args.expected_version, app_identity,
        ))

        # Never clear an unproven latch. A failed injection remains fail-safe
        # for inspection; only exact, machine-checked proof may restore Home.
        if not failures:
            with PassiveSerial(args.port, 115200, timeout=0.05) as device:
                synchronize_console(device, 15.0)
                device.write(b"safety.clear confirm\n")
                device.flush()
                records["clear_request"] = read_json(
                    device, "leshy.safety.v1", "clear_confirmed", 5.0
                )
                clear_raw, clear_ready_ms = capture_until_ready(
                    device, args.boot_seconds
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
                    device, b"safety.state", "leshy.safety.v1", "state"
                )
                records["ui_final"] = query(
                    device, b"ui.state", "leshy.ui.v1", "state"
                )
                records["outputs_final"] = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state",
                )
            failures.extend(final_failures(
                records["clear_ready"], records["recovery_final"],
                records["safety_final"], records["ui_final"],
                records["outputs_final"], recovery,
                args.expected_version, app_identity, expected_cid,
            ))
    except Exception as error:  # retain terminal fail-closed evidence
        failures.append(f"{type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": (
            flash_completed or args.reuse_exact_flash
        ) and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "runner_sha256": runner_sha,
            "flash_requested": args.flash,
            "flashed": flash_completed,
            "reused_exact_flash": args.reuse_exact_flash,
        },
        "expected_cid": expected_cid,
        "watchdog_raw": {
            "bytes": len(watchdog_raw),
            "sha256": hashlib.sha256(watchdog_raw).hexdigest(),
        },
        "clear_raw": {
            "bytes": len(clear_raw),
            "sha256": hashlib.sha256(clear_raw).hexdigest(),
        },
        "records": records,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
