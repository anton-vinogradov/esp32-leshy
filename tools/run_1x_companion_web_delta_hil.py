#!/usr/bin/env python3
"""Focused one-flash HIL for the explicit ephemeral local Web runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import serial

from capture_1x_ui import PassiveSerial, read_json
from esp_app_identity import app_elf_sha256
from partition_safety import (
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    canonical_partition_table,
    validated_partition_layout,
)
from run_1x_littlefs_parity_hil import read_flash_with_retry
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    query,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.companion_web_delta_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
IDLE_TIMEOUT_US = 10 * 60 * 1_000_000
MAXIMUM_LIFETIME_US = 30 * 60 * 1_000_000


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def checkpoint(output: Path, record: dict[str, Any], name: str) -> None:
    record["checkpoint"] = name
    write_json(output / "run.json", record)


def web_state(device: PassiveSerial) -> dict[str, Any]:
    return query(
        device, b"companion.web.state", "leshy.companion.web.v1", "state")


def open_console_reconnecting(
        port: str, timeout: float) -> tuple[PassiveSerial, int, int]:
    """Open native USB after reset without an unbounded tcdrain()."""
    deadline = time.monotonic() + timeout
    attempts = 0
    disconnects = 0
    last_error = "not opened"
    while time.monotonic() < deadline:
        attempts += 1
        device: PassiveSerial | None = None
        try:
            device = PassiveSerial(
                port, 115200, timeout=0.20, write_timeout=0.5)
            device.reset_input_buffer()
            # Five bytes fit atomically in the native-USB buffer.  Calling
            # flush() here can block forever in termios.tcdrain() while the
            # ESP32-S3 disconnects and re-enumerates after reset.
            device.write(b"ping\n")
            read_json(device, "leshy.boot.v1", "pong", timeout=0.75)
            device.reset_input_buffer()
            return device, attempts, disconnects
        except (OSError, serial.SerialException, TimeoutError) as error:
            last_error = f"{type(error).__name__}: {error}"
            if device is not None:
                disconnects += 1
                try:
                    device.close()
                except (OSError, serial.SerialException):
                    pass
            time.sleep(0.10)
    raise TimeoutError(
        f"native USB console did not reconnect in {timeout:.1f}s: "
        f"{last_error}")


def precursor_candidate_matches(
    precursor: dict[str, Any], candidate: dict[str, Any],
) -> bool:
    """Match an exact legacy installation while verifying layout separately."""
    required = (
        "version", "firmware_sha256", "firmware_bytes", "elf_sha256",
        "map_sha256", "app_elf_sha256",
    )
    if any(precursor.get(field) != candidate.get(field) for field in required):
        return False
    precursor_partitions = precursor.get("partitions_sha256")
    return (precursor_partitions is None or
            precursor_partitions == candidate.get("partitions_sha256"))


def proven_clearable_runtime_watchdog(state: dict[str, Any]) -> bool:
    """Permit an explicit clear only for an idle, fully quiesced old latch."""
    trip_count = state.get("trip_count")
    quiesce_count = state.get("emergency_quiesce_count")
    return (
        state.get("schema") == "leshy.safety.v1" and
        state.get("kind") == "state" and
        state.get("state") == "latched" and
        state.get("reason") == "runtime_watchdog" and
        state.get("armed") is True and
        state.get("latched") is True and
        state.get("clear_pending") is False and
        state.get("automatic_clear") is False and
        state.get("startup_guard_tripped") is False and
        state.get("buzzer_inactive") is True and
        state.get("nrf_ce_inactive") is True and
        state.get("runtime_owner") == "none" and
        state.get("lease_mask") == 0 and
        state.get("worker_active") == "none" and
        state.get("worker_armed") is False and
        state.get("worker_expired") is False and
        state.get("worker_last_expired") == "none" and
        state.get("worker_trip_count") == 0 and
        isinstance(trip_count, int) and not isinstance(trip_count, bool) and
        trip_count > 0 and
        isinstance(quiesce_count, int) and
        not isinstance(quiesce_count, bool) and quiesce_count >= trip_count
    )


def valid_target_id(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 32 and
        all(character in "0123456789ABCDEF" for character in value)
    )


def open_first_target_actions(
    device: PassiveSerial,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Enter Actions through a real Target, never the comparison row."""
    action(device, "down")  # comparison is row 0; first Target is row 1
    focused = query(
        device, b"targets.state", "leshy.targets.product.v1", "state")
    require(
        focused.get("view") == "list" and
        focused.get("selection") == 1 and
        focused.get("selected_target_present") is True and
        valid_target_id(focused.get("selected_target_id")) and
        focused.get("lease_mask") == 13,
        f"first Target row is not focused: {focused}")
    target_id = focused["selected_target_id"]

    action(device, "right")
    detail = query(
        device, b"targets.state", "leshy.targets.product.v1", "state")
    require(
        detail.get("view") == "detail" and
        detail.get("selected_target_present") is True and
        detail.get("selected_target_id") == target_id and
        detail.get("lease_mask") == 13,
        f"first Target detail is not open: {detail}")

    action(device, "right")
    actions = query(
        device, b"targets.state", "leshy.targets.product.v1", "state")
    require(
        actions.get("view") == "actions" and
        actions.get("selected_target_present") is True and
        actions.get("selected_target_id") == target_id and
        actions.get("action_selection") == 0 and
        actions.get("lease_mask") == 13,
        f"first Target actions are not open: {actions}")
    return focused, detail, actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--partitions", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-installed-from", type=Path)
    parser.add_argument(
        "--clear-proven-preexisting-safety-latch", action="store_true",
        help=("explicitly clear only an idle, quiesced runtime-watchdog "
              "latch after exact candidate identity is proven"),
    )
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

    for path in (args.firmware, args.partitions, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    try:
        partition_layout = validated_partition_layout(
            args.partitions, args.firmware.stat().st_size)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        parser.error(f"unsafe candidate partition table: {error}")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if status or head != args.source_commit:
        parser.error("exact Web delta HIL requires the clean candidate commit")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    candidate_partitions = args.output / "partitions.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    shutil.copyfile(args.firmware, candidate)
    candidate_partitions.write_bytes(canonical_partition_table(args.partitions))
    shutil.copyfile(args.elf, retained_elf)
    shutil.copyfile(args.map, retained_map)
    app_identity = app_elf_sha256(candidate)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "harness_commit": head,
        "target": {
            "port": args.port,
            "serial_port_discovery_calls": 0,
            "ports_opened": [args.port],
            "cardputer_ports_opened": 0,
        },
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(retained_elf),
            "map_sha256": sha256_file(retained_map),
            "partitions_sha256": sha256_file(candidate_partitions),
            "partition_layout": partition_layout,
            "app_elf_sha256": app_identity,
        },
        "flash_count": 0,
        "partition_flash_count": 0,
        "radio_tx_scope": "explicit_ephemeral_softap_only",
        "http_exchange_tested": False,
        "http_exchange_reason": "host_wifi_state_not_modified",
    }
    if args.reuse_installed_from is not None:
        precursor_path = args.reuse_installed_from / "run.json"
        if not precursor_path.is_file():
            parser.error("reuse precursor run.json is missing")
        precursor = json.loads(precursor_path.read_text(encoding="utf-8"))
        precursor_target = precursor.get("target", {})
        safe_precursor = (
            precursor.get("status") == "pass" and
            precursor.get("cleanup", {}).get("complete") is True
        ) or (
            precursor.get("status") == "interrupted" and
            precursor.get("checkpoint") == "console_sync"
        )
        if (precursor.get("flash_count") != 1 or not safe_precursor or
                precursor_target.get("port") != args.port or
                precursor_target.get("ports_opened") != [args.port] or
                not precursor_candidate_matches(
                    precursor.get("candidate", {}), record["candidate"])):
            parser.error(
                "reuse precursor does not prove this exact installed candidate")
        record["installed_candidate_reused"] = True
        record["installation_precursor"] = str(precursor_path)
        record["installation_precursor_status"] = precursor.get("status")
        record["installation_flash_count"] = 1
    else:
        record["installed_candidate_reused"] = False
        record["installation_flash_count"] = 0
    write_json(args.output / "run.json", record)
    cleanup: dict[str, Any] = {"attempted": False}
    device: PassiveSerial | None = None

    try:
        checkpoint(args.output, record, "partition_preflight")
        installed_partitions = args.output / "installed-partitions.bin"
        installed_partition_sha, partition_read_attempts = \
            read_flash_with_retry(
                args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                PARTITION_TABLE_SIZE, installed_partitions)
        record["partition_preflight"] = {
            "offset": PARTITION_TABLE_OFFSET,
            "bytes": PARTITION_TABLE_SIZE,
            "read_attempts": partition_read_attempts,
            "expected_sha256": record["candidate"]["partitions_sha256"],
            "observed_sha256": installed_partition_sha,
            "matched": (
                installed_partition_sha ==
                record["candidate"]["partitions_sha256"]),
            "performed_before_application_flash": True,
        }
        write_json(args.output / "run.json", record)
        require(
            record["partition_preflight"]["matched"] is True,
            "installed partition table does not match the candidate; "
            "migration must be backed up and explicitly authorized before HIL")

        if args.reuse_installed_from is None:
            checkpoint(args.output, record, "flash")
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            record["flash_count"] = 1
            record["installation_flash_count"] = 1
            write_json(args.output / "run.json", record)
            time.sleep(1.0)
        else:
            checkpoint(args.output, record, "reuse_installed_candidate")

        checkpoint(args.output, record, "console_sync")
        device, open_attempts, usb_disconnects = open_console_reconnecting(
            args.port, 45.0)
        record["console"] = {
            "open_attempts": open_attempts,
            "disconnects": usb_disconnects,
            "flush_calls_during_reconnect": 0,
        }
        write_json(args.output / "run.json", record)
        try:
            metrics_before = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics_before.get("version") == args.expected_version and
                    metrics_before.get("app_elf_sha256") == app_identity,
                    f"wrong candidate booted: {metrics_before}")
            record["metrics_before"] = metrics_before
            checkpoint(args.output, record, "safety_preflight")
            safety_before = query(
                device, b"safety.state", "leshy.safety.v1", "state")
            safety_preflight: dict[str, Any] = {
                "clear_authorized":
                    args.clear_proven_preexisting_safety_latch,
                "clear_performed": False,
                "before": safety_before,
            }
            record["safety_preflight"] = safety_preflight
            write_json(args.output / "run.json", record)
            if safety_before.get("latched") is True:
                require(args.clear_proven_preexisting_safety_latch,
                        "preexisting safety latch requires explicit clear "
                        f"authorization: {safety_before}")
                require(proven_clearable_runtime_watchdog(safety_before),
                        "preexisting safety latch is not proven clearable: "
                        f"{safety_before}")
                checkpoint(args.output, record, "explicit_safety_clear")
                clear_confirmed: dict[str, Any] = {}
                clear_ack_error = ""
                try:
                    clear_confirmed = query(
                        device, b"safety.clear confirm",
                        "leshy.safety.v1", "clear_confirmed", timeout=5.0)
                    require(clear_confirmed.get("restart_required") is True,
                            "safety clear acknowledgement is invalid: "
                            f"{clear_confirmed}")
                except (OSError, serial.SerialException, TimeoutError) as error:
                    # The command is sent exactly once. Native USB may vanish
                    # before its acknowledgement reaches macOS; recovery below
                    # proves the resulting state read-only and never replays it.
                    clear_ack_error = f"{type(error).__name__}: {error}"
                safety_preflight.update({
                    "clear_action_writes": 1,
                    "clear_action_replays": 0,
                    "clear_ack_received": bool(clear_confirmed),
                    "clear_ack_error": clear_ack_error,
                    "clear_confirmation": clear_confirmed,
                })
                safety_preflight["clear_performed"] = True
                write_json(args.output / "run.json", record)
                device.close()
                device = None
                device, clear_open_attempts, clear_disconnects = \
                    open_console_reconnecting(args.port, 30.0)
                metrics_after_clear = query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                require(
                    metrics_after_clear.get("version") ==
                    args.expected_version and
                    metrics_after_clear.get("app_elf_sha256") == app_identity,
                    f"wrong candidate after safety clear: "
                    f"{metrics_after_clear}")
                safety_after = query(
                    device, b"safety.state", "leshy.safety.v1", "state")
                require(
                    safety_after.get("state") == "armed" and
                    safety_after.get("reason") == "none" and
                    safety_after.get("armed") is True and
                    safety_after.get("latched") is False and
                    safety_after.get("clear_pending") is False and
                    safety_after.get("buzzer_inactive") is True and
                    safety_after.get("nrf_ce_inactive") is True and
                    safety_after.get("runtime_owner") == "none" and
                    safety_after.get("lease_mask") == 0 and
                    safety_after.get("worker_active") == "none" and
                    safety_after.get("worker_armed") is False and
                    safety_after.get("worker_expired") is False,
                    f"safety clear did not restore an armed idle state: "
                    f"{safety_after}")
                safety_preflight.update({
                    "after": safety_after,
                    "metrics_after": metrics_after_clear,
                    "reopen_attempts": clear_open_attempts,
                    "reopen_disconnects": clear_disconnects,
                })
                write_json(args.output / "run.json", record)
            else:
                require(
                    safety_before.get("state") == "armed" and
                    safety_before.get("reason") == "none" and
                    safety_before.get("armed") is True and
                    safety_before.get("buzzer_inactive") is True and
                    safety_before.get("nrf_ce_inactive") is True and
                    safety_before.get("runtime_owner") == "none" and
                    safety_before.get("lease_mask") == 0 and
                    safety_before.get("worker_active") == "none" and
                    safety_before.get("worker_armed") is False and
                    safety_before.get("worker_expired") is False,
                    f"safety preflight is not an armed idle state: "
                    f"{safety_before}")
                safety_preflight["after"] = safety_before

            checkpoint(args.output, record, "storage_baseline")
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == EXPECTED_CID and
                    recovery.get("observed_fingerprint") == EXPECTED_CID and
                    recovery.get("mounted_read_only") is True and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"product storage baseline is not safe: {recovery}")

            checkpoint(args.output, record, "open_targets")
            home = normalize_home(device)
            for _ in range(5):
                home = action(device, "down")
            require(home.get("page") == "home" and
                    home.get("selection") == 5 and
                    home.get("selected_id") == "targets",
                    f"cannot focus Targets: {home}")
            opened = action(device, "right", timeout=40.0)
            require(opened.get("page") == "targets" and
                    opened.get("runtime_owner") == "targets" and
                    opened.get("lease_mask") == 13,
                    f"cannot open Targets: {opened}")
            targets = query(
                device, b"targets.state", "leshy.targets.product.v1", "state")
            require(targets.get("status") == "ready" and
                    int(targets.get("target_count", 0)) > 0 and
                    targets.get("cleanup_complete") is True and
                    targets.get("blocked_write_attempts") == 0,
                    f"Targets snapshot unavailable: {targets}")

            focused, detail, actions = open_first_target_actions(device)
            for _ in range(5):
                action(device, "down")
            selected = query(
                device, b"targets.state", "leshy.targets.product.v1", "state")
            require(selected.get("view") == "actions" and
                    selected.get("action_selection") == 5 and
                    selected.get("lease_mask") == 13,
                    f"local Web action is not selected: {selected}")

            checkpoint(args.output, record, "explicit_authorization")
            action(device, "right")
            staged = web_state(device)
            require(staged.get("overlay_open") is True and
                    staged.get("authorized") is False and
                    staged.get("server_active") is False and
                    staged.get("credential_present") is False and
                    staged.get("network_core_ready") is False and
                    staged.get("begin_stage") == "idle" and
                    staged.get("cleanup_complete") is True and
                    staged.get("targets_suspended") is False and
                    staged.get("lease_mask") == 13,
                    f"Web session started without confirmation: {staged}")
            action(device, "right")
            active = web_state(device)
            require(active.get("overlay_open") is True and
                    active.get("authorized") is True and
                    active.get("server_active") is True and
                    active.get("protocol_connected") is False and
                    int(active.get("generation", 0)) > 0 and
                    active.get("credential_present") is True and
                    active.get("credential_persisted") is False and
                    active.get("credential_exposed_over_diagnostic") is False and
                    active.get("network_core_ready") is True and
                    active.get("begin_stage") == "ready" and
                    active.get("driver_error") == 0 and
                    active.get("cleanup_complete") is False and
                    active.get("targets_suspended") is True and
                    int(active.get("heap_free_before_suspend", 0)) > 0 and
                    int(active.get("heap_free_after_suspend", 0)) >
                    int(active.get("heap_free_before_suspend", 0)) and
                    int(active.get("heap_free_before_begin", 0)) > 0 and
                    int(active.get("heap_largest_before_begin", 0)) > 0 and
                    int(active.get("heap_free_after_begin", 0)) > 0 and
                    active.get("maximum_clients") == 1 and
                    active.get("idle_timeout_us") == IDLE_TIMEOUT_US and
                    active.get("maximum_lifetime_us") == MAXIMUM_LIFETIME_US and
                    active.get("lease_mask") == 15,
                    f"explicit Web session is not bounded: {active}")
            time.sleep(1.0)
            stable = web_state(device)
            require(stable.get("authorized") is True and
                    stable.get("server_active") is True and
                    stable.get("generation") == active.get("generation") and
                    stable.get("requests_handled") == 0 and
                    stable.get("requests_rejected") == 0 and
                    stable.get("lease_mask") == 15,
                    f"idle Web session did not remain stable: {stable}")

            checkpoint(args.output, record, "explicit_stop")
            action(device, "left")
            stopped = web_state(device)
            require(stopped.get("overlay_open") is False and
                    stopped.get("authorized") is False and
                    stopped.get("server_active") is False and
                    stopped.get("protocol_connected") is False and
                    stopped.get("credential_present") is False and
                    stopped.get("stop_reason") == "user" and
                    stopped.get("cleanup_complete") is True and
                    stopped.get("targets_suspended") is False and
                    int(stopped.get("heap_free_after_stop", 0)) > 0 and
                    stopped.get("lease_mask") == 13,
                    f"Web stop did not revoke and scrub: {stopped}")

            cleanup = best_effort_cleanup(device)
            require(cleanup.get("complete") is True,
                    f"final cleanup unproven: {cleanup}")
            released = web_state(device)
            require(released.get("authorized") is False and
                    released.get("server_active") is False and
                    released.get("credential_present") is False and
                    released.get("cleanup_complete") is True and
                    released.get("lease_mask") == 0,
                    f"Web resources survived Targets teardown: {released}")
            safe = query(device, b"hardware.safe-outputs",
                         "leshy.hardware.safe-outputs.v1", "state")
            require(safe.get("buzzer_inactive") is True and
                    safe.get("nrf_ce_inactive") is True and
                    safe.get("software_quiesce_complete") is True,
                    f"safe outputs violated: {safe}")
            inputs = query(device, b"input.state",
                           "leshy.input.frontend.v1", "state")
            require(inputs.get("status") == "ready" and
                    inputs.get("read_errors") == 0 and
                    inputs.get("queue_drops") == 0,
                    f"input regression: {inputs}")
            metrics_after = query(
                device, b"metrics", "leshy.boot.v1", "ready")
        finally:
            device.close()
            device = None

        record.update({
            "status": "pass",
            "checkpoint": "complete",
            "exact_cid": EXPECTED_CID,
            "boot_recovery": recovery,
            "safety_preflight": safety_preflight,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "targets": targets,
            "focused": focused,
            "detail": detail,
            "actions": actions,
            "selected": selected,
            "staged": staged,
            "active": active,
            "stable": stable,
            "stopped": stopped,
            "released": released,
            "safe_outputs": safe,
            "input": inputs,
            "cleanup": cleanup,
            "storage_write_commands": 0,
            "raw_radio_tx_commands": 0,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({
            "schema": SCHEMA,
            "status": "pass",
            "run": str(args.output / "run.json"),
            "generation": active["generation"],
            "final_lease_mask": released["lease_mask"],
        }, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        if device is not None:
            try:
                device.close()
            except (OSError, serial.SerialException):
                pass
            device = None
        checkpoint_name = record.get("checkpoint")
        if (checkpoint_name == "partition_preflight" and
                record.get("flash_count") == 0):
            cleanup = {
                "attempted": False,
                "complete": True,
                "reason": "runtime_not_opened_before_partition_rejection",
            }
        else:
            try:
                device, cleanup_open_attempts, cleanup_disconnects = \
                    open_console_reconnecting(args.port, 10.0)
                try:
                    cleanup = best_effort_cleanup(device)
                    cleanup["open_attempts"] = cleanup_open_attempts
                    cleanup["disconnects"] = cleanup_disconnects
                finally:
                    device.close()
                    device = None
            except Exception as cleanup_error:
                cleanup = {
                    "attempted": True,
                    "complete": False,
                    "errors": [
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    ],
                }
        record.update({
            "status": (
                "interrupted" if isinstance(error, KeyboardInterrupt)
                else "failed"
            ),
            "failure": f"{type(error).__name__}: {error}",
            "cleanup": cleanup,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
