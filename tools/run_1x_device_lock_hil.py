#!/usr/bin/env python3
"""Verify Device Lock UI/KDF on board-01 without enrolling a credential."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
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
    valid_cid,
)


RUN_SCHEMA = "leshy.device_lock_hil.run.v1"
LOCK_SCHEMA = "leshy.device_lock.v1"


def read_only_query(device: PassiveSerial, command: bytes, schema: str,
                    kind: str, timeout: float = 5.0) -> dict[str, Any]:
    """Retry state only; commands that mutate HIL state are never replayed."""
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            result = query(device, command, schema, kind, timeout=timeout)
            result["host_transport_attempts"] = attempt
            result["host_transport_transient_retries"] = attempt - 1
            result["host_transport_transient_errors"] = errors
            return result
        except TimeoutError as error:
            if attempt == 2:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable query retry")


def lock_state_unchanged_failures(before: dict[str, Any],
                                  after: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in ("status", "failure", "failed_attempts",
                  "credential_generation", "protected_access"):
        if before.get(field) != after.get(field):
            failures.append(
                f"Device Lock {field} changed: "
                f"{before.get(field)!r}->{after.get(field)!r}"
            )
    return failures


def benchmark_failures(report: dict[str, Any], label: str,
                       require_stable_heap: bool) -> list[str]:
    failures = expect(report, {
        "benchmark_requested": True,
        "benchmark_complete": True,
        "benchmark_success": True,
        "benchmark_vector_verified": True,
        "persistence_touched_by_benchmark": False,
        "radio_touched": False,
        "worker_active": False,
    }, label)
    elapsed = report.get("benchmark_elapsed_us")
    if not isinstance(elapsed, int) or elapsed <= 0 or elapsed > 15_000_000:
        failures.append(f"{label}.elapsed_us={elapsed!r} outside 1..15000000")
    heap_before = report.get("benchmark_heap_before")
    heap_after = report.get("benchmark_heap_after")
    if require_stable_heap and heap_before != heap_after:
        failures.append(
            f"{label} heap did not return to its in-task baseline: "
            f"{heap_before!r}->{heap_after!r}"
        )
    if not require_stable_heap:
        if (not isinstance(heap_before, int) or
                not isinstance(heap_after, int) or
                heap_after > heap_before or heap_before - heap_after > 256):
            failures.append(
                f"{label} one-time heap initialization is outside 0..256 B: "
                f"{heap_before!r}->{heap_after!r}"
            )
    return failures


def home_device(device: PassiveSerial) -> dict[str, Any]:
    current = read_only_query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(16):
        if current.get("page") == "home":
            break
        current = action(device, "left")
    if current.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {current}")
    for _ in range(16):
        if current.get("selected_id") == "device":
            return current
        current = action(device, "down")
    raise RuntimeError(f"Device item not reachable from Home: {current}")


def device_lock_page(device: PassiveSerial) -> dict[str, Any]:
    current = action(device, "right")
    if current.get("page") != "device":
        raise RuntimeError(f"Device menu did not open: {current}")
    while int(current.get("device_selection", -1)) > 0:
        current = action(device, "up")
    # Connectivity was inserted before Device Lock in the task-first Device
    # tree.  Keep every shared HIL caller aligned with the production menu.
    while int(current.get("device_selection", -1)) < 3:
        current = action(device, "down")
    if int(current.get("device_selection", -1)) != 3:
        raise RuntimeError(f"Device Lock item not reachable: {current}")
    current = action(device, "right")
    if current.get("page") != "device_lock":
        raise RuntimeError(f"Device Lock page did not open: {current}")
    return current


def wait_benchmark(device: PassiveSerial,
                   timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = read_only_query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        if latest.get("benchmark_complete"):
            return latest
        time.sleep(0.05)
    raise TimeoutError(f"Device Lock KDF benchmark did not complete: {latest}")


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

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    hil_begun = False
    hil_ended: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.6)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                metrics_before = read_only_query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                recovery_before = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                reports["metrics_before"] = metrics_before
                reports["recovery_before"] = recovery_before
                failures.extend(boot_failures(
                    metrics_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("candidate boot contract failed")

                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                begun = query(
                    device,
                    f"hil.begin {run_id} {app_identity}".encode("ascii"),
                    "leshy.hil.session.v1", "begun")
                hil_begun = True
                reports["hil_begun"] = begun

                lock_before = read_only_query(
                    device, b"device-lock.state", LOCK_SCHEMA, "state")
                reports["lock_before"] = lock_before
                accepted = query(
                    device,
                    b"device-lock.kdf-benchmark confirm-no-persist",
                    LOCK_SCHEMA, "benchmark")
                reports["benchmark_accepted"] = accepted
                failures.extend(expect(accepted, {
                    "status": "accepted", "accepted": True,
                    "iterations": 120000, "persistence_touched": False,
                    "radio_touched": False,
                }, "benchmark_start"))

                responsive_started = time.monotonic()
                responsive = read_only_query(
                    device, b"ui.state", "leshy.ui.v1", "state")
                responsive_ms = round(
                    (time.monotonic() - responsive_started) * 1000.0, 3)
                responsive["host_ack_ms"] = responsive_ms
                reports["ui_during_kdf"] = responsive
                if responsive_ms > 500.0:
                    failures.append(
                        f"UI command blocked {responsive_ms} ms during KDF")

                benchmark_warmup = wait_benchmark(device)
                reports["benchmark_warmup"] = benchmark_warmup
                failures.extend(benchmark_failures(
                    benchmark_warmup, "kdf_benchmark_warmup", False))
                failures.extend(lock_state_unchanged_failures(
                    lock_before, benchmark_warmup))

                accepted_repeat = query(
                    device,
                    b"device-lock.kdf-benchmark confirm-no-persist",
                    LOCK_SCHEMA, "benchmark")
                reports["benchmark_repeat_accepted"] = accepted_repeat
                failures.extend(expect(accepted_repeat, {
                    "status": "accepted", "accepted": True,
                    "iterations": 120000, "persistence_touched": False,
                    "radio_touched": False,
                }, "benchmark_repeat_start"))
                benchmark = wait_benchmark(device)
                reports["benchmark"] = benchmark
                failures.extend(benchmark_failures(
                    benchmark, "kdf_benchmark_repeat", True))
                failures.extend(lock_state_unchanged_failures(
                    lock_before, benchmark))
                if (benchmark.get("benchmark_heap_before") !=
                        benchmark_warmup.get("benchmark_heap_after")):
                    failures.append(
                        "KDF repeat did not start from the warm heap baseline: "
                        f"{benchmark_warmup.get('benchmark_heap_after')!r}->"
                        f"{benchmark.get('benchmark_heap_before')!r}"
                    )

                home_device(device)
                trace.append(device_lock_page(device))
                screens["device_lock_status"] = capture(
                    device, frames, "device-lock-status")

                if lock_before.get("status") in {"unconfigured", "locked"}:
                    editor = action(device, "right")
                    trace.append(editor)
                    failures.extend(expect(editor, {
                        "page": "device_lock",
                        "runtime_event": "device_lock_editor_opened",
                        "render_mode": "full",
                    }, "editor_open"))
                    screens["device_lock_editor"] = capture(
                        device, frames, "device-lock-editor")
                    digit = action(device, "down")
                    trace.append(digit)
                    failures.extend(expect(digit, {
                        "page": "device_lock", "changed": True,
                        "render_mode": "incremental",
                    }, "editor_digit_delta"))
                    advance = action(device, "right")
                    trace.append(advance)
                    failures.extend(expect(advance, {
                        "page": "device_lock", "changed": True,
                        "render_mode": "incremental",
                    }, "editor_cursor_delta"))
                    screens["device_lock_editor_delta"] = capture(
                        device, frames, "device-lock-editor-delta")
                    cancelled = action(device, "left")
                    trace.append(cancelled)
                    failures.extend(expect(cancelled, {
                        "page": "device_lock",
                        "runtime_event": "device_lock_editor_cancelled",
                    }, "editor_cancel"))

                lock_after = read_only_query(
                    device, b"device-lock.state", LOCK_SCHEMA, "state")
                reports["lock_after"] = lock_after
                failures.extend(lock_state_unchanged_failures(
                    lock_before, lock_after))
                trace.append(action(device, "left"))
                home = action(device, "left")
                trace.append(home)
                failures.extend(expect(home, {
                    "page": "home", "runtime_owner": "none",
                    "lease_mask": 0,
                }, "final_home"))

                recovery_after = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                reports["recovery_after"] = recovery_after
                for field in ("generation", "observations"):
                    if recovery_before.get(field) != recovery_after.get(field):
                        failures.append(f"persistent {field} changed")
                if recovery_after.get("physical_write_calls") != 0:
                    failures.append("physical SD write observed")
                input_state = read_only_query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                reports["input"] = input_state
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0,
                    "queue_drops": 0,
                }, "input"))
                safe = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                reports["safe_outputs"] = safe
                failures.extend(expect(safe, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
                metrics_after = read_only_query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                reports["metrics_after"] = metrics_after
                warmup_before = benchmark_warmup.get("benchmark_heap_before")
                warmup_after = benchmark_warmup.get("benchmark_heap_after")
                expected_heap_after = metrics_before.get("heap_free")
                if (isinstance(expected_heap_after, int) and
                        isinstance(warmup_before, int) and
                        isinstance(warmup_after, int)):
                    expected_heap_after -= warmup_before - warmup_after
                if metrics_after.get("heap_free") != expected_heap_after:
                    failures.append(
                        "heap free did not settle at the measured warm baseline: "
                        f"{expected_heap_after!r}->"
                        f"{metrics_after.get('heap_free')!r}"
                    )
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
                if hil_begun:
                    try:
                        hil_ended = query(
                            device, f"hil.end {run_id}".encode("ascii"),
                            "leshy.hil.session.v1", "ended")
                    except Exception as error:
                        failures.append(
                            f"hil_end: {type(error).__name__}: {error}")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": bool(args.flash or args.reuse_exact_flash) and
            not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "app_elf_sha256": app_identity,
            "flashed": bool(args.flash or args.reuse_exact_flash),
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "reports": reports,
        "screens": screens,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "hil_ended": hil_ended,
        "scope": {
            "credential_enrollment": False,
            "credential_persistence": False,
            "radio": False,
            "storage_write": False,
            "mac_wifi": False,
            "clone": False,
            "cardputer": False,
        },
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
    }, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
