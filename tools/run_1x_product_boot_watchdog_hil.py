#!/usr/bin/env python3
"""Exercise the hardware-backed product boot-recovery watchdog on one board."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    expect,
    query,
    reset_capture,
    resolve_expected_cid,
)


RUN_SCHEMA = "leshy.product_boot_watchdog_hil.run.v1"
WATCHDOG_RESET_REASONS = {4, 5, 6, 7}


def capture_until_ready(device: Any, seconds: float) -> tuple[bytes, float | None]:
    deadline = time.monotonic() + seconds
    started = time.monotonic()
    ready_at: float | None = None
    raw = bytearray()
    while time.monotonic() < deadline:
        chunk = device.read(device.in_waiting or 1)
        if chunk:
            raw.extend(chunk)
            if ready_at is None and b'"schema":"leshy.boot.v1","kind":"ready"' in raw:
                ready_at = time.monotonic()
        if ready_at is not None and time.monotonic() - ready_at >= 1.0:
            break
    ready_ms = None if ready_at is None else round((ready_at - started) * 1000.0, 3)
    return bytes(raw), ready_ms


def parse_ready(raw: bytes) -> dict[str, Any]:
    ready: dict[str, Any] = {}
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (isinstance(value, dict) and value.get("schema") == "leshy.boot.v1"
                and value.get("kind") == "ready"):
            ready = value
    return ready


def injection_failures(ready: dict[str, Any], recovery: dict[str, Any],
                       final: dict[str, Any], expected_version: str,
                       app_identity: str, expected_cid: str) -> list[str]:
    failures = boot_failures(
        ready, recovery, expected_version, app_identity, expected_cid
    )
    if ready.get("reset_reason_code") not in WATCHDOG_RESET_REASONS:
        failures.append(
            "watchdog_boot.reset_reason_code: expected panic/watchdog reset"
        )
    attempts = recovery.get("attempts")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 2:
        failures.append("watchdog_recovery.attempts: expected >= 2")
    if recovery.get("timeout_restarts") != 1:
        failures.append(
            "watchdog_recovery.timeout_restarts: expected exactly 1"
        )
    failures.extend(expect(final, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
    }, "final"))
    return failures


def main() -> int:
    from capture_1x_ui import PassiveSerial, read_json, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=30.0)
    parser.add_argument("--watchdog-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    initial_ready: dict[str, Any] = {}
    initial_recovery: dict[str, Any] = {}
    initial_state: dict[str, Any] = {}
    initial_timing: dict[str, Any] = {}
    armed: dict[str, Any] = {}
    watchdog_ready: dict[str, Any] = {}
    watchdog_recovery: dict[str, Any] = {}
    final_state: dict[str, Any] = {}
    watchdog_raw = b""
    watchdog_ready_ms: float | None = None
    expected_cid = args.expected_cid or ""

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
            time.sleep(1.0)
        initial_ready, initial_recovery, initial_timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        device = PassiveSerial(args.port, 115200, timeout=0.05)
        with device:
            synchronize_console(device)
            initial_recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            expected_cid = resolve_expected_cid(args.expected_cid, initial_recovery)
            failures.extend(boot_failures(
                initial_ready, initial_recovery, args.expected_version,
                app_identity, expected_cid
            ))
            initial_state = query(device, b"ui.state", "leshy.ui.v1", "state")
            failures.extend(expect(initial_state, {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            }, "initial"))
            if not failures:
                device.write(b"storage.product.boot-watchdog-test confirm\n")
                device.flush()
                armed = read_json(
                    device, "leshy.storage.product_boot_watchdog_test.v1",
                    "armed", timeout=5.0
                )
                failures.extend(expect(armed, {
                    "status": "ready", "filesystem_write_attempted": False,
                    "physical_write_calls": 0,
                }, "armed"))
                watchdog_raw, watchdog_ready_ms = capture_until_ready(
                    device, args.watchdog_seconds
                )
        (args.output / "watchdog-reset.ndjson").write_bytes(watchdog_raw)
        watchdog_ready = parse_ready(watchdog_raw)

        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
            synchronize_console(device)
            watchdog_recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            final_state = query(device, b"ui.state", "leshy.ui.v1", "state")
        failures.extend(injection_failures(
            watchdog_ready, watchdog_recovery, final_state,
            args.expected_version, app_identity, expected_cid
        ))
    except Exception as error:  # retain a terminal fail-closed artifact
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
            "flashed": args.flash,
        },
        "expected_cid": expected_cid,
        "boot_before": {
            "ready": initial_ready, "recovery": initial_recovery,
            "state": initial_state, "timing": initial_timing,
        },
        "injection": armed,
        "watchdog_boot": {
            "ready": watchdog_ready,
            "ready_marker_ms": watchdog_ready_ms,
            "raw_bytes": len(watchdog_raw),
            "raw_sha256": hashlib.sha256(watchdog_raw).hexdigest(),
            "recovery": watchdog_recovery,
        },
        "final_state": final_state,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
