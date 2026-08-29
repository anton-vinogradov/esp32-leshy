#!/usr/bin/env python3
"""Run the board-01 CAP049 passive authentication-capture delta HIL.

The runner never creates traffic.  It observes the ambient network selected in
the product UI, and therefore treats a capture with no EAPOL evidence as a
valid, honest ``inconclusive`` result rather than as a fixture failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    action,
    begin_hil_session,
    candidate_verification_succeeded,
    end_hil_session,
    read_only_query,
    robust_cleanup,
)
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


RUN_SCHEMA = "leshy.wifi.authentication_capture_hil.run.v1"
AUTH_SCHEMA = "leshy.wifi.authentication_capture.v1"
AUTH_HOLD_SCHEMA = "leshy.wifi.authentication.hil_hold.v1"
HIL_SESSION_SCHEMA = "leshy.hil.session.v1"
AUTH_HOLD_COMMAND = b"wifi.authentication.hil-hold-survey-stop once"
SYNTHETIC_FIXTURE_SCHEMA = \
    "leshy.wifi.authentication.synthetic_fixture.v1"
SYNTHETIC_FIXTURE_COMMAND = \
    b"wifi.authentication.hil-load-synthetic-report once"
AMBIENT_REPORT_ORIGIN = "ambient_rf"
NO_REPORT_ORIGIN = "none"
CAPTURE_SCHEMA = "leshy.capture.wifi_frame.v1"
UI_SCHEMA = "leshy.ui.v1"
NETWORK_SELECTOR_SCHEMA = "leshy.wifi.network_hil_selector.v1"
NETWORK_SELECTOR_COMMAND = "wifi.network.hil-select-label-fnv1a64"
BOARD_ID = "board-01"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_FIXTURE_PORT = "/dev/cu.usbmodem1101"
WIDTH = 240
HEIGHT = 320
CONTENT_X0 = 12
CONTENT_X1 = 228
CONTENT_Y0 = 32
CONTENT_Y1 = 293
TITLE_X0 = 10
TITLE_X1 = 136
TITLE_Y0 = 5
TITLE_Y1 = 20
STATUS_X0 = 136
STATUS_X1 = 240
STATUS_Y0 = 0
STATUS_Y1 = 26
FOOTER_X0 = 0
FOOTER_X1 = 240
FOOTER_Y0 = 294
FOOTER_Y1 = 320
NOTE_X0 = 12
NOTE_X1 = 228
NOTE_Y0 = 186
NOTE_Y1 = 214
CAPTURE_DURATION_MS = 10_000
CAPTURE_TERMINAL_SLACK_US = 2_500_000
AUTH_HOLD_TIMEOUT_MS = 1_500
AUTH_HOLD_ACK_TIMEOUT_S = 0.250
AUTH_HOLD_STATE_TIMEOUT_S = 0.250
AUTH_HOLD_NAV_ACK_TIMEOUT_S = 0.250
AUTH_FAILURE_STAGES = frozenset({
    "admission", "capture_begin", "event_loop_create", "wifi_init",
    "set_storage", "set_mode", "wifi_start", "set_channel",
    "set_filter", "set_callback", "enable_promiscuous",
})
AUTH_FAILURE_STAGES_BEFORE_HEAP_SNAPSHOT = frozenset({
    "admission", "capture_begin", "event_loop_create",
})
UNCERTAINTY_NO_EVIDENCE = 1 << 7
UNCERTAINTY_CAPTURE_LOSS = 1 << 2
UNCERTAINTY_SOURCE_READ = 1 << 3
UNCERTAINTY_MALFORMED = 1 << 4
UNCERTAINTY_TRUNCATED = 1 << 5
UNCERTAINTY_CAPACITY = 1 << 6
UNCERTAINTY_UNSUPPORTED = 1 << 8
REPORT_COUNTER_FIELDS = (
    "source_frames", "frames_read", "data_frames",
    "analysis_frames_ignored", "eapol_frames", "eapol_key_frames",
    "classified_key_frames", "unclassified_key_frames",
    "unsupported_key_frames", "sequence_rejected", "malformed_frames",
    "truncated_frames", "source_read_failures", "evidence_dropped",
    "peers_dropped", "pmkids_dropped", "report_capture_frames_reported",
    "report_capture_frames_accepted",
    "report_capture_frames_dropped_capacity",
    "report_capture_frames_dropped_invalid",
)
FILESYSTEM_MOUNT_TELEMETRY_FIELDS = (
    "survey_product_filesystem_mount_stage",
    "survey_product_filesystem_bus_initialize_error",
    "survey_product_filesystem_mount_error",
    "survey_product_filesystem_mount_attempts",
    "survey_product_filesystem_mount_transient_retries",
    "survey_product_filesystem_mount_last_failure_error",
    "survey_product_mount_attempts_total",
    "survey_product_mount_successes_total",
    "survey_product_filesystem_heap_free_before_bus",
    "survey_product_filesystem_heap_largest_before_bus",
    "survey_product_filesystem_heap_free_before_vfs",
    "survey_product_filesystem_heap_largest_before_vfs",
    "survey_product_filesystem_drive_available_before_vfs",
    "survey_product_status",
    "survey_product_cleanup_complete",
    "survey_product_backend_open",
    "survey_product_storage_mounted",
)
PRIVATE_TARGET_KEYS = frozenset({
    "target_bssid", "target_identity_hash", "identity_hash",
    "wifi_network_selected_identity_hash", "ssid", "bssid", "target_label",
    "wifi_network_order_hash", "wifi_device_order_hash",
})
MAC_ADDRESS = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def scrub_private_target_identifiers(value: Any) -> Any:
    """Return evidence-safe data while live private values stay in memory."""
    if isinstance(value, dict):
        return {
            key: scrub_private_target_identifiers(item)
            for key, item in value.items()
            if not (isinstance(key, str) and
                    key.lower() in PRIVATE_TARGET_KEYS)
        }
    if isinstance(value, list):
        return [scrub_private_target_identifiers(item) for item in value]
    if isinstance(value, str):
        return MAC_ADDRESS.sub("<redacted-private-identifier>", value)
    return value


def private_target_failures(value: Any, path: str = "run") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in PRIVATE_TARGET_KEYS:
                failures.append(f"{path}.{key}: private target key retained")
            failures.extend(private_target_failures(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(private_target_failures(item, f"{path}[{index}]"))
    elif isinstance(value, str) and MAC_ADDRESS.search(value):
        failures.append(f"{path}: MAC-like private identifier retained")
    return failures


def privacy_safe_repr(value: Any) -> str:
    """Format diagnostics only after removing private radio identifiers."""
    return repr(scrub_private_target_identifiers(value))


def privacy_safe_exception(error: BaseException) -> str:
    """Retain an exception class, never opaque transport text or raw JSON."""
    return type(error).__name__


def filesystem_mount_telemetry(state: dict[str, Any]) -> dict[str, Any]:
    """Retain only non-identifying ProductSurvey mount diagnostics."""
    return {
        name: state[name]
        for name in FILESYSTEM_MOUNT_TELEMETRY_FIELDS
        if name in state
    }


def retain_cleanup_mount_telemetry(
        cleanup: dict[str, Any]) -> dict[str, Any]:
    """Attach pre/post-cleanup mount facts and scrub all UI identifiers."""
    retained = scrub_private_target_identifiers(cleanup)
    telemetry: dict[str, dict[str, Any]] = {}
    for name in ("initial_state", "final_state"):
        state = cleanup.get(name)
        if isinstance(state, dict):
            telemetry[name] = filesystem_mount_telemetry(state)
    retained["filesystem_mount_telemetry"] = telemetry
    return retained


class UiStateWaitTimeout(TimeoutError):
    """A bounded wait failure with an evidence-safe last-state snapshot."""

    def __init__(self, description: str, last_state: dict[str, Any],
                 transport_errors: list[str]) -> None:
        super().__init__(description)
        self.last_state = filesystem_mount_telemetry(last_state)
        self.transport_errors = list(transport_errors)


def finalize_evidence_result(value: dict[str, Any], failures: list[str],
                             base_passed: bool) -> tuple[dict[str, Any], bool]:
    retained = scrub_private_target_identifiers(value)
    failures.extend(private_target_failures(retained))
    final_passed = base_passed and not failures
    retained["passed"] = final_passed
    retained["gate_eligible"] = final_passed
    retained["failures"] = list(failures)
    scope = retained.get("scope")
    if isinstance(scope, dict):
        scope["application_rx_only"] = final_passed
    return retained, final_passed


def capture_evidence_safe(device: PassiveSerial, frames: Path,
                          name: str) -> dict[str, Any]:
    """Capture a frame without ever writing private UI state to its sidecar."""
    artifacts = tuple(
        frames / f"{name}.{suffix}" for suffix in ("json", "png", "rgb565"))
    for artifact in artifacts:
        artifact.unlink(missing_ok=True)

    def retention_safe_record(live: dict[str, Any]) -> dict[str, Any]:
        retained = scrub_private_target_identifiers(live)
        privacy_failures = private_target_failures(
            retained, f"frames/{name}.json")
        if privacy_failures:
            raise RuntimeError("; ".join(privacy_failures))
        return retained

    try:
        return capture(
            device, frames, name, record_transform=retention_safe_record)
    except Exception:
        for artifact in artifacts:
            artifact.unlink(missing_ok=True)
        raise


def pixel_changes(frames: Path, before_name: str,
                  after_name: str) -> dict[str, int]:
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    expected = WIDTH * HEIGHT * 2
    if len(before) != expected or len(after) != expected:
        raise RuntimeError("TFT comparison requires two complete 240x320 frames")
    content = 0
    static = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            offset = (y * WIDTH + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if CONTENT_X0 <= x < CONTENT_X1 and CONTENT_Y0 <= y < CONTENT_Y1:
                content += 1
            else:
                static += 1
    return {
        "content_changed_pixels": content,
        "static_chrome_changed_pixels": static,
    }


def terminal_pixel_changes(frames: Path, before_name: str,
                           after_name: str) -> dict[str, int]:
    """Classify the exact localized Running -> Result screen transition."""
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    expected = WIDTH * HEIGHT * 2
    if len(before) != expected or len(after) != expected:
        raise RuntimeError("terminal TFT comparison requires two complete frames")
    changed = {
        "content_changed_pixels": 0,
        "title_changed_pixels": 0,
        "status_changed_pixels": 0,
        "footer_changed_pixels": 0,
        "unexpected_static_chrome_changed_pixels": 0,
    }
    for y in range(HEIGHT):
        for x in range(WIDTH):
            offset = (y * WIDTH + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if TITLE_X0 <= x < TITLE_X1 and TITLE_Y0 <= y < TITLE_Y1:
                changed["title_changed_pixels"] += 1
            elif STATUS_X0 <= x < STATUS_X1 and STATUS_Y0 <= y < STATUS_Y1:
                changed["status_changed_pixels"] += 1
            elif CONTENT_X0 <= x < CONTENT_X1 and CONTENT_Y0 <= y < CONTENT_Y1:
                changed["content_changed_pixels"] += 1
            elif FOOTER_X0 <= x < FOOTER_X1 and FOOTER_Y0 <= y < FOOTER_Y1:
                changed["footer_changed_pixels"] += 1
            else:
                changed["unexpected_static_chrome_changed_pixels"] += 1
    return changed


def terminal_pixel_delta_failures(delta: dict[str, int],
                                  label: str) -> list[str]:
    failures: list[str] = []
    for name in (
            "content_changed_pixels", "title_changed_pixels",
            "status_changed_pixels", "footer_changed_pixels",
            "unexpected_static_chrome_changed_pixels"):
        if not non_negative_integer(delta.get(name)):
            failures.append(f"{label}.{name}: missing counter")
    if failures:
        return failures
    if delta["content_changed_pixels"] <= 0:
        failures.append(f"{label}.content: terminal content stayed stale")
    if delta["title_changed_pixels"] <= 0:
        failures.append(f"{label}.title: lifecycle title stayed stale")
    if delta["status_changed_pixels"] <= 0:
        failures.append(f"{label}.status: RX/TX status stayed stale")
    if delta["unexpected_static_chrome_changed_pixels"] != 0:
        failures.append(f"{label}.chrome: unexpected static pixels changed")
    return failures


def pixel_region_proof(frames: Path, before_name: str, after_name: str,
                       *, x0: int, x1: int, y0: int,
                       y1: int) -> dict[str, Any]:
    """Hash and count one exact visible region in two complete frames."""
    before = (frames / f"{before_name}.rgb565").read_bytes()
    after = (frames / f"{after_name}.rgb565").read_bytes()
    expected = WIDTH * HEIGHT * 2
    if len(before) != expected or len(after) != expected:
        raise RuntimeError("region proof requires two complete TFT frames")
    before_region = bytearray()
    after_region = bytearray()
    changed = 0
    changed_rows: set[int] = set()
    changed_columns: set[int] = set()
    for y in range(y0, y1):
        row_start = (y * WIDTH + x0) * 2
        row_end = (y * WIDTH + x1) * 2
        before_row = before[row_start:row_end]
        after_row = after[row_start:row_end]
        before_region.extend(before_row)
        after_region.extend(after_row)
        for offset in range(0, len(before_row), 2):
            if before_row[offset:offset + 2] != after_row[offset:offset + 2]:
                changed += 1
                changed_rows.add(y)
                changed_columns.add(x0 + offset // 2)
    bbox_width = (max(changed_columns) - min(changed_columns) + 1
                  if changed_columns else 0)
    bbox_height = (max(changed_rows) - min(changed_rows) + 1
                   if changed_rows else 0)
    return {
        "x0": x0, "x1": x1, "y0": y0, "y1": y1,
        "changed_pixels": changed,
        "changed_rows": len(changed_rows),
        "changed_columns": len(changed_columns),
        "bbox_width": bbox_width, "bbox_height": bbox_height,
        "before_sha256": hashlib.sha256(before_region).hexdigest(),
        "after_sha256": hashlib.sha256(after_region).hexdigest(),
    }


AUTH_RESOURCE_FIELDS = (
    "schema", "kind", "read_only_query", "generation",
    "capture_state", "capture_active", "capture_cleanup_complete",
    "adapter_cleanup_complete", "esp_rf_owned_by_foreground",
    "target_selected", "target_selection_continuity", "channel",
    "duration_ms", "maximum_frames", "snap_length",
    "production_report_fingerprint",
    "production_report_fingerprint_scope",
    "production_controller_ready", "production_controller_view",
    "production_controller_action_selection",
    "production_controller_peer_selection",
    "production_controller_evidence_selection",
    "production_controller_report_bound",
)


def stable_read_only_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Drop transport retry metadata while retaining every device field."""
    return {
        key: value for key, value in record.items()
        if not key.startswith("host_transport_")
    }


def fixture_side_effect_snapshot(
        auth: dict[str, Any], capture: dict[str, Any],
        storage: dict[str, Any]) -> dict[str, Any]:
    return {
        "auth_resource": {name: auth.get(name) for name in AUTH_RESOURCE_FIELDS},
        "capture": stable_read_only_payload(capture),
        "boot_recovery": stable_read_only_payload(storage),
    }


def fixture_side_effect_failures(
        before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Prove fixture isolation from independent read-only state queries."""
    failures: list[str] = []
    if before.get("auth_resource") != after.get("auth_resource"):
        failures.append("fixture_side_effects.auth_resource: changed")
    if before.get("capture") != after.get("capture"):
        failures.append("fixture_side_effects.capture: changed")
    if before.get("boot_recovery") != after.get("boot_recovery"):
        failures.append("fixture_side_effects.boot_recovery_continuity: changed")
    capture = before.get("capture", {})
    if not (
            capture.get("schema") == CAPTURE_SCHEMA and
            capture.get("kind") == "state" and
            capture.get("state") == "complete" and
            capture.get("passive_only") is True and
            capture.get("rx_only") is True and
            capture.get("application_connect_calls") == 0 and
            capture.get("application_raw_tx_calls") == 0 and
            capture.get("storage_written") is False and
            capture.get("cleanup_complete") is True and
            capture.get("lease_mask") == 15):
        failures.append("fixture_side_effects.capture: unsafe baseline")
    storage = before.get("boot_recovery", {})
    if not (
            storage.get("schema") ==
                "leshy.storage.product_boot_recovery.v1" and
            storage.get("kind") == "state" and
            storage.get("write_enabled") is False and
            storage.get("cleanup_complete") is True and
            storage.get("owned_after") == 0):
        failures.append(
            "fixture_side_effects.boot_recovery_continuity: unsafe baseline")
    auth = before.get("auth_resource", {})
    if not (
            auth.get("schema") == AUTH_SCHEMA and
            auth.get("kind") == "state" and
            auth.get("read_only_query") is True and
            auth.get("capture_state") == "complete" and
            auth.get("capture_active") is False and
            auth.get("capture_cleanup_complete") is True and
            auth.get("adapter_cleanup_complete") is True and
            auth.get("esp_rf_owned_by_foreground") is True and
            auth.get("target_selected") is True and
            auth.get("target_selection_continuity") is True):
        failures.append("fixture_side_effects.auth_resource: unsafe baseline")
    return failures


def production_continuity_failures(
        baseline: dict[str, Any], state: dict[str, Any],
        label: str) -> list[str]:
    projection = {name: state.get(name) for name in AUTH_RESOURCE_FIELDS}
    failures = []
    if projection != baseline:
        failures.append(f"{label}.production_continuity: changed")
    fingerprint = projection.get("production_report_fingerprint")
    if (not isinstance(fingerprint, str) or
            re.fullmatch(r"[0-9a-f]{16}", fingerprint) is None or
            projection.get("production_report_fingerprint_scope") !=
                "hil_session" or
            projection.get("production_controller_report_bound") is not True):
        failures.append(f"{label}.production_continuity: invalid fingerprint")
    return failures


def auth_state(device: PassiveSerial) -> dict[str, Any]:
    return read_only_query(
        device, b"wifi.authentication.state", AUTH_SCHEMA, "state",
        timeout=5.0, maximum_attempts=3)


def capture_state(device: PassiveSerial) -> dict[str, Any]:
    return read_only_query(
        device, b"capture.state", CAPTURE_SCHEMA, "state",
        timeout=5.0, maximum_attempts=3)


def load_synthetic_report_once(device: PassiveSerial) -> dict[str, Any]:
    """Load the bounded HIL report with one mutation and no replay."""
    ack = query(
        device, SYNTHETIC_FIXTURE_COMMAND, SYNTHETIC_FIXTURE_SCHEMA,
        "loaded", timeout=2.0)
    ack["host_fixture_action_writes"] = 1
    ack["host_fixture_action_replays"] = 0
    ack["host_fixture_ack_received"] = True
    require_exact(ack, {
        "schema": SYNTHETIC_FIXTURE_SCHEMA,
        "kind": "loaded", "status": "loaded",
        "loaded": True, "synthetic": True, "profile": "full",
        "report_identity": "wifi-auth-ui-full-v1",
        "one_shot": True, "replayed": False,
        "report_origin": "synthetic_hil",
        "hil_active": True,
        "display_touched": True, "rf_hardware_touched": False,
        "radio_started": False,
        "storage_mounted": False, "storage_written": False,
        "connect_calls": 0, "raw_tx_calls": 0,
    }, "authentication_synthetic_fixture")
    if not non_negative_integer(ack.get("generation")) or \
            ack["generation"] == 0:
        raise RuntimeError("synthetic fixture has no nonzero generation")
    return ack


def reject_synthetic_report_replay(device: PassiveSerial) -> dict[str, Any]:
    """Deliberately prove that the one-shot cannot be loaded twice."""
    replay = query(
        device, SYNTHETIC_FIXTURE_COMMAND, SYNTHETIC_FIXTURE_SCHEMA,
        "error", timeout=2.0)
    replay["host_fixture_action_writes"] = 1
    replay["host_fixture_action_replays"] = 0
    replay["host_fixture_ack_received"] = True
    require_exact(replay, {
        "schema": SYNTHETIC_FIXTURE_SCHEMA,
        "kind": "error", "status": "replay_rejected",
        "synthetic": True, "loaded": False,
        "profile": "full", "report_identity": "wifi-auth-ui-full-v1",
        "one_shot": True, "replayed": True,
        "report_origin": "synthetic_hil",
        "hil_active": True,
        "display_touched": False, "rf_hardware_touched": False,
        "radio_started": False,
        "storage_mounted": False, "storage_written": False,
        "connect_calls": 0, "raw_tx_calls": 0,
    }, "authentication_synthetic_fixture_replay")
    return replay


def wait_auth_state(device: PassiveSerial,
                    predicate: Callable[[dict[str, Any]], bool],
                    timeout: float, description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = auth_state(device)
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(
        f"{description}: last state {privacy_safe_repr(last)}")


def wait_ui_state(device: PassiveSerial,
                  predicate: Callable[[dict[str, Any]], bool],
                  timeout: float, description: str) -> dict[str, Any]:
    """Poll read-only UI state through bounded transient serial timeouts."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    transport_errors: list[str] = []
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            last = query(
                device, b"ui.state", UI_SCHEMA, "state",
                timeout=min(2.0, max(0.001, remaining)))
        except TimeoutError as error:
            # Exception text can contain a raw serial record.  Preserve the
            # failure class without retaining already-formatted identifiers.
            transport_errors.append(type(error).__name__)
            device.reset_input_buffer()
            time.sleep(0.05)
            continue
        if predicate(last):
            last["host_wait_transport_timeouts"] = len(transport_errors)
            last["host_wait_transport_errors"] = transport_errors
            return last
        time.sleep(0.05)
    raise UiStateWaitTimeout(description, last, transport_errors)


def wifi_menu_quiescent(state: dict[str, Any]) -> bool:
    """Require idle Wi-Fi menu state before its eager worker is snapshotted."""
    return (
        state.get("page") == "survey" and
        state.get("wifi_product_view") == "menu" and
        state.get("runtime_owner") == "wifi" and
        state.get("lease_mask") == 15 and
        state.get("survey_workflow_state") == "setup" and
        state.get("survey_product_backend_open") is False and
        state.get("survey_product_storage_mounted") is False and
        state.get("survey_product_cleanup_complete") is True and
        state.get("survey_product_source_active") is False and
        state.get("survey_product_scan_active") is False
    )


def arm_authentication_survey_stop_hold(
        device: PassiveSerial,
        pre_arm_state: dict[str, Any]) -> dict[str, Any]:
    """Arm the HIL-only hold exactly once; never replay a lost mutation ACK."""
    require_exact(pre_arm_state, {
        "schema": AUTH_SCHEMA, "kind": "state", "read_only_query": True,
        "survey_terminal_hold_armed": False,
    }, "authentication_hil_hold_pre_arm")
    arm_started_at = time.monotonic()
    try:
        ack = query(
            device, AUTH_HOLD_COMMAND, AUTH_HOLD_SCHEMA, "armed",
            timeout=AUTH_HOLD_ACK_TIMEOUT_S)
        ack_received = True
        ack_error = ""
    except TimeoutError as error:
        ack = {}
        ack_received = False
        ack_error = privacy_safe_exception(error)

    # A lost mutation ACK must still leave enough of the firmware's 1.5 s hold
    # for a read-only proof and the immediately following Back action.  Do not
    # retry either command inside this time-critical one-shot boundary.
    armed_state = read_only_query(
        device, b"wifi.authentication.state", AUTH_SCHEMA, "state",
        timeout=AUTH_HOLD_STATE_TIMEOUT_S, maximum_attempts=1)
    record: dict[str, Any] = {
        "ack": ack,
        "pre_arm_state": pre_arm_state,
        "armed_state": armed_state,
        "host_arm_action_writes": 1,
        "host_arm_action_replays": 0,
        "host_arm_ack_received": ack_received,
        "host_arm_ack_timeout_ms": AUTH_HOLD_ACK_TIMEOUT_S * 1000.0,
        "host_arm_state_timeout_ms": AUTH_HOLD_STATE_TIMEOUT_S * 1000.0,
        "host_arm_elapsed_ms": (time.monotonic() - arm_started_at) * 1000.0,
    }
    if not ack_received:
        record["host_arm_ack_error"] = ack_error

    if ack_received:
        require_exact(ack, {
            "schema": AUTH_HOLD_SCHEMA,
            "kind": "armed", "status": "armed",
            "armed": True, "one_shot": True, "replayed": False,
            "timeout_ms": AUTH_HOLD_TIMEOUT_MS,
            "hil_active": True, "hardware_touched": False,
            "radio_started": False, "storage_mounted": False,
            "storage_written": False,
        }, "authentication_hil_hold")
    if armed_state.get("survey_terminal_hold_armed") is not True:
        raise RuntimeError(
            "authentication HIL hold was not armed after the one host write")
    return record


def read_expected_ui_action_ack(
        device: PassiveSerial, action_name: str, timeout: float,
        semantic_predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """Ignore a delayed previous UI ACK and return only this action's ACK."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_json(
            device, UI_SCHEMA, "state",
            timeout=max(0.001, deadline - time.monotonic()))
        if (state.get("action") == action_name and
                semantic_predicate(state)):
            return state
    raise TimeoutError(f"timed out waiting for ui.key {action_name} ACK")


def bounded_hold_navigation(device: PassiveSerial, action_name: str,
                            hold_armed_at: float,
                            semantic_predicate: Callable[
                                [dict[str, Any]], bool]) -> dict[str, Any]:
    """Write one time-critical key once and never delay/replay on lost ACK."""
    device.write(f"ui.key {action_name}\n".encode("ascii"))
    device.flush()
    write_after_arm_ms = (time.monotonic() - hold_armed_at) * 1000.0
    try:
        record = read_expected_ui_action_ack(
            device, action_name, AUTH_HOLD_NAV_ACK_TIMEOUT_S,
            semantic_predicate)
        ack_received = True
        ack_error = ""
    except TimeoutError as error:
        record = {}
        ack_received = False
        ack_error = privacy_safe_exception(error)
    record.update({
        "host_navigation_action": action_name,
        "host_navigation_action_writes": 1,
        "host_navigation_action_replays": 0,
        "host_navigation_ack_received": ack_received,
        "host_navigation_ack_timeout_ms":
            AUTH_HOLD_NAV_ACK_TIMEOUT_S * 1000.0,
        "host_navigation_write_after_arm_ms": write_after_arm_ms,
    })
    if not ack_received:
        record["host_navigation_ack_error"] = ack_error
    return record


def authentication_start_state(state: dict[str, Any]) -> bool:
    return state.get("state") in ("running", "result", "failed")


def start_failure_diagnostic_failures(
        diagnostics: dict[str, Any]) -> list[str]:
    """Validate the minimum retained evidence for a failed adapter start."""
    failures: list[str] = []
    auth = diagnostics.get("authentication", {})
    capture_record = diagnostics.get("capture", {})
    stage = auth.get("adapter_failure_stage")
    driver_error = auth.get("adapter_driver_error")
    heap_free = auth.get("adapter_heap_free_before_init")
    heap_largest = auth.get("adapter_heap_largest_before_init")
    failure = auth.get("failure")
    if (auth.get("state") != "failed" or not isinstance(failure, str) or
            failure == "none"):
        failures.append("start_failure.authentication: not a failed state")
    if stage not in AUTH_FAILURE_STAGES | {"none"}:
        failures.append(
            f"start_failure.adapter_failure_stage: {stage!r}")
    if not isinstance(driver_error, int) or isinstance(driver_error, bool):
        failures.append("start_failure.adapter_driver_error: missing integer")
    for name, value in (
            ("adapter_heap_free_before_init", heap_free),
            ("adapter_heap_largest_before_init", heap_largest)):
        if not non_negative_integer(value):
            failures.append(f"start_failure.{name}: missing counter")
    if (failure == "start_failed" and
            (stage not in AUTH_FAILURE_STAGES or driver_error == 0)):
        failures.append(
            "start_failure.adapter: start_failed lacks exact stage/error")
    if (failure == "start_failed" and
            stage in AUTH_FAILURE_STAGES -
            AUTH_FAILURE_STAGES_BEFORE_HEAP_SNAPSHOT and
            (heap_free == 0 or heap_largest == 0)):
        failures.append(
            "start_failure.heap: post-snapshot failure retained zero heap")
    if capture_record.get("schema") != CAPTURE_SCHEMA or \
            capture_record.get("kind") != "state":
        failures.append("start_failure.capture: exact capture state missing")
    capture_error = capture_record.get("driver_error")
    if not isinstance(capture_error, int) or isinstance(capture_error, bool):
        failures.append("start_failure.capture.driver_error: missing integer")
    if failure == "start_failed" and capture_error == 0:
        failures.append(
            "start_failure.capture.driver_error: start_failed retained zero")
    return failures


def collect_authentication_failure_diagnostics(
        device: PassiveSerial,
        authentication: dict[str, Any]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"authentication": authentication}
    try:
        diagnostics["capture"] = read_only_query(
            device, b"capture.state", CAPTURE_SCHEMA, "state",
            timeout=3.0, maximum_attempts=1)
    except Exception as error:
        diagnostics["capture_query_error"] = privacy_safe_exception(error)
    return diagnostics


def best_effort_final_diagnostics(
        device: PassiveSerial) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Read safety state independently so an earlier failure remains primary."""
    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    requests = (
        ("input", b"input.state", "leshy.input.frontend.v1"),
        ("safe_outputs", b"hardware.safe-outputs",
         "leshy.hardware.safe-outputs.v1"),
        ("recovery", b"storage.product.boot-recovery",
         "leshy.storage.product_boot_recovery.v1"),
    )
    for name, command, schema in requests:
        try:
            records[name] = read_only_query(
                device, command, schema, "state",
                timeout=2.5, maximum_attempts=1)
        except Exception as error:
            errors.append(f"{name}: {privacy_safe_exception(error)}")
    return records, errors


def non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


SYNTHETIC_CONTROLLER_FIELDS = (
    "presenter_view", "presenter_tone",
    "presenter_evidence_incomplete", "presenter_report_openable",
    "presenter_cleanup_complete", "presenter_row_count",
    "presenter_synthetic", "presenter_synthetic_label_visible",
    "presenter_title_semantic", "presenter_headline_semantic",
    "presenter_note_semantic",
    "controller_ready", "controller_view", "controller_action_count",
    "controller_action_selection", "controller_selected_action",
    "controller_peer_count", "controller_peer_selection",
    "controller_peer_position", "controller_selected_peer_mask",
    "controller_selected_peer_evidence_count", "controller_evidence_count",
    "controller_evidence_selection",
    "controller_selected_evidence_present",
    "controller_selected_evidence_report_index",
    "controller_selected_evidence_source_frame",
    "controller_selected_evidence_message",
    "controller_selected_evidence_has_pmkid",
    "repeat_requested", "repeat_request_generation",
)

SYNTHETIC_PRESENTER_SEMANTICS = {
    "outcome": {
        "view": "result", "tone": "positive", "row_count": 4,
        "title": "capture_result", "headline": "full_handshake",
    },
    "actions": {
        "view": "actions", "tone": "neutral", "row_count": 2,
        "title": "authentication_actions",
        "headline": "authentication_actions",
    },
    "peer_detail": {
        "view": "peer_detail", "tone": "positive", "row_count": 4,
        "title": "authentication_peer",
        "headline": "authentication_peer",
    },
    "evidence_list": {
        "view": "evidence_list", "tone": "neutral", "row_count": 4,
        "title": "authentication_evidence",
        "headline": "authentication_evidence",
    },
    "evidence_detail": {
        "view": "evidence_detail", "tone": "neutral", "row_count": 4,
        "title": "authentication_evidence_detail",
        "headline": "authentication_evidence_detail",
    },
}


def controller_semantic_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Return only stable controller semantics, excluding repaint counters."""
    return {name: state.get(name) for name in SYNTHETIC_CONTROLLER_FIELDS}


def synthetic_controller_failures(
        state: dict[str, Any], label: str, expected_view: str,
        *, action_selection: int = 0, selected_action: str = "details",
        peer_selection: int = 0, peer_position: int = 0,
        peer_mask: int = 0x0f, peer_evidence: int = 4,
        evidence_selection: int = 0, evidence_report_index: int = 0,
        evidence_source_frame: int = 0,
        evidence_message: str = "message_1",
        evidence_has_pmkid: bool = True,
        repeat_requested: bool = False,
        repeat_request_generation: int = 0) -> list[str]:
    """Validate the exact deterministic full-profile controller state."""
    presenter = dict(SYNTHETIC_PRESENTER_SEMANTICS[expected_view])
    if expected_view == "peer_detail" and peer_mask != 0x0f:
        presenter["tone"] = "caution"
    expected = {
        "schema": AUTH_SCHEMA, "kind": "state", "read_only_query": True,
        "view": "authentication_capture", "state": "result",
        "failure": "none", "capture_active": False,
        "capture_cleanup_complete": True,
        "adapter_cleanup_complete": True,
        "synthetic": True, "report_origin": "synthetic_hil",
        "outcome": "complete", "uncertainty": 0,
        "evidence": 6, "peers": 2, "complete_peers": 1,
        "pmkids": 1, "source_frames": 6,
        "presenter_view": presenter["view"],
        "presenter_tone": presenter["tone"],
        "presenter_evidence_incomplete": False,
        "presenter_report_openable": True,
        "presenter_cleanup_complete": True,
        "presenter_row_count": presenter["row_count"],
        "presenter_synthetic": True,
        "presenter_synthetic_label_visible": True,
        "presenter_title_semantic": presenter["title"],
        "presenter_headline_semantic": presenter["headline"],
        "presenter_note_semantic": "simulated_data",
        "controller_ready": True,
        "controller_view": expected_view,
        "controller_action_count": 2,
        "controller_action_selection": action_selection,
        "controller_selected_action": selected_action,
        "controller_peer_count": 2,
        "controller_peer_selection": peer_selection,
        "controller_peer_position": peer_position,
        "controller_selected_peer_mask": peer_mask,
        "controller_selected_peer_evidence_count": peer_evidence,
        "controller_evidence_count": 6,
        "controller_evidence_selection": evidence_selection,
        "controller_selected_evidence_present": True,
        "controller_selected_evidence_report_index": evidence_report_index,
        "controller_selected_evidence_source_frame": evidence_source_frame,
        "controller_selected_evidence_message": evidence_message,
        "controller_selected_evidence_has_pmkid": evidence_has_pmkid,
        "repeat_requested": repeat_requested,
        "repeat_request_generation": repeat_request_generation,
    }
    return expect(state, expected, label)


def navigation_repaint_failures(
        before: dict[str, Any], after: dict[str, Any], label: str,
        *, expected_chrome_delta: int) -> list[str]:
    """Require one content-only UI delta and never a full-screen clear."""
    failures: list[str] = []
    fields = ("generation", "content_repaints", "full_repaints",
              "chrome_repaints")
    for name in fields:
        if not all(non_negative_integer(state.get(name))
                   for state in (before, after)):
            failures.append(f"{label}.{name}: missing repaint counter")
    if failures:
        return failures
    if after["generation"] != before["generation"]:
        failures.append(f"{label}.generation: changed during navigation")
    if after["content_repaints"] <= before["content_repaints"]:
        failures.append(f"{label}.content: no incremental repaint")
    if after["full_repaints"] != before["full_repaints"]:
        failures.append(f"{label}.full: full-screen clear observed")
    if after["chrome_repaints"] - before["chrome_repaints"] != \
            expected_chrome_delta:
        failures.append(f"{label}.chrome: unexpected localized delta")
    return failures


def navigation_pixel_delta_failures(
        delta: dict[str, int], label: str,
        *, title_change_required: bool,
        footer_change_required: bool | None = None) -> list[str]:
    """Check physical pixels without treating the dynamic title as static."""
    failures = terminal_pixel_delta_failures(delta, label)
    # The terminal helper requires both title and status changes. Navigation
    # keeps RX/TX status stable and only some controller views change title.
    failures = [
        failure for failure in failures
        if not failure.endswith("title: lifecycle title stayed stale") and
        not failure.endswith("status: RX/TX status stayed stale")
    ]
    if title_change_required and delta.get("title_changed_pixels", 0) <= 0:
        failures.append(f"{label}.title: expected localized title repaint")
    if not title_change_required and delta.get("title_changed_pixels") != 0:
        failures.append(f"{label}.title: unchanged title was repainted")
    if footer_change_required is not None and \
            (delta.get("footer_changed_pixels", 0) > 0) != \
            footer_change_required:
        failures.append(f"{label}.footer: navigation hint delta mismatch")
    if delta.get("status_changed_pixels") != 0:
        failures.append(f"{label}.status: static RX/TX status changed")
    return failures


def report_accounting_failures(state: dict[str, Any],
                               label: str) -> list[str]:
    failures: list[str] = []
    for name in REPORT_COUNTER_FIELDS:
        if not non_negative_integer(state.get(name)):
            failures.append(f"{label}.{name}: expected a non-negative integer")
    if failures:
        return failures
    inspected = min(state["source_frames"], 64)
    if state["frames_read"] + state["source_read_failures"] != inspected:
        failures.append(f"{label}.source_inspection_partition: mismatch")
    classified = (state["classified_key_frames"] +
                  state["unclassified_key_frames"] +
                  state["unsupported_key_frames"])
    if state["eapol_key_frames"] != classified:
        failures.append(f"{label}.key_classification_partition: mismatch")
    decoded = (state["analysis_frames_ignored"] +
               state["malformed_frames"] + state["truncated_frames"] +
               classified)
    if state["frames_read"] != decoded:
        failures.append(f"{label}.decode_partition: mismatch")
    if (state["data_frames"] > state["frames_read"] or
            state["eapol_key_frames"] > state["eapol_frames"] or
            state["eapol_frames"] > state["frames_read"]):
        failures.append(f"{label}.counter_bounds: invalid")
    if state["evidence"] + state["evidence_dropped"] != \
            state["eapol_key_frames"]:
        failures.append(f"{label}.evidence_partition: mismatch")
    if state["report_capture_frames_reported"] != \
            state["analysis_frames_reported"]:
        failures.append(f"{label}.report_capture_reported: mismatch")
    if state["report_capture_frames_accepted"] != \
            state["analysis_frames_accepted"]:
        failures.append(f"{label}.report_capture_accepted: mismatch")
    if state["source_frames"] != state["report_capture_frames_accepted"]:
        failures.append(f"{label}.source_frames: retained source mismatch")
    if state["report_capture_frames_dropped_capacity"] != \
            state["analysis_dropped_capacity"]:
        failures.append(f"{label}.report_capture_capacity: mismatch")
    if state["report_capture_frames_dropped_invalid"] != \
            state["analysis_dropped_invalid"]:
        failures.append(f"{label}.report_capture_invalid: mismatch")
    complete_peers = state.get("complete_peers")
    if (not non_negative_integer(complete_peers) or
            complete_peers > state["peers"]):
        failures.append(f"{label}.complete_peers: invalid")
        return failures
    expected_uncertainty = 0
    if (state["report_capture_frames_dropped_capacity"] or
            state["report_capture_frames_dropped_invalid"]):
        expected_uncertainty |= UNCERTAINTY_CAPTURE_LOSS
    if state["source_read_failures"]:
        expected_uncertainty |= UNCERTAINTY_SOURCE_READ
    if state["malformed_frames"]:
        expected_uncertainty |= UNCERTAINTY_MALFORMED
    if state["truncated_frames"]:
        expected_uncertainty |= UNCERTAINTY_TRUNCATED
    if (state["source_frames"] > 64 or state["evidence_dropped"] or
            state["peers_dropped"] or state["pmkids_dropped"]):
        expected_uncertainty |= UNCERTAINTY_CAPACITY
    if state["eapol_key_frames"] == 0:
        expected_uncertainty |= UNCERTAINTY_NO_EVIDENCE
    if state["unclassified_key_frames"] or \
            state["unsupported_key_frames"]:
        expected_uncertainty |= UNCERTAINTY_UNSUPPORTED
    if state["uncertainty"] != expected_uncertainty:
        failures.append(
            f"{label}.uncertainty: {state['uncertainty']} != "
            f"{expected_uncertainty}")
    expected_outcome = (
        "inconclusive" if expected_uncertainty else
        ("complete" if complete_peers else "incomplete"))
    if state.get("outcome") != expected_outcome:
        failures.append(
            f"{label}.outcome: {state.get('outcome')!r} != "
            f"{expected_outcome!r}")
    return failures


def presenter_failures(state: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    product_state = state.get("state")
    outcome = state.get("outcome")
    expected: tuple[str, str, bool, bool, bool, int] | None = None
    if product_state == "waiting_for_survey_stop":
        expected = (
            "cancelling" if state.get("cancel_pending") else "preparing",
            "caution" if state.get("cancel_pending") else "neutral",
            False, False, False, 0)
    elif product_state == "running":
        expected = ("running", "neutral", False, False, False, 4)
    elif product_state == "result" and outcome == "complete":
        expected = ("result", "positive", False, True, True, 4)
    elif product_state == "result" and outcome == "incomplete":
        expected = ("result", "caution", False, True, True, 4)
    elif product_state == "result" and outcome == "inconclusive":
        expected = ("inconclusive", "caution", True, True, True, 4)
    if expected is None:
        failures.append(
            f"{label}.presenter: unsupported state/outcome projection")
        return failures
    actual = (
        state.get("presenter_view"), state.get("presenter_tone"),
        state.get("presenter_evidence_incomplete"),
        state.get("presenter_report_openable"),
        state.get("presenter_cleanup_complete"),
        state.get("presenter_row_count"))
    if actual != expected:
        failures.append(
            f"{label}.presenter: {actual!r} != {expected!r}")
    if state.get("failure") != "none":
        failures.append(f"{label}.failure: expected none")
    return failures


def repaint_delta_failures(before: dict[str, Any], after: dict[str, Any],
                           label: str) -> list[str]:
    failures: list[str] = []
    fields = ("generation", "content_repaints", "full_repaints",
              "chrome_repaints")
    for name in fields:
        if not non_negative_integer(before.get(name)) or not \
                non_negative_integer(after.get(name)):
            failures.append(f"{label}.{name}: missing counter")
    if failures:
        return failures
    if before["generation"] == 0 or \
            after["generation"] != before["generation"]:
        failures.append(f"{label}.generation: changed or zero")
    if after["content_repaints"] <= before["content_repaints"]:
        failures.append(f"{label}.content_repaints: no live content repaint")
    if after["full_repaints"] != before["full_repaints"]:
        failures.append(f"{label}.full_repaints: live full repaint observed")
    if after["chrome_repaints"] != before["chrome_repaints"]:
        failures.append(f"{label}.chrome_repaints: live chrome repaint observed")
    return failures


def home_wifi(device: PassiveSerial,
              trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = read_only_query(device, b"ui.state", UI_SCHEMA, "state")
    for _ in range(10):
        if state.get("page") == "home":
            break
        state = action(device, "back")
        trace.append(state)
    if state.get("page") != "home":
        raise RuntimeError(
            f"cannot reach Home: {privacy_safe_repr(state)}")
    for _ in range(10):
        if int(state.get("selection", -1)) == 0:
            break
        state = action(device, "up")
        trace.append(state)
    require_exact(state, {
        "page": "home", "selection": 0, "selected_id": "wifi",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "home_wifi")
    return state


def select_authorized_network(
        device: PassiveSerial, allowed_label_hash: str,
        label: str) -> dict[str, Any]:
    """Select the strongest exact authorized SSID without retaining its ID."""
    command = f"{NETWORK_SELECTOR_COMMAND} {allowed_label_hash}".encode(
        "ascii")
    deadline = time.monotonic() + 30.0
    attempts = 0
    selected: dict[str, Any] = {}
    while time.monotonic() < deadline:
        attempts += 1
        selected = query(
            device, command, NETWORK_SELECTOR_SCHEMA, "state", timeout=2.0)
        if selected.get("status") == "selected":
            break
        if selected.get("status") not in ("not_found", "runtime_not_ready"):
            raise RuntimeError(
                f"{label}: authorized selector rejected unsafe state")
        time.sleep(0.5)
    if selected.get("status") != "selected":
        raise RuntimeError(
            f"{label}: authorized network absent after bounded retries")
    require_exact(selected, {
        "schema": NETWORK_SELECTOR_SCHEMA,
        "kind": "state", "status": "selected", "selected": True,
        "strongest_match": True, "hil_active": True,
        "display_touched": True, "rf_hardware_touched": False,
        "radio_started": False, "storage_mounted": False,
        "storage_written": False, "identifier_disclosed": False,
        "response_complete": True,
    }, f"{label}_authorized_network_selector")
    matches = selected.get("match_count")
    if (not isinstance(matches, int) or isinstance(matches, bool) or
            matches < 1):
        raise RuntimeError(
            f"{label}: authorized network selector returned no match")
    selected["host_selector_attempts"] = attempts
    selected["host_selector_transient_retries"] = attempts - 1
    return selected


def enter_network_detail(
        device: PassiveSerial,
        trace: list[dict[str, Any]],
        label: str,
        allowed_label_hash: str,
        mount_diagnostics: dict[str, Any] | None = None,
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    preparing = action(device, "right")
    trace.append(preparing)
    require_exact(preparing, {
        "page": "survey", "wifi_product_view": "networks",
        "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_selected_source_mask": 1,
    }, f"{label}_networks_preparing")
    try:
        network_list = wait_ui_state(
            device,
            lambda state: (
                state.get("wifi_product_view") == "networks" and
                state.get("survey_workflow_state") == "running" and
                state.get("survey_product_worker_ready") is True and
                state.get("wifi_networks_strongest_first") is True and
                int(state.get("wifi_networks_unique", 0)) >= 1 and
                int(state.get("survey_product_wifi_scan_cycles", 0)) >= 1
            ), 45.0, f"{label}: nearby Wi-Fi network did not appear")
    except UiStateWaitTimeout as error:
        if mount_diagnostics is not None:
            mount_diagnostics[label] = {
                "completed": False,
                "last_ui_state": error.last_state,
                "host_wait_transport_timeouts":
                    len(error.transport_errors),
                "host_wait_transport_errors": error.transport_errors,
            }
        raise
    if mount_diagnostics is not None:
        mount_diagnostics[label] = {
            "completed": True,
            "last_ui_state": filesystem_mount_telemetry(network_list),
            "host_wait_transport_timeouts": network_list.get(
                "host_wait_transport_timeouts", 0),
            "host_wait_transport_errors": network_list.get(
                "host_wait_transport_errors", []),
        }
    require_exact(network_list, {
        "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_worker_ready": True,
        "survey_product_status": "running",
        "survey_product_active_source_mask": 1,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_store_open_attempted": True,
        "survey_product_store_status": "permitted",
        "survey_product_admission_status": "permitted",
        "survey_product_filesystem_mount_stage": "mounted",
        "survey_product_filesystem_bus_initialize_error": 0,
        "survey_product_filesystem_drive_available_before_vfs": True,
        "survey_product_filesystem_mount_error": 0,
        "survey_scan_status": "valid", "survey_scan_dropped": 0,
    }, f"{label}_networks_live")
    mount_attempts = network_list.get(
        "survey_product_filesystem_mount_attempts")
    mount_retries = network_list.get(
        "survey_product_filesystem_mount_transient_retries")
    mount_last_failure = network_list.get(
        "survey_product_filesystem_mount_last_failure_error")
    mount_attempts_total = network_list.get(
        "survey_product_mount_attempts_total")
    mount_successes_total = network_list.get(
        "survey_product_mount_successes_total")
    heap_fields = (
        "survey_product_filesystem_heap_free_before_bus",
        "survey_product_filesystem_heap_largest_before_bus",
        "survey_product_filesystem_heap_free_before_vfs",
        "survey_product_filesystem_heap_largest_before_vfs",
    )
    if (not isinstance(mount_attempts, int) or
            isinstance(mount_attempts, bool) or
            not 1 <= mount_attempts <= 3 or
            mount_retries != mount_attempts - 1 or
            mount_last_failure != (257 if mount_retries else 0) or
            not isinstance(mount_attempts_total, int) or
            isinstance(mount_attempts_total, bool) or
            mount_attempts_total < mount_attempts or
            not isinstance(mount_successes_total, int) or
            isinstance(mount_successes_total, bool) or
            mount_successes_total < 1 or
            mount_successes_total > mount_attempts_total or
            any(not non_negative_integer(network_list.get(name)) or
                network_list[name] == 0 for name in heap_fields)):
        raise RuntimeError(
            f"{label}: invalid filesystem remount accounting: "
            f"{privacy_safe_repr(network_list)}")
    network_list["authorized_selector"] = select_authorized_network(
        device, allowed_label_hash, label)
    detail_ui = action(device, "right")
    trace.append(detail_ui)
    require_exact(detail_ui, {
        "wifi_product_view": "network_detail",
        "wifi_network_navigation_locked": True,
        "runtime_owner": "wifi", "lease_mask": 15,
    }, f"{label}_detail_ui")
    detail = read_only_query(
        device, b"wifi.network.detail",
        "leshy.wifi.network_detail.v1", "state")
    require_exact(detail, {
        "active": True, "passive": True,
        "active_probe_allowed": False,
    }, f"{label}_detail")
    if (not isinstance(detail.get("identity_hash"), int) or
            detail["identity_hash"] == 0 or
            not isinstance(detail.get("channel"), int) or
            not 1 <= detail["channel"] <= 13):
        raise RuntimeError(
            f"{label}: network detail has no fixed identity/channel: "
            f"{privacy_safe_repr(detail)}")
    return network_list, detail_ui, detail


def run_minimal_ambient_terminal(
        device: PassiveSerial,
        trace: list[dict[str, Any]],
        label: str,
        allowed_label_hash: str,
        mount_diagnostics: dict[str, Any],
        ) -> dict[str, Any]:
    """Reach a second honest terminal report without synthetic shortcuts."""
    home_wifi(device, trace)
    wifi_menu = action(device, "right")
    trace.append(wifi_menu)
    require_exact(wifi_menu, {
        "page": "survey", "wifi_product_view": "menu",
        "wifi_product_selection": 0, "runtime_owner": "wifi",
        "lease_mask": 15,
    }, f"{label}_wifi_menu")
    wait_ui_state(
        device, wifi_menu_quiescent, 15.0,
        f"{label}: Wi-Fi menu did not become quiescent")
    network_list, detail_ui, detail = enter_network_detail(
        device, trace, label, allowed_label_hash, mount_diagnostics)
    requested_ui = action(device, "right")
    trace.append(requested_ui)
    require_exact(requested_ui, {
        "wifi_product_view": "authentication_capture",
        "runtime_event": "authentication_waiting_for_survey_stop",
        "runtime_owner": "wifi", "lease_mask": 15,
    }, f"{label}_requested_ui")
    requested = auth_state(device)
    running = requested if requested.get("state") != \
        "waiting_for_survey_stop" else wait_auth_state(
            device, authentication_start_state, 15.0,
            f"{label}: authentication capture did not start")
    if running.get("state") != "running":
        raise RuntimeError(
            f"{label}: authentication capture did not run: "
            f"{privacy_safe_repr(running)}")
    require_exact(running, {
        "view": "authentication_capture", "synthetic": False,
        "report_origin": NO_REPORT_ORIGIN, "passive": True,
        "tx_path": False, "connect_path": False,
        "target_selected": True, "target_selection_continuity": True,
        "channel": detail["channel"], "capture_state": "running",
        "capture_active": True, "capture_cleanup_complete": False,
        "adapter_cleanup_complete": False,
        "esp_rf_owned_by_foreground": True,
    }, f"{label}_running")
    capture_running = capture_state(device)
    require_exact(capture_running, {
        "state": "running", "passive_only": True, "rx_only": True,
        "application_connect_calls": 0, "application_raw_tx_calls": 0,
        "channel_plan": detail["channel"],
        "current_channel": detail["channel"],
        "cleanup_complete": False, "lease_mask": 15,
    }, f"{label}_capture_running")
    terminal = wait_auth_state(
        device, lambda state: state.get("state") in ("result", "failed"),
        13.0, f"{label}: authentication capture did not finish")
    if terminal.get("state") != "result":
        raise RuntimeError(
            f"{label}: authentication capture failed: "
            f"{privacy_safe_repr(terminal)}")
    require_exact(terminal, {
        "view": "authentication_capture", "synthetic": False,
        "report_origin": AMBIENT_REPORT_ORIGIN, "passive": True,
        "tx_path": False, "connect_path": False,
        "target_selected": True, "target_selection_continuity": True,
        "channel": detail["channel"], "capture_state": "complete",
        "capture_active": False, "capture_cleanup_complete": True,
        "adapter_cleanup_complete": True, "failure": "none",
        "esp_rf_owned_by_foreground": True,
    }, f"{label}_terminal")
    capture_terminal = capture_state(device)
    require_exact(capture_terminal, {
        "state": "complete", "passive_only": True, "rx_only": True,
        "application_connect_calls": 0, "application_raw_tx_calls": 0,
        "channel_plan": detail["channel"],
        "current_channel": detail["channel"],
        "cleanup_complete": True, "lease_mask": 15,
    }, f"{label}_capture_terminal")
    return {
        "wifi_menu": wifi_menu,
        "network_list": network_list,
        "network_detail_ui": detail_ui,
        "network_detail": detail,
        "requested_ui": requested_ui,
        "requested": requested,
        "running": running,
        "capture_running": capture_running,
        "terminal": terminal,
        "capture_terminal": capture_terminal,
    }


def ingress_accounting_failures(state: dict[str, Any],
                                label: str) -> list[str]:
    failures: list[str] = []
    names = (
        "frames_reported", "frames_accepted", "frames_dropped_capacity",
        "frames_dropped_invalid", "frames_observed", "frames_ignored",
        "ingress_invalid", "candidates", "candidates_accepted",
        "candidates_dropped", "uncertainty", "evidence", "peers", "pmkids",
    )
    for name in names:
        value = state.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            failures.append(f"{label}.{name}: expected a non-negative integer")
    if failures:
        return failures
    observed = state["frames_observed"]
    ingress_total = (state["frames_ignored"] + state["ingress_invalid"] +
                     state["candidates"])
    if observed != ingress_total:
        failures.append(
            f"{label}.ingress_accounting: {observed} != {ingress_total}")
    retained_total = state["candidates_accepted"] + state["candidates_dropped"]
    if state["candidates"] != retained_total:
        failures.append(
            f"{label}.candidate_accounting: {state['candidates']} != "
            f"{retained_total}")
    projections = {
        "frames_reported": "candidates",
        "frames_accepted": "candidates_accepted",
        "frames_dropped_capacity": "candidates_dropped",
    }
    for capture_name, ingress_name in projections.items():
        if state[capture_name] != state[ingress_name]:
            failures.append(
                f"{label}.{capture_name}: {state[capture_name]} != "
                f"{ingress_name} {state[ingress_name]}")
    if state["frames_dropped_invalid"] != 0:
        failures.append(
            f"{label}.frames_dropped_invalid: append-layer loss is nonzero")
    expected_analysis_reported = state["candidates"] + state["ingress_invalid"]
    analysis_projection = {
        "analysis_frames_reported": expected_analysis_reported,
        "analysis_frames_accepted": state["candidates_accepted"],
        "analysis_dropped_capacity": state["candidates_dropped"],
        "analysis_dropped_invalid": state["ingress_invalid"],
        "analysis_accounting_valid": True,
    }
    for name, expected in analysis_projection.items():
        if state.get(name) != expected:
            failures.append(
                f"{label}.{name}: {state.get(name)!r} != {expected!r}")
    outcome = state.get("outcome")
    if outcome not in ("complete", "incomplete", "inconclusive"):
        failures.append(f"{label}.outcome: unsupported {outcome!r}")
    loss = state["ingress_invalid"] + state["candidates_dropped"]
    if (state["evidence"] == 0 or loss != 0) and outcome != "inconclusive":
        failures.append(
            f"{label}.outcome: absent/lost evidence must be inconclusive")
    if state["evidence"] == 0:
        if state["peers"] != 0 or state["pmkids"] != 0:
            failures.append(f"{label}.empty_evidence_projection: nonempty result")
        if state["uncertainty"] & UNCERTAINTY_NO_EVIDENCE == 0:
            failures.append(f"{label}.uncertainty: no-evidence bit is missing")
    if outcome == "complete" and (state["peers"] < 1 or state["evidence"] < 4):
        failures.append(f"{label}.complete: insufficient retained evidence")
    if outcome == "incomplete" and state["evidence"] < 1:
        failures.append(f"{label}.incomplete: no retained evidence")
    failures.extend(report_accounting_failures(state, label))
    failures.extend(presenter_failures(state, label))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--allowed-ssid-fnv1a64", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if args.port == FORBIDDEN_FIXTURE_PORT:
        parser.error("board-02/fixture port is forbidden for CAP049")
    if args.port != BOARD_PORT:
        parser.error(f"CAP049 is bound to {BOARD_ID} at {BOARD_PORT}")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if (len(args.source_commit) != 40 or
            any(character not in "0123456789abcdefABCDEF"
                for character in args.source_commit)):
        parser.error("--source-commit must be a full hexadecimal Git commit ID")
    if (re.fullmatch(r"[0-9a-fA-F]{16}", args.allowed_ssid_fnv1a64) is None or
            int(args.allowed_ssid_fnv1a64, 16) == 0):
        parser.error(
            "--allowed-ssid-fnv1a64 must be one non-zero 64-bit hex value")
    allowed_label_hash = args.allowed_ssid_fnv1a64.lower()
    if not args.flash or args.reuse_exact_flash:
        parser.error("CAP049 requires exactly one fresh app flash (--flash)")

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
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    post_hil_end: dict[str, Any] = {}
    wifi_menu_ready_state: dict[str, Any] = {}
    cancel_network_list: dict[str, Any] = {}
    cancel_network_detail_ui: dict[str, Any] = {}
    cancel_network_detail: dict[str, Any] = {}
    cancel_hold: dict[str, Any] = {}
    cancel_requested_ui: dict[str, Any] = {}
    cancel_requested: dict[str, Any] = {}
    cancel_back_ui: dict[str, Any] = {}
    cancel_pending: dict[str, Any] = {}
    cancel_terminal_ui: dict[str, Any] = {}
    cancel_terminal: dict[str, Any] = {}
    cancel_capture_terminal: dict[str, Any] = {}
    network_list: dict[str, Any] = {}
    network_detail_ui: dict[str, Any] = {}
    network_detail: dict[str, Any] = {}
    auth_requested_ui: dict[str, Any] = {}
    auth_requested: dict[str, Any] = {}
    auth_running: dict[str, Any] = {}
    auth_render_before: dict[str, Any] = {}
    auth_render_after: dict[str, Any] = {}
    capture_running: dict[str, Any] = {}
    auth_terminal: dict[str, Any] = {}
    capture_terminal: dict[str, Any] = {}
    auth_after_back: dict[str, Any] = {}
    menu_after_back: dict[str, Any] = {}
    home_after_back: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    start_failure_diagnostics: dict[str, Any] = {}
    filesystem_mount_diagnostics: dict[str, Any] = {}
    final_diagnostic_errors: list[str] = []
    delta: dict[str, int] = {}
    repaint_delta: dict[str, int] = {}
    terminal_repaint_delta: dict[str, int] = {}
    terminal_pixel_delta: dict[str, int] = {}
    ambient_rf_proof: dict[str, Any] = {}
    synthetic_ui_proof: dict[str, Any] = {}
    synthetic_fixture_ack: dict[str, Any] = {}
    synthetic_fixture_replay: dict[str, Any] = {}
    synthetic_navigation: dict[str, dict[str, Any]] = {}
    synthetic_pixel_deltas: dict[str, dict[str, int]] = {}
    synthetic_back_cleanup: dict[str, Any] = {}
    hil_session_cycle: dict[str, Any] = {}
    host_capture_elapsed_ms: float | None = None
    flash_completed = False
    candidate_verified = False
    hil_started = False
    workflow_completed = False

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flash_completed = True
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                candidate_verified = candidate_verification_succeeded(
                    fresh_flash_requested=args.flash,
                    reuse_exact_requested=args.reuse_exact_flash,
                    flash_completed=flash_completed,
                    exact_boot_verified=True)
                if not candidate_verified:
                    raise RuntimeError("exact candidate verification failed")
                cleanup_before = robust_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)
                hil_started = True

                home_wifi(device, trace)
                wifi_menu = action(device, "right")
                trace.append(wifi_menu)
                require_exact(wifi_menu, {
                    "page": "survey", "wifi_product_view": "menu",
                    "wifi_product_selection": 0, "runtime_owner": "wifi",
                    "lease_mask": 15,
                }, "wifi_menu")
                wifi_menu_ready_state = wait_ui_state(
                    device, wifi_menu_quiescent, 15.0,
                    "Wi-Fi menu did not become quiescent before Networks")
                # First prove the highest-risk lifecycle edge: Back while the
                # shared survey worker is still stopping must not start a
                # capture and must return to an entirely quiescent Wi-Fi menu.
                (cancel_network_list, cancel_network_detail_ui,
                 cancel_network_detail) = enter_network_detail(
                    device, trace, "cancel", allowed_label_hash,
                    filesystem_mount_diagnostics)
                hold_pre_arm_state = auth_state(device)
                hold_armed_at = time.monotonic()
                cancel_hold = arm_authentication_survey_stop_hold(
                    device, hold_pre_arm_state)
                cancel_requested_ui = bounded_hold_navigation(
                    device, "right", hold_armed_at,
                    lambda state: (
                        state.get("wifi_product_view") ==
                            "authentication_capture" and
                        state.get("runtime_event") ==
                            "authentication_waiting_for_survey_stop" and
                        state.get("runtime_owner") == "wifi" and
                        state.get("lease_mask") == 15))
                trace.append(cancel_requested_ui)
                if cancel_requested_ui.get(
                        "host_navigation_ack_received") is True:
                    require_exact(cancel_requested_ui, {
                        "wifi_product_view": "authentication_capture",
                        "runtime_event":
                            "authentication_waiting_for_survey_stop",
                        "runtime_owner": "wifi", "lease_mask": 15,
                    }, "cancel_requested_ui")
                # Do not insert another read here: a lost Right ACK must not
                # consume the 1.5 s hold.  The later read-only state proves both
                # one-shot keys even when either transport ACK was lost.
                cancel_back_ui = bounded_hold_navigation(
                    device, "left", hold_armed_at,
                    lambda state: (
                        state.get("wifi_product_view") ==
                            "authentication_capture" and
                        state.get("runtime_event") ==
                            "authentication_back_waiting_for_survey_stop" and
                        state.get("runtime_owner") == "wifi" and
                        state.get("lease_mask") == 15 and
                        state.get("changed") is True))
                trace.append(cancel_back_ui)
                if cancel_back_ui.get(
                        "host_navigation_ack_received") is True:
                    require_exact(cancel_back_ui, {
                        "wifi_product_view": "authentication_capture",
                        "runtime_event":
                            "authentication_back_waiting_for_survey_stop",
                        "runtime_owner": "wifi", "lease_mask": 15,
                        "changed": True,
                    }, "cancel_back_ui")
                cancel_hold["host_back_after_arm_ms"] = cancel_back_ui[
                    "host_navigation_write_after_arm_ms"]
                if cancel_hold["host_back_after_arm_ms"] >= \
                        AUTH_HOLD_TIMEOUT_MS:
                    raise RuntimeError(
                        "Back did not arrive before the bounded HIL hold timeout")
                cancel_pending = auth_state(device)
                cancel_generation = cancel_pending.get("generation")
                if not non_negative_integer(cancel_generation) or \
                        cancel_generation == 0:
                    raise RuntimeError("cancel lifecycle has no generation")
                if (cancel_pending.get("generation") != cancel_generation or
                        cancel_pending.get("back_during_wait_observed") is not
                        True):
                    raise RuntimeError(
                        "Back-during-wait was not retained in diagnostics")
                if cancel_pending.get("state") == "waiting_for_survey_stop":
                    require_exact(cancel_pending, {
                        "view": "authentication_capture",
                        "cancel_pending": True, "failure": "none",
                    }, "cancel_pending")
                    failures.extend(presenter_failures(
                        cancel_pending, "cancel_pending"))
                elif cancel_pending.get("state") != "idle":
                    raise RuntimeError(
                        "unexpected cancel transition: "
                        f"{privacy_safe_repr(cancel_pending)}")
                cancel_terminal_ui = wait_ui_state(
                    device,
                    lambda state: (
                        state.get("wifi_product_view") == "menu" and
                        state.get("runtime_owner") == "wifi" and
                        state.get("lease_mask") == 15),
                    15.0, "Back-during-wait did not return to Wi-Fi menu")
                cancel_terminal = auth_state(device)
                require_exact(cancel_terminal, {
                    "view": "menu", "state": "idle",
                    "generation": cancel_generation,
                    "cancel_pending": False,
                    "back_during_wait_observed": True,
                    "failure": "none", "capture_state": "idle",
                    "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                    "survey_worker_deadline_armed": False,
                    "survey_terminal_hold_armed": False,
                    "esp_rf_owned_by_foreground": True,
                }, "cancel_terminal")
                cancel_capture_terminal = capture_state(device)
                require_exact(cancel_capture_terminal, {
                    "state": "idle", "passive_only": True,
                    "rx_only": True, "application_connect_calls": 0,
                    "application_raw_tx_calls": 0,
                    "cleanup_complete": True, "lease_mask": 15,
                }, "cancel_capture_terminal")

                # Start a fresh, complete capture lifecycle after cancellation.
                network_list, network_detail_ui, network_detail = \
                    enter_network_detail(
                        device, trace, "capture", allowed_label_hash,
                        filesystem_mount_diagnostics)
                second_mount_attempts = network_list[
                    "survey_product_filesystem_mount_attempts"]
                if (network_list["survey_product_mount_attempts_total"] !=
                        cancel_network_list[
                            "survey_product_mount_attempts_total"] +
                        second_mount_attempts or
                        network_list[
                            "survey_product_mount_successes_total"] !=
                        cancel_network_list[
                            "survey_product_mount_successes_total"] + 1):
                    raise RuntimeError(
                        "same-boot second ProductSurvey start did not prove "
                        "a fresh bounded filesystem remount")

                auth_requested_ui = action(device, "right")
                trace.append(auth_requested_ui)
                require_exact(auth_requested_ui, {
                    "wifi_product_view": "authentication_capture",
                    "runtime_event": "authentication_waiting_for_survey_stop",
                    "runtime_owner": "wifi", "lease_mask": 15,
                }, "auth_requested_ui")
                auth_requested = auth_state(device)
                require_exact(auth_requested, {
                    "view": "authentication_capture",
                    "cancel_pending": False,
                    "back_during_wait_observed": False,
                    "passive": True,
                    "tx_path": False, "connect_path": False,
                }, "auth_requested")
                generation = auth_requested.get("generation")
                if (not non_negative_integer(generation) or generation == 0 or
                        generation <= cancel_generation):
                    raise RuntimeError(
                        "capture generation did not advance after cancellation")
                if auth_requested.get("target_selected") is not True or \
                        auth_requested.get(
                            "target_selection_continuity") is not True:
                    raise RuntimeError(
                        "authentication target lost selected-detail continuity")
                if auth_requested.get("channel") != network_detail["channel"]:
                    raise RuntimeError(
                        "authentication target channel differs from NetworkDetail")

                if auth_requested.get("state") == "waiting_for_survey_stop":
                    failures.extend(presenter_failures(
                        auth_requested, "auth_requested"))
                    auth_running = wait_auth_state(
                        device, authentication_start_state, 15.0,
                        "authentication capture did not reach a terminal "
                        "start outcome")
                else:
                    auth_running = auth_requested
                if auth_running.get("state") == "failed":
                    start_failure_diagnostics = \
                        collect_authentication_failure_diagnostics(
                            device, auth_running)
                    failures.extend(start_failure_diagnostic_failures(
                        start_failure_diagnostics))
                    raise RuntimeError(
                        "authentication capture adapter start failed; exact "
                        "driver/stage/heap diagnostics retained")
                if auth_running.get("state") != "running":
                    raise RuntimeError(
                        f"authentication capture skipped running proof: "
                        f"{privacy_safe_repr(auth_running)}")
                require_exact(auth_running, {
                    "view": "authentication_capture", "passive": True,
                    "generation": generation,
                    "cancel_pending": False,
                    "back_during_wait_observed": False,
                    "failure": "none",
                    "tx_path": False, "connect_path": False,
                    "target_selected": True,
                    "target_selection_continuity": True,
                    "channel": network_detail["channel"],
                    "duration_ms": CAPTURE_DURATION_MS,
                    "maximum_frames": 16, "snap_length": 256,
                    "capture_state": "running", "capture_active": True,
                    "capture_cleanup_complete": False,
                    "adapter_cleanup_complete": False,
                    "adapter_driver_error": 0,
                    "adapter_failure_stage": "none",
                    "esp_rf_owned_by_foreground": True,
                }, "auth_running")
                for name in ("adapter_heap_free_before_init",
                             "adapter_heap_largest_before_init"):
                    if not non_negative_integer(auth_running.get(name)) or \
                            auth_running[name] == 0:
                        failures.append(f"auth_running.{name}: expected > 0")
                failures.extend(presenter_failures(
                    auth_running, "auth_running"))
                capture_running = capture_state(device)
                require_exact(capture_running, {
                    "state": "running", "passive_only": True,
                    "rx_only": True, "application_connect_calls": 0,
                    "application_raw_tx_calls": 0,
                    "physical_no_tx_verified": False,
                    "channel_plan": network_detail["channel"],
                    "current_channel": network_detail["channel"],
                    "duration_ms": CAPTURE_DURATION_MS,
                    "snap_length": 256, "maximum_frames": 16,
                    "cleanup_complete": False, "lease_mask": 15,
                }, "capture_running")
                running_observed_at = time.monotonic()
                screens["running_first"] = capture_evidence_safe(
                    device, frames, "wifi-auth-running-first")
                auth_render_before = auth_state(device)
                if auth_render_before.get("state") != "running":
                    raise RuntimeError(
                        "capture terminated before two running screenshots")
                time.sleep(0.75)
                screens["running_second"] = capture_evidence_safe(
                    device, frames, "wifi-auth-running-second")
                auth_render_after = auth_state(device)
                if auth_render_after.get("state") != "running":
                    raise RuntimeError(
                        "capture terminated before live repaint proof")
                delta = pixel_changes(
                    frames, "wifi-auth-running-first",
                    "wifi-auth-running-second")
                failures.extend(repaint_delta_failures(
                    auth_render_before, auth_render_after,
                    "live_repaint"))
                if delta["content_changed_pixels"] <= 0 or \
                        delta["static_chrome_changed_pixels"] != 0:
                    raise RuntimeError(
                        f"authentication live redraw delta invalid: {delta}")
                if all(non_negative_integer(state.get(name))
                       for state in (auth_render_before, auth_render_after)
                       for name in ("content_repaints", "full_repaints",
                                    "chrome_repaints")):
                    repaint_delta = {
                        "content_repaints":
                            auth_render_after["content_repaints"] -
                            auth_render_before["content_repaints"],
                        "full_repaints":
                            auth_render_after["full_repaints"] -
                            auth_render_before["full_repaints"],
                        "chrome_repaints":
                            auth_render_after["chrome_repaints"] -
                            auth_render_before["chrome_repaints"],
                    }

                auth_terminal = wait_auth_state(
                    device,
                    lambda state: state.get("state") in ("result", "failed"),
                    13.0, "10-second authentication capture did not finish")
                host_capture_elapsed_ms = (
                    time.monotonic() - running_observed_at) * 1000.0
                if auth_terminal.get("state") != "result":
                    start_failure_diagnostics = \
                        collect_authentication_failure_diagnostics(
                            device, auth_terminal)
                    failures.extend(start_failure_diagnostic_failures(
                        start_failure_diagnostics))
                    raise RuntimeError(
                        "authentication capture failed: "
                        f"{privacy_safe_repr(auth_terminal)}")
                require_exact(auth_terminal, {
                    "view": "authentication_capture", "passive": True,
                    "generation": generation,
                    "cancel_pending": False,
                    "back_during_wait_observed": False,
                    "failure": "none",
                    "tx_path": False, "connect_path": False,
                    "target_selected": True,
                    "target_selection_continuity": True,
                    "channel": network_detail["channel"],
                    "duration_ms": CAPTURE_DURATION_MS,
                    "maximum_frames": 16, "snap_length": 256,
                    "capture_state": "complete", "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                    "adapter_driver_error": 0,
                    "adapter_failure_stage": "none",
                    "survey_worker_deadline_armed": False,
                    "esp_rf_owned_by_foreground": True,
                }, "auth_terminal")
                for name in ("adapter_heap_free_before_init",
                             "adapter_heap_largest_before_init"):
                    if auth_terminal.get(name) != auth_running.get(name) or \
                            not non_negative_integer(auth_terminal.get(name)) or \
                            auth_terminal[name] == 0:
                        failures.append(
                            f"auth_terminal.{name}: missing/changed snapshot")
                failures.extend(ingress_accounting_failures(
                    auth_terminal, "auth_terminal"))
                for name in ("content_repaints", "full_repaints",
                             "chrome_repaints"):
                    if not all(non_negative_integer(state.get(name)) for state
                               in (auth_render_after, auth_terminal)):
                        failures.append(
                            f"terminal_repaint.{name}: missing counter")
                if not any(failure.startswith("terminal_repaint.")
                           for failure in failures):
                    terminal_repaint_delta = {
                        name: auth_terminal[name] - auth_render_after[name]
                        for name in ("content_repaints", "full_repaints",
                                     "chrome_repaints")
                    }
                    if (terminal_repaint_delta["content_repaints"] <= 0 or
                            terminal_repaint_delta["full_repaints"] != 0 or
                            terminal_repaint_delta["chrome_repaints"] != 1):
                        failures.append(
                            "terminal transition did not repaint exactly one "
                            "localized header region without a full clear")
                capture_terminal = capture_state(device)
                require_exact(capture_terminal, {
                    "state": "complete", "passive_only": True,
                    "rx_only": True, "application_connect_calls": 0,
                    "application_raw_tx_calls": 0,
                    "physical_no_tx_verified": False,
                    "channel_plan": network_detail["channel"],
                    "current_channel": network_detail["channel"],
                    "duration_ms": CAPTURE_DURATION_MS,
                    "snap_length": 256, "maximum_frames": 16,
                    "cleanup_complete": True, "lease_mask": 15,
                }, "capture_terminal")
                for capture_name, auth_name in (
                        ("frames_reported", "candidates"),
                        ("frames_accepted", "candidates_accepted"),
                        ("frames_dropped_capacity", "candidates_dropped"),
                        ("frames_dropped_invalid", "frames_dropped_invalid")):
                    if capture_terminal.get(capture_name) != \
                            auth_terminal.get(auth_name):
                        failures.append(
                            f"terminal.{capture_name}: capture/auth mismatch")
                started_us = capture_terminal.get("started_us")
                ended_us = capture_terminal.get("ended_us")
                if (not isinstance(started_us, int) or isinstance(started_us, bool)
                        or not isinstance(ended_us, int) or
                        isinstance(ended_us, bool)):
                    failures.append("terminal.capture_clock: missing")
                else:
                    elapsed_us = ended_us - started_us
                    if not (CAPTURE_DURATION_MS * 1000 <= elapsed_us <=
                            CAPTURE_DURATION_MS * 1000 +
                            CAPTURE_TERMINAL_SLACK_US):
                        failures.append(
                            f"terminal.capture_elapsed_us: {elapsed_us}")
                screens["result"] = capture_evidence_safe(
                    device, frames, "wifi-auth-result")
                terminal_pixel_delta = terminal_pixel_changes(
                    frames, "wifi-auth-running-second", "wifi-auth-result")
                failures.extend(terminal_pixel_delta_failures(
                    terminal_pixel_delta, "terminal_pixel_delta"))

                if (auth_terminal.get("synthetic") is not False or
                        auth_terminal.get("report_origin") !=
                            AMBIENT_REPORT_ORIGIN):
                    failures.append(
                        "ambient terminal was not exact real-RF evidence")
                ambient_rf_proof = {
                    "schema": "leshy.wifi.authentication.ambient_rf_proof.v1",
                    "synthetic": False,
                    "report_origin": AMBIENT_REPORT_ORIGIN,
                    "generation": auth_terminal.get("generation"),
                    "outcome": auth_terminal.get("outcome"),
                    "evidence": auth_terminal.get("evidence"),
                    "capture_state": capture_terminal.get("state"),
                    "capture_cleanup_complete": capture_terminal.get(
                        "cleanup_complete"),
                    "application_connect_calls": capture_terminal.get(
                        "application_connect_calls"),
                    "application_raw_tx_calls": capture_terminal.get(
                        "application_raw_tx_calls"),
                    "ambient_eapol_required": False,
                }

                # The ambient run above is the only RF evidence. The fixture
                # below replaces only the immutable terminal report so every
                # report-navigation branch can be checked deterministically.
                fixture_before = fixture_side_effect_snapshot(
                    auth_state(device), capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                synthetic_fixture_ack = load_synthetic_report_once(device)
                synthetic_outcome = auth_state(device)
                fixture_after = fixture_side_effect_snapshot(
                    synthetic_outcome, capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                fixture_isolation_failures = fixture_side_effect_failures(
                    fixture_before, fixture_after)
                failures.extend(fixture_isolation_failures)
                repeat_generation_before = synthetic_outcome.get(
                    "repeat_request_generation")
                if not non_negative_integer(repeat_generation_before):
                    raise RuntimeError(
                        "synthetic outcome lacks repeat request generation")
                failures.extend(synthetic_controller_failures(
                    synthetic_outcome, "synthetic_outcome", "outcome",
                    repeat_request_generation=repeat_generation_before))
                if synthetic_fixture_ack.get("generation") != \
                        synthetic_outcome.get("generation"):
                    failures.append(
                        "synthetic fixture/report generation mismatch")
                synthetic_navigation["outcome"] = synthetic_outcome
                screens["synthetic_outcome"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-outcome")
                ambient_to_synthetic_note = pixel_region_proof(
                    frames, "wifi-auth-result",
                    "wifi-auth-synthetic-outcome",
                    x0=NOTE_X0, x1=NOTE_X1, y0=NOTE_Y0, y1=NOTE_Y1)
                if (ambient_to_synthetic_note["changed_pixels"] < 80 or
                        ambient_to_synthetic_note["changed_rows"] < 7 or
                        ambient_to_synthetic_note["changed_columns"] < 32 or
                        ambient_to_synthetic_note["bbox_width"] < 40 or
                        ambient_to_synthetic_note["before_sha256"] ==
                        ambient_to_synthetic_note["after_sha256"]):
                    failures.append(
                        "synthetic simulated-data label has no physical "
                        "note-region delta")
                synthetic_fixture_replay = reject_synthetic_report_replay(
                    device)

                trace.append(action(device, "right"))
                actions_right = auth_state(device)
                synthetic_navigation["actions_right"] = actions_right
                failures.extend(synthetic_controller_failures(
                    actions_right, "synthetic_actions_right", "actions",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    synthetic_outcome, actions_right,
                    "synthetic_outcome_to_actions", expected_chrome_delta=1))
                screens["synthetic_actions"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-actions")
                synthetic_pixel_deltas["outcome_to_actions"] = \
                    terminal_pixel_changes(
                        frames, "wifi-auth-synthetic-outcome",
                        "wifi-auth-synthetic-actions")
                failures.extend(navigation_pixel_delta_failures(
                    synthetic_pixel_deltas["outcome_to_actions"],
                    "synthetic_outcome_to_actions",
                    title_change_required=True,
                    footer_change_required=True))

                trace.append(action(device, "left"))
                outcome_left = auth_state(device)
                synthetic_navigation["outcome_left"] = outcome_left
                failures.extend(synthetic_controller_failures(
                    outcome_left, "synthetic_outcome_left", "outcome",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_right, outcome_left, "synthetic_actions_left",
                    expected_chrome_delta=1))

                trace.append(action(device, "select"))
                actions_select = auth_state(device)
                synthetic_navigation["actions_select"] = actions_select
                failures.extend(synthetic_controller_failures(
                    actions_select, "synthetic_actions_select", "actions",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    outcome_left, actions_select,
                    "synthetic_outcome_select", expected_chrome_delta=1))
                if controller_semantic_snapshot(actions_select) != \
                        controller_semantic_snapshot(actions_right):
                    failures.append(
                        "Right and Select do not open equivalent Actions state")

                trace.append(action(device, "back"))
                outcome_back = auth_state(device)
                synthetic_navigation["outcome_back"] = outcome_back
                failures.extend(synthetic_controller_failures(
                    outcome_back, "synthetic_outcome_back", "outcome",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_select, outcome_back, "synthetic_actions_back",
                    expected_chrome_delta=1))
                if controller_semantic_snapshot(outcome_back) != \
                        controller_semantic_snapshot(outcome_left):
                    failures.append(
                        "Left and Back do not return equivalent Outcome state")

                trace.append(action(device, "right"))
                actions_details = auth_state(device)
                synthetic_navigation["actions_details"] = actions_details
                failures.extend(synthetic_controller_failures(
                    actions_details, "synthetic_actions_details", "actions",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    outcome_back, actions_details,
                    "synthetic_outcome_to_actions_details",
                    expected_chrome_delta=1))

                trace.append(action(device, "down"))
                actions_repeat = auth_state(device)
                synthetic_navigation["actions_repeat"] = actions_repeat
                failures.extend(synthetic_controller_failures(
                    actions_repeat, "synthetic_actions_repeat", "actions",
                    action_selection=1, selected_action="repeat",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_details, actions_repeat,
                    "synthetic_actions_down", expected_chrome_delta=0))

                trace.append(action(device, "up"))
                actions_details_again = auth_state(device)
                synthetic_navigation["actions_details_again"] = \
                    actions_details_again
                failures.extend(synthetic_controller_failures(
                    actions_details_again,
                    "synthetic_actions_details_again", "actions",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_repeat, actions_details_again,
                    "synthetic_actions_up", expected_chrome_delta=0))

                trace.append(action(device, "select"))
                peer_first = auth_state(device)
                synthetic_navigation["peer_first"] = peer_first
                failures.extend(synthetic_controller_failures(
                    peer_first, "synthetic_peer_first", "peer_detail",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_details_again, peer_first,
                    "synthetic_actions_to_peer", expected_chrome_delta=1))
                screens["synthetic_peer_first"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-peer-first")
                synthetic_pixel_deltas["actions_to_peer"] = \
                    terminal_pixel_changes(
                        frames, "wifi-auth-synthetic-actions",
                        "wifi-auth-synthetic-peer-first")
                failures.extend(navigation_pixel_delta_failures(
                    synthetic_pixel_deltas["actions_to_peer"],
                    "synthetic_actions_to_peer",
                    title_change_required=True,
                    footer_change_required=False))

                trace.append(action(device, "down"))
                peer_second = auth_state(device)
                synthetic_navigation["peer_second"] = peer_second
                failures.extend(synthetic_controller_failures(
                    peer_second, "synthetic_peer_second", "peer_detail",
                    peer_selection=1, peer_position=1, peer_mask=0x03,
                    peer_evidence=2,
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    peer_first, peer_second, "synthetic_peer_down",
                    expected_chrome_delta=1))
                screens["synthetic_peer_second"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-peer-second")
                synthetic_pixel_deltas["peer_first_to_second"] = \
                    terminal_pixel_changes(
                        frames, "wifi-auth-synthetic-peer-first",
                        "wifi-auth-synthetic-peer-second")
                failures.extend(navigation_pixel_delta_failures(
                    synthetic_pixel_deltas["peer_first_to_second"],
                    "synthetic_peer_first_to_second",
                    title_change_required=True,
                    footer_change_required=False))

                trace.append(action(device, "up"))
                peer_first_again = auth_state(device)
                synthetic_navigation["peer_first_again"] = peer_first_again
                failures.extend(synthetic_controller_failures(
                    peer_first_again, "synthetic_peer_first_again",
                    "peer_detail",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    peer_second, peer_first_again, "synthetic_peer_up",
                    expected_chrome_delta=1))

                trace.append(action(device, "right"))
                evidence_list = auth_state(device)
                synthetic_navigation["evidence_list"] = evidence_list
                failures.extend(synthetic_controller_failures(
                    evidence_list, "synthetic_evidence_list",
                    "evidence_list",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    peer_first_again, evidence_list,
                    "synthetic_peer_to_evidence", expected_chrome_delta=1))
                screens["synthetic_evidence_list"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-evidence-list")

                trace.append(action(device, "down"))
                evidence_second = auth_state(device)
                synthetic_navigation["evidence_second"] = evidence_second
                failures.extend(synthetic_controller_failures(
                    evidence_second, "synthetic_evidence_second",
                    "evidence_list", evidence_selection=1,
                    evidence_report_index=1, evidence_source_frame=1,
                    evidence_message="message_2", evidence_has_pmkid=False,
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    evidence_list, evidence_second,
                    "synthetic_evidence_down", expected_chrome_delta=0))

                trace.append(action(device, "up"))
                evidence_first_again = auth_state(device)
                synthetic_navigation["evidence_first_again"] = \
                    evidence_first_again
                failures.extend(synthetic_controller_failures(
                    evidence_first_again, "synthetic_evidence_first_again",
                    "evidence_list",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    evidence_second, evidence_first_again,
                    "synthetic_evidence_up", expected_chrome_delta=0))

                trace.append(action(device, "right"))
                evidence_detail = auth_state(device)
                synthetic_navigation["evidence_detail"] = evidence_detail
                failures.extend(synthetic_controller_failures(
                    evidence_detail, "synthetic_evidence_detail",
                    "evidence_detail",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    evidence_first_again, evidence_detail,
                    "synthetic_evidence_to_detail", expected_chrome_delta=1))
                screens["synthetic_evidence_detail"] = capture_evidence_safe(
                    device, frames, "wifi-auth-synthetic-evidence-detail")
                synthetic_pixel_deltas["evidence_list_to_detail"] = \
                    terminal_pixel_changes(
                        frames, "wifi-auth-synthetic-evidence-list",
                        "wifi-auth-synthetic-evidence-detail")
                failures.extend(navigation_pixel_delta_failures(
                    synthetic_pixel_deltas["evidence_list_to_detail"],
                    "synthetic_evidence_list_to_detail",
                    title_change_required=False,
                    footer_change_required=True))

                # Return to Actions and prove synthetic Repeat is recorded
                # exactly once, closes the overlay, and cannot start RF.
                trace.append(action(device, "left"))
                evidence_list_back = auth_state(device)
                synthetic_navigation["evidence_list_back"] = \
                    evidence_list_back
                failures.extend(synthetic_controller_failures(
                    evidence_list_back, "synthetic_evidence_list_back",
                    "evidence_list",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    evidence_detail, evidence_list_back,
                    "synthetic_detail_left", expected_chrome_delta=1))
                trace.append(action(device, "left"))
                peer_back = auth_state(device)
                synthetic_navigation["peer_back"] = peer_back
                failures.extend(synthetic_controller_failures(
                    peer_back, "synthetic_peer_back", "peer_detail",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    evidence_list_back, peer_back,
                    "synthetic_evidence_left", expected_chrome_delta=1))
                trace.append(action(device, "left"))
                actions_back = auth_state(device)
                synthetic_navigation["actions_back"] = actions_back
                failures.extend(synthetic_controller_failures(
                    actions_back, "synthetic_actions_back", "actions",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    peer_back, actions_back, "synthetic_peer_left",
                    expected_chrome_delta=1))
                trace.append(action(device, "down"))
                repeat_selected = auth_state(device)
                synthetic_navigation["repeat_selected"] = repeat_selected
                failures.extend(synthetic_controller_failures(
                    repeat_selected, "synthetic_repeat_selected", "actions",
                    action_selection=1, selected_action="repeat",
                    repeat_request_generation=repeat_generation_before))
                failures.extend(navigation_repaint_failures(
                    actions_back, repeat_selected,
                    "synthetic_repeat_down", expected_chrome_delta=0))

                production_continuity = fixture_before["auth_resource"]
                for navigation_name, navigation_state in \
                        synthetic_navigation.items():
                    failures.extend(production_continuity_failures(
                        production_continuity, navigation_state,
                        f"synthetic_{navigation_name}"))

                repeat_ack = action(device, "select")
                trace.append(repeat_ack)
                repeat_state = auth_state(device)
                repeat_request_generation = repeat_generation_before + 1
                if repeat_request_generation > 0xffffffff:
                    repeat_request_generation = 1
                require_exact(repeat_state, {
                    "view": "menu", "state": "idle",
                    "synthetic": False,
                    "report_origin": NO_REPORT_ORIGIN,
                    "generation": synthetic_outcome.get("generation"),
                    "repeat_requested": True,
                    "repeat_request_generation": repeat_request_generation,
                    "capture_state": "complete", "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                    "failure": "none", "passive": True,
                    "tx_path": False, "connect_path": False,
                    "esp_rf_owned_by_foreground": True,
                }, "synthetic_repeat_request")
                repeat_resource = fixture_side_effect_snapshot(
                    repeat_state, capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                failures.extend(fixture_side_effect_failures(
                    fixture_before, repeat_resource))
                failures.extend(production_continuity_failures(
                    production_continuity, repeat_state,
                    "synthetic_repeat_immediate"))
                time.sleep(0.15)
                repeat_delayed = auth_state(device)
                failures.extend(production_continuity_failures(
                    production_continuity, repeat_delayed,
                    "synthetic_repeat_delayed"))
                require_exact(repeat_delayed, {
                    "view": "menu", "state": "idle",
                    "synthetic": False,
                    "report_origin": NO_REPORT_ORIGIN,
                    "generation": synthetic_outcome.get("generation"),
                    "repeat_requested": True,
                    "repeat_request_generation": repeat_request_generation,
                    "capture_state": "complete", "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                }, "synthetic_repeat_delayed")
                synthetic_navigation["repeat_request"] = repeat_state
                synthetic_ui_proof = {
                    "schema":
                        "leshy.wifi.authentication.synthetic_ui_proof.v1",
                    "synthetic": True,
                    "report_origin": "synthetic_hil",
                    "export_eligibility": "not_evaluated",
                    "fixture": synthetic_fixture_ack,
                    "replay_rejected": synthetic_fixture_replay,
                    "side_effects": {
                        "schema":
                            "leshy.wifi.authentication.synthetic_side_effects.v1",
                        "production_continuity_proven":
                            not fixture_isolation_failures,
                        "boot_recovery_continuity":
                            fixture_before.get("boot_recovery") ==
                            fixture_after.get("boot_recovery"),
                        "product_storage_writes_measured": False,
                        "static_no_storage_api_contract_required": True,
                        "before": fixture_before,
                        "after": fixture_after,
                    },
                    "ambient_to_synthetic_note": ambient_to_synthetic_note,
                    "navigation": synthetic_navigation,
                    "right_select_equivalent":
                        controller_semantic_snapshot(actions_right) ==
                        controller_semantic_snapshot(actions_select),
                    "left_back_equivalent":
                        controller_semantic_snapshot(outcome_left) ==
                        controller_semantic_snapshot(outcome_back),
                    "pixel_deltas": synthetic_pixel_deltas,
                    "repeat_action": repeat_ack,
                    "repeat_request": repeat_state,
                    "repeat_resource": repeat_resource,
                    "repeat_delayed": repeat_delayed,
                    "production_continuity": production_continuity,
                }

                repeat_menu = repeat_ack
                require_exact(repeat_menu, {
                    "wifi_product_view": "menu", "wifi_product_selection": 0,
                    "runtime_owner": "wifi", "lease_mask": 15,
                }, "synthetic_repeat_menu")
                home_after_repeat = action(device, "left")
                trace.append(home_after_repeat)
                require_exact(home_after_repeat, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "synthetic_repeat_home")

                # A second authenticated HIL session resets the one-shot fixture.
                # Reach a fresh terminal state through the real passive capture,
                # then exercise Outcome -> Back itself (not a renamed Repeat ACK).
                hil_session_cycle["end"] = end_hil_session(
                    device, run_id, app_identity)
                hil_started = False
                hil_session_cycle["begin"] = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)
                hil_started = True
                back_ambient = run_minimal_ambient_terminal(
                    device, trace, "synthetic_back", allowed_label_hash,
                    filesystem_mount_diagnostics)
                back_ambient_state = auth_state(device)
                back_repeat_generation = back_ambient_state.get(
                    "repeat_request_generation")
                if not non_negative_integer(back_repeat_generation):
                    raise RuntimeError(
                        "synthetic Back baseline lacks repeat generation")
                back_fixture_before = fixture_side_effect_snapshot(
                    back_ambient_state, capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                back_fixture_ack = load_synthetic_report_once(device)
                back_outcome = auth_state(device)
                back_fixture_after = fixture_side_effect_snapshot(
                    back_outcome, capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                failures.extend(fixture_side_effect_failures(
                    back_fixture_before, back_fixture_after))
                failures.extend(synthetic_controller_failures(
                    back_outcome, "synthetic_back_outcome", "outcome",
                    repeat_request_generation=back_repeat_generation))
                if back_fixture_ack.get("generation") != \
                        back_outcome.get("generation"):
                    failures.append(
                        "synthetic Back fixture/report generation mismatch")
                back_replay = reject_synthetic_report_replay(device)
                back_production_continuity = \
                    back_fixture_before["auth_resource"]
                failures.extend(production_continuity_failures(
                    back_production_continuity, back_outcome,
                    "synthetic_back_outcome"))

                menu_after_back = action(device, "back")
                trace.append(menu_after_back)
                require_exact(menu_after_back, {
                    "wifi_product_view": "menu", "wifi_product_selection": 0,
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "changed": True,
                }, "synthetic_terminal_back_menu")
                auth_after_back = auth_state(device)
                require_exact(auth_after_back, {
                    "view": "menu", "state": "idle",
                    "synthetic": False,
                    "report_origin": NO_REPORT_ORIGIN,
                    "generation": back_outcome.get("generation"),
                    "cancel_pending": False,
                    "back_during_wait_observed": False,
                    "repeat_requested": False,
                    "repeat_request_generation": back_repeat_generation,
                    "failure": "none",
                    "capture_state": "complete", "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                    "survey_worker_deadline_armed": False,
                    "esp_rf_owned_by_foreground": True,
                }, "synthetic_terminal_back_state")
                back_resource = fixture_side_effect_snapshot(
                    auth_after_back, capture_state(device),
                    read_only_query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state"))
                failures.extend(fixture_side_effect_failures(
                    back_fixture_before, back_resource))
                failures.extend(production_continuity_failures(
                    back_production_continuity, auth_after_back,
                    "synthetic_terminal_back"))
                time.sleep(0.15)
                back_delayed = auth_state(device)
                failures.extend(production_continuity_failures(
                    back_production_continuity, back_delayed,
                    "synthetic_terminal_back_delayed"))
                require_exact(back_delayed, {
                    "view": "menu", "state": "idle", "synthetic": False,
                    "report_origin": NO_REPORT_ORIGIN,
                    "generation": back_outcome.get("generation"),
                    "repeat_requested": False,
                    "repeat_request_generation": back_repeat_generation,
                    "capture_state": "complete", "capture_active": False,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                }, "synthetic_terminal_back_delayed")
                home_after_back = action(device, "left")
                trace.append(home_after_back)
                require_exact(home_after_back, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "back_home")
                screens["home_final"] = capture_evidence_safe(
                    device, frames, "wifi-auth-home-final")
                synthetic_back_cleanup = {
                    "schema":
                        "leshy.wifi.authentication.synthetic_back_cleanup.v1",
                    "session_cycle": hil_session_cycle,
                    "ambient": back_ambient,
                    "fixture": back_fixture_ack,
                    "replay_rejected": back_replay,
                    "baseline_resource": back_fixture_before,
                    "loaded_resource": back_fixture_after,
                    "outcome": back_outcome,
                    "back_action": menu_after_back,
                    "back_state": auth_after_back,
                    "back_resource": back_resource,
                    "back_delayed": back_delayed,
                    "home": home_after_back,
                    "production_continuity": back_production_continuity,
                    "boot_recovery_continuity":
                        back_fixture_before.get("boot_recovery") ==
                        back_resource.get("boot_recovery"),
                    "product_storage_writes_measured": False,
                    "static_no_storage_api_contract_required": True,
                }

                input_state = read_only_query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "nrf_ce_inactive": True,
                    "software_quiesce_complete": True,
                }, "safe_outputs"))
                for name in ("generation", "observations"):
                    if recovery_after.get(name) != recovery_before.get(name):
                        failures.append(f"persistent {name} changed")
                workflow_completed = True
            except Exception as error:
                failures.append(
                    f"workflow: {privacy_safe_exception(error)}")
            finally:
                diagnostics, diagnostic_errors = \
                    best_effort_final_diagnostics(device)
                final_diagnostic_errors.extend(diagnostic_errors)
                if workflow_completed:
                    failures.extend(
                        f"final_diagnostics: {error}"
                        for error in diagnostic_errors)
                input_state = diagnostics.get("input", input_state)
                safe_outputs = diagnostics.get("safe_outputs", safe_outputs)
                recovery_after = diagnostics.get("recovery", recovery_after)
                try:
                    cleanup_after = retain_cleanup_mount_telemetry(
                        robust_cleanup(device))
                    if not cleanup_after.get("complete"):
                        failures.append("cleanup_after: Home/zero lease unproven")
                except Exception as error:
                    failures.append(
                        f"cleanup_after: {privacy_safe_exception(error)}")
                finally:
                    if hil_started:
                        try:
                            hil_end = end_hil_session(
                                device, run_id, app_identity)
                            require_exact(hil_end, {"active": False},
                                          "hil_session_end")
                            post_hil_end = {
                                "hil": read_only_query(
                                    device, b"hil.state",
                                    HIL_SESSION_SCHEMA, "state"),
                                "ui": read_only_query(
                                    device, b"ui.state", UI_SCHEMA, "state"),
                                "auth": auth_state(device),
                            }
                            require_exact(post_hil_end["hil"], {
                                "active": False,
                            }, "post_hil_end_hil")
                            require_exact(post_hil_end["ui"], {
                                "page": "home", "runtime_owner": "none",
                                "lease_mask": 0,
                            }, "post_hil_end_ui")
                            require_exact(post_hil_end["auth"], {
                                "view": "none", "state": "idle",
                                "synthetic": False,
                                "production_report_fingerprint":
                                    "unavailable",
                                "production_report_fingerprint_scope": "none",
                            }, "post_hil_end_auth")
                        except Exception as error:
                            failures.append(
                                "hil_session_end: "
                                f"{privacy_safe_exception(error)}")
    except Exception as error:
        failures.append(f"runner: {privacy_safe_exception(error)}")

    passed = candidate_verified and not failures
    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": passed,
        "gate_eligible": passed,
        "failures": failures,
        "device": {"board_id": BOARD_ID, "port": args.port},
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit.lower(),
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": candidate_verified,
            "flash_completed": flash_completed,
            "exact_boot_verified": candidate_verified,
            "flash_mode": "fresh",
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "hil_session": {"begin": hil_begin, "end": hil_end},
        "post_hil_end": post_hil_end,
        "wifi_menu_ready": wifi_menu_ready_state,
        "cancel_network_list": cancel_network_list,
        "cancel_network_detail_ui": cancel_network_detail_ui,
        "cancel_network_detail": cancel_network_detail,
        "cancel_hold": cancel_hold,
        "cancel_requested_ui": cancel_requested_ui,
        "cancel_requested": cancel_requested,
        "cancel_back_ui": cancel_back_ui,
        "cancel_pending": cancel_pending,
        "cancel_terminal_ui": cancel_terminal_ui,
        "cancel_terminal": cancel_terminal,
        "cancel_capture_terminal": cancel_capture_terminal,
        "network_list": network_list,
        "network_detail_ui": network_detail_ui,
        "network_detail": network_detail,
        "auth_requested_ui": auth_requested_ui,
        "auth_requested": auth_requested,
        "auth_running": auth_running,
        "auth_render_before": auth_render_before,
        "auth_render_after": auth_render_after,
        "capture_running": capture_running,
        "auth_terminal": auth_terminal,
        "capture_terminal": capture_terminal,
        "ambient_rf_proof": ambient_rf_proof,
        "synthetic_ui_proof": synthetic_ui_proof,
        "synthetic_back_cleanup": synthetic_back_cleanup,
        "auth_after_back": auth_after_back,
        "menu_after_back": menu_after_back,
        "home_after_back": home_after_back,
        "host_capture_elapsed_ms": host_capture_elapsed_ms,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "start_failure_diagnostics": start_failure_diagnostics,
        "filesystem_mount_diagnostics": filesystem_mount_diagnostics,
        "final_diagnostic_errors": final_diagnostic_errors,
        "screens": screens,
        "pixel_delta": delta,
        "repaint_delta": repaint_delta,
        "terminal_repaint_delta": terminal_repaint_delta,
        "terminal_pixel_delta": terminal_pixel_delta,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": candidate_verified and flash_completed,
            "manual_button_presses": 0,
            "screenshots_automatic": set(screens) == {
                "running_first", "running_second", "result", "home_final",
                "synthetic_outcome", "synthetic_actions",
                "synthetic_peer_first", "synthetic_peer_second",
                "synthetic_evidence_list", "synthetic_evidence_detail"},
            "application_rx_only": passed,
            "application_wifi_connect_calls": 0 if passed else None,
            "application_raw_tx_calls": 0 if passed else None,
            "physical_no_tx_instrumented": False,
            "ambient_eapol_required": False,
            "ambient_capture_lifecycle_proven":
                ambient_rf_proof.get("synthetic") is False and
                ambient_rf_proof.get("report_origin") ==
                    AMBIENT_REPORT_ORIGIN,
            "ambient_authentication_evidence_observed":
                isinstance(ambient_rf_proof.get("evidence"), int) and
                ambient_rf_proof.get("evidence", 0) > 0,
            "synthetic_ui_proven":
                synthetic_ui_proof.get("synthetic") is True and
                synthetic_ui_proof.get("report_origin") == "synthetic_hil",
            "synthetic_fixture_display_touched":
                synthetic_fixture_ack.get("display_touched"),
            "synthetic_fixture_rf_hardware_touched":
                synthetic_fixture_ack.get("rf_hardware_touched"),
            "synthetic_fixture_radio_started":
                synthetic_fixture_ack.get("radio_started"),
            "synthetic_fixture_connect_calls":
                synthetic_fixture_ack.get("connect_calls"),
            "synthetic_fixture_raw_tx_calls":
                synthetic_fixture_ack.get("raw_tx_calls"),
            "synthetic_label_visible": synthetic_ui_proof.get(
                "navigation", {}).get("outcome", {}).get(
                    "presenter_synthetic_label_visible") is True,
            "synthetic_production_continuity_proven":
                synthetic_ui_proof.get("side_effects", {}).get(
                    "production_continuity_proven") is True,
            "synthetic_boot_recovery_continuity_proven":
                synthetic_ui_proof.get("side_effects", {}).get(
                    "boot_recovery_continuity") is True,
            "product_storage_writes_measured": False,
            "static_no_storage_api_contract_required": True,
            "synthetic_replay_rejected":
                synthetic_fixture_replay.get("status") == "replay_rejected",
            "right_select_equivalent": synthetic_ui_proof.get(
                "right_select_equivalent") is True,
            "left_back_equivalent": synthetic_ui_proof.get(
                "left_back_equivalent") is True,
            "repeat_request_proven": synthetic_ui_proof.get(
                "repeat_request", {}).get("repeat_requested") is True,
            "repeat_delayed_stable": synthetic_ui_proof.get(
                "repeat_delayed", {}).get("repeat_requested") is True,
            "terminal_back_cleanup_proven":
                synthetic_back_cleanup.get("back_state", {}).get(
                    "synthetic") is False and
                synthetic_back_cleanup.get("back_state", {}).get(
                    "repeat_requested") is False and
                synthetic_back_cleanup.get("home", {}).get(
                    "lease_mask") == 0,
            "production_continuity_proven": bool(
                synthetic_ui_proof.get("production_continuity")),
            "post_hil_end_proven": bool(post_hil_end),
            "export_eligibility": "not_evaluated",
            "mac_wifi_control_calls": 0,
            "mac_ble_fixture_calls": 0,
            "fixture_ports_opened": [],
            "fixed_target_continuity": passed,
            "fixed_channel_continuity": passed,
            "capture_duration_ms": CAPTURE_DURATION_MS,
            "back_during_wait_proven":
                cancel_terminal.get("back_during_wait_observed") is True,
            "survey_stop_hold_bounded":
                (cancel_hold.get("host_arm_action_writes") == 1 and
                 cancel_hold.get("host_arm_action_replays") == 0 and
                 cancel_hold.get("armed_state", {}).get(
                     "survey_terminal_hold_armed") is True and
                 (cancel_hold.get("host_arm_ack_received") is False or
                  cancel_hold.get("ack", {}).get("timeout_ms") ==
                    AUTH_HOLD_TIMEOUT_MS) and
                 cancel_hold.get("host_back_after_arm_ms", float("inf")) <
                    AUTH_HOLD_TIMEOUT_MS and
                 cancel_terminal.get("survey_terminal_hold_armed") is False),
            "generation_advanced_after_cancel":
                (non_negative_integer(cancel_terminal.get("generation")) and
                 non_negative_integer(auth_terminal.get("generation")) and
                 auth_terminal["generation"] >
                    cancel_terminal["generation"]),
            "content_changed_pixels": delta.get("content_changed_pixels"),
            "static_chrome_changed_pixels": delta.get(
                "static_chrome_changed_pixels"),
            "live_content_repaints": repaint_delta.get("content_repaints"),
            "live_full_repaints": repaint_delta.get("full_repaints"),
            "live_chrome_repaints": repaint_delta.get("chrome_repaints"),
            "terminal_content_changed_pixels": terminal_pixel_delta.get(
                "content_changed_pixels"),
            "terminal_title_changed_pixels": terminal_pixel_delta.get(
                "title_changed_pixels"),
            "terminal_status_changed_pixels": terminal_pixel_delta.get(
                "status_changed_pixels"),
            "terminal_unexpected_static_chrome_changed_pixels":
                terminal_pixel_delta.get(
                    "unexpected_static_chrome_changed_pixels"),
            "complete_cleanup": cleanup_after.get("complete") is True,
            "final_lease_mask": cleanup_after.get(
                "final_state", {}).get("lease_mask"),
        },
        "privacy": {
            "generic_target_ui": True,
            "private_target_identifiers_retained": False,
        },
    }
    result, final_passed = finalize_evidence_result(
        result, failures, passed)
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if final_passed else "failed",
        "failures": failures,
        "output": str(args.output),
        "outcome": auth_terminal.get("outcome"),
        "static_chrome_changed_pixels": delta.get(
            "static_chrome_changed_pixels"),
        "final_lease_mask": cleanup_after.get(
            "final_state", {}).get("lease_mask"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if final_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
