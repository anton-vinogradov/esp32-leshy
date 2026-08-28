#!/usr/bin/env python3
"""Flash and validate the enrolled real-passive/product-SD Survey lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json


RUN_SCHEMA = "leshy.product_survey_hil.run.v1"


def valid_cid(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 32 and value.upper() == value and
        all(character in "0123456789ABCDEF" for character in value)
    )


def resolve_expected_cid(argument: str | None,
                         recovery: dict[str, Any]) -> str:
    if argument is not None:
        if not valid_cid(argument):
            raise ValueError("expected CID must be 32 uppercase hexadecimal characters")
        return argument
    expected = recovery.get("expected_fingerprint")
    observed = recovery.get("observed_fingerprint")
    if (not valid_cid(expected) or expected != observed or
            recovery.get("status") != "admitted" or
            recovery.get("enrolled") is not True or
            recovery.get("fingerprint_matched") is not True):
        raise ValueError(
            "automatic CID discovery requires an admitted exact-card enrollment"
        )
    return expected


def parse_boot_records(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    ready: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("schema") == "leshy.boot.v1" and value.get("kind") == "ready":
            ready = value
        if (value.get("schema") == "leshy.storage.product_boot_recovery.v1" and
                value.get("kind") == "state"):
            recovery = value
    return ready, recovery


def expect(record: dict[str, Any], expected: dict[str, Any], prefix: str) -> list[str]:
    failures: list[str] = []
    for key, wanted in expected.items():
        actual = record.get(key)
        if actual != wanted:
            failures.append(f"{prefix}.{key}: {actual!r} != {wanted!r}")
    return failures


def boot_ready_failures(ready: dict[str, Any], expected_version: str,
                        app_identity: str) -> list[str]:
    failures = expect(ready, {
        "version": expected_version,
        "app_elf_sha256": app_identity,
        "buzzer_inactive": True,
        "input_detected": True,
    }, "boot")
    input_attempts = ready.get("input_probe_attempts")
    input_retries = ready.get("input_probe_transient_retries")
    if (not isinstance(input_attempts, int) or isinstance(input_attempts, bool)
            or input_attempts < 1 or input_attempts > 8):
        failures.append("boot.input_probe_attempts: expected 1..8")
    if (not isinstance(input_retries, int) or isinstance(input_retries, bool)
            or not isinstance(input_attempts, int)
            or input_retries != input_attempts - 1):
        failures.append(
            "boot.input_probe_transient_retries: expected attempts - 1"
        )
    return failures


def boot_failures(ready: dict[str, Any], recovery: dict[str, Any],
                  expected_version: str, app_identity: str,
                  expected_cid: str) -> list[str]:
    failures = boot_ready_failures(
        ready, expected_version, app_identity)
    failures.extend(expect(recovery, {
        "status": "admitted",
        "enrolled": True,
        "expected_fingerprint": expected_cid,
        "observed_fingerprint": expected_cid,
        "fingerprint_matched": True,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "blocked_write_attempts": 0,
        "catalog_admitted": True,
        "cleanup_complete": True,
        "physical_write_calls": 0,
    }, "boot_recovery"))
    if not isinstance(recovery.get("generation"), int) or recovery["generation"] < 1:
        failures.append("boot_recovery.generation: expected >= 1")
    attempts = recovery.get("attempts")
    retries = recovery.get("transient_retries")
    if (not isinstance(attempts, int) or isinstance(attempts, bool)
            or attempts < 1 or attempts > 8):
        failures.append("boot_recovery.attempts: expected 1..8")
    if (not isinstance(retries, int) or isinstance(retries, bool)
            or not isinstance(attempts, int) or retries != attempts - 1):
        failures.append(
            "boot_recovery.transient_retries: expected attempts - 1"
        )
    return failures


def setup_failures(state: dict[str, Any],
                   expected_owner: str = "survey") -> list[str]:
    return expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_simulated": False,
        "survey_persistent": True,
        "survey_product_selected": True,
        "survey_workflow_state": "setup",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": True,
        "survey_product_worker_ready": True,
        "survey_product_source_active": False,
    }, "setup")


def running_failures(state: dict[str, Any], expected_cid: str,
                     expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_simulated": False,
        "survey_persistent": True,
        "survey_workflow_state": "running",
        "survey_pipeline_status": "drained",
        "survey_product_status": "running",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_store_status": "permitted",
        "survey_product_admission_status": "permitted",
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_product_identity_status": "valid",
        "survey_scan_status": "valid",
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_product_cleanup_complete": False,
        "survey_product_worker_ready": True,
        "survey_product_source_active": True,
    }, "running")
    observations = state.get("survey_observations")
    wifi_accepted = state.get("survey_scan_accepted")
    ble_accepted = state.get("survey_ble_scan_accepted")
    forwarded = state.get("survey_forwarded")
    if not isinstance(observations, int) or observations < 1:
        failures.append("running.survey_observations: expected >= 1")
    if (not isinstance(wifi_accepted, int) or
            not isinstance(ble_accepted, int) or
            wifi_accepted + ble_accepted != observations or
            forwarded != observations):
        failures.append(
            "running.observation_accounting: "
            "wifi+ble accepted/forwarded/observations differ"
        )
    identity_attempts = state.get("survey_product_identity_attempts")
    identity_retries = state.get("survey_product_identity_transient_retries")
    if (not isinstance(identity_attempts, int)
            or isinstance(identity_attempts, bool)
            or identity_attempts < 1 or identity_attempts > 8):
        failures.append("running.survey_product_identity_attempts: expected 1..8")
    if (not isinstance(identity_retries, int)
            or isinstance(identity_retries, bool)
            or not isinstance(identity_attempts, int)
            or identity_retries != identity_attempts - 1):
        failures.append(
            "running.survey_product_identity_transient_retries: "
            "expected attempts - 1"
        )
    free_bytes = state.get("survey_product_cached_free_bytes")
    capacity = state.get("survey_product_capacity_bytes")
    if not isinstance(free_bytes, int) or free_bytes < 64 * 1024 + 1024 * 1024:
        failures.append("running.survey_product_cached_free_bytes: insufficient")
    if not isinstance(capacity, int) or capacity <= 0 or free_bytes > capacity:
        failures.append("running.survey_product_capacity_bytes: invalid geometry")
    if not isinstance(state.get("survey_product_scan_cycles"), int) or state[
            "survey_product_scan_cycles"] < 1:
        failures.append("running.survey_product_scan_cycles: expected >= 1")
    start_action_us = state.get("survey_product_start_action_us")
    if (not isinstance(start_action_us, int) or isinstance(start_action_us, bool)
            or start_action_us <= 0 or start_action_us > 10_000):
        failures.append(
            "running.survey_product_start_action_us: expected in (0, 10000]"
        )
    return failures


def detail_failures(state: dict[str, Any], minimum_observations: int,
                    minimum_scan_cycles: int,
                    expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_view": "detail",
        "survey_workflow_state": "running",
        "survey_running": True,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": True,
    }, "running_detail")
    observed = state.get("survey_observations")
    if (not isinstance(observed, int) or isinstance(observed, bool)
            or observed < minimum_observations):
        failures.append("running_detail.survey_observations: regressed")
    cycles = state.get("survey_product_scan_cycles")
    if (not isinstance(cycles, int) or isinstance(cycles, bool)
            or cycles < minimum_scan_cycles):
        failures.append("running_detail.survey_product_scan_cycles: worker did not progress")
    return failures


def list_after_detail_failures(state: dict[str, Any], minimum_observations: int,
                               back_ack_ms: float,
                               expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_view": "list",
        "survey_workflow_state": "running",
        "survey_running": True,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": True,
    }, "running_list_after_detail")
    observed = state.get("survey_observations")
    if (not isinstance(observed, int) or isinstance(observed, bool)
            or observed < minimum_observations):
        failures.append("running_list_after_detail.survey_observations: regressed")
    if back_ack_ms <= 0 or back_ack_ms > 150:
        failures.append(
            f"running_list_after_detail.back_ack_ms: {back_ack_ms:.3f} not in (0, 150]"
        )
    return failures


def committed_failures(state: dict[str, Any], before_generation: int,
                       expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_workflow_state": "result",
        "survey_workflow_status": "committed",
        "survey_pipeline_status": "committed",
        "survey_product_status": "committed",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
        "library_persistent": True,
        "library_simulated": False,
    }, "committed")
    if state.get("survey_generation") != before_generation + 1:
        failures.append(
            f"committed.survey_generation: {state.get('survey_generation')!r} "
            f"!= {before_generation + 1}"
        )
    if state.get("library_generation") != state.get("survey_generation"):
        failures.append("committed.library_generation: does not match Survey")
    stop_action_us = state.get("survey_product_stop_action_us")
    if (not isinstance(stop_action_us, int) or isinstance(stop_action_us, bool)
            or stop_action_us <= 0 or stop_action_us > 10_000):
        failures.append(
            "committed.survey_product_stop_action_us: expected in (0, 10000]"
        )
    return failures


def recovered_failures(recovery: dict[str, Any], generation: int,
                       observations: int, expected_cid: str) -> list[str]:
    failures = expect(recovery, {
        "status": "admitted",
        "expected_fingerprint": expected_cid,
        "observed_fingerprint": expected_cid,
        "generation": generation,
        "observations": observations,
        "catalog_admitted": True,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
        "physical_write_calls": 0,
    }, "post_boot_recovery")
    return failures


def export_failures(artifact: dict[str, Any], generation: int,
                    observations: int) -> list[str]:
    failures = expect(artifact, {
        "status": "valid",
        "generation": generation,
        "integrity": "valid",
        "persistent": True,
        "simulated": False,
        "storage_backend": "persistent_media",
        "radio_touched": False,
    }, "library_export")
    session = artifact.get("session")
    if not isinstance(session, dict):
        failures.append("library_export.session: missing")
    else:
        failures.extend(expect(session, {
            "id": "product-passive-live",
            "observations": observations,
            "dropped": 0,
        }, "library_export.session"))
    return failures


def paused_failures(state: dict[str, Any], observations: int,
                    scan_cycles: int,
                    expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_view": "list",
        "survey_workflow_state": "running",
        "survey_running": True,
        "survey_product_status": "paused",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": False,
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_ble_scan_rejected": 0,
        "survey_ble_scan_dropped": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
    }, "paused")
    if state.get("survey_observations") != observations:
        failures.append("paused.survey_observations: changed after pause")
    if state.get("survey_product_scan_cycles") != scan_cycles:
        failures.append("paused.survey_product_scan_cycles: changed after pause")
    return failures


def paused_detail_failures(state: dict[str, Any], observations: int,
                           scan_cycles: int,
                           expected_owner: str = "survey") -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": expected_owner,
        "lease_mask": 15,
        "survey_view": "detail",
        "survey_workflow_state": "running",
        "survey_running": True,
        "survey_product_status": "paused",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": False,
    }, "paused_detail")
    if state.get("survey_observations") != observations:
        failures.append("paused_detail.survey_observations: changed")
    if state.get("survey_product_scan_cycles") != scan_cycles:
        failures.append("paused_detail.survey_product_scan_cycles: changed")
    return failures


def action(device: Any, name: str, timeout: float = 15.0) -> dict[str, Any]:
    from capture_1x_ui import read_json

    device.write(f"ui.key {name}\n".encode("ascii"))
    device.flush()
    return read_json(device, "leshy.ui.v1", "state", timeout=timeout)


def normalize_home(device: Any,
                   trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(8):
        if state.get("page") == "home":
            break
        state = action(device, "back")
        if trace is not None:
            trace.append(state)
    if state.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {state}")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            break
        state = action(device, "up")
        if trace is not None:
            trace.append(state)
    if int(state.get("selection", -1)) != 0:
        raise RuntimeError(f"cannot normalize Home selection: {state}")
    return state


def open_product_survey_visit(
        device: Any,
        trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Open the retained Survey through the current Wi-Fi -> Visit route."""
    state = normalize_home(device, trace)
    if state.get("selected_id") != "wifi":
        raise RuntimeError(f"cannot focus Home Wi-Fi row: {state}")
    state = action(device, "right")
    if trace is not None:
        trace.append(state)
    if not (
        state.get("page") == "survey"
        and state.get("wifi_product_view") == "menu"
        and state.get("runtime_owner") == "wifi"
    ):
        raise RuntimeError(f"cannot open Wi-Fi product menu: {state}")
    for _ in range(4):
        if int(state.get("wifi_product_selection", -1)) == 3:
            break
        state = action(device, "down")
        if trace is not None:
            trace.append(state)
    if int(state.get("wifi_product_selection", -1)) != 3:
        raise RuntimeError(f"cannot focus Wi-Fi Visit row: {state}")
    state = action(device, "right")
    if trace is not None:
        trace.append(state)
    return state


def configure_wifi_only_sources(
        device: Any, state: dict[str, Any],
        trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Leave only Wi-Fi selected through the public Survey setup UI."""
    if not (
        state.get("page") == "survey" and
        state.get("survey_workflow_state") == "setup" and
        state.get("survey_setup_view") == "plan" and
        state.get("survey_setup_selection") == 0 and
        state.get("survey_source_wifi_state") == "available"
    ):
        raise RuntimeError(f"cannot configure Wi-Fi-only Survey sources: {state}")
    if (
        state.get("survey_source_selected_mask") == 1 and
        state.get("survey_source_selected_count") == 1 and
        state.get("survey_source_can_start") is True
    ):
        return state
    if not (
        state.get("survey_source_ble_state") == "available" and
        state.get("survey_source_selected_mask") == 3 and
        state.get("survey_source_selected_count") == 2
    ):
        raise RuntimeError(f"unexpected Survey source selection: {state}")

    state = action(device, "select")
    if trace is not None:
        trace.append(state)
    if not (
        state.get("survey_setup_view") == "sources" and
        state.get("survey_setup_selection") == 0 and
        state.get("survey_source_selected_mask") == 3 and
        state.get("survey_source_selected_count") == 2
    ):
        raise RuntimeError(f"cannot open Survey sources: {state}")

    state = action(device, "down")
    if trace is not None:
        trace.append(state)
    if not (
        state.get("survey_setup_view") == "sources" and
        state.get("survey_setup_selection") == 1
    ):
        raise RuntimeError(f"cannot focus Survey BLE source: {state}")

    state = action(device, "select")
    if trace is not None:
        trace.append(state)
    if not (
        state.get("survey_setup_view") == "sources" and
        state.get("survey_setup_selection") == 1 and
        state.get("survey_source_selected_mask") == 1 and
        state.get("survey_source_selected_count") == 1 and
        state.get("survey_source_can_start") is True
    ):
        raise RuntimeError(f"cannot disable Survey BLE source: {state}")

    state = action(device, "back")
    if trace is not None:
        trace.append(state)
    if not (
        state.get("survey_setup_view") == "plan" and
        state.get("survey_setup_selection") == 0 and
        state.get("survey_source_selected_mask") == 1 and
        state.get("survey_source_selected_count") == 1 and
        state.get("survey_source_can_start") is True
    ):
        raise RuntimeError(f"cannot return to Wi-Fi-only Survey plan: {state}")
    return state


def open_latest_library(device: Any,
                        trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = normalize_home(device, trace)
    for _ in range(6):
        state = action(device, "down")
        trace.append(state)
    if (state.get("page") != "home" or state.get("selection") != 6 or
            state.get("selected_id") != "library"):
        raise RuntimeError(f"cannot focus final Home Library row: {state}")
    state = action(device, "right")
    trace.append(state)
    if state.get("page") != "library":
        raise RuntimeError(f"cannot open Library: {state}")
    return state


def focus_survey_start(device: Any) -> dict[str, Any]:
    """Reach the public Start row after Sources and RF spectrum."""
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(3):
        if (state.get("page") == "survey" and
                state.get("survey_workflow_state") == "setup" and
                state.get("survey_setup_view") == "plan" and
                state.get("survey_setup_selection") == 2):
            return state
        state = action(device, "down")
    raise RuntimeError(f"could not focus public Survey Start row: {state!r}")


def return_home_after_commit(device: Any,
                             trace: list[dict[str, Any]]) -> dict[str, Any]:
    """Leave the result/list/setup stack without assuming a fixed depth."""
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(4):
        if (state.get("page") == "home" and
                state.get("runtime_owner") == "none" and
                state.get("lease_mask") == 0):
            return state
        state = action(device, "back")
        trace.append(state)
    raise RuntimeError(f"cannot return Home after commit: {state!r}")


def query(device: Any, command: bytes, schema: str, kind: str,
          timeout: float = 5.0) -> dict[str, Any]:
    from capture_1x_ui import read_json

    device.write(command + b"\n")
    device.flush()
    return read_json(device, schema, kind, timeout=timeout)


def wait_ui_state(device: Any, predicate: Any, timeout: float,
                  description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"ui.state", "leshy.ui.v1", "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def best_effort_cleanup(device: Any, timeout: float = 20.0) -> dict[str, Any]:
    """Abort live work, return Home, and retain the observed terminal state."""
    cleanup: dict[str, Any] = {"attempted": True, "actions": [], "errors": []}
    deadline = time.monotonic() + timeout
    try:
        state = query(device, b"ui.state", "leshy.ui.v1", "state")
        cleanup["initial_state"] = state
        while time.monotonic() < deadline:
            page = state.get("page")
            owner = state.get("runtime_owner")
            lease = state.get("lease_mask")
            if page == "home" and owner == "none" and lease == 0:
                break
            if page == "survey":
                status = state.get("survey_product_status")
                if status in ("stopping", "cancelling"):
                    time.sleep(0.05)
                    state = query(device, b"ui.state", "leshy.ui.v1", "state")
                    continue
                response = action(device, "back")
            else:
                response = action(device, "back")
            cleanup["actions"].append(response)
            state = response
        cleanup["final_state"] = query(
            device, b"ui.state", "leshy.ui.v1", "state"
        )
    except Exception as error:  # cleanup evidence must survive the original failure
        cleanup["errors"].append(f"{type(error).__name__}: {error}")
    final = cleanup.get("final_state", {})
    cleanup["complete"] = (
        final.get("page") == "home" and
        final.get("runtime_owner") == "none" and
        final.get("lease_mask") == 0 and
        final.get("survey_product_backend_open") is False and
        final.get("survey_product_storage_mounted") is False and
        final.get("survey_product_source_active") is False
    )
    return cleanup


def _capture_once(
        device: Any, output: Path, name: str,
        record_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from capture_1x_ui import read_json, rgb565be_to_png

    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    size = int(begin["bytes"])
    frame = bytearray()
    deadline = time.monotonic() + 30.0
    while len(frame) < size and time.monotonic() < deadline:
        chunk = device.read(size - len(frame))
        if chunk:
            frame.extend(chunk)
    if len(frame) != size:
        raise TimeoutError(f"{name}: frame ended at {len(frame)} of {size}")
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    if begin.get("revision") != end.get("revision") or begin.get("revision") != state.get("revision"):
        raise RuntimeError(f"{name}: UI revision changed during capture")
    raw = bytes(frame)
    png = rgb565be_to_png(raw, int(begin["width"]), int(begin["height"]))
    (output / f"{name}.rgb565").write_bytes(raw)
    (output / f"{name}.png").write_bytes(png)
    record = {
        "frame_begin": begin,
        "frame_end": end,
        "state": state,
        "rgb565_sha256": hashlib.sha256(raw).hexdigest(),
        "png_sha256": hashlib.sha256(png).hexdigest(),
    }
    if record_transform is not None:
        record = record_transform(record)
        if not isinstance(record, dict):
            raise TypeError("framebuffer capture record transform must return a dict")
    write_json(output / f"{name}.json", record)
    return record


def synchronize_capture_console(device: Any) -> None:
    from capture_1x_ui import synchronize_console

    synchronize_console(device, 10.0)


def capture(
        device: Any, output: Path, name: str, maximum_attempts: int = 2,
        record_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Capture one framebuffer with one bounded USB transport retry."""
    if maximum_attempts < 1:
        raise ValueError("maximum_attempts must be positive")
    transient_errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = _capture_once(
                device, output, name, record_transform=record_transform)
            record["transport_attempts"] = attempt
            record["transport_transient_retries"] = attempt - 1
            record["transport_transient_errors"] = transient_errors
            write_json(output / f"{name}.json", record)
            return record
        except TimeoutError as error:
            if attempt == maximum_attempts:
                raise
            transient_errors.append(str(error))
            device.reset_input_buffer()
            synchronize_capture_console(device)
    raise RuntimeError("unreachable framebuffer capture state")


def reset_capture(
        port: str, output: Path, name: str, seconds: float,
        maximum_attempts: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from capture_1x_boot import reset_and_capture_reconnecting

    if maximum_attempts < 1 or maximum_attempts > 2:
        raise ValueError("maximum_attempts must be in 1..2")
    capture_errors: list[str] = []
    attempt_records: list[dict[str, Any]] = []
    for attempt in range(1, maximum_attempts + 1):
        # Native USB disappears and re-enumerates during reset. Keeping the old
        # descriptor open can wedge the macOS CDC endpoint until a physical
        # power cycle, so each bounded attempt closes and reconnects by port.
        (raw, ready_marker_ms, usb_disconnects,
         usb_open_attempts) = reset_and_capture_reconnecting(port, seconds)
        if maximum_attempts > 1:
            (output / f"{name}.attempt-{attempt}.ndjson").write_bytes(raw)
        ready, recovery = parse_boot_records(raw)
        attempt_record = {
            "attempt": attempt,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "first_byte_ms": None,
            "ready_marker_ms": ready_marker_ms,
            "usb_disconnects": usb_disconnects,
            "usb_open_attempts": usb_open_attempts,
            "ready_present": bool(ready),
            "recovery_present": bool(recovery),
        }
        attempt_records.append(attempt_record)
        missing_markers = []
        if not ready:
            missing_markers.append("ready")
        if not recovery:
            missing_markers.append("recovery")
        if missing_markers:
            capture_errors.append(
                f"attempt {attempt}: missing {','.join(missing_markers)} marker(s)"
            )
        if not missing_markers or attempt == maximum_attempts:
            # Preserve the long-standing canonical artifact as the accepted or
            # final fail-closed attempt while retaining every raw attempt too.
            (output / f"{name}.ndjson").write_bytes(raw)
            return ready, recovery, {
                **attempt_record,
                "capture_attempts": attempt,
                "capture_transient_retries": attempt - 1,
                "capture_errors": capture_errors,
                "attempt_records": attempt_records,
            }
    raise RuntimeError("unreachable reset capture state")


def artifact_manifest(output: Path) -> None:
    lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "artifacts.sha256":
            lines.append(f"{sha256_file(path)}  {path.relative_to(output)}")
    (output / "artifacts.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    from capture_1x_ui import PassiveSerial, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--expected-cid",
        help=(
            "exact enrolled card CID; when omitted it is discovered fail-closed "
            "from admitted boot recovery"
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    parser.add_argument(
        "--release-cycle", action="store_true",
        help=(
            "pause after the first complete selected-source cycle, capture the stable "
            "paused state, and commit without a second acquisition cycle"
        ),
    )
    parser.add_argument(
        "--wifi-only", action="store_true",
        help=(
            "disable BLE through the public setup UI and run the Survey with "
            "the exact Wi-Fi-only source mask"
        ),
    )
    parser.add_argument(
        "--post-flash-settle", type=float, default=1.0,
        help="seconds allowed for the esptool-triggered boot to finish before cold reset",
    )
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.expected_cid is not None and not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be exactly 32 uppercase hexadecimal characters")
    if args.post_flash_settle < 0 or args.post_flash_settle > 10:
        parser.error("--post-flash-settle must be between 0 and 10 seconds")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    failures: list[str] = []
    run_id = secrets.token_hex(16)
    runner_source_sha256 = sha256_file(Path(__file__).resolve())
    firmware_sha = ""
    app_identity = ""
    before_ready: dict[str, Any] = {}
    before_recovery: dict[str, Any] = {}
    before_timing: dict[str, Any] = {}
    before_generation = 0
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    setup: dict[str, Any] = {}
    source_configuration: dict[str, Any] = {}
    start_row: dict[str, Any] = {}
    start_ack: dict[str, Any] = {}
    start_ack_ms = 0.0
    running: dict[str, Any] = {}
    paused: dict[str, Any] = {}
    paused_browser: dict[str, Any] = {}
    running_detail: dict[str, Any] = {}
    running_list_after_detail: dict[str, Any] = {}
    detail_back_ack_ms = 0.0
    right_detail_ack: dict[str, Any] = {}
    right_detail_ack_ms = 0.0
    stop_ack: dict[str, Any] = {}
    stop_ack_ms = 0.0
    committed: dict[str, Any] = {}
    post_ready: dict[str, Any] = {}
    post_recovery: dict[str, Any] = {}
    post_timing: dict[str, Any] = {}
    export: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before_reboot: dict[str, Any] = {"attempted": False}
    cleanup_final: dict[str, Any] = {"attempted": False}
    expected_cid = args.expected_cid or ""
    flash_completed = False
    try:
        shutil.copyfile(args.firmware, candidate)
        firmware_sha = sha256_file(candidate)
        app_identity = app_elf_sha256(candidate)
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
            flash_completed = True
            # esptool already hard-resets the board. Let that boot finish its SD
            # identification/cleanup before issuing the separately measured reset.
            time.sleep(args.post_flash_settle)

        before_ready, before_recovery, before_timing = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds,
            maximum_attempts=2,
        )
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
            try:
                synchronize_console(device)
                before_recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state"
                )
                try:
                    expected_cid = resolve_expected_cid(
                        args.expected_cid, before_recovery
                    )
                except ValueError as error:
                    failures.append(f"product_identity: {error}")
                failures.extend(boot_failures(
                    before_ready, before_recovery, args.expected_version,
                    app_identity, expected_cid
                ))
                before_generation = int(before_recovery.get("generation", 0))
                if not failures:
                    setup = open_product_survey_visit(device, trace)
                    # The retained Visit route remains owned by Wi-Fi for its
                    # complete setup, running, detail and result lifecycle.
                    failures.extend(setup_failures(setup, "wifi"))
                    source_configuration = setup
                    if not failures and args.wifi_only:
                        source_configuration = configure_wifi_only_sources(
                            device, setup, trace
                        )
                    captures["setup"] = capture(device, frames, "setup")
                if not failures:
                    start_row = focus_survey_start(device)
                    trace.append(start_row)
                    failures.extend(expect(start_row, {
                        "page": "survey",
                        "survey_workflow_state": "setup",
                        "survey_setup_view": "plan",
                        "survey_setup_selection": 2,
                        "survey_source_can_start": True,
                    }, "start_row"))
                    if args.wifi_only:
                        failures.extend(expect(start_row, {
                            "survey_source_selected_mask": 1,
                            "survey_source_selected_count": 1,
                        }, "start_row_wifi_only"))
                if not failures:
                    started = time.monotonic()
                    start_ack = action(device, "select")
                    start_ack_ms = (time.monotonic() - started) * 1000.0
                    trace.append(start_ack)
                    failures.extend(expect(start_ack, {
                        "page": "survey", "runtime_owner": "wifi",
                        "lease_mask": 15,
                        "survey_workflow_state": "setup",
                        "survey_product_status": "preparing",
                        "survey_product_source_active": False,
                    }, "start_ack"))
                    running = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "running" and
                            state.get("survey_product_scan_cycles", 0) >= 1 and
                            state.get("survey_observations", 0) >= 1
                        ),
                        20.0,
                        "product Survey did not reach live running state",
                    )
                    trace.append(running)
                    failures.extend(running_failures(
                        running, expected_cid, "wifi"
                    ))
                    if not args.release_cycle:
                        captures["running"] = capture(
                            device, frames, "running"
                        )
                if not failures and args.release_cycle:
                    observations = int(running["survey_observations"])
                    scan_cycles = int(running["survey_product_scan_cycles"])
                    pause_ack = action(device, "up")
                    trace.append(pause_ack)
                    failures.extend(expect(pause_ack, {
                        "page": "survey",
                        "survey_view": "list",
                        "survey_workflow_state": "running",
                    }, "pause_ack"))
                    paused = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "paused" and
                            state.get("survey_product_source_active") is False
                        ),
                        20.0,
                        "product Survey did not reach stable paused state",
                    )
                    trace.append(paused)
                    failures.extend(paused_failures(
                        paused, observations, scan_cycles, "wifi"
                    ))
                    paused_browser = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state"
                    )
                    failures.extend(expect(paused_browser, {
                        "view": "list",
                        "filter_focused": True,
                        "total": observations,
                        "selected": False,
                        "radio_touched": False,
                        "storage_touched": False,
                    }, "paused_browser"))
                    captures["paused"] = capture(device, frames, "paused")
                if not failures and args.release_cycle:
                    list_ack = action(device, "down")
                    trace.append(list_ack)
                    failures.extend(expect(list_ack, {
                        "page": "survey",
                        "survey_view": "list",
                        "survey_product_status": "paused",
                    }, "paused_list"))
                    right_detail_ack = action(device, "right")
                    trace.append(right_detail_ack)
                    failures.extend(paused_detail_failures(
                        right_detail_ack, observations, scan_cycles, "wifi"
                    ))
                    stop_ack = action(device, "select", timeout=40.0)
                    trace.append(stop_ack)
                    committed = stop_ack
                    if not (
                        committed.get("survey_workflow_state") == "result" and
                        committed.get("survey_product_status") == "committed"
                    ):
                        committed = wait_ui_state(
                            device,
                            lambda state: (
                                state.get("survey_workflow_state") == "result" and
                                state.get("survey_product_status") == "committed"
                            ),
                            20.0,
                            "paused product Survey did not commit",
                        )
                        trace.append(committed)
                    failures.extend(committed_failures(
                        committed, before_generation, "wifi"
                    ))
                    captures["committed"] = capture(
                        device, frames, "committed"
                    )
                    final = return_home_after_commit(device, trace)
                    failures.extend(expect(final, {
                        "page": "home", "runtime_owner": "none", "lease_mask": 0,
                        "survey_product_backend_open": False,
                        "survey_product_storage_mounted": False,
                        "survey_product_cleanup_complete": True,
                        "survey_product_source_active": False,
                    }, "after_commit_home"))
                if not failures and not args.release_cycle:
                    observations = int(running["survey_observations"])
                    scan_cycles = int(running["survey_product_scan_cycles"])
                    detail_ack = action(device, "select")
                    trace.append(detail_ack)
                    failures.extend(detail_failures(
                        detail_ack, observations, scan_cycles, "wifi"
                    ))
                    running_detail = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_view") == "detail" and
                            state.get("survey_product_source_active") is True and
                            state.get("survey_product_scan_cycles", 0) > scan_cycles
                        ),
                        10.0,
                        "live Survey worker did not progress while Detail was open",
                    )
                    trace.append(running_detail)
                    failures.extend(detail_failures(
                        running_detail, observations, scan_cycles + 1, "wifi"
                    ))
                    captures["detail"] = capture(device, frames, "detail")
                if not failures and not args.release_cycle:
                    back_started = time.monotonic()
                    running_list_after_detail = action(device, "back")
                    detail_back_ack_ms = (
                        time.monotonic() - back_started
                    ) * 1000.0
                    trace.append(running_list_after_detail)
                    failures.extend(list_after_detail_failures(
                        running_list_after_detail,
                        int(running_detail["survey_observations"]),
                        detail_back_ack_ms,
                        "wifi",
                    ))
                if not failures and not args.release_cycle:
                    right_detail_started = time.monotonic()
                    right_detail_ack = action(device, "right")
                    right_detail_ack_ms = (
                        time.monotonic() - right_detail_started
                    ) * 1000.0
                    trace.append(right_detail_ack)
                    failures.extend(detail_failures(
                        right_detail_ack,
                        int(running_list_after_detail["survey_observations"]),
                        int(running_list_after_detail["survey_product_scan_cycles"]),
                        "wifi",
                    ))
                    if right_detail_ack_ms <= 0 or right_detail_ack_ms > 150:
                        failures.append(
                            "right_detail_ack_ms: "
                            f"{right_detail_ack_ms:.3f} not in (0, 150]"
                        )
                if not failures and not args.release_cycle:
                    stop_started = time.monotonic()
                    stop_ack = action(device, "select")
                    stop_ack_ms = (time.monotonic() - stop_started) * 1000.0
                    trace.append(stop_ack)
                    failures.extend(expect(stop_ack, {
                        "page": "survey", "runtime_owner": "wifi",
                        "lease_mask": 15,
                        "survey_workflow_state": "running",
                        "survey_product_status": "stopping",
                    }, "stop_ack"))
                    committed = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_workflow_state") == "result" and
                            state.get("survey_product_status") == "committed"
                        ),
                        20.0,
                        "product Survey did not commit after worker stop",
                    )
                    trace.append(committed)
                    failures.extend(committed_failures(
                        committed, before_generation, "wifi"
                    ))
                    captures["committed"] = capture(
                        device, frames, "committed"
                    )
                    final = return_home_after_commit(device, trace)
                    failures.extend(expect(final, {
                        "page": "home", "runtime_owner": "none", "lease_mask": 0,
                        "survey_product_backend_open": False,
                        "survey_product_storage_mounted": False,
                        "survey_product_cleanup_complete": True,
                        "survey_product_source_active": False,
                    }, "after_commit_home"))
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_before_reboot = best_effort_cleanup(device)
                if not cleanup_before_reboot.get("complete"):
                    failures.append("workflow_cleanup: terminal zero-lease state unproven")

        if committed and not failures:
            post_ready, post_recovery, post_timing = reset_capture(
                args.port, args.output, "boot-after", args.boot_seconds,
                maximum_attempts=2,
            )
            generation = int(committed["survey_generation"])
            observations = int(committed["survey_observations"])
            device = PassiveSerial(args.port, 115200, timeout=0.25)
            with device:
                try:
                    synchronize_console(device)
                    post_recovery = query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"
                    )
                    failures.extend(boot_failures(
                        post_ready, post_recovery, args.expected_version,
                        app_identity, expected_cid
                    ))
                    failures.extend(recovered_failures(
                        post_recovery, generation, observations, expected_cid
                    ))
                    library = open_latest_library(device, trace)
                    failures.extend(expect(library, {
                        "page": "library", "runtime_owner": "library",
                        "lease_mask": 5, "library_persistent": True,
                        "library_simulated": False,
                        "library_generation": generation,
                    }, "library"))
                    trace.append(action(device, "right"))
                    trace.append(action(device, "right"))
                    captures["export"] = capture(device, frames, "export")
                    export = query(
                        device, b"library.export",
                        "leshy.library.export.v1", "artifact"
                    )
                    failures.extend(export_failures(
                        export, generation, observations
                    ))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    final = query(
                        device, b"ui.state", "leshy.ui.v1", "state"
                    )
                    failures.extend(expect(final, {
                        "page": "home", "runtime_owner": "none", "lease_mask": 0,
                    }, "final"))
                except Exception as error:
                    failures.append(f"post_boot: {type(error).__name__}: {error}")
                finally:
                    cleanup_final = best_effort_cleanup(device)
                    if not cleanup_final.get("complete"):
                        failures.append("post_boot_cleanup: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": runner_source_sha256,
        "passed": not failures,
        "gate_eligible": flash_completed and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "flash_requested": args.flash,
            "flashed": flash_completed,
        },
        "expected_cid": expected_cid,
        "boot_before": {"ready": before_ready, "recovery": before_recovery,
                        "timing": before_timing},
        "setup": setup,
        "wifi_only": args.wifi_only,
        "source_configuration": source_configuration,
        "start_row": start_row,
        "start_ack": start_ack,
        "start_ack_ms": start_ack_ms,
        "running": running,
        "release_cycle": args.release_cycle,
        "paused": paused,
        "paused_browser": paused_browser,
        "running_detail": running_detail,
        "running_list_after_detail": running_list_after_detail,
        "detail_back_ack_ms": detail_back_ack_ms,
        "right_detail_ack": right_detail_ack,
        "right_detail_ack_ms": right_detail_ack_ms,
        "stop_ack": stop_ack,
        "stop_ack_ms": stop_ack_ms,
        "committed": committed,
        "boot_after": {"ready": post_ready, "recovery": post_recovery,
                       "timing": post_timing},
        "library_export": export,
        "final_state": final,
        "cleanup_before_reboot": cleanup_before_reboot,
        "cleanup_final": cleanup_final,
        "captures": captures,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
