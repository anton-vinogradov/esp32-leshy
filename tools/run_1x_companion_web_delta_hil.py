#!/usr/bin/env python3
"""Focused one-flash HIL for the explicit ephemeral local Web runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import serial

from capture_1x_ui import PassiveSerial, read_json
from companion_web_http_hil import (
    MacWifiGuard,
    derive_local_credentials,
    http_companion_request,
    http_get,
)
from esp_app_identity import app_elf_sha256
from partition_safety import (
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    canonical_partition_table,
    validated_partition_layout,
)
from run_1x_littlefs_parity_hil import read_flash_with_retry
from run_1x_companion_usb_delta_hil import (
    companion_request as usb_companion_exchange,
)
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
READ_SCOPES = ["session.read", "target.read", "target.compare"]
READ_CAPABILITIES = [
    "session.list", "session.detail", "target.list", "target.detail",
    "target.compare",
]
WEB_SCOPES = READ_SCOPES + ["target.mutate"]
WEB_CAPABILITIES = READ_CAPABILITIES + [
    "target.favorite.set", "target.name.set", "target.notes.set",
    "target.tag.add", "target.tag.remove",
]
CompanionExchange = Callable[[dict[str, Any]], dict[str, Any]]


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def checkpoint(output: Path, record: dict[str, Any], name: str) -> None:
    record["checkpoint"] = name
    write_json(output / "run.json", record)


def web_state(device: PassiveSerial) -> dict[str, Any]:
    return query(
        device, b"companion.web.state", "leshy.companion.web.v1", "state")


def query_expected_error(device: PassiveSerial, command: bytes, schema: str,
                         timeout: float = 5.0) -> dict[str, Any]:
    """Read an error response that is itself the expected test outcome."""
    deadline = time.monotonic() + timeout
    device.write(command + b"\n")
    device.flush()
    while time.monotonic() < deadline:
        line = device.readline()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (isinstance(value, dict) and value.get("schema") == schema and
                value.get("kind") == "error"):
            return value
    raise TimeoutError(f"timed out waiting for {schema}/error")


def protocol_request(kind: str, request_id: str,
                     **fields: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "leshy.companion.request.v1",
        "kind": kind,
        "request_id": request_id,
    }
    value.update(fields)
    return value


def without_request_id(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "request_id"}


def collect_companion_pages(
        exchange: CompanionExchange, kind: str, request_prefix: str,
        fixed: dict[str, Any], maximum_pages: int = 64,
) -> tuple[list[Any], list[dict[str, Any]]]:
    offset = 0
    items: list[Any] = []
    pages: list[dict[str, Any]] = []
    for page_number in range(maximum_pages):
        response = exchange(protocol_request(
            kind, f"{request_prefix}-{page_number}", offset=offset,
            **fixed))
        require(
            response.get("status") == "ok" and
            response.get("reason") == "none",
            f"{kind} page rejected: {response}")
        page_items = response.get("items", [])
        require(isinstance(page_items, list),
                f"{kind} page does not contain a list: {response}")
        items.extend(page_items)
        pages.append(response)
        next_offset = response.get("next_offset")
        if next_offset is None:
            return items, pages
        require(
            isinstance(next_offset, int) and next_offset > offset,
            f"{kind} pagination did not advance: {response}")
        offset = next_offset
    raise RuntimeError(f"{kind} exceeded bounded pagination")


def normalized_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [without_request_id(page) for page in pages]


def target_from_items(items: list[Any], target_id: str) -> dict[str, Any]:
    for item in items:
        if isinstance(item, dict) and item.get("target_id") == target_id:
            return item
    raise RuntimeError(f"Target {target_id} disappeared from companion list")


def wait_companion_mutation(
        exchange: CompanionExchange, mutation_id: str,
        request_prefix: str, timeout: float = 20.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    samples: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        response = exchange(protocol_request(
            "target.mutation.status",
            f"{request_prefix}-{len(samples)}", mutation_id=mutation_id))
        samples.append(response)
        if response.get("state") in ("saved", "failed"):
            return response, samples
        time.sleep(0.05)
    raise TimeoutError(
        f"companion mutation did not finish: {samples[-4:]}")


def assert_atomic_mutation_state(
        state: dict[str, Any], expected_generation: int) -> None:
    require(
        state.get("status") == "ready" and
        state.get("mutation_state") == "saved" and
        state.get("mutation_status") == "saved" and
        state.get("mutation_persisted") is True and
        state.get("mutation_generation") == expected_generation and
        state.get("target_state_generation") == expected_generation and
        state.get("mutation_expected_cid") == EXPECTED_CID and
        state.get("mutation_observed_cid") == EXPECTED_CID and
        state.get("mutation_write_calls") == 3 and
        state.get("mutation_file_syncs") == 3 and
        state.get("mutation_directory_syncs") == 3 and
        state.get("cleanup_complete") is True and
        state.get("lease_mask") == 15,
        f"atomic Web companion save invariant failed: {state}")
    attempts = int(state.get("mutation_identity_attempts", 0))
    retries = int(state.get("mutation_identity_transient_retries", -1))
    require(1 <= attempts <= 8 and retries == attempts - 1,
            f"identity retry accounting invalid: {state}")


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


def failed_precursor_proves_safe_reuse(
        precursor: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Accept a failed run only after exact boot and proven safe cleanup."""
    if precursor.get("status") != "failed":
        return False
    metrics = precursor.get("metrics_before", {})
    cleanup = precursor.get("cleanup", {})
    final_state = cleanup.get("final_state", {})
    host_wifi = precursor.get("host_wifi")
    host_restored = (
        host_wifi is None or
        (host_wifi.get("restore_attempted") is True and
         host_wifi.get("restored") is True)
    )
    return (
        metrics.get("version") == candidate.get("version") and
        metrics.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
        cleanup.get("attempted") is True and
        cleanup.get("complete") is True and
        cleanup.get("errors") == [] and
        final_state.get("page") == "home" and
        final_state.get("runtime_owner") == "none" and
        final_state.get("lease_mask") == 0 and
        final_state.get("safety_state") == "armed" and
        final_state.get("safety_latched") is False and
        host_restored
    )


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
        "--allow-host-wifi-change", action="store_true",
        help="explicitly authorize one guarded join and exact restoration")
    parser.add_argument("--wifi-interface")
    parser.add_argument("--wifi-service")
    parser.add_argument("--softap-mac")
    parser.add_argument(
        "--web-base-url", default="http://192.168.4.1",
        help="fixed local device origin; defaults to the SoftAP gateway")
    parser.add_argument(
        "--clear-proven-preexisting-safety-latch", action="store_true",
        help=("explicitly clear only an idle, quiesced runtime-watchdog "
              "latch after exact candidate identity is proven"),
    )
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

    wifi_arguments = (
        args.wifi_interface, args.wifi_service, args.softap_mac)
    http_exchange_requested = args.allow_host_wifi_change or any(
        value is not None for value in wifi_arguments)
    if http_exchange_requested and not (
            args.allow_host_wifi_change and all(wifi_arguments)):
        parser.error(
            "physical HTTP requires --allow-host-wifi-change, "
            "--wifi-interface, --wifi-service and --softap-mac together")
    if args.web_base_url.rstrip("/") != "http://192.168.4.1":
        parser.error("Web HIL origin must remain the fixed local SoftAP gateway")
    if http_exchange_requested:
        try:
            derive_local_credentials(args.softap_mac, bytes(range(16)))
        except ValueError as error:
            parser.error(str(error))

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
        "http_exchange_reason": (
            "pending_guarded_host_wifi_exchange" if http_exchange_requested
            else "host_wifi_state_not_modified"),
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
        ) or failed_precursor_proves_safe_reuse(
            precursor, record["candidate"])
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
    hil_session_id = secrets.token_hex(16) if http_exchange_requested else ""
    hil_session_started = False
    wifi_guard: MacWifiGuard | None = None
    host_wifi: dict[str, Any] = {
        "change_authorized": http_exchange_requested,
        "interface_explicit": args.wifi_interface is not None,
        "service_explicit": args.wifi_service is not None,
        "snapshot_complete": False,
        "restore_attempted": False,
        "restored": False,
        "prior_ssid_recorded": False,
        "transient_passphrase_recorded": False,
    }

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

            if http_exchange_requested:
                checkpoint(args.output, record, "hil_session_begin")
                hil_begin = query(
                    device,
                    f"hil.begin {hil_session_id} {app_identity}".encode(
                        "ascii"),
                    "leshy.hil.session.v1", "begun")
                require(
                    hil_begin.get("status") == "begun" and
                    hil_begin.get("session_id") == hil_session_id and
                    hil_begin.get("active") is True and
                    hil_begin.get("app_elf_sha256") == app_identity,
                    f"exact HIL session was not admitted: {hil_begin}")
                hil_session_started = True

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
                    staged.get("hil_seed_armed") is False and
                    staged.get("network_core_ready") is False and
                    staged.get("begin_stage") == "idle" and
                    staged.get("cleanup_complete") is True and
                    staged.get("targets_suspended") is False and
                    staged.get("survey_worker_suspended") is False and
                    staged.get("lease_mask") == 13,
                    f"Web session started without confirmation: {staged}")

            expected_ssid = ""
            expected_passphrase = ""
            invalid_seed: dict[str, Any] = {}
            seed_armed: dict[str, Any] = {}
            seed_replay: dict[str, Any] = {}
            seeded_state: dict[str, Any] = {}
            if http_exchange_requested:
                invalid_seed = query_expected_error(
                    device, b"companion.web.hil-seed " + b"0" * 32,
                    "leshy.companion.web.seed.v1")
                require(
                    invalid_seed.get("status") == "invalid" and
                    invalid_seed.get("reason") == "invalid_entropy" and
                    invalid_seed.get("credential_exposed") is False,
                    f"invalid HIL seed did not fail closed: {invalid_seed}")
                entropy = secrets.token_bytes(16)
                while not any(entropy):
                    entropy = secrets.token_bytes(16)
                expected_ssid, expected_passphrase = \
                    derive_local_credentials(args.softap_mac, entropy)
                seed_armed = query(
                    device,
                    f"companion.web.hil-seed {entropy.hex()}".encode("ascii"),
                    "leshy.companion.web.seed.v1", "armed")
                require(
                    seed_armed.get("status") == "armed" and
                    seed_armed.get("bytes") == 16 and
                    seed_armed.get("one_shot") is True and
                    seed_armed.get("softap_mac", "").lower() ==
                    args.softap_mac.lower() and
                    seed_armed.get("credential_exposed") is False,
                    f"one-shot Web HIL seed was not armed: {seed_armed}")
                seed_replay = query_expected_error(
                    device,
                    f"companion.web.hil-seed {entropy.hex()}".encode("ascii"),
                    "leshy.companion.web.seed.v1")
                entropy = b""
                require(
                    seed_replay.get("status") == "denied" and
                    seed_replay.get("reason") == "invalid_hil_scope" and
                    seed_replay.get("credential_exposed") is False,
                    f"one-shot HIL seed replay was accepted: {seed_replay}")
                seeded_state = web_state(device)
                require(
                    seeded_state.get("hil_seed_armed") is True and
                    seeded_state.get("credential_present") is False and
                    seeded_state.get("authorized") is False and
                    seeded_state.get("lease_mask") == 13,
                    f"armed seed escaped the staged boundary: {seeded_state}")
            action(device, "right")
            active = web_state(device)
            require(active.get("overlay_open") is True and
                    active.get("authorized") is True and
                    active.get("server_active") is True and
                    active.get("protocol_connected") is False and
                    int(active.get("generation", 0)) > 0 and
                    active.get("credential_present") is True and
                    active.get("hil_seed_armed") is False and
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
                    active.get("survey_worker_suspended") is True and
                    int(active.get("heap_free_before_worker_suspend", 0)) > 0 and
                    int(active.get("heap_free_after_worker_suspend", 0)) >
                    int(active.get("heap_free_before_worker_suspend", 0)) and
                    int(active.get("heap_free_before_begin", 0)) > 0 and
                    int(active.get("heap_largest_before_begin", 0)) > 0 and
                    int(active.get("heap_free_after_begin", 0)) > 0 and
                    active.get("maximum_clients") == 1 and
                    active.get("idle_timeout_us") == IDLE_TIMEOUT_US and
                    active.get("maximum_lifetime_us") == MAXIMUM_LIFETIME_US and
                    active.get("lease_mask") == 15,
                    f"explicit Web session is not bounded: {active}")

            http_exchange: dict[str, Any] = {
                "tested": False,
                "reason": "host_wifi_state_not_modified",
            }
            if http_exchange_requested:
                checkpoint(args.output, record, "host_wifi_snapshot")
                wifi_guard = MacWifiGuard(
                    args.wifi_interface, args.wifi_service)
                snapshot = wifi_guard.capture()
                host_wifi.update({
                    "snapshot_complete": True,
                    "prior_power_on": snapshot.power_on,
                    "prior_ssid_present": snapshot.ssid is not None,
                })
                record["host_wifi"] = host_wifi
                write_json(args.output / "run.json", record)
                checkpoint(args.output, record, "physical_http_exchange")
                try:
                    wifi_guard.connect(expected_ssid, expected_passphrase)
                    expected_passphrase = ""
                    index_status, index_type, index_body = http_get(
                        args.web_base_url.rstrip("/") + "/")
                    require(
                        index_status == 200 and index_type == "text/html" and
                        b"LESHY \xc2\xb7 LOCAL" in index_body and
                        b"/api/v1/companion" in index_body,
                        "local Web index did not match the embedded UI")

                    api_url = (args.web_base_url.rstrip("/") +
                               "/api/v1/companion")
                    connect_status, connect_type, web_connect = \
                        http_companion_request(api_url, protocol_request(
                            "connect", "web-connect", protocol=1,
                            scopes=WEB_SCOPES))
                    require(
                        connect_status == 200 and
                        connect_type == "application/json" and
                        web_connect.get("status") == "ready" and
                        web_connect.get("reason") == "none" and
                        web_connect.get("transport") == "local_web_json" and
                        web_connect.get("scopes") == WEB_SCOPES and
                        web_connect.get("capabilities") == WEB_CAPABILITIES,
                        f"local Web connection parity failed: {web_connect}")

                    http_request_count = 2  # GET / and POST connect.

                    def web_exchange(
                            request_value: dict[str, Any]) -> dict[str, Any]:
                        nonlocal http_request_count
                        status, content_type, response = \
                            http_companion_request(api_url, request_value)
                        http_request_count += 1
                        require(
                            status == 200 and
                            content_type == "application/json",
                            "local Web companion response was not exact JSON")
                        return response

                    def usb_exchange(
                            request_value: dict[str, Any]) -> dict[str, Any]:
                        return usb_companion_exchange(
                            device, json.dumps(
                                request_value,
                                separators=(",", ":")).encode("ascii"))

                    web_sessions, web_session_pages = \
                        collect_companion_pages(
                            web_exchange, "session.list", "web-sessions", {})
                    web_targets, web_target_pages = collect_companion_pages(
                        web_exchange, "target.list", "web-targets", {})
                    require(
                        len(web_sessions) == 2 and
                        len(web_targets) == targets.get("catalog_count"),
                        "local Web projections are incomplete")
                    baseline, current = web_sessions
                    compare_fields = {
                        "baseline_source_id": baseline["source_id"],
                        "baseline_generation": baseline["generation"],
                        "current_source_id": current["source_id"],
                        "current_generation": current["generation"],
                    }
                    web_compared, web_compare_pages = \
                        collect_companion_pages(
                            web_exchange, "target.compare", "web-compare",
                            compare_fields)
                    require(
                        len(web_compared) == targets.get("comparison_count"),
                        "local Web comparison projection is incomplete")

                    usb_connect = usb_exchange(protocol_request(
                        "connect", "usb-parity-connect", protocol=1,
                        scopes=WEB_SCOPES))
                    usb_sessions, usb_session_pages = \
                        collect_companion_pages(
                            usb_exchange, "session.list", "usb-sessions", {})
                    usb_targets, usb_target_pages = collect_companion_pages(
                        usb_exchange, "target.list", "usb-targets", {})
                    usb_compared, usb_compare_pages = \
                        collect_companion_pages(
                            usb_exchange, "target.compare", "usb-compare",
                            compare_fields)
                    require(
                        usb_connect.get("status") == "ready" and
                        usb_connect.get("transport") ==
                        "usb_serial_ndjson" and
                        usb_connect.get("scopes") == WEB_SCOPES and
                        usb_connect.get("capabilities") == WEB_CAPABILITIES,
                        f"USB parity connection failed: {usb_connect}")
                    require(
                        normalized_pages(web_session_pages) ==
                        normalized_pages(usb_session_pages),
                        "session.list differs between Web and native USB")
                    require(
                        normalized_pages(web_target_pages) ==
                        normalized_pages(usb_target_pages),
                        "target.list differs between Web and native USB")
                    require(
                        normalized_pages(web_compare_pages) ==
                        normalized_pages(usb_compare_pages),
                        "target.compare differs between Web and native USB")

                    checkpoint(args.output, record,
                               "physical_http_confirmed_mutation")
                    generation_before = int(
                        targets["target_state_generation"])
                    target_before = web_targets[0]
                    target_id = str(target_before["target_id"])
                    revision_before = int(target_before["revision"])
                    favorite_before = bool(target_before["favorite"])
                    first_preview = web_exchange(protocol_request(
                        "target.mutation.preview", "web-first-preview",
                        action="target.favorite.set", target_id=target_id,
                        expected_revision=revision_before,
                        favorite=not favorite_before))
                    mutation_id = first_preview.get("mutation_id")
                    require(
                        first_preview.get("status") == "ok" and
                        first_preview.get("state") == "previewed" and
                        isinstance(mutation_id, str) and
                        len(mutation_id) == 32 and
                        first_preview.get("target_revision") ==
                        revision_before + 1,
                        f"Web mutation preview failed: {first_preview}")
                    first_confirm = web_exchange(protocol_request(
                        "target.mutation.confirm", "web-first-confirm",
                        mutation_id=mutation_id))
                    require(
                        first_confirm.get("status") == "ok" and
                        first_confirm.get("state") == "saving",
                        f"Web mutation confirm failed: {first_confirm}")
                    first_replay = web_exchange(protocol_request(
                        "target.mutation.confirm", "web-first-replay",
                        mutation_id=mutation_id))
                    require(
                        first_replay.get("status") == "error" and
                        first_replay.get("reason") == "already_confirmed",
                        f"Web mutation confirmation replay succeeded: "
                        f"{first_replay}")
                    first_terminal, first_samples = wait_companion_mutation(
                        web_exchange, mutation_id, "web-first-status")
                    require(
                        first_terminal.get("status") == "ok" and
                        first_terminal.get("state") == "saved" and
                        first_terminal.get("target_revision") ==
                        revision_before + 1 and
                        first_terminal.get("state_generation") ==
                        generation_before + 1,
                        f"Web mutation did not save: {first_terminal}")
                    first_state = query(
                        device, b"targets.state",
                        "leshy.targets.product.v1", "state")
                    assert_atomic_mutation_state(
                        first_state, generation_before + 1)
                    first_items, _ = collect_companion_pages(
                        web_exchange, "target.list", "web-first-list", {})
                    target_after = target_from_items(first_items, target_id)
                    require(
                        target_after.get("revision") == revision_before + 1 and
                        target_after.get("favorite") is not favorite_before,
                        f"Web mutation value did not reopen: {target_after}")

                    restore_preview = web_exchange(protocol_request(
                        "target.mutation.preview", "web-restore-preview",
                        action="target.favorite.set", target_id=target_id,
                        expected_revision=revision_before + 1,
                        favorite=favorite_before))
                    restore_id = restore_preview.get("mutation_id")
                    require(
                        restore_preview.get("status") == "ok" and
                        restore_preview.get("state") == "previewed" and
                        isinstance(restore_id, str) and len(restore_id) == 32,
                        f"Web restore preview failed: {restore_preview}")
                    restore_confirm = web_exchange(protocol_request(
                        "target.mutation.confirm", "web-restore-confirm",
                        mutation_id=restore_id))
                    require(
                        restore_confirm.get("status") == "ok" and
                        restore_confirm.get("state") == "saving",
                        f"Web restore confirm failed: {restore_confirm}")
                    restore_terminal, restore_samples = \
                        wait_companion_mutation(
                            web_exchange, restore_id, "web-restore-status")
                    require(
                        restore_terminal.get("status") == "ok" and
                        restore_terminal.get("state") == "saved" and
                        restore_terminal.get("target_revision") ==
                        revision_before + 2 and
                        restore_terminal.get("state_generation") ==
                        generation_before + 2,
                        f"Web restore did not save: {restore_terminal}")
                    restored_state = query(
                        device, b"targets.state",
                        "leshy.targets.product.v1", "state")
                    assert_atomic_mutation_state(
                        restored_state, generation_before + 2)
                    restored_web_items, restored_web_pages = \
                        collect_companion_pages(
                            web_exchange, "target.list",
                            "web-restored-list", {})
                    restored_usb_items, restored_usb_pages = \
                        collect_companion_pages(
                            usb_exchange, "target.list",
                            "usb-restored-list", {})
                    target_restored = target_from_items(
                        restored_web_items, target_id)
                    require(
                        target_restored.get("revision") ==
                        revision_before + 2 and
                        target_restored.get("favorite") is favorite_before,
                        f"Web mutation did not restore value: "
                        f"{target_restored}")
                    require(
                        normalized_pages(restored_web_pages) ==
                        normalized_pages(restored_usb_pages) and
                        restored_web_items == restored_usb_items,
                        "restored Target projection differs between Web "
                        "and native USB")
                    http_exchange = {
                        "tested": True,
                        "reason": "none",
                        "index_status": index_status,
                        "index_content_type": index_type,
                        "index_bytes": len(index_body),
                        "api_status": connect_status,
                        "api_content_type": connect_type,
                        "transport": web_connect.get("transport"),
                        "scopes": web_connect.get("scopes"),
                        "capabilities": web_connect.get("capabilities"),
                        "requests_handled": http_request_count,
                        "session_projection": {
                            "items": len(web_sessions),
                            "pages": len(web_session_pages),
                            "usb_parity": True,
                        },
                        "target_projection": {
                            "items": len(web_targets),
                            "pages": len(web_target_pages),
                            "usb_parity": True,
                        },
                        "compare_projection": {
                            "items": len(web_compared),
                            "pages": len(web_compare_pages),
                            "usb_parity": True,
                        },
                        "confirmed_mutation": {
                            "target_id": target_id,
                            "favorite_before": favorite_before,
                            "favorite_restored": favorite_before,
                            "revision_before": revision_before,
                            "revision_after": revision_before + 2,
                            "generation_before": generation_before,
                            "generation_after": generation_before + 2,
                            "first_status_samples": len(first_samples),
                            "restore_status_samples": len(restore_samples),
                            "confirmation_replay_rejected": True,
                            "atomic_commits": 2,
                            "write_calls_per_commit": 3,
                            "exact_cid": EXPECTED_CID,
                            "usb_projection_parity_after_restore": True,
                        },
                        "expected_ssid_sha256": hashlib.sha256(
                            expected_ssid.encode("ascii")).hexdigest(),
                        "credential_exposed": False,
                    }
                finally:
                    expected_passphrase = ""
                    host_wifi["restore_attempted"] = True
                    try:
                        wifi_guard.restore()
                    finally:
                        host_wifi["restored"] = wifi_guard.restored
                        record["host_wifi"] = host_wifi
                        write_json(args.output / "run.json", record)
                require(host_wifi["restored"] is True,
                        "host Wi-Fi restoration was not proven")
                record["http_exchange_tested"] = True
                record["http_exchange_reason"] = "none"
                record["http_exchange"] = http_exchange
            time.sleep(1.0)
            stable = web_state(device)
            require(stable.get("authorized") is True and
                    stable.get("server_active") is True and
                    stable.get("generation") == active.get("generation") and
                    stable.get("requests_handled") ==
                    (http_exchange.get("requests_handled", 0)
                     if http_exchange_requested else 0) and
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
                    stopped.get("hil_seed_armed") is False and
                    stopped.get("stop_reason") == "user" and
                    stopped.get("cleanup_complete") is True and
                    stopped.get("targets_suspended") is False and
                    stopped.get("survey_worker_suspended") is True and
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
                    released.get("hil_seed_armed") is False and
                    released.get("cleanup_complete") is True and
                    released.get("survey_worker_suspended") is False and
                    released.get("lease_mask") == 0,
                    f"Web resources survived Targets teardown: {released}")
            hil_end: dict[str, Any] = {}
            if http_exchange_requested:
                hil_end = query(
                    device, f"hil.end {hil_session_id}".encode("ascii"),
                    "leshy.hil.session.v1", "ended")
                require(
                    hil_end.get("status") == "ended" and
                    hil_end.get("session_id") == hil_session_id and
                    hil_end.get("active") is False,
                    f"HIL session was not closed: {hil_end}")
                hil_session_started = False
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
            "host_wifi": host_wifi,
            "http_exchange": http_exchange,
            "storage_write_commands": (2 if http_exchange_requested else 0),
            "expected_atomic_commits": (
                2 if http_exchange_requested else 0),
            "expected_write_calls_per_commit": (
                3 if http_exchange_requested else 0),
            "raw_radio_tx_commands": 0,
        })
        if http_exchange_requested:
            record["hil_session"] = {
                "begin": hil_begin,
                "invalid_seed": invalid_seed,
                "seed": seed_armed,
                "seed_replay": seed_replay,
                "seeded_state": seeded_state,
                "end": hil_end,
                "seed_recorded": False,
                "credential_recorded": False,
            }
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
        if (wifi_guard is not None and wifi_guard.snapshot is not None and
                not wifi_guard.restored):
            host_wifi["restore_attempted"] = True
            try:
                wifi_guard.restore()
            except Exception as restore_error:
                host_wifi["restore_error"] = type(restore_error).__name__
            host_wifi["restored"] = wifi_guard.restored
            record["host_wifi"] = host_wifi
        if device is not None:
            if hil_session_started:
                try:
                    query(
                        device,
                        f"hil.end {hil_session_id}".encode("ascii"),
                        "leshy.hil.session.v1", "ended", timeout=2.0)
                    hil_session_started = False
                except Exception:
                    pass
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
