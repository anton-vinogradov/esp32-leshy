#!/usr/bin/env python3
"""One-flash delta HIL for reversible on-device Target merge/split."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from check_targets_stack_elf_contract import stack_frames
from esp_app_identity import app_elf_sha256
from partition_safety import (
    PARTITION_ARTIFACT_SIZE,
    PARTITION_MAGIC,
    PARTITION_MD5_MAGIC,
    validated_partition_layout,
)
from run_1x_littlefs_parity_hil import (
    OTA1_OFFSET,
    OTA1_SIZE,
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    read_flash_with_retry,
    restore_flash,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    capture,
    query,
    reset_capture,
)


SCHEMA = "leshy.targets_merge_split_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
WATCHDOG_RESET_REASONS = {4, 5, 6, 7}
MUTATION_ACTION_ACK_TIMEOUT = 5.0


def require(record: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: record.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def valid_hex(value: Any, width: int) -> bool:
    return (isinstance(value, str) and len(value) == width and
            all(character in "0123456789ABCDEF" for character in value))


def require_non_watchdog_boot(state: dict[str, Any], label: str) -> None:
    reason = state.get("reset_reason_code")
    if not isinstance(reason, int) or isinstance(reason, bool):
        raise RuntimeError(f"{label}: missing reset reason: {state}")
    if reason in WATCHDOG_RESET_REASONS:
        raise RuntimeError(f"{label}: watchdog/panic reset: {state}")


def require_bounded_target_load(state: dict[str, Any], label: str) -> None:
    elapsed = state.get("load_elapsed_us")
    feeds = state.get("load_watchdog_feeds")
    maximum_phase = state.get("load_maximum_phase_us")
    if (not isinstance(elapsed, int) or isinstance(elapsed, bool) or
            elapsed <= 0 or
            not isinstance(feeds, int) or isinstance(feeds, bool) or
            feeds < 8 or
            not isinstance(maximum_phase, int) or
            isinstance(maximum_phase, bool) or maximum_phase <= 0 or
            maximum_phase >= 5_000_000 or maximum_phase > elapsed):
        raise RuntimeError(f"{label}: invalid load watchdog proof: {state}")


def read_only_query(
    device: Any,
    command: bytes,
    schema: str,
    kind: str,
    timeout: float = 5.0,
    maximum_attempts: int = 3,
) -> dict[str, Any]:
    """Retry a diagnostic query within a fixed bound; never replay actions."""
    if maximum_attempts < 1:
        raise ValueError("maximum_attempts must be positive")
    errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = query(
                device, command, schema, kind, timeout=timeout)
            record["host_transport_attempts"] = attempt
            record["host_transport_transient_retries"] = attempt - 1
            record["host_transport_transient_errors"] = errors
            return record
        except TimeoutError as error:
            if attempt == maximum_attempts:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable state-query retry state")


def navigation_action(
    device: Any, name: str, timeout: float = 15.0,
) -> dict[str, Any]:
    """Send a reversible UI action once and recover only its lost reply.

    A timed-out acknowledgement is never grounds to replay the key.  The
    current UI state is queried read-only instead; the caller's semantic
    checkpoint decides whether the original key took effect.  Every
    irreversible merge/split confirmation continues to use
    trigger_mutation_once(), which has its own stricter no-replay contract.
    """
    try:
        state = action(device, name, timeout=timeout)
        state["host_navigation_ack_received"] = True
        state["host_navigation_action_writes"] = 1
        state["host_navigation_action_replays"] = 0
        return state
    except TimeoutError as error:
        state = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state",
            timeout=5.0, maximum_attempts=3)
        state["host_navigation_ack_received"] = False
        state["host_navigation_ack_error"] = str(error)
        state["host_navigation_action_writes"] = 1
        state["host_navigation_action_replays"] = 0
        return state


def normalize_home(device: Any) -> dict[str, Any]:
    state = read_only_query(
        device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(8):
        if state.get("page") == "home":
            break
        state = navigation_action(device, "back")
    if state.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {state}")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            break
        state = navigation_action(device, "up")
    if int(state.get("selection", -1)) != 0:
        raise RuntimeError(f"cannot normalize Home selection: {state}")
    return state


def open_targets(
    device: Any, minimum_target_count: int = 2,
) -> dict[str, Any]:
    if minimum_target_count < 1:
        raise ValueError("minimum_target_count must be positive")
    home = normalize_home(device)
    for _ in range(5):
        home = navigation_action(device, "down")
    require(home, "select Targets", page="home", selection=5,
            selected_id="targets")
    # Loading is deliberately segmented by the unchanged five-second hardware
    # watchdog.  The aggregate of several bounded SD/decode phases may exceed
    # the generic UI acknowledgement timeout, while each individual phase is
    # still proven below the watchdog threshold by targets.state telemetry.
    opened = navigation_action(device, "right", timeout=40.0)
    require(opened, "open Targets", page="targets",
            runtime_owner="targets", lease_mask=13)
    listed = read_only_query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
    require(listed, "Targets list", status="ready", page_open=True,
            workspace_allocated=True, view="list", compare_available=True,
            read_only=False, write_enabled=False,
            blocked_write_attempts=0, filesystem_mount_error=0,
            cleanup_complete=True, lease_mask=13)
    require_bounded_target_load(listed, "Targets list")
    if int(listed.get("target_count", 0)) < minimum_target_count:
        raise RuntimeError(
            f"fewer than {minimum_target_count} Targets are available: "
            f"{listed}")
    return listed


def find_target(
    device: Any,
    predicate: Callable[[dict[str, Any]], bool],
    minimum_target_count: int = 2,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    listed = open_targets(device, minimum_target_count)
    count = int(listed["target_count"])
    searched: list[dict[str, Any]] = []
    navigation_action(
        device, "down")  # comparison is row 0; the first Target is row 1
    for index in range(count):
        navigation_action(device, "right")
        detail = read_only_query(device, b"targets.state",
                                 "leshy.targets.product.v1", "state")
        require(detail, f"Target detail {index}", status="ready",
                view="detail", selected_target_present=True, lease_mask=13)
        target_id = detail.get("selected_target_id")
        graph = detail.get("selected_graph_fingerprint")
        if not valid_hex(target_id, 32) or not valid_hex(graph, 16):
            raise RuntimeError(f"invalid Target identity/graph: {detail}")
        searched.append({
            "target_id": target_id,
            "graph_fingerprint": graph,
            "identity_count": int(detail["selected_identity_count"]),
            "evidence_count": int(detail["selected_evidence_count"]),
            "merge_candidate_count": int(detail["merge_candidate_count"]),
            "active_merge_available": bool(
                detail["active_merge_available"]),
        })
        if predicate(detail):
            return listed, detail, searched
        navigation_action(device, "left")
        if index + 1 < count:
            navigation_action(device, "down")
    normalize_home(device)
    raise RuntimeError(f"requested Target not found: {searched}")


def find_target_id(device: Any, target_id: str) -> tuple[
        dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    return find_target(
        device, lambda state: state.get("selected_target_id") == target_id,
        minimum_target_count=1)


def close_targets(device: Any) -> dict[str, Any]:
    home = normalize_home(device)
    require(home, "Targets cleanup", page="home",
            runtime_owner="none", lease_mask=0)
    return read_only_query(device, b"targets.state",
                           "leshy.targets.product.v1", "state")


def capture_mutation_loss_diagnostics(
    device: Any, last: dict[str, Any],
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"targets": last}
    queries = (
        ("boot", b"metrics", "leshy.boot.v1", "ready"),
        ("safety", b"safety.state", "leshy.safety.v1", "state"),
        ("fixture", b"targets.merge-split-fixture state",
         "leshy.targets_merge_split_fixture.v1", "state"),
        ("ui", b"ui.state", "leshy.ui.v1", "state"),
    )
    for label, command, schema, kind in queries:
        try:
            diagnostics[label] = read_only_query(
                device, command, schema, kind, timeout=5.0)
        except (RuntimeError, TimeoutError) as error:
            diagnostics[label] = {
                "error": f"{type(error).__name__}: {error}",
            }
    return diagnostics


def wait_mutation(
    device: Any, timeout: float = 40.0,
    failure_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = read_only_query(device, b"targets.state",
                               "leshy.targets.product.v1", "state")
        if last.get("mutation_state") in ("saved", "failed"):
            return last
        # During the asynchronous hand-off, workspace_allocated=false is
        # expected only while mutation_state=saving. Returning to the boot
        # defaults (idle/not_loaded) means the worker context was lost. Capture
        # reset reason plus retained RTC stage before cleanup restores OTA1.
        if (last.get("status") == "not_loaded" and
                last.get("workspace_allocated") is False and
                last.get("mutation_state") == "idle"):
            diagnostics = capture_mutation_loss_diagnostics(device, last)
            if failure_diagnostics is not None:
                failure_diagnostics.update(diagnostics)
            fixture = diagnostics.get("fixture", {})
            boot = diagnostics.get("boot", {})
            raise RuntimeError(
                "Targets mutation worker context lost: "
                f"reset_reason={boot.get('reset_reason_code')}, "
                f"stage={fixture.get('mutation_stage')}, "
                f"stage_valid={fixture.get('mutation_stage_valid')}")
        time.sleep(0.05)
    raise TimeoutError(f"Target mutation did not finish: {last}")


def trigger_mutation_once(
    device: Any,
    timeout: float = MUTATION_ACTION_ACK_TIMEOUT,
) -> dict[str, Any]:
    """Send one irreversible UI action without treating its UI ACK as truth.

    Internal-flash work may temporarily delay the generic UI response.  The
    action must never be replayed after that ambiguous transport boundary;
    callers determine the outcome only through read-only targets.state polls.
    """
    from capture_1x_ui import read_json

    device.write(b"ui.key right\n")
    device.flush()
    try:
        state = read_json(
            device, "leshy.ui.v1", "state", timeout=timeout)
    except TimeoutError as error:
        return {
            "received": False,
            "error": str(error),
            "timeout_seconds": timeout,
            "action_writes": 1,
            "action_replays": 0,
        }
    return {
        "received": True,
        "state": state,
        "timeout_seconds": timeout,
        "action_writes": 1,
        "action_replays": 0,
    }


def require_atomic_save(state: dict[str, Any], label: str) -> None:
    attempts = int(state.get("mutation_identity_attempts", 0))
    retries = int(state.get("mutation_identity_transient_retries", -1))
    if attempts != 0 or retries != 0:
        raise RuntimeError(
            f"{label}: disposable mutation touched SD identity: {state}")
    if (int(state.get("mutation_action_us", 0)) <= 0 or
            int(state.get("mutation_action_us", 0)) > 10000 or
            int(state.get("mutation_elapsed_us", 0)) <= 0 or
            int(state.get("mutation_elapsed_us", 0)) > 8000000 or
            int(state.get("mutation_bytes_written", 0)) <= 0 or
            int(state.get("mutation_write_calls", 0)) < 3 or
            int(state.get("mutation_file_syncs", 0)) < 3 or
            int(state.get("mutation_directory_syncs", 0)) < 3):
        raise RuntimeError(f"{label}: incomplete atomic save: {state}")


def enter_merge_action(device: Any, target_id: str) -> dict[str, Any]:
    navigation_action(device, "right")
    for _ in range(6):
        navigation_action(device, "down")
    state = read_only_query(device, b"targets.state",
                            "leshy.targets.product.v1", "state")
    require(state, "Target merge/split action", status="ready",
            view="actions", selected_target_id=target_id,
            action_selection=6, lease_mask=13)
    return state


def cold_reopen(
    port: str,
    output: Path,
    name: str,
    expected_version: str,
    app_identity: str,
    run_id: str,
) -> tuple[PassiveSerial, dict[str, Any]]:
    ready, _, timing = reset_capture(port, output, name, 20.0)
    require(ready, f"{name} candidate", version=expected_version,
            app_elf_sha256=app_identity)
    require_non_watchdog_boot(ready, f"{name} candidate")
    device = PassiveSerial(port, 115200, timeout=0.25)
    synchronize_console(device, 20.0)
    recovery = read_only_query(
        device, b"storage.product.boot-recovery",
        "leshy.storage.product_boot_recovery.v1", "state")
    require(recovery, f"{name} product SD bypass",
            status="fixture_bypassed", cleanup_complete=True,
            physical_write_calls=0)
    fixture = read_only_query(
        device, b"targets.merge-split-fixture state",
        "leshy.targets_merge_split_fixture.v1", "state")
    require(fixture, f"{name} fixture continuity", armed=True,
            continuity_valid=True, runtime_active=False, run_id=run_id,
            storage="disposable_ota1", ota1_restore_required=True,
            sd_accessed=False, product_target_state_touched=False,
            radio_touched=False, rf_tx_attempts=0)
    return device, {
        "timing": timing, "recovery": recovery, "fixture": fixture}


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
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help=("skip flashing and prove the already-installed candidate by "
              "version and app ELF identity"),
    )
    parser.add_argument(
        "--predecessor-failed-run", type=Path,
        help=("failed run.json (or its directory) that installed the exact "
              "candidate reused by --reuse-exact-flash"),
    )
    parser.add_argument(
        "--clear-proven-preexisting-safety-latch", action="store_true",
        help=("explicitly clear only an exact runtime-watchdog latch proven "
              "by --predecessor-failed-run before any flash backup/mutation"),
    )
    args = parser.parse_args()
    for path in (args.firmware, args.partitions, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    try:
        temporary_partition_layout = validated_partition_layout(
            args.partitions, args.firmware.stat().st_size)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        parser.error(f"unsafe candidate partition table: {error}")
    predecessor_path: Path | None = None
    predecessor_record: dict[str, Any] = {}
    if args.reuse_exact_flash:
        if args.predecessor_failed_run is None:
            parser.error(
                "--reuse-exact-flash requires --predecessor-failed-run")
        predecessor_path = args.predecessor_failed_run
        if predecessor_path.is_dir():
            predecessor_path = predecessor_path / "run.json"
        if not predecessor_path.is_file():
            parser.error("predecessor failed run.json is missing")
        try:
            loaded = json.loads(predecessor_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            parser.error(f"invalid predecessor failed run: {error}")
        if not isinstance(loaded, dict):
            parser.error("predecessor failed run must be a JSON object")
        predecessor_record = loaded
        predecessor_firmware = predecessor_record.get("candidate", {}).get(
            "firmware_sha256")
        if (predecessor_record.get("status") != "failed" or
                predecessor_firmware != sha256_file(args.firmware) or
                predecessor_record.get("usb", {}).get("opened_ports") !=
                [args.port] or
                predecessor_record.get("usb", {}).get(
                    "cardputer_ports_opened") != 0):
            parser.error(
                "predecessor must be a failed exact-candidate run on the "
                "same sole DUT port")
    elif args.predecessor_failed_run is not None:
        parser.error(
            "--predecessor-failed-run is only valid with --reuse-exact-flash")
    if args.clear_proven_preexisting_safety_latch:
        predecessor_error = predecessor_record.get("error", "")
        if (not args.reuse_exact_flash or
                not isinstance(predecessor_error, str) or
                "safety_latched" not in predecessor_error):
            parser.error(
                "safety-latch clear requires an exact failed predecessor "
                "whose terminal error proves safety_latched")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")
    try:
        checked_stack_frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError,
            ValueError) as error:
        parser.error(f"unsafe or unverifiable Targets stack: {error}")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    candidate_partitions = args.output / "candidate-partitions.bin"
    shutil.copyfile(args.firmware, candidate)
    candidate_partitions.write_bytes(
        args.partitions.read_bytes().ljust(PARTITION_TABLE_SIZE, b"\xff"))
    predecessor: dict[str, Any] = {}
    if predecessor_path is not None:
        retained_predecessor = args.output / "predecessor-failed-run.json"
        shutil.copyfile(predecessor_path, retained_predecessor)
        predecessor = {
            "status": predecessor_record["status"],
            "error": predecessor_record.get("error"),
            "source_commit": predecessor_record.get("source_commit"),
            "firmware_sha256": predecessor_record["candidate"][
                "firmware_sha256"],
            "run_sha256": sha256_file(retained_predecessor),
            "retained_as": retained_predecessor.name,
        }
    app_identity = app_elf_sha256(candidate)
    run_id = f"targets-merge-{secrets.token_hex(6)}"
    ota1_backup = args.output / "ota1-private-backup.bin"
    ota1_backup_second = args.output / "ota1-private-backup-second.bin"
    ota1_restore_readback = args.output / "ota1-private-restore-readback.bin"
    partition_before = args.output / "partition-table-before.bin"
    partition_before_second = (
        args.output / "partition-table-before-second.bin")
    partition_install_readback = (
        args.output / "partition-table-install-readback.bin")
    partition_restore_readback = (
        args.output / "partition-table-restore-readback.bin")
    partition_after = args.output / "partition-table-after.bin"
    ota1_before_sha = ""
    ota1_second_sha = ""
    ota1_after_sha = ""
    partition_before_sha = ""
    partition_second_sha = ""
    partition_candidate_sha = sha256_file(candidate_partitions)
    partition_installed_sha = ""
    partition_after_sha = ""
    ota1_backup_attempts = 0
    ota1_second_attempts = 0
    partition_before_attempts = 0
    partition_second_attempts = 0
    partition_install_attempts = 0
    partition_restore_attempts = 0
    partition_after_attempts = 0
    restore_attempts = 0
    backup_ready = False
    partition_mutation_attempted = False
    partition_installed = False
    partition_restored = False
    restore_attempted = False
    restore_verified = False
    private_backup_deleted = False
    workflow_error = ""
    cleanup: dict[str, Any] = {"attempted": False}
    states: dict[str, Any] = {}
    screens: dict[str, Any] = {}
    resets: dict[str, Any] = {}
    initial_timing: dict[str, Any] = {}
    preflight_safety: dict[str, Any] = {
        "clear_authorized": args.clear_proven_preexisting_safety_latch,
        "clear_performed": False,
    }
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "run_id": run_id,
        "usb": {
            "opened_ports": [args.port],
            "cardputer_ports_opened": 0,
            "port_discovery_calls": 0,
        },
        "flash_count": 0 if args.reuse_exact_flash else 1,
        "candidate_installation": (
            "reused_exact_flash" if args.reuse_exact_flash else "flashed"),
        "predecessor_failed_run": predecessor,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "partitions_sha256": partition_candidate_sha,
            "temporary_partition_layout": temporary_partition_layout,
            "app_elf_sha256": app_identity,
            "checked_stack_frames": checked_stack_frames,
        },
        "disposable_target": {
            "kind": "inactive_ota1_littlefs",
            "offset": OTA1_OFFSET,
            "size": OTA1_SIZE,
            "two_read_backup_verified": False,
            "restore_verified": False,
        },
    }
    write_json(args.output / "run.json", record)

    device: PassiveSerial | None = None
    try:
        # This runner never enumerates serial ports. The caller-selected DUT is
        # the only path passed to esptool/pyserial; a parallel Cardputer remains
        # unopened, unprobed and unflashed.
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(1.0)
        initial_ready, _, initial_timing = reset_capture(
            args.port, args.output, "targets-merge-split-initial-boot", 20.0)
        require(initial_ready, "controlled initial candidate",
                version=args.expected_version, app_elf_sha256=app_identity)
        require_non_watchdog_boot(
            initial_ready, "controlled initial candidate")
        states["controlled_initial_boot"] = initial_ready
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics = read_only_query(
            device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics, "candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        require_non_watchdog_boot(metrics, "candidate")
        states["boot_metrics"] = metrics
        safety_before = read_only_query(
            device, b"safety.state", "leshy.safety.v1", "state")
        preflight_safety["before"] = safety_before
        if safety_before.get("latched") is True:
            if not args.clear_proven_preexisting_safety_latch:
                raise RuntimeError(
                    f"preexisting safety latch requires explicit proof: "
                    f"{safety_before}")
            require(safety_before, "proven preexisting safety latch",
                    state="latched", reason="runtime_watchdog", armed=True,
                    latched=True, clear_pending=False, runtime_owner="none",
                    lease_mask=0, automatic_clear=False,
                    buzzer_inactive=True, nrf_ce_inactive=True)
            clear_confirmed = query(
                device, b"safety.clear confirm",
                "leshy.safety.v1", "clear_confirmed", timeout=5.0)
            require(clear_confirmed, "explicit safety clear",
                    restart_required=True)
            preflight_safety["clear_confirmation"] = clear_confirmed
            preflight_safety["clear_performed"] = True
            device.close()
            device = None
            cleared_ready, _, cleared_timing = reset_capture(
                args.port, args.output,
                "targets-merge-split-safety-cleared-boot", 20.0)
            require(cleared_ready, "safety-cleared candidate",
                    version=args.expected_version,
                    app_elf_sha256=app_identity)
            require_non_watchdog_boot(
                cleared_ready, "safety-cleared candidate")
            preflight_safety["cleared_boot"] = cleared_ready
            preflight_safety["cleared_timing"] = cleared_timing
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            synchronize_console(device, 20.0)
            safety_after = read_only_query(
                device, b"safety.state", "leshy.safety.v1", "state")
            require(safety_after, "safety clear result", state="armed",
                    reason="none", armed=True, latched=False,
                    clear_pending=False, runtime_owner="none", lease_mask=0)
            preflight_safety["after"] = safety_after
        else:
            require(safety_before, "preflight safety", state="armed",
                    reason="none", armed=True, latched=False,
                    clear_pending=False, runtime_owner="none", lease_mask=0)
            preflight_safety["after"] = safety_before
        recovery = read_only_query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery, "exact media", status="admitted",
                expected_fingerprint=EXPECTED_CID,
                observed_fingerprint=EXPECTED_CID,
                fingerprint_matched=True, mounted_read_only=True,
                read_only_guaranteed=True, blocked_write_attempts=0,
                cleanup_complete=True, physical_write_calls=0)
        states["boot_recovery"] = recovery

        # Preserve both mutable regions twice before installing the temporary
        # reviewed table. No serial-port discovery is performed: every esptool
        # invocation receives the caller-selected DIV path verbatim, leaving a
        # parallel Cardputer unopened.
        device.close()
        device = None
        ota1_before_sha, ota1_backup_attempts = read_flash_with_retry(
            args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE, ota1_backup)
        ota1_second_sha, ota1_second_attempts = read_flash_with_retry(
            args.port, args.flash_baud, OTA1_OFFSET, OTA1_SIZE,
            ota1_backup_second)
        partition_before_sha, partition_before_attempts = (
            read_flash_with_retry(
                args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                PARTITION_TABLE_SIZE, partition_before))
        partition_second_sha, partition_second_attempts = (
            read_flash_with_retry(
                args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                PARTITION_TABLE_SIZE, partition_before_second))
        backup_ready = (
            ota1_before_sha == ota1_second_sha and
            partition_before_sha == partition_second_sha)
        if not backup_ready:
            raise RuntimeError(
                "two independent OTA1 or partition-table backup reads differ")
        ota1_backup_second.unlink(missing_ok=True)
        partition_before_second.unlink(missing_ok=True)

        # The board may still carry the factory app0/font/spiffs table. Install
        # the build's exact reviewed app0/app1 table only after both backups,
        # verify the write immediately, and always restore the original table
        # in finally after restoring the whole disposable OTA1 window.
        partition_mutation_attempted = True
        _, partition_installed_sha, partition_install_attempts = restore_flash(
            args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
            candidate_partitions, partition_install_readback)
        partition_installed = partition_installed_sha == partition_candidate_sha
        if not partition_installed:
            raise RuntimeError("temporary partition-table install mismatch")
        partition_install_readback.unlink(missing_ok=True)

        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        temporary_metrics = read_only_query(
            device, b"metrics", "leshy.boot.v1", "ready")
        require(temporary_metrics, "temporary-layout candidate",
                version=args.expected_version, app_elf_sha256=app_identity)
        require_non_watchdog_boot(
            temporary_metrics, "temporary-layout candidate")
        states["temporary_layout_boot_metrics"] = temporary_metrics
        recovery_rechecked = read_only_query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery_rechecked, "pre-fixture exact media",
                status="admitted", expected_fingerprint=EXPECTED_CID,
                observed_fingerprint=EXPECTED_CID,
                fingerprint_matched=True, mounted_read_only=True,
                read_only_guaranteed=True, blocked_write_attempts=0,
                cleanup_complete=True, physical_write_calls=0)
        states["boot_recovery_rechecked"] = recovery_rechecked
        prepare_command = (
            "targets.merge-split-fixture prepare disposable-ota1 "
            f"{ota1_before_sha} {run_id} confirm").encode("ascii")
        prepared = query(
            device, prepare_command,
            "leshy.targets_merge_split_fixture.v1", "prepared",
            timeout=120.0)
        require(prepared, "fixture prepare", status="ready", run_id=run_id,
                expected_fingerprint=ota1_before_sha,
                observed_fingerprint=ota1_before_sha,
                fingerprint_matched=True, target="ota1",
                target_address=OTA1_OFFSET, target_size=OTA1_SIZE,
                target_inactive=True, format_performed=True,
                scratch_preexisting=False, scratch_created=True,
                permit_status="permitted", byte_limit=256 * 1024,
                continuity_armed=True, cleanup_complete=True,
                owned_after=0, ota1_restore_required=True,
                product_partition_touched=False, sd_accessed=False,
                product_target_state_touched=False, nvs_touched=False,
                radio_touched=False, rf_tx_attempts=0)
        states["fixture_prepared"] = prepared
        fixture_armed = read_only_query(
            device, b"targets.merge-split-fixture state",
            "leshy.targets_merge_split_fixture.v1", "state")
        require(fixture_armed, "fixture armed", armed=True,
                continuity_valid=True, runtime_active=False, run_id=run_id,
                storage="disposable_ota1", ota1_restore_required=True,
                sd_accessed=False, product_target_state_touched=False,
                radio_touched=False, rf_tx_attempts=0)
        states["fixture_armed"] = fixture_armed

        listed_before, destination_before, searched = find_target(
            device,
            lambda state: int(state.get("merge_candidate_count", 0)) > 0 and
            not bool(state.get("active_merge_available")),
        )
        states["destination_search"] = searched
        states["destination_before"] = destination_before
        require(destination_before, "fixture Targets", fixture_mode=True,
                fixture_run_id=run_id,
                fixture_storage="disposable_ota1",
                fixture_sd_accessed=False,
                fixture_product_target_state_touched=False,
                fixture_ota1_restore_required=True,
                catalog_count=2, merge_candidate_count=1,
                target_state_generation=0, target_state_head="none")
        destination_id = destination_before["selected_target_id"]
        destination_graph = destination_before["selected_graph_fingerprint"]
        destination_identities = int(
            destination_before["selected_identity_count"])
        destination_evidence = int(
            destination_before["selected_evidence_count"])
        generation_before = int(
            destination_before["target_state_generation"])
        catalog_before = int(destination_before["catalog_count"])
        history_before = int(destination_before["merge_history_count"])
        screens["destination_before"] = capture(
            device, frames, "targets-merge-destination-before")

        enter_merge_action(device, destination_id)
        navigation_action(device, "right")
        merge_list = read_only_query(
            device, b"targets.state",
            "leshy.targets.product.v1", "state")
        require(merge_list, "merge source list", status="ready",
                view="merge_list", selected_target_id=destination_id,
                merge_selection=0, lease_mask=13)
        source_id = merge_list.get("merge_candidate_target_id")
        source_graph = merge_list.get("merge_candidate_graph_fingerprint")
        if not valid_hex(source_id, 32) or not valid_hex(source_graph, 16):
            raise RuntimeError(f"invalid merge source state: {merge_list}")
        source_identities = int(merge_list["merge_candidate_identity_count"])
        source_evidence = int(merge_list["merge_candidate_evidence_count"])
        states["merge_list"] = merge_list
        screens["merge_list"] = capture(
            device, frames, "targets-merge-source-list")
        navigation_action(device, "right")
        merge_confirm = read_only_query(
            device, b"targets.state",
            "leshy.targets.product.v1", "state")
        require(merge_confirm, "merge explicit confirmation", status="ready",
                view="merge_confirm", selected_target_id=destination_id,
                merge_candidate_target_id=source_id, write_enabled=True,
                lease_mask=13)
        states["merge_confirm"] = merge_confirm
        screens["merge_confirm"] = capture(
            device, frames, "targets-merge-confirm")
        states["merge_action_ack"] = trigger_mutation_once(device)
        merge_failure_diagnostics: dict[str, Any] = {}
        states["merge_failure_diagnostics"] = merge_failure_diagnostics
        merged = wait_mutation(
            device, failure_diagnostics=merge_failure_diagnostics)
        if not merge_failure_diagnostics:
            states.pop("merge_failure_diagnostics")
        states["merged"] = merged
        require(merged, "merged state", status="ready", view="actions",
                selected_target_id=destination_id, action_selection=6,
                mutation_state="saved", mutation_status="saved",
                mutation_merge=True, mutation_merge_kind="merge",
                mutation_merge_status="merged", mutation_persisted=True,
                mutation_expected_cid="", mutation_observed_cid="",
                fixture_mode=True, fixture_run_id=run_id,
                fixture_storage="disposable_ota1",
                fixture_sd_accessed=False,
                fixture_product_target_state_touched=False,
                active_merge_available=True,
                catalog_count=catalog_before - 1,
                merge_history_count=history_before + 1,
                selected_identity_count=(destination_identities +
                                         source_identities),
                selected_evidence_count=(destination_evidence +
                                         source_evidence),
                cleanup_complete=True, lease_mask=13)
        merge_operation_id = merged.get("mutation_merge_operation_id")
        if (not valid_hex(merge_operation_id, 32) or
                merged.get("active_merge_operation_id") !=
                merge_operation_id or
                merged.get("mutation_merge_source_id") != source_id):
            raise RuntimeError(f"merge operation identity mismatch: {merged}")
        generation_merged = int(merged["target_state_generation"])
        if (generation_merged != generation_before + 1 or
                int(merged["mutation_generation"]) != generation_merged):
            raise RuntimeError(f"merge generation mismatch: {merged}")
        require_atomic_save(merged, "merge")
        screens["merged"] = capture(
            device, frames, "targets-merge-saved")
        released_after_merge = close_targets(device)
        require(released_after_merge, "release after merge",
                status="not_loaded", workspace_allocated=False,
                page_open=False, view="none", cleanup_complete=True,
                lease_mask=0)
        device.close()
        device = None

        device, resets["merged"] = cold_reopen(
            args.port, args.output, "targets-merge-cold-reopen",
            args.expected_version, app_identity, run_id)
        _, merged_reopened, searched_merged = find_target_id(
            device, destination_id)
        states["merged_reopen_search"] = searched_merged
        states["merged_reopened"] = merged_reopened
        require(merged_reopened, "cold merged Target", status="ready",
                view="detail", selected_target_id=destination_id,
                target_state_generation=generation_merged,
                active_merge_available=True,
                active_merge_operation_id=merge_operation_id,
                catalog_count=catalog_before - 1,
                merge_history_count=history_before + 1,
                selected_identity_count=(destination_identities +
                                         source_identities),
                selected_evidence_count=(destination_evidence +
                                         source_evidence),
                cleanup_complete=True, lease_mask=13)
        screens["merged_reopened"] = capture(
            device, frames, "targets-merge-cold-reopened")

        enter_merge_action(device, destination_id)
        navigation_action(device, "right")
        split_confirm = read_only_query(
            device, b"targets.state",
            "leshy.targets.product.v1", "state")
        require(split_confirm, "split explicit confirmation", status="ready",
                view="split_confirm", selected_target_id=destination_id,
                active_merge_available=True,
                active_merge_operation_id=merge_operation_id,
                write_enabled=True, lease_mask=13)
        states["split_confirm"] = split_confirm
        screens["split_confirm"] = capture(
            device, frames, "targets-split-confirm")
        states["split_action_ack"] = trigger_mutation_once(device)
        split_failure_diagnostics: dict[str, Any] = {}
        states["split_failure_diagnostics"] = split_failure_diagnostics
        split = wait_mutation(
            device, failure_diagnostics=split_failure_diagnostics)
        if not split_failure_diagnostics:
            states.pop("split_failure_diagnostics")
        states["split"] = split
        require(split, "split state", status="ready", view="actions",
                selected_target_id=destination_id, action_selection=6,
                mutation_state="saved", mutation_status="saved",
                mutation_merge=True, mutation_merge_kind="split",
                mutation_merge_status="split", mutation_persisted=True,
                mutation_merge_operation_id=merge_operation_id,
                mutation_merge_source_id=source_id,
                mutation_expected_cid="", mutation_observed_cid="",
                fixture_mode=True, fixture_run_id=run_id,
                fixture_storage="disposable_ota1",
                fixture_sd_accessed=False,
                fixture_product_target_state_touched=False,
                active_merge_available=False,
                catalog_count=catalog_before,
                merge_history_count=history_before + 1,
                selected_identity_count=destination_identities,
                selected_evidence_count=destination_evidence,
                selected_graph_fingerprint=destination_graph,
                cleanup_complete=True, lease_mask=13)
        generation_split = int(split["target_state_generation"])
        if (generation_split != generation_merged + 1 or
                int(split["mutation_generation"]) != generation_split):
            raise RuntimeError(f"split generation mismatch: {split}")
        require_atomic_save(split, "split")
        screens["split"] = capture(
            device, frames, "targets-split-saved")
        released_after_split = close_targets(device)
        require(released_after_split, "release after split",
                status="not_loaded", workspace_allocated=False,
                page_open=False, view="none", cleanup_complete=True,
                lease_mask=0)
        device.close()
        device = None

        device, resets["split"] = cold_reopen(
            args.port, args.output, "targets-split-cold-reopen",
            args.expected_version, app_identity, run_id)
        _, destination_reopened, destination_search = find_target_id(
            device, destination_id)
        states["destination_reopen_search"] = destination_search
        states["destination_reopened"] = destination_reopened
        require(destination_reopened, "cold split destination", status="ready",
                view="detail", selected_target_id=destination_id,
                target_state_generation=generation_split,
                active_merge_available=False,
                catalog_count=catalog_before,
                merge_history_count=history_before + 1,
                selected_identity_count=destination_identities,
                selected_evidence_count=destination_evidence,
                selected_graph_fingerprint=destination_graph,
                cleanup_complete=True, lease_mask=13)
        screens["destination_reopened"] = capture(
            device, frames, "targets-split-destination-reopened")
        normalize_home(device)
        _, source_reopened, source_search = find_target_id(device, source_id)
        states["source_reopen_search"] = source_search
        states["source_reopened"] = source_reopened
        require(source_reopened, "cold split source", status="ready",
                view="detail", selected_target_id=source_id,
                target_state_generation=generation_split,
                active_merge_available=False,
                catalog_count=catalog_before,
                merge_history_count=history_before + 1,
                selected_identity_count=source_identities,
                selected_evidence_count=source_evidence,
                selected_graph_fingerprint=source_graph,
                cleanup_complete=True, lease_mask=13)
        screens["source_reopened"] = capture(
            device, frames, "targets-split-source-reopened")
        released = close_targets(device)
        require(released, "final release", status="not_loaded",
                workspace_allocated=False, page_open=False, view="none",
                cleanup_complete=True, lease_mask=0)
        if int(released.get("heap_free_after_release", 0)) + 512 < int(
                released.get("heap_free_before", 0)):
            raise RuntimeError(
                f"Targets workspace heap did not recover: {released}")
        clear_command = (
            "targets.merge-split-fixture clear disposable-ota1 "
            f"{ota1_before_sha} {run_id} confirm").encode("ascii")
        cleared = query(
            device, clear_command,
            "leshy.targets_merge_split_fixture.v1", "cleared")
        require(cleared, "fixture clear", status="cleared", run_id=run_id,
                identity_matched=True, continuity_disarmed=True,
                ota1_restore_required=True, ota1_restored=False,
                product_partition_touched=False, sd_accessed=False,
                product_target_state_touched=False, nvs_touched=False,
                radio_touched=False, rf_tx_attempts=0)
        states["fixture_cleared"] = cleared
        fixture_inactive = read_only_query(
            device, b"targets.merge-split-fixture state",
            "leshy.targets_merge_split_fixture.v1", "state")
        require(fixture_inactive, "fixture inactive", armed=False,
                continuity_valid=False, runtime_active=False, run_id="",
                storage="product_sd", ota1_restore_required=False,
                sd_accessed=False, product_target_state_touched=False,
                radio_touched=False, rf_tx_attempts=0)
        states["fixture_inactive"] = fixture_inactive
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            raise RuntimeError(f"final cleanup failed: {cleanup}")

        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "session_generation": int(recovery["generation"]),
            "destination_id": destination_id,
            "source_id": source_id,
            "merge_operation_id": merge_operation_id,
            "target_state_generation_before": generation_before,
            "target_state_generation_merged": generation_merged,
            "target_state_generation_split": generation_split,
            "catalog_count_before": catalog_before,
            "merge_history_count_before": history_before,
            "graph_fingerprints": {
                "destination_before": destination_graph,
                "destination_after_split":
                    destination_reopened["selected_graph_fingerprint"],
                "source_before": source_graph,
                "source_after_split":
                    source_reopened["selected_graph_fingerprint"],
            },
            "states": states,
            "screens": screens,
            "resets": resets,
            "released": released,
            "cleanup": cleanup,
        })
    except Exception as error:
        if device is not None:
            try:
                cleanup = best_effort_cleanup(device)
            except Exception as cleanup_error:
                cleanup = {
                    "attempted": True, "complete": False,
                    "error": (f"{type(cleanup_error).__name__}: "
                              f"{cleanup_error}"),
                }
        workflow_error = f"{type(error).__name__}: {error}"
    finally:
        if device is not None:
            device.close()
            device = None
        if not backup_ready:
            # The destructive prepare command is unreachable until both reads
            # match, so a failed backup proof can discard its private partial
            # artifacts without losing the original inactive partition.
            ota1_backup.unlink(missing_ok=True)
            ota1_backup_second.unlink(missing_ok=True)
            partition_before.unlink(missing_ok=True)
            partition_before_second.unlink(missing_ok=True)
        if (backup_ready and partition_mutation_attempted and
                ota1_backup.is_file() and partition_before.is_file()):
            restore_attempted = True
            restore_errors: list[str] = []
            try:
                _, ota1_after_sha, restore_attempts = restore_flash(
                    args.port, args.flash_baud, OTA1_OFFSET, ota1_backup,
                    ota1_restore_readback)
            except Exception as restore_error:
                restore_errors.append(
                    f"OTA1 {type(restore_error).__name__}: {restore_error}")
            # Restore the original table even when OTA1 restoration reports an
            # error. This minimizes the board's exposure to the temporary map;
            # private backups remain retained unless both regions verify.
            try:
                _, partition_restore_sha, partition_restore_attempts = (
                    restore_flash(
                        args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                        partition_before, partition_restore_readback))
                partition_restored = (
                    partition_restore_sha == partition_before_sha)
                partition_after_sha, partition_after_attempts = (
                    read_flash_with_retry(
                        args.port, args.flash_baud, PARTITION_TABLE_OFFSET,
                        PARTITION_TABLE_SIZE, partition_after))
            except Exception as restore_error:
                restore_errors.append(
                    "partition table "
                    f"{type(restore_error).__name__}: {restore_error}")
            restore_verified = (
                ota1_after_sha == ota1_before_sha and
                partition_restored and
                partition_after_sha == partition_before_sha)
            if restore_verified:
                ota1_backup.unlink(missing_ok=True)
                ota1_restore_readback.unlink(missing_ok=True)
                partition_before.unlink(missing_ok=True)
                partition_restore_readback.unlink(missing_ok=True)
                partition_after.unlink(missing_ok=True)
                private_backup_deleted = True
            else:
                restore_errors.append(
                    "OTA1 or partition-table restore mismatch")
            if restore_errors:
                restore_message = "restore " + "; ".join(restore_errors)
                workflow_error = (
                    f"{workflow_error} | {restore_message}"
                    if workflow_error else restore_message)

    final_boot: dict[str, Any] = {}
    final_recovery: dict[str, Any] = {}
    final_fixture: dict[str, Any] = {}
    final_timing: dict[str, Any] = {}
    final_cleanup: dict[str, Any] = {"attempted": False}
    if backup_ready and restore_verified:
        try:
            final_boot, _, final_timing = reset_capture(
                args.port, args.output, "targets-merge-split-final-boot", 20.0)
            require(final_boot, "final candidate",
                    version=args.expected_version,
                    app_elf_sha256=app_identity)
            require_non_watchdog_boot(final_boot, "final candidate")
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            synchronize_console(device, 20.0)
            final_fixture = read_only_query(
                device, b"targets.merge-split-fixture state",
                "leshy.targets_merge_split_fixture.v1", "state")
            if final_fixture.get("armed") is True:
                # An interrupted UI path may not have reached the normal clear,
                # but the exact RTC identity still permits a bounded disarm
                # after OTA1 has already been restored byte-for-byte.
                normalize_home(device)
                clear_command = (
                    "targets.merge-split-fixture clear disposable-ota1 "
                    f"{ota1_before_sha} {run_id} confirm").encode("ascii")
                emergency_clear = query(
                    device, clear_command,
                    "leshy.targets_merge_split_fixture.v1", "cleared")
                require(emergency_clear, "post-restore fixture clear",
                        status="cleared", identity_matched=True,
                        continuity_disarmed=True)
                states["post_restore_emergency_clear"] = emergency_clear
                device.close()
                device = None
                final_boot, _, final_timing = reset_capture(
                    args.port, args.output,
                    "targets-merge-split-final-product-boot", 20.0)
                require(final_boot, "final product candidate",
                        version=args.expected_version,
                        app_elf_sha256=app_identity)
                require_non_watchdog_boot(final_boot,
                                          "final product candidate")
                device = PassiveSerial(args.port, 115200, timeout=0.25)
                synchronize_console(device, 20.0)
            final_recovery = read_only_query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(final_recovery, "final exact media", status="admitted",
                    expected_fingerprint=EXPECTED_CID,
                    observed_fingerprint=EXPECTED_CID,
                    fingerprint_matched=True, mounted_read_only=True,
                    read_only_guaranteed=True, blocked_write_attempts=0,
                    cleanup_complete=True, physical_write_calls=0)
            for key in ("generation", "observations"):
                if final_recovery.get(key) != recovery.get(key):
                    raise RuntimeError(
                        f"product {key} changed: {recovery.get(key)} -> "
                        f"{final_recovery.get(key)}")
            final_fixture = read_only_query(
                device, b"targets.merge-split-fixture state",
                "leshy.targets_merge_split_fixture.v1", "state")
            require(final_fixture, "final fixture state", armed=False,
                    continuity_valid=False, runtime_active=False, run_id="",
                    storage="product_sd", ota1_restore_required=False,
                    sd_accessed=False, product_target_state_touched=False,
                    radio_touched=False, rf_tx_attempts=0)
            final_cleanup = best_effort_cleanup(device)
            if not final_cleanup.get("complete"):
                raise RuntimeError(
                    f"final post-restore cleanup failed: {final_cleanup}")
        except Exception as final_error:
            if not workflow_error:
                workflow_error = (
                    f"final verification {type(final_error).__name__}: "
                    f"{final_error}")
        finally:
            if device is not None:
                device.close()
                device = None
    elif backup_ready and not workflow_error:
        workflow_error = "private OTA1 restore was not verified"

    record["disposable_target"] = {
        "kind": "inactive_ota1_littlefs",
        "offset": OTA1_OFFSET,
        "size": OTA1_SIZE,
        "two_read_backup_verified": backup_ready,
        "before_sha256": ota1_before_sha,
        "second_read_sha256": ota1_second_sha,
        "backup_read_attempts": ota1_backup_attempts,
        "second_read_attempts": ota1_second_attempts,
        "restore_attempted": restore_attempted,
        "restore_attempts": restore_attempts,
        "after_sha256": ota1_after_sha,
        "restore_verified": restore_verified,
        "private_backup_deleted_after_verified_restore":
            private_backup_deleted,
        "partition_table_before_sha256": partition_before_sha,
        "partition_table_second_read_sha256": partition_second_sha,
        "partition_table_candidate_sha256": partition_candidate_sha,
        "partition_table_installed_sha256": partition_installed_sha,
        "partition_table_after_sha256": partition_after_sha,
        "partition_table_before_read_attempts": partition_before_attempts,
        "partition_table_second_read_attempts": partition_second_attempts,
        "partition_table_install_attempts": partition_install_attempts,
        "partition_table_restore_attempts": partition_restore_attempts,
        "partition_table_after_read_attempts": partition_after_attempts,
        "partition_table_two_read_backup_verified": (
            bool(partition_before_sha) and
            partition_before_sha == partition_second_sha),
        "partition_table_mutation_attempted": partition_mutation_attempted,
        "partition_table_candidate_installed": partition_installed,
        "partition_table_original_restored": partition_restored,
        "partition_table_unchanged": (
            bool(partition_before_sha) and
            partition_before_sha == partition_after_sha),
    }
    record.update({
        "status": "failed" if workflow_error else "pass",
        "error": workflow_error or None,
        "states": states,
        "screens": screens,
        "resets": resets,
        "cleanup": cleanup,
        "initial_timing": initial_timing,
        "preflight_safety": preflight_safety,
        "final_boot": final_boot,
        "final_recovery": final_recovery,
        "final_fixture": final_fixture,
        "final_timing": final_timing,
        "final_cleanup": final_cleanup,
    })

    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(str(args.output / "run.json"))
    return 2 if workflow_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
