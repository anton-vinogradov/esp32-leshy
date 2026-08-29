#!/usr/bin/env python3
"""Independently verify one CAP049 board-01 delta-HIL bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.wifi.authentication_capture_hil.run.v1"
AUTH_SCHEMA = "leshy.wifi.authentication_capture.v1"
CAPTURE_SCHEMA = "leshy.capture.wifi_frame.v1"
RECOVERY_SCHEMA = "leshy.storage.product_boot_recovery.v1"
AUTH_HOLD_SCHEMA = "leshy.wifi.authentication.hil_hold.v1"
SYNTHETIC_FIXTURE_SCHEMA = \
    "leshy.wifi.authentication.synthetic_fixture.v1"
AMBIENT_REPORT_ORIGIN = "ambient_rf"
NO_REPORT_ORIGIN = "none"
RUNNER = Path(__file__).with_name("run_1x_wifi_authentication_capture_hil.py")
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
AUTH_HOLD_ACK_TIMEOUT_MS = 250.0
AUTH_HOLD_STATE_TIMEOUT_MS = 250.0
AUTH_HOLD_NAV_ACK_TIMEOUT_MS = 250.0
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
PRIVATE_TARGET_KEYS = frozenset({
    "target_bssid", "target_identity_hash", "identity_hash",
    "wifi_network_selected_identity_hash", "ssid", "bssid", "target_label",
    "wifi_network_order_hash", "wifi_device_order_hash",
})
MAC_ADDRESS = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
SCREEN_NAMES = {
    "running_first": "wifi-auth-running-first",
    "running_second": "wifi-auth-running-second",
    "result": "wifi-auth-result",
    "home_final": "wifi-auth-home-final",
    "synthetic_outcome": "wifi-auth-synthetic-outcome",
    "synthetic_actions": "wifi-auth-synthetic-actions",
    "synthetic_peer_first": "wifi-auth-synthetic-peer-first",
    "synthetic_peer_second": "wifi-auth-synthetic-peer-second",
    "synthetic_evidence_list": "wifi-auth-synthetic-evidence-list",
    "synthetic_evidence_detail": "wifi-auth-synthetic-evidence-detail",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_region_proof(frames: Path, before_name: str, after_name: str,
                       *, x0: int, x1: int, y0: int,
                       y1: int) -> dict[str, Any] | None:
    before_path = frames / f"{before_name}.rgb565"
    after_path = frames / f"{after_name}.rgb565"
    if not before_path.is_file() or not after_path.is_file():
        return None
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    if len(before) != WIDTH * HEIGHT * 2 or len(after) != len(before):
        return None
    before_region = bytearray()
    after_region = bytearray()
    changed = 0
    changed_rows: set[int] = set()
    changed_columns: set[int] = set()
    for y in range(y0, y1):
        start = (y * WIDTH + x0) * 2
        end = (y * WIDTH + x1) * 2
        before_row = before[start:end]
        after_row = after[start:end]
        before_region.extend(before_row)
        after_region.extend(after_row)
        changed += sum(
            before_row[offset:offset + 2] != after_row[offset:offset + 2]
            for offset in range(0, len(before_row), 2))
        for offset in range(0, len(before_row), 2):
            if before_row[offset:offset + 2] != after_row[offset:offset + 2]:
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


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def verify_product_mount(failures: list[str], state: dict[str, Any],
                         label: str) -> None:
    attempts = state.get("survey_product_filesystem_mount_attempts")
    retries = state.get(
        "survey_product_filesystem_mount_transient_retries")
    last_failure = state.get(
        "survey_product_filesystem_mount_last_failure_error")
    attempts_total = state.get("survey_product_mount_attempts_total")
    successes_total = state.get("survey_product_mount_successes_total")
    drive_available = state.get(
        "survey_product_filesystem_drive_available_before_vfs")
    heap_fields = (
        "survey_product_filesystem_heap_free_before_bus",
        "survey_product_filesystem_heap_largest_before_bus",
        "survey_product_filesystem_heap_free_before_vfs",
        "survey_product_filesystem_heap_largest_before_vfs",
    )
    require(failures,
            state.get("survey_product_backend_open") is False and
            state.get("survey_product_storage_mounted") is False and
            state.get("survey_product_store_open_attempted") is True and
            state.get("survey_product_store_status") == "permitted" and
            state.get("survey_product_admission_status") == "permitted" and
            state.get("survey_product_filesystem_mount_stage") == "mounted" and
            state.get("survey_product_filesystem_bus_initialize_error") == 0 and
            drive_available is True and
            state.get("survey_product_filesystem_mount_error") == 0,
            f"{label}: physical storage was not released after admission")
    require(failures,
            non_negative_integer(attempts) and 1 <= attempts <= 3 and
            retries == attempts - 1 and
            last_failure == (257 if retries else 0) and
            non_negative_integer(attempts_total) and
            attempts_total >= attempts and
            non_negative_integer(successes_total) and
            1 <= successes_total <= attempts_total and
            all(non_negative_integer(state.get(name)) and state[name] > 0
                for name in heap_fields),
            f"{label}: bounded filesystem remount accounting mismatch")


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


def controller_semantic_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {name: state.get(name) for name in SYNTHETIC_CONTROLLER_FIELDS}


def verify_synthetic_fixture_ack(
        failures: list[str], ack: dict[str, Any]) -> None:
    require(failures,
            ack.get("schema") == SYNTHETIC_FIXTURE_SCHEMA and
            ack.get("kind") == "loaded" and
            ack.get("status") == "loaded" and
            ack.get("loaded") is True and
            ack.get("synthetic") is True and
            ack.get("profile") == "full" and
            ack.get("report_identity") == "wifi-auth-ui-full-v1" and
            ack.get("one_shot") is True and
            ack.get("replayed") is False and
            ack.get("report_origin") == "synthetic_hil" and
            ack.get("hil_active") is True and
            ack.get("display_touched") is True and
            ack.get("rf_hardware_touched") is False and
            ack.get("radio_started") is False and
            ack.get("storage_mounted") is False and
            ack.get("storage_written") is False and
            ack.get("connect_calls") == 0 and
            ack.get("raw_tx_calls") == 0 and
            non_negative_integer(ack.get("generation")) and
            ack.get("generation", 0) > 0 and
            ack.get("host_fixture_action_writes") == 1 and
            ack.get("host_fixture_action_replays") == 0 and
            ack.get("host_fixture_ack_received") is True,
            "synthetic fixture load ACK contract mismatch")


def verify_synthetic_replay_rejected(
        failures: list[str], replay: dict[str, Any]) -> None:
    require(failures,
            replay.get("schema") == SYNTHETIC_FIXTURE_SCHEMA and
            replay.get("kind") == "error" and
            replay.get("status") == "replay_rejected" and
            replay.get("synthetic") is True and
            replay.get("loaded") is False and
            replay.get("profile") == "full" and
            replay.get("report_identity") == "wifi-auth-ui-full-v1" and
            replay.get("one_shot") is True and
            replay.get("replayed") is True and
            replay.get("report_origin") == "synthetic_hil" and
            replay.get("hil_active") is True and
            replay.get("display_touched") is False and
            replay.get("rf_hardware_touched") is False and
            replay.get("radio_started") is False and
            replay.get("storage_mounted") is False and
            replay.get("storage_written") is False and
            replay.get("connect_calls") == 0 and
            replay.get("raw_tx_calls") == 0 and
            replay.get("host_fixture_action_writes") == 1 and
            replay.get("host_fixture_action_replays") == 0 and
            replay.get("host_fixture_ack_received") is True,
            "synthetic fixture replay was not exactly rejected")


def verify_synthetic_controller_state(
        failures: list[str], state: dict[str, Any], label: str,
        expected_view: str, *, action_selection: int = 0,
        selected_action: str = "details", peer_selection: int = 0,
        peer_position: int = 0, peer_mask: int = 0x0f,
        peer_evidence: int = 4, evidence_selection: int = 0,
        evidence_report_index: int = 0, evidence_source_frame: int = 0,
        evidence_message: str = "message_1",
        evidence_has_pmkid: bool = True,
        repeat_requested: bool = False,
        repeat_request_generation: int = 0) -> None:
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
        "controller_ready": True, "controller_view": expected_view,
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
    for name, value in expected.items():
        require(failures, state.get(name) == value,
                f"{label}.{name}: {state.get(name)!r} != {value!r}")


def verify_fixture_side_effects(
        failures: list[str], proof: dict[str, Any]) -> None:
    require(failures,
            proof.get("schema") ==
                "leshy.wifi.authentication.synthetic_side_effects.v1" and
            proof.get("production_continuity_proven") is True and
            proof.get("boot_recovery_continuity") is True and
            proof.get("product_storage_writes_measured") is False and
            proof.get("static_no_storage_api_contract_required") is True,
            "synthetic fixture continuity/scope declaration mismatch")
    before = proof.get("before", {})
    after = proof.get("after", {})
    require(failures, isinstance(before, dict) and before == after,
            "synthetic fixture changed a read-only resource snapshot")
    if not isinstance(before, dict):
        return
    auth = before.get("auth_resource", {})
    capture = before.get("capture", {})
    storage = before.get("boot_recovery", {})
    require(failures,
            set(auth) == set(AUTH_RESOURCE_FIELDS) and
            auth.get("schema") == AUTH_SCHEMA and
            auth.get("kind") == "state" and
            auth.get("read_only_query") is True and
            auth.get("capture_state") == "complete" and
            auth.get("capture_active") is False and
            auth.get("capture_cleanup_complete") is True and
            auth.get("adapter_cleanup_complete") is True and
            auth.get("esp_rf_owned_by_foreground") is True and
            isinstance(auth.get("production_report_fingerprint"), str) and
            re.fullmatch(
                r"[0-9a-f]{16}",
                auth.get("production_report_fingerprint", "")) is not None and
            auth.get("production_report_fingerprint_scope") == "hil_session" and
            auth.get("production_controller_report_bound") is True,
            "synthetic fixture auth resource baseline is unsafe")
    require(failures,
            capture.get("schema") == CAPTURE_SCHEMA and
            capture.get("kind") == "state" and
            capture.get("state") == "complete" and
            capture.get("passive_only") is True and
            capture.get("rx_only") is True and
            capture.get("application_connect_calls") == 0 and
            capture.get("application_raw_tx_calls") == 0 and
            capture.get("storage_written") is False and
            capture.get("cleanup_complete") is True and
            capture.get("lease_mask") == 15,
            "synthetic fixture capture baseline is unsafe")
    require(failures,
            storage.get("schema") == RECOVERY_SCHEMA and
            storage.get("kind") == "state" and
            storage.get("write_enabled") is False and
            storage.get("cleanup_complete") is True and
            storage.get("owned_after") == 0,
            "synthetic fixture boot-recovery baseline is unsafe")


def verify_navigation_repaint(
        failures: list[str], before: dict[str, Any], after: dict[str, Any],
        label: str, expected_chrome_delta: int) -> None:
    fields = ("generation", "content_repaints", "full_repaints",
              "chrome_repaints")
    if not all(non_negative_integer(state.get(name))
               for state in (before, after) for name in fields):
        failures.append(f"{label}: missing repaint counter")
        return
    require(failures, after["generation"] == before["generation"],
            f"{label}: report generation changed")
    require(failures,
            after["content_repaints"] > before["content_repaints"],
            f"{label}: content was not incrementally repainted")
    require(failures, after["full_repaints"] == before["full_repaints"],
            f"{label}: full-screen clear observed")
    require(failures,
            after["chrome_repaints"] - before["chrome_repaints"] ==
                expected_chrome_delta,
            f"{label}: unexpected localized chrome delta")


def verify_navigation_pixel_delta(
        failures: list[str], delta: dict[str, Any], label: str,
        title_change_required: bool,
        footer_change_required: bool | None = None) -> None:
    for name in (
            "content_changed_pixels", "title_changed_pixels",
            "status_changed_pixels", "footer_changed_pixels",
            "unexpected_static_chrome_changed_pixels"):
        require(failures, non_negative_integer(delta.get(name)),
                f"{label}.{name}: missing counter")
    if not all(non_negative_integer(delta.get(name)) for name in (
            "content_changed_pixels", "title_changed_pixels",
            "status_changed_pixels", "footer_changed_pixels",
            "unexpected_static_chrome_changed_pixels")):
        return
    require(failures, delta["content_changed_pixels"] > 0,
            f"{label}: content stayed stale")
    require(failures,
            (delta["title_changed_pixels"] > 0) == title_change_required,
            f"{label}: title delta mismatch")
    require(failures, delta["status_changed_pixels"] == 0,
            f"{label}: static status changed")
    if footer_change_required is not None:
        require(failures,
                (delta["footer_changed_pixels"] > 0) ==
                    footer_change_required,
                f"{label}: navigation footer delta mismatch")
    require(failures,
            delta["unexpected_static_chrome_changed_pixels"] == 0,
            f"{label}: static pixels changed")


def verify_ambient_and_synthetic_proofs(
        failures: list[str], run: dict[str, Any], root: Path) -> None:
    """Keep real RF evidence and deterministic UI evidence disjoint."""
    terminal = run.get("auth_terminal", {})
    capture_terminal = run.get("capture_terminal", {})
    ambient = run.get("ambient_rf_proof", {})
    require(failures,
            ambient.get("schema") ==
                "leshy.wifi.authentication.ambient_rf_proof.v1" and
            ambient.get("synthetic") is False and
            ambient.get("report_origin") == AMBIENT_REPORT_ORIGIN and
            terminal.get("synthetic") is False and
            terminal.get("report_origin") == AMBIENT_REPORT_ORIGIN and
            terminal.get("state") == "result" and
            ambient.get("generation") == terminal.get("generation") and
            ambient.get("outcome") == terminal.get("outcome") and
            ambient.get("evidence") == terminal.get("evidence") and
            ambient.get("capture_state") == capture_terminal.get("state") ==
                "complete" and
            ambient.get("capture_cleanup_complete") is True and
            capture_terminal.get("cleanup_complete") is True and
            ambient.get("application_connect_calls") == 0 and
            ambient.get("application_raw_tx_calls") == 0 and
            ambient.get("ambient_eapol_required") is False,
            "ambient RF proof is missing, synthetic, or not pre-injection")

    proof = run.get("synthetic_ui_proof", {})
    require(failures,
            proof.get("schema") ==
                "leshy.wifi.authentication.synthetic_ui_proof.v1" and
            proof.get("synthetic") is True and
            proof.get("report_origin") == "synthetic_hil" and
            proof.get("export_eligibility") == "not_evaluated" and
            proof.get("right_select_equivalent") is True and
            proof.get("left_back_equivalent") is True,
            "synthetic UI proof declaration mismatch")
    fixture = proof.get("fixture", {})
    replay = proof.get("replay_rejected", {})
    verify_synthetic_fixture_ack(failures, fixture)
    verify_synthetic_replay_rejected(failures, replay)
    verify_fixture_side_effects(failures, proof.get("side_effects", {}))

    note = pixel_region_proof(
        root / "frames", "wifi-auth-result",
        "wifi-auth-synthetic-outcome",
        x0=NOTE_X0, x1=NOTE_X1, y0=NOTE_Y0, y1=NOTE_Y1)
    require(failures,
            note is not None and
            note == proof.get("ambient_to_synthetic_note") and
            note.get("changed_pixels", 0) >= 80 and
            note.get("changed_rows", 0) >= 7 and
            note.get("changed_columns", 0) >= 32 and
            note.get("bbox_width", 0) >= 40 and
            note.get("before_sha256") != note.get("after_sha256"),
            "synthetic label lacks reproducible physical note-region delta")

    navigation = proof.get("navigation", {})
    require(failures, isinstance(navigation, dict),
            "synthetic navigation is not an exact state map")
    if not isinstance(navigation, dict):
        return
    repeat_before = navigation.get("outcome", {}).get(
        "repeat_request_generation")
    require(failures, non_negative_integer(repeat_before),
            "synthetic baseline repeat generation missing")
    if not non_negative_integer(repeat_before):
        return
    specs: dict[str, tuple[str, dict[str, Any]]] = {
        "outcome": ("outcome", {}),
        "actions_right": ("actions", {}),
        "outcome_left": ("outcome", {}),
        "actions_select": ("actions", {}),
        "outcome_back": ("outcome", {}),
        "actions_details": ("actions", {}),
        "actions_repeat": ("actions", {
            "action_selection": 1, "selected_action": "repeat"}),
        "actions_details_again": ("actions", {}),
        "peer_first": ("peer_detail", {}),
        "peer_second": ("peer_detail", {
            "peer_selection": 1, "peer_position": 1,
            "peer_mask": 0x03, "peer_evidence": 2}),
        "peer_first_again": ("peer_detail", {}),
        "evidence_list": ("evidence_list", {}),
        "evidence_second": ("evidence_list", {
            "evidence_selection": 1, "evidence_report_index": 1,
            "evidence_source_frame": 1,
            "evidence_message": "message_2",
            "evidence_has_pmkid": False}),
        "evidence_first_again": ("evidence_list", {}),
        "evidence_detail": ("evidence_detail", {}),
        "evidence_list_back": ("evidence_list", {}),
        "peer_back": ("peer_detail", {}),
        "actions_back": ("actions", {}),
        "repeat_selected": ("actions", {
            "action_selection": 1, "selected_action": "repeat"}),
    }
    require(failures, set(navigation) == set(specs) | {"repeat_request"},
            "synthetic navigation inventory mismatch")
    for name, (view, keyword) in specs.items():
        state = navigation.get(name, {})
        verify_synthetic_controller_state(
            failures, state, f"synthetic.navigation.{name}", view,
            repeat_request_generation=repeat_before, **keyword)

    continuity = proof.get("production_continuity", {})
    require(failures,
            isinstance(continuity, dict) and
            set(continuity) == set(AUTH_RESOURCE_FIELDS),
            "production continuity baseline is incomplete")
    if isinstance(continuity, dict):
        for name, state in navigation.items():
            if name == "repeat_request":
                continue
            projection = {
                field: state.get(field) for field in AUTH_RESOURCE_FIELDS}
            changed_fields = [
                field for field in AUTH_RESOURCE_FIELDS
                if projection.get(field) != continuity.get(field)]
            require(failures, projection == continuity,
                    f"production continuity changed at {name}: "
                    f"{changed_fields}")

    require(failures,
            controller_semantic_snapshot(navigation.get("actions_right", {})) ==
            controller_semantic_snapshot(navigation.get("actions_select", {})),
            "Right and Select are not semantically equivalent")
    require(failures,
            controller_semantic_snapshot(navigation.get("outcome_left", {})) ==
            controller_semantic_snapshot(navigation.get("outcome_back", {})),
            "Left and Back are not semantically equivalent")

    repaint_edges = (
        ("outcome", "actions_right", 1),
        ("actions_right", "outcome_left", 1),
        ("outcome_left", "actions_select", 1),
        ("actions_select", "outcome_back", 1),
        ("outcome_back", "actions_details", 1),
        ("actions_details", "actions_repeat", 0),
        ("actions_repeat", "actions_details_again", 0),
        ("actions_details_again", "peer_first", 1),
        ("peer_first", "peer_second", 0),
        ("peer_second", "peer_first_again", 0),
        ("peer_first_again", "evidence_list", 1),
        ("evidence_list", "evidence_second", 0),
        ("evidence_second", "evidence_first_again", 0),
        ("evidence_first_again", "evidence_detail", 1),
        ("evidence_detail", "evidence_list_back", 1),
        ("evidence_list_back", "peer_back", 1),
        ("peer_back", "actions_back", 1),
        ("actions_back", "repeat_selected", 0),
    )
    for before, after, chrome in repaint_edges:
        verify_navigation_repaint(
            failures, navigation.get(before, {}),
            navigation.get(after, {}),
            f"synthetic.repaint.{before}_to_{after}", chrome)

    repeat = navigation.get("repeat_request", {})
    expected_repeat_request = repeat_before + 1
    if expected_repeat_request > 0xffffffff:
        expected_repeat_request = 1
    require(failures,
            repeat.get("schema") == AUTH_SCHEMA and
            repeat.get("kind") == "state" and
            repeat.get("read_only_query") is True and
            repeat.get("view") == "menu" and
            repeat.get("state") == "idle" and
            repeat.get("synthetic") is False and
            repeat.get("report_origin") == NO_REPORT_ORIGIN and
            repeat.get("generation") == fixture.get("generation") and
            repeat.get("repeat_requested") is True and
            repeat.get("repeat_request_generation") ==
                expected_repeat_request and
            repeat.get("capture_state") == "complete" and
            repeat.get("capture_active") is False and
            repeat.get("capture_cleanup_complete") is True and
            repeat.get("adapter_cleanup_complete") is True and
            repeat.get("failure") == "none" and
            repeat.get("passive") is True and
            repeat.get("tx_path") is False and
            repeat.get("connect_path") is False and
            repeat.get("esp_rf_owned_by_foreground") is True,
            "synthetic Repeat was not safely suppressed")
    repeat_resource = proof.get("repeat_resource", {})
    side_effects = proof.get("side_effects", {})
    require(failures,
            repeat_resource == side_effects.get("before"),
            "synthetic Repeat changed production RF/storage resources")
    delayed = proof.get("repeat_delayed", {})
    require(failures,
            delayed.get("view") == "menu" and
            delayed.get("state") == "idle" and
            delayed.get("generation") == repeat.get("generation") and
            delayed.get("repeat_requested") is True and
            delayed.get("repeat_request_generation") ==
                repeat.get("repeat_request_generation") and
            delayed.get("capture_state") == "complete" and
            delayed.get("capture_active") is False and
            delayed.get("capture_cleanup_complete") is True and
            delayed.get("adapter_cleanup_complete") is True and
            {field: delayed.get(field) for field in AUTH_RESOURCE_FIELDS} ==
                continuity,
            "suppressed Repeat was not stable after delay")
    require(failures, proof.get("repeat_request") == repeat,
            "Repeat request proof is not the retained navigation state")
    repeat_action = proof.get("repeat_action", {})
    require(failures,
            repeat_action.get("host_navigation_action_writes") == 1 and
            repeat_action.get("host_navigation_action_replays") == 0 and
            isinstance(repeat_action.get(
                "host_navigation_ack_received"), bool) and
            (repeat_action.get("host_navigation_ack_received") is False or
             (repeat_action.get("action") == "select" and
              repeat_action.get("changed") is True)),
            "Repeat Select action accounting mismatch")

    pixel_specs = {
        "outcome_to_actions": (
            "wifi-auth-synthetic-outcome",
            "wifi-auth-synthetic-actions", True, True),
        "actions_to_peer": (
            "wifi-auth-synthetic-actions",
            "wifi-auth-synthetic-peer-first", True, True),
        "peer_first_to_second": (
            "wifi-auth-synthetic-peer-first",
            "wifi-auth-synthetic-peer-second", False, False),
        "evidence_list_to_detail": (
            "wifi-auth-synthetic-evidence-list",
            "wifi-auth-synthetic-evidence-detail", True, True),
    }
    retained_deltas = proof.get("pixel_deltas", {})
    require(failures, set(retained_deltas) == set(pixel_specs),
            "synthetic pixel-delta inventory mismatch")
    for name, (before, after, title_change,
               footer_change) in pixel_specs.items():
        actual = screen_pixel_changes(root / "frames", before, after)
        require(failures, actual is not None and
                actual == retained_deltas.get(name),
                f"synthetic pixel delta cannot be reproduced: {name}")
        if actual is not None:
            verify_navigation_pixel_delta(
                failures, actual, f"synthetic.pixel.{name}", title_change,
                footer_change)


def verify_synthetic_terminal_back_cleanup(
        failures: list[str], run: dict[str, Any], app_identity: object,
        version: str) -> None:
    proof = run.get("synthetic_back_cleanup", {})
    require(failures,
            proof.get("schema") ==
                "leshy.wifi.authentication.synthetic_back_cleanup.v1" and
            proof.get("boot_recovery_continuity") is True and
            proof.get("product_storage_writes_measured") is False and
            proof.get("static_no_storage_api_contract_required") is True,
            "synthetic terminal Back proof scope mismatch")

    run_id = run.get("run_id")
    cycle = proof.get("session_cycle", {})
    ended = cycle.get("end", {})
    begun = cycle.get("begin", {})
    require(failures,
            ended.get("schema") == "leshy.hil.session.v1" and
            ended.get("active") is False and
            ended.get("app_elf_sha256") == app_identity and
            ended.get("host_end_requested_session_id") == run_id and
            non_negative_integer(ended.get("host_end_action_writes")) and
            1 <= ended.get("host_end_action_writes", 0) <= 2 and
            ended.get("host_end_action_replays") ==
                ended.get("host_end_action_writes") - 1,
            "synthetic Back intermediate HIL end mismatch")
    require(failures,
            begun.get("schema") == "leshy.hil.session.v1" and
            begun.get("active") is True and begun.get("session_id") == run_id and
            begun.get("app_elf_sha256") == app_identity and
            begun.get("firmware_version") == version and
            begun.get("host_begin_action_writes") == 1 and
            begun.get("host_begin_action_replays") == 0,
            "synthetic Back intermediate HIL begin mismatch")

    ambient = proof.get("ambient", {})
    ambient_terminal = ambient.get("terminal", {})
    ambient_capture = ambient.get("capture_terminal", {})
    require(failures,
            ambient_terminal.get("state") == "result" and
            ambient_terminal.get("synthetic") is False and
            ambient_terminal.get("report_origin") == AMBIENT_REPORT_ORIGIN and
            ambient_terminal.get("passive") is True and
            ambient_terminal.get("tx_path") is False and
            ambient_terminal.get("connect_path") is False and
            ambient_terminal.get("capture_cleanup_complete") is True and
            ambient_terminal.get("adapter_cleanup_complete") is True and
            ambient_capture.get("state") == "complete" and
            ambient_capture.get("passive_only") is True and
            ambient_capture.get("rx_only") is True and
            ambient_capture.get("application_connect_calls") == 0 and
            ambient_capture.get("application_raw_tx_calls") == 0 and
            ambient_capture.get("cleanup_complete") is True,
            "synthetic Back preflight was not an honest ambient terminal")

    fixture = proof.get("fixture", {})
    replay = proof.get("replay_rejected", {})
    verify_synthetic_fixture_ack(failures, fixture)
    verify_synthetic_replay_rejected(failures, replay)
    baseline = proof.get("baseline_resource", {})
    loaded = proof.get("loaded_resource", {})
    back_resource = proof.get("back_resource", {})
    require(failures,
            isinstance(baseline, dict) and baseline == loaded and
            baseline == back_resource,
            "synthetic terminal Back changed production/capture/boot recovery")
    continuity = proof.get("production_continuity", {})
    require(failures,
            isinstance(continuity, dict) and
            set(continuity) == set(AUTH_RESOURCE_FIELDS),
            "synthetic terminal Back continuity baseline is incomplete")
    outcome = proof.get("outcome", {})
    repeat_generation = outcome.get("repeat_request_generation")
    require(failures, non_negative_integer(repeat_generation),
            "synthetic terminal Back repeat generation missing")
    if non_negative_integer(repeat_generation):
        verify_synthetic_controller_state(
            failures, outcome, "synthetic_back.outcome", "outcome",
            repeat_request_generation=repeat_generation)

    back_action = proof.get("back_action", {})
    back_state = proof.get("back_state", {})
    delayed = proof.get("back_delayed", {})
    home = proof.get("home", {})
    require(failures,
            back_action.get("host_navigation_action_writes") == 1 and
            back_action.get("host_navigation_action_replays") == 0 and
            back_action.get("wifi_product_view") == "menu" and
            back_action.get("runtime_owner") == "wifi" and
            back_action.get("lease_mask") == 15 and
            back_action.get("changed") is True,
            "terminal Outcome -> Back action was not directly observed")
    require(failures,
            back_state.get("schema") == AUTH_SCHEMA and
            back_state.get("kind") == "state" and
            back_state.get("read_only_query") is True and
            back_state.get("view") == "menu" and
            back_state.get("state") == "idle" and
            back_state.get("synthetic") is False and
            back_state.get("report_origin") == NO_REPORT_ORIGIN and
            back_state.get("generation") == outcome.get("generation") and
            back_state.get("repeat_requested") is False and
            back_state.get("repeat_request_generation") == repeat_generation and
            back_state.get("capture_state") == "complete" and
            back_state.get("capture_active") is False and
            back_state.get("capture_cleanup_complete") is True and
            back_state.get("adapter_cleanup_complete") is True,
            "terminal Outcome -> Back did not clear synthetic state safely")
    require(failures,
            delayed.get("view") == "menu" and delayed.get("state") == "idle" and
            delayed.get("synthetic") is False and
            delayed.get("repeat_requested") is False and
            delayed.get("generation") == back_state.get("generation") and
            delayed.get("repeat_request_generation") == repeat_generation,
            "terminal Outcome -> Back cleanup was not delayed-stable")
    for label, state in (("outcome", outcome), ("back", back_state),
                         ("delayed", delayed)):
        projection = {name: state.get(name) for name in AUTH_RESOURCE_FIELDS}
        require(failures, projection == continuity,
                f"synthetic terminal Back production continuity changed: {label}")
    require(failures,
            home.get("page") == "home" and
            home.get("runtime_owner") == "none" and
            home.get("lease_mask") == 0,
            "synthetic terminal Back did not release Home lease")


def verify_wifi_menu_quiescent(failures: list[str],
                               state: dict[str, Any]) -> None:
    require(failures,
            state.get("page") == "survey" and
            state.get("wifi_product_view") == "menu" and
            state.get("runtime_owner") == "wifi" and
            state.get("lease_mask") == 15 and
            state.get("survey_workflow_state") == "setup" and
            state.get("survey_product_backend_open") is False and
            state.get("survey_product_storage_mounted") is False and
            state.get("survey_product_cleanup_complete") is True and
            state.get("survey_product_source_active") is False and
            state.get("survey_product_scan_active") is False,
            "Wi-Fi menu was not quiescent before Networks")


def verify_cancel_hold(failures: list[str], hold: dict[str, Any]) -> None:
    ack = hold.get("ack", {})
    pre_arm_state = hold.get("pre_arm_state", {})
    armed_state = hold.get("armed_state", {})
    ack_received = hold.get("host_arm_ack_received")
    pre_attempts = pre_arm_state.get("host_transport_attempts")
    pre_retries = pre_arm_state.get("host_transport_transient_retries")
    pre_errors = pre_arm_state.get("host_transport_transient_errors")
    require(failures,
            pre_arm_state.get("schema") == AUTH_SCHEMA and
            pre_arm_state.get("kind") == "state" and
            pre_arm_state.get("read_only_query") is True and
            pre_arm_state.get("survey_terminal_hold_armed") is False and
            isinstance(pre_attempts, int) and
            not isinstance(pre_attempts, bool) and
            1 <= pre_attempts <= 3 and
            pre_retries == pre_attempts - 1 and
            isinstance(pre_errors, list) and
            len(pre_errors) == pre_retries and
            all(isinstance(error, str) and error for error in pre_errors),
            "read-only pre-arm state did not prove the hold inactive")
    require(failures,
            hold.get("host_arm_action_writes") == 1 and
            hold.get("host_arm_action_replays") == 0 and
            isinstance(ack_received, bool),
            "survey-stop hold mutation was replayed or lacks host accounting")
    if ack_received is True:
        require(failures,
                ack.get("schema") == AUTH_HOLD_SCHEMA and
                ack.get("kind") == "armed" and
                ack.get("status") == "armed" and
                ack.get("armed") is True and
                ack.get("one_shot") is True and
                ack.get("replayed") is False and
                ack.get("timeout_ms") == AUTH_HOLD_TIMEOUT_MS and
                ack.get("hil_active") is True and
                ack.get("hardware_touched") is False and
                ack.get("radio_started") is False and
                ack.get("storage_mounted") is False and
                ack.get("storage_written") is False and
                "host_arm_ack_error" not in hold,
                "survey-stop hold ACK contract mismatch")
    else:
        require(failures,
                ack == {} and
                isinstance(hold.get("host_arm_ack_error"), str) and
                bool(hold.get("host_arm_ack_error")),
                "lost hold ACK has contradictory data or no retained error")
    require(failures,
            armed_state.get("schema") == AUTH_SCHEMA and
            armed_state.get("kind") == "state" and
            armed_state.get("read_only_query") is True and
            armed_state.get("survey_terminal_hold_armed") is True and
            armed_state.get("host_transport_attempts") == 1 and
            armed_state.get("host_transport_transient_retries") == 0 and
            armed_state.get("host_transport_transient_errors") == [],
            "exact read-only auth state did not prove the one-shot hold armed")
    arm_elapsed = hold.get("host_arm_elapsed_ms")
    require(failures,
            hold.get("host_arm_ack_timeout_ms") ==
                AUTH_HOLD_ACK_TIMEOUT_MS and
            hold.get("host_arm_state_timeout_ms") ==
                AUTH_HOLD_STATE_TIMEOUT_MS and
            isinstance(arm_elapsed, (int, float)) and
            not isinstance(arm_elapsed, bool) and
            0 <= arm_elapsed < AUTH_HOLD_TIMEOUT_MS,
            "survey-stop hold host recovery budget was not bounded")
    elapsed = hold.get("host_back_after_arm_ms")
    require(failures,
            isinstance(elapsed, (int, float)) and
            not isinstance(elapsed, bool) and
            isinstance(arm_elapsed, (int, float)) and
            0 <= arm_elapsed <= elapsed < AUTH_HOLD_TIMEOUT_MS,
            "Back was not sent inside the bounded survey-stop hold")


def verify_bounded_hold_navigation(
        failures: list[str], record: dict[str, Any], action_name: str,
        label: str) -> None:
    ack_received = record.get("host_navigation_ack_received")
    write_elapsed = record.get("host_navigation_write_after_arm_ms")
    require(failures,
            record.get("host_navigation_action") == action_name and
            record.get("host_navigation_action_writes") == 1 and
            record.get("host_navigation_action_replays") == 0 and
            record.get("host_navigation_ack_timeout_ms") ==
                AUTH_HOLD_NAV_ACK_TIMEOUT_MS and
            isinstance(ack_received, bool) and
            isinstance(write_elapsed, (int, float)) and
            not isinstance(write_elapsed, bool) and
            0 <= write_elapsed < AUTH_HOLD_TIMEOUT_MS,
            f"{label}: one-shot navigation timing/accounting mismatch")
    if ack_received is True:
        require(failures,
                record.get("schema") == "leshy.ui.v1" and
                record.get("kind") == "state" and
                record.get("action") == action_name and
                "host_navigation_ack_error" not in record,
                f"{label}: received ACK does not match the exact action")
    else:
        require(failures,
                isinstance(record.get("host_navigation_ack_error"), str) and
                bool(record.get("host_navigation_ack_error")) and
                "schema" not in record and "kind" not in record and
                "action" not in record and "changed" not in record,
                f"{label}: lost ACK retained contradictory UI state")


def verify_start_failure_diagnostics(
        failures: list[str], diagnostics: dict[str, Any]) -> None:
    auth = diagnostics.get("authentication", {})
    capture = diagnostics.get("capture", {})
    stage = auth.get("adapter_failure_stage")
    driver_error = auth.get("adapter_driver_error")
    heap_free = auth.get("adapter_heap_free_before_init")
    heap_largest = auth.get("adapter_heap_largest_before_init")
    failure = auth.get("failure")
    require(failures,
            auth.get("state") == "failed" and
            isinstance(failure, str) and failure != "none",
            "failed start lacks exact authentication state")
    require(failures, stage in AUTH_FAILURE_STAGES | {"none"},
            "failed start lacks exact adapter_failure_stage")
    require(failures,
            isinstance(driver_error, int) and
            not isinstance(driver_error, bool),
            "failed start lacks adapter_driver_error")
    require(failures,
            non_negative_integer(heap_free) and
            non_negative_integer(heap_largest),
            "failed start lacks pre-init heap counters")
    if failure == "start_failed":
        require(failures,
                stage in AUTH_FAILURE_STAGES and driver_error != 0,
                "start_failed lacks exact nonzero adapter stage/error")
    if (failure == "start_failed" and
            stage in AUTH_FAILURE_STAGES -
            AUTH_FAILURE_STAGES_BEFORE_HEAP_SNAPSHOT):
        require(failures, heap_free > 0 and heap_largest > 0,
                "post-snapshot failed start retained zero heap")
    require(failures,
            capture.get("schema") == "leshy.capture.wifi_frame.v1" and
            capture.get("kind") == "state" and
            isinstance(capture.get("driver_error"), int) and
            not isinstance(capture.get("driver_error"), bool),
            "failed start lacks exact capture.state driver error")
    if failure == "start_failed":
        require(failures, capture.get("driver_error") != 0,
                "start_failed retained zero capture driver error")


def verify_private_target_absent(failures: list[str], value: Any,
                                 path: str = "run") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            private_key = (isinstance(key, str) and
                           key.lower() in PRIVATE_TARGET_KEYS)
            require(failures, not private_key,
                    f"{path}.{key}: private target key retained")
            verify_private_target_absent(failures, item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            verify_private_target_absent(failures, item,
                                         f"{path}[{index}]")
    elif isinstance(value, str):
        require(failures, MAC_ADDRESS.search(value) is None,
                f"{path}: MAC-like private identifier retained")


def pixel_changes(frames: Path) -> dict[str, int] | None:
    before_path = frames / "wifi-auth-running-first.rgb565"
    after_path = frames / "wifi-auth-running-second.rgb565"
    if not before_path.is_file() or not after_path.is_file():
        return None
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    if len(before) != WIDTH * HEIGHT * 2 or len(after) != len(before):
        return None
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


def screen_pixel_changes(frames: Path, before_name: str,
                         after_name: str) -> dict[str, int] | None:
    before_path = frames / f"{before_name}.rgb565"
    after_path = frames / f"{after_name}.rgb565"
    if not before_path.is_file() or not after_path.is_file():
        return None
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    if len(before) != WIDTH * HEIGHT * 2 or len(after) != len(before):
        return None
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


def terminal_pixel_changes(frames: Path) -> dict[str, int] | None:
    return screen_pixel_changes(
        frames, "wifi-auth-running-second", "wifi-auth-result")


def verify_terminal_pixel_delta(failures: list[str],
                                delta: dict[str, int] | None) -> None:
    require(failures, delta is not None,
            "terminal screenshot delta cannot be recomputed")
    if delta is None:
        return
    require(failures, delta.get("content_changed_pixels", 0) > 0,
            "terminal content stayed stale")
    require(failures, delta.get("title_changed_pixels", 0) > 0,
            "terminal lifecycle title stayed stale")
    require(failures, delta.get("status_changed_pixels", 0) > 0,
            "terminal RX/TX status stayed stale")
    require(failures,
            delta.get("unexpected_static_chrome_changed_pixels") == 0,
            "terminal transition changed unexpected static chrome")


def verify_manifest(failures: list[str], root: Path) -> None:
    manifest = root / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifacts.sha256 missing")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or any(
                character not in "0123456789abcdef" for character in parts[0]):
            failures.append(f"manifest:{number}: malformed")
            continue
        expected, relative = parts
        pure = PurePosixPath(relative)
        if (pure.is_absolute() or ".." in pure.parts or relative in indexed or
                relative == "artifacts.sha256"):
            failures.append(f"manifest:{number}: unsafe/duplicate {relative!r}")
            continue
        indexed.add(relative)
        target = root.joinpath(*pure.parts)
        require(failures, target.is_file(), f"indexed artifact missing: {relative}")
        if target.is_file():
            require(failures, digest(target) == expected,
                    f"artifact hash mismatch: {relative}")
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, indexed == actual,
            f"manifest inventory mismatch: missing={sorted(actual-indexed)}, "
            f"extra={sorted(indexed-actual)}")


def verify_ingress(failures: list[str], state: dict[str, Any]) -> None:
    names = (
        "frames_reported", "frames_accepted", "frames_dropped_capacity",
        "frames_dropped_invalid", "frames_observed", "frames_ignored",
        "ingress_invalid", "candidates", "candidates_accepted",
        "candidates_dropped", "uncertainty", "evidence", "peers", "pmkids",
    )
    for name in names:
        require(failures, non_negative_integer(state.get(name)),
                f"auth_terminal.{name} is not a non-negative integer")
    if not all(non_negative_integer(state.get(name)) for name in names):
        return
    require(failures,
            state["frames_observed"] == state["frames_ignored"] +
                state["ingress_invalid"] + state["candidates"],
            "authentication ingress accounting mismatch")
    require(failures,
            state["candidates"] == state["candidates_accepted"] +
                state["candidates_dropped"],
            "authentication candidate accounting mismatch")
    require(failures, state["frames_reported"] == state["candidates"] and
            state["frames_accepted"] == state["candidates_accepted"] and
            state["frames_dropped_capacity"] == state["candidates_dropped"] and
            state["frames_dropped_invalid"] == 0,
            "capture/ingress projection mismatch")
    require(failures,
            state.get("analysis_frames_reported") ==
                state["candidates"] + state["ingress_invalid"] and
            state.get("analysis_frames_accepted") ==
                state["candidates_accepted"] and
            state.get("analysis_dropped_capacity") ==
                state["candidates_dropped"] and
            state.get("analysis_dropped_invalid") ==
                state["ingress_invalid"] and
            state.get("analysis_accounting_valid") is True,
            "analysis input projection/accounting mismatch")
    outcome = state.get("outcome")
    require(failures, outcome in ("complete", "incomplete", "inconclusive"),
            "unsupported authentication outcome")
    loss = state["ingress_invalid"] + state["candidates_dropped"]
    if state["evidence"] == 0 or loss:
        require(failures, outcome == "inconclusive",
                "absent/lost evidence was presented as conclusive")
    if state["evidence"] == 0:
        require(failures, state["peers"] == 0 and state["pmkids"] == 0 and
                state["uncertainty"] & UNCERTAINTY_NO_EVIDENCE != 0,
                "empty ambient capture is not honestly inconclusive")
    if outcome == "complete":
        require(failures, state["peers"] >= 1 and state["evidence"] >= 4,
                "complete result lacks a complete-handshake envelope")
    if outcome == "incomplete":
        require(failures, state["evidence"] >= 1,
                "incomplete result has no evidence")
    verify_report(failures, state)
    verify_presenter(failures, state, "auth_terminal")


def verify_report(failures: list[str], state: dict[str, Any]) -> None:
    for name in REPORT_COUNTER_FIELDS:
        require(failures, non_negative_integer(state.get(name)),
                f"auth_terminal.{name} is not a non-negative integer")
    if not all(non_negative_integer(state.get(name))
               for name in REPORT_COUNTER_FIELDS):
        return
    require(failures,
            state["frames_read"] + state["source_read_failures"] ==
                min(state["source_frames"], 64),
            "analyzer source inspection partition mismatch")
    classified = (state["classified_key_frames"] +
                  state["unclassified_key_frames"] +
                  state["unsupported_key_frames"])
    require(failures, state["eapol_key_frames"] == classified,
            "analyzer key classification partition mismatch")
    require(failures,
            state["frames_read"] == state["analysis_frames_ignored"] +
                state["malformed_frames"] + state["truncated_frames"] +
                classified,
            "analyzer decode partition mismatch")
    require(failures,
            state["data_frames"] <= state["frames_read"] and
            state["eapol_key_frames"] <= state["eapol_frames"] <=
                state["frames_read"],
            "analyzer counter bounds invalid")
    require(failures,
            state["evidence"] + state["evidence_dropped"] ==
                state["eapol_key_frames"],
            "analyzer evidence partition mismatch")
    require(failures,
            state["report_capture_frames_reported"] ==
                state["analysis_frames_reported"] and
            state["report_capture_frames_accepted"] ==
                state["analysis_frames_accepted"] and
            state["source_frames"] ==
                state["report_capture_frames_accepted"] and
            state["report_capture_frames_dropped_capacity"] ==
                state["analysis_dropped_capacity"] and
            state["report_capture_frames_dropped_invalid"] ==
                state["analysis_dropped_invalid"],
            "analyzer capture accounting projection mismatch")
    complete_peers = state.get("complete_peers")
    require(failures, non_negative_integer(complete_peers) and
            complete_peers <= state["peers"],
            "analyzer complete-peer count invalid")
    if not non_negative_integer(complete_peers):
        return
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
    require(failures, state.get("uncertainty") == expected_uncertainty,
            "analyzer uncertainty mask is not exactly derived")
    expected_outcome = (
        "inconclusive" if expected_uncertainty else
        ("complete" if complete_peers else "incomplete"))
    require(failures, state.get("outcome") == expected_outcome,
            "analyzer outcome does not match uncertainty/complete peers")


def verify_presenter(failures: list[str], state: dict[str, Any],
                     label: str) -> None:
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
        expected = ("result", "positive", False, False, True, 4)
    elif product_state == "result" and outcome == "incomplete":
        expected = ("result", "caution", False, False, True, 4)
    elif product_state == "result" and outcome == "inconclusive":
        expected = ("inconclusive", "caution", True, False, True, 4)
    actual = (
        state.get("presenter_view"), state.get("presenter_tone"),
        state.get("presenter_evidence_incomplete"),
        state.get("presenter_report_openable"),
        state.get("presenter_cleanup_complete"),
        state.get("presenter_row_count"))
    require(failures, expected is not None and actual == expected,
            f"{label} presenter projection mismatch")
    require(failures, state.get("failure") == "none",
            f"{label} exposes a product/presenter failure")


def verify_repaint_delta(failures: list[str], before: dict[str, Any],
                         after: dict[str, Any]) -> None:
    fields = ("generation", "content_repaints", "full_repaints",
              "chrome_repaints")
    for name in fields:
        require(failures,
                non_negative_integer(before.get(name)) and
                non_negative_integer(after.get(name)),
                f"live repaint counter missing: {name}")
    if not all(non_negative_integer(state.get(name))
               for state in (before, after) for name in fields):
        return
    require(failures,
            before["generation"] != 0 and
            after["generation"] == before["generation"],
            "live repaint generation changed or is zero")
    require(failures,
            after["content_repaints"] > before["content_repaints"],
            "live content was not incrementally repainted")
    require(failures,
            after["full_repaints"] == before["full_repaints"],
            "live capture performed a full repaint")
    require(failures,
            after["chrome_repaints"] == before["chrome_repaints"],
            "live capture repainted static chrome")


def verify_hil_session(failures: list[str], run: dict[str, Any],
                       app_identity: object, version: str) -> None:
    run_id = run.get("run_id")
    session = run.get("hil_session", {})
    begun = session.get("begin", {})
    ended = session.get("end", {})
    require(failures, isinstance(run_id, str) and len(run_id) == 32 and
            all(character in "0123456789abcdef" for character in run_id),
            "invalid HIL run ID")
    require(failures, begun.get("schema") == "leshy.hil.session.v1" and
            begun.get("active") is True and
            begun.get("session_id") == run_id and
            begun.get("app_elf_sha256") == app_identity and
            begun.get("firmware_version") == version and
            begun.get("host_begin_action_writes") == 1 and
            begun.get("host_begin_action_replays") == 0 and
            isinstance(begun.get("host_begin_ack_received"), bool),
            "HIL begin proof mismatch")
    if begun.get("host_begin_ack_received") is True:
        require(failures,
                begun.get("kind") == "begun" and
                begun.get("status") == "begun",
                "acknowledged HIL begin semantic mismatch")
    elif begun.get("host_begin_ack_received") is False:
        require(failures,
                begun.get("kind") == "state" and
                begun.get("status") == "active" and
                isinstance(begun.get("host_begin_ack_error"), str) and
                bool(begun.get("host_begin_ack_error")),
                "lost-ACK HIL begin proof mismatch")
    writes = ended.get("host_end_action_writes")
    replays = ended.get("host_end_action_replays")
    require(failures, ended.get("schema") == "leshy.hil.session.v1" and
            ended.get("active") is False and
            ended.get("app_elf_sha256") == app_identity and
            ended.get("host_end_requested_session_id") == run_id and
            non_negative_integer(writes) and 1 <= writes <= 2 and
            replays == writes - 1 and
            isinstance(ended.get("host_end_ack_received"), bool),
            "HIL end/cleanup proof mismatch")
    if ended.get("host_end_ack_received") is True:
        require(failures,
                ended.get("kind") == "ended" and
                ended.get("status") == "ended" and
                ended.get("session_id") == run_id,
                "acknowledged HIL end semantic mismatch")
    elif ended.get("host_end_ack_received") is False:
        require(failures,
                ended.get("kind") == "state" and
                ended.get("status") == "inactive" and
                ended.get("session_id") == "" and
                ended.get("firmware_version") == version and
                isinstance(ended.get("host_end_ack_error"), str) and
                bool(ended.get("host_end_ack_error")),
                "lost-ACK HIL end proof mismatch")
    begin_revision = begun.get("ui_revision")
    end_revision = ended.get("ui_revision")
    require(failures,
            non_negative_integer(begin_revision) and
            non_negative_integer(end_revision) and
            end_revision >= begin_revision,
            "HIL session UI revision continuity mismatch")


def verify_post_hil_end(failures: list[str], run: dict[str, Any]) -> None:
    proof = run.get("post_hil_end", {})
    hil = proof.get("hil", {})
    ui = proof.get("ui", {})
    auth = proof.get("auth", {})
    require(failures,
            hil.get("schema") == "leshy.hil.session.v1" and
            hil.get("kind") == "state" and hil.get("active") is False,
            "post-HIL session is not read-only inactive")
    require(failures,
            ui.get("schema") == "leshy.ui.v1" and
            ui.get("kind") == "state" and ui.get("page") == "home" and
            ui.get("runtime_owner") == "none" and ui.get("lease_mask") == 0,
            "post-HIL UI is not Home/zero lease")
    require(failures,
            auth.get("schema") == AUTH_SCHEMA and
            auth.get("kind") == "state" and
            auth.get("read_only_query") is True and
            auth.get("view") == "menu" and auth.get("state") == "idle" and
            auth.get("synthetic") is False and
            auth.get("production_report_fingerprint") == "unavailable" and
            auth.get("production_report_fingerprint_scope") == "none",
            "post-HIL auth state leaked session-scoped evidence")


def verify_boot_and_recovery(failures: list[str], run: dict[str, Any],
                             app_identity: object, version: str,
                             expected_cid: str) -> None:
    boot = run.get("boot", {})
    require(failures,
            boot.get("schema") == "leshy.boot.v1" and
            boot.get("kind") == "ready" and
            boot.get("version") == version and
            boot.get("app_elf_sha256") == app_identity and
            boot.get("buzzer_inactive") is True and
            boot.get("input_detected") is True,
            "exact boot identity/safety proof mismatch")
    attempts = boot.get("input_probe_attempts")
    retries = boot.get("input_probe_transient_retries")
    require(failures,
            non_negative_integer(attempts) and 1 <= attempts <= 8 and
            non_negative_integer(retries) and retries == attempts - 1,
            "boot input probe retry accounting mismatch")
    heap_fields = ("heap_total", "heap_free", "heap_min_free")
    require(failures, all(non_negative_integer(boot.get(field)) and
                          boot.get(field) > 0 for field in heap_fields),
            "boot heap baseline missing")
    samples = run.get("boot_metrics_samples")
    require(failures, isinstance(samples, list) and len(samples) >= 2,
            "stable boot metric samples missing")
    if isinstance(samples, list):
        for index, sample in enumerate(samples):
            require(failures, isinstance(sample, dict) and
                    sample.get("schema") == "leshy.boot.v1" and
                    sample.get("kind") == "ready" and
                    sample.get("version") == version and
                    sample.get("app_elf_sha256") == app_identity and
                    all(sample.get(field) == boot.get(field)
                        for field in heap_fields),
                    f"boot metric sample {index} is not the exact stable boot")

    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    for label, recovery in (("before", before), ("after", after)):
        require(failures,
                recovery.get("schema") ==
                    "leshy.storage.product_boot_recovery.v1" and
                recovery.get("kind") == "state" and
                recovery.get("status") == "admitted" and
                recovery.get("enrolled") is True and
                recovery.get("expected_fingerprint") == expected_cid and
                recovery.get("observed_fingerprint") == expected_cid and
                recovery.get("fingerprint_matched") is True and
                recovery.get("mounted_read_only") is True and
                recovery.get("read_only_guaranteed") is True and
                recovery.get("write_enabled") is False and
                recovery.get("blocked_write_attempts") == 0 and
                recovery.get("catalog_admitted") is True and
                recovery.get("cleanup_complete") is True,
                f"read-only boot-recovery {label} policy mismatch")
        recovery_attempts = recovery.get("attempts")
        recovery_retries = recovery.get("transient_retries")
        require(failures,
                non_negative_integer(recovery_attempts) and
                1 <= recovery_attempts <= 8 and
                non_negative_integer(recovery_retries) and
                recovery_retries == recovery_attempts - 1,
                f"read-only recovery {label} retry accounting mismatch")
    require(failures,
            non_negative_integer(before.get("generation")) and
            before.get("generation", 0) >= 1 and
            before.get("generation") == after.get("generation") and
            non_negative_integer(before.get("observations")) and
            before.get("observations") == after.get("observations"),
            "read-only recovery generation/observation continuity mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    failures: list[str] = []
    run_path = root / "run.json"
    require(failures, run_path.is_file(), "run.json missing")
    require(failures, RUNNER.is_file(), "current CAP049 runner missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    try:
        run: dict[str, Any] = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: run.json invalid: {error}")
        return 1

    require(failures, run.get("schema") == SCHEMA, "run schema mismatch")
    retained_start_failure = run.get("start_failure_diagnostics", {})
    failed_start_observed = any(
        isinstance(state, dict) and
        state.get("state") == "failed"
        for state in (
            run.get("auth_requested", {}),
            run.get("auth_running", {}),
            run.get("auth_terminal", {})))
    if failed_start_observed:
        verify_start_failure_diagnostics(
            failures, retained_start_failure)
    require(failures, run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "run is not a clean pass")
    require(failures, run.get("runner_source_sha256") == digest(RUNNER),
            "run is not bound to the current CAP049 runner")
    device = run.get("device", {})
    require(failures, device == {"board_id": BOARD_ID, "port": BOARD_PORT},
            "run is not bound to board-01 exact port")
    require(failures, FORBIDDEN_FIXTURE_PORT not in json.dumps(run),
            "board-02/fixture port appears in CAP049 evidence")

    candidate = run.get("candidate", {})
    firmware = root / "firmware.bin"
    source_commit = args.source_commit.lower()
    require(failures, len(source_commit) == 40 and all(
            character in "0123456789abcdef" for character in source_commit),
            "expected source commit is not full hexadecimal")
    require(failures, candidate.get("version") == args.expected_version,
            "candidate version mismatch")
    require(failures, candidate.get("source_commit") == source_commit,
            "candidate source commit mismatch")
    require(failures, candidate.get("flashed") is True and
            candidate.get("exact_boot_verified") is True and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flash_completed") is True,
            "exact candidate verification missing")
    require(failures, run.get("expected_cid") == args.expected_cid,
            "exact SD CID mismatch")
    require(failures, firmware.is_file(), "retained firmware missing")
    if firmware.is_file():
        require(failures, candidate.get("firmware_sha256") == digest(firmware),
                "retained firmware hash mismatch")
        require(failures,
                candidate.get("app_elf_sha256") == app_elf_sha256(firmware),
                "retained app identity mismatch")
    verify_hil_session(
        failures, run, candidate.get("app_elf_sha256"), args.expected_version)
    verify_post_hil_end(failures, run)
    verify_boot_and_recovery(
        failures, run, candidate.get("app_elf_sha256"),
        args.expected_version, args.expected_cid)
    verify_wifi_menu_quiescent(failures, run.get("wifi_menu_ready", {}))

    cancel_list = run.get("cancel_network_list", {})
    cancel_detail_ui = run.get("cancel_network_detail_ui", {})
    cancel_detail = run.get("cancel_network_detail", {})
    cancel_hold = run.get("cancel_hold", {})
    cancel_requested_ui = run.get("cancel_requested_ui", {})
    cancel_back_ui = run.get("cancel_back_ui", {})
    cancel_pending = run.get("cancel_pending", {})
    cancel_terminal_ui = run.get("cancel_terminal_ui", {})
    cancel_terminal = run.get("cancel_terminal", {})
    cancel_capture = run.get("cancel_capture_terminal", {})
    require(failures,
            cancel_list.get("wifi_product_view") == "networks" and
            cancel_list.get("survey_workflow_state") == "running" and
            cancel_list.get("survey_product_worker_ready") is True and
            cancel_list.get("survey_scan_status") == "valid" and
            cancel_list.get("survey_scan_dropped") == 0 and
            cancel_list.get("runtime_owner") == "wifi" and
            cancel_list.get("lease_mask") == 15,
            "cancel preflight network list proof mismatch")
    verify_product_mount(failures, cancel_list, "cancel preflight")
    require(failures,
            cancel_detail_ui.get("wifi_product_view") == "network_detail" and
            cancel_detail_ui.get("wifi_network_navigation_locked") is True and
            cancel_detail.get("active") is True and
            cancel_detail.get("passive") is True and
            cancel_detail.get("active_probe_allowed") is False,
            "cancel preflight NetworkDetail proof mismatch")
    verify_cancel_hold(failures, cancel_hold)
    verify_bounded_hold_navigation(
        failures, cancel_requested_ui, "right", "cancel request")
    verify_bounded_hold_navigation(
        failures, cancel_back_ui, "left", "cancel Back")
    require(failures,
            cancel_hold.get("host_back_after_arm_ms") ==
                cancel_back_ui.get("host_navigation_write_after_arm_ms") and
            isinstance(cancel_requested_ui.get(
                "host_navigation_write_after_arm_ms"), (int, float)) and
            isinstance(cancel_back_ui.get(
                "host_navigation_write_after_arm_ms"), (int, float)) and
            cancel_requested_ui["host_navigation_write_after_arm_ms"] <=
                cancel_back_ui["host_navigation_write_after_arm_ms"],
            "cancel Right/Back write chronology mismatch")
    cancel_generation = cancel_pending.get("generation")
    if cancel_requested_ui.get("host_navigation_ack_received") is True:
        require(failures,
                cancel_requested_ui.get("wifi_product_view") ==
                    "authentication_capture" and
                cancel_requested_ui.get("runtime_event") ==
                    "authentication_waiting_for_survey_stop",
                "cancel Right ACK did not prove waiting_for_survey_stop")
    if cancel_back_ui.get("host_navigation_ack_received") is True:
        require(failures,
                cancel_back_ui.get("wifi_product_view") ==
                    "authentication_capture" and
                cancel_back_ui.get("runtime_event") ==
                    "authentication_back_waiting_for_survey_stop" and
                cancel_back_ui.get("runtime_owner") == "wifi" and
                cancel_back_ui.get("lease_mask") == 15 and
                cancel_back_ui.get("changed") is True,
                "cancel Back ACK did not prove the waiting-state latch")
    require(failures,
            non_negative_integer(cancel_generation) and cancel_generation != 0,
            "cancel lifecycle has no nonzero generation")
    require(failures,
            cancel_pending.get("generation") == cancel_generation and
            cancel_pending.get("back_during_wait_observed") is True and
            cancel_pending.get("state") in ("waiting_for_survey_stop", "idle"),
            "Back-during-wait latch/generation missing")
    if cancel_pending.get("state") == "waiting_for_survey_stop":
        require(failures, cancel_pending.get("cancel_pending") is True,
                "waiting cancellation did not expose cancel_pending")
        verify_presenter(failures, cancel_pending, "cancel_pending")
    require(failures,
            cancel_terminal_ui.get("wifi_product_view") == "menu" and
            cancel_terminal_ui.get("runtime_owner") == "wifi" and
            cancel_terminal_ui.get("lease_mask") == 15 and
            cancel_terminal.get("view") == "menu" and
            cancel_terminal.get("state") == "idle" and
            cancel_terminal.get("generation") == cancel_generation and
            cancel_terminal.get("cancel_pending") is False and
            cancel_terminal.get("back_during_wait_observed") is True and
            cancel_terminal.get("failure") == "none" and
            cancel_terminal.get("capture_state") == "idle" and
            cancel_terminal.get("capture_active") is False and
            cancel_terminal.get("capture_cleanup_complete") is True and
            cancel_terminal.get("adapter_cleanup_complete") is True and
            cancel_terminal.get("survey_worker_deadline_armed") is False and
            cancel_terminal.get("survey_terminal_hold_armed") is False,
            "Back-during-wait did not end in clean Wi-Fi menu state")
    require(failures,
            cancel_capture.get("state") == "idle" and
            cancel_capture.get("passive_only") is True and
            cancel_capture.get("rx_only") is True and
            cancel_capture.get("application_connect_calls") == 0 and
            cancel_capture.get("application_raw_tx_calls") == 0 and
            cancel_capture.get("cleanup_complete") is True and
            cancel_capture.get("lease_mask") == 15,
            "Back-during-wait left capture/adapter state behind")

    network_list = run.get("network_list", {})
    require(failures,
            network_list.get("wifi_product_view") == "networks" and
            network_list.get("runtime_owner") == "wifi" and
            network_list.get("lease_mask") == 15 and
            network_list.get("survey_product_worker_ready") is True and
            network_list.get("survey_product_status") == "running" and
            network_list.get("survey_product_active_source_mask") == 1 and
            network_list.get("survey_scan_status") == "valid" and
            network_list.get("survey_scan_dropped") == 0 and
            isinstance(network_list.get("wifi_networks_unique"), int) and
            network_list.get("wifi_networks_unique", 0) >= 1,
            "nearby-network selection proof mismatch")
    verify_product_mount(failures, network_list, "same-boot second start")
    second_attempts = network_list.get(
        "survey_product_filesystem_mount_attempts")
    if non_negative_integer(second_attempts):
        require(failures,
                network_list.get("survey_product_mount_attempts_total") ==
                    cancel_list.get("survey_product_mount_attempts_total") +
                    second_attempts and
                network_list.get("survey_product_mount_successes_total") ==
                    cancel_list.get("survey_product_mount_successes_total") + 1,
                "same-boot second start did not prove a fresh successful "
                "bounded filesystem remount")
    detail_ui = run.get("network_detail_ui", {})
    detail = run.get("network_detail", {})
    require(failures,
            detail_ui.get("wifi_product_view") == "network_detail" and
            detail_ui.get("wifi_network_navigation_locked") is True and
            detail_ui.get("runtime_owner") == "wifi" and
            detail_ui.get("lease_mask") == 15,
            "NetworkDetail navigation/identity lock missing")
    require(failures, detail.get("active") is True and
            detail.get("passive") is True and
            detail.get("active_probe_allowed") is False and
            isinstance(detail.get("channel"), int) and
            1 <= detail.get("channel", 0) <= 13,
            "NetworkDetail identity/channel proof mismatch")

    requested_ui = run.get("auth_requested_ui", {})
    requested = run.get("auth_requested", {})
    running = run.get("auth_running", {})
    render_before = run.get("auth_render_before", {})
    render_after = run.get("auth_render_after", {})
    capture_running = run.get("capture_running", {})
    terminal = run.get("auth_terminal", {})
    capture_terminal = run.get("capture_terminal", {})
    require(failures,
            requested_ui.get("wifi_product_view") ==
                "authentication_capture" and
            requested_ui.get("runtime_event") ==
                "authentication_waiting_for_survey_stop" and
            requested_ui.get("runtime_owner") == "wifi" and
            requested_ui.get("lease_mask") == 15,
            "NetworkDetail -> authentication capture transition missing")
    generation = requested.get("generation")
    require(failures,
            requested.get("state") in ("waiting_for_survey_stop", "running") and
            requested.get("cancel_pending") is False and
            requested.get("back_during_wait_observed") is False and
            requested.get("failure") == "none" and
            non_negative_integer(generation) and
            non_negative_integer(cancel_generation) and
            generation > cancel_generation,
            "fresh capture admission/generation mismatch")
    verify_presenter(failures, requested, "auth_requested")
    require(failures,
            requested.get("target_selected") is True and
            requested.get("target_selection_continuity") is True and
            requested.get("channel") == detail.get("channel"),
            "fixed target does not match selected NetworkDetail")
    for name, state, expected_state, active, cleanup in (
            ("running", running, "running", True, False),
            ("terminal", terminal, "result", False, True)):
        require(failures,
                state.get("view") == "authentication_capture" and
                state.get("state") == expected_state and
                state.get("generation") == generation and
                state.get("cancel_pending") is False and
                state.get("back_during_wait_observed") is False and
                state.get("failure") == "none" and
                state.get("passive") is True and
                state.get("tx_path") is False and
                state.get("connect_path") is False and
                state.get("target_selected") is True and
                state.get("target_selection_continuity") is True and
                state.get("channel") == detail.get("channel") and
                state.get("duration_ms") == CAPTURE_DURATION_MS and
                state.get("maximum_frames") == 16 and
                state.get("snap_length") == 256 and
                state.get("capture_state") ==
                    ("running" if active else "complete") and
                state.get("capture_active") is active and
                state.get("capture_cleanup_complete") is cleanup and
                state.get("adapter_cleanup_complete") is cleanup and
                state.get("adapter_driver_error") == 0 and
                state.get("adapter_failure_stage") == "none" and
                non_negative_integer(
                    state.get("adapter_heap_free_before_init")) and
                state.get("adapter_heap_free_before_init", 0) > 0 and
                non_negative_integer(
                    state.get("adapter_heap_largest_before_init")) and
                state.get("adapter_heap_largest_before_init", 0) > 0 and
                state.get("esp_rf_owned_by_foreground") is True,
                f"authentication {name} lifecycle mismatch")
        verify_presenter(failures, state, f"auth_{name}")
    require(failures, terminal.get("survey_worker_deadline_armed") is False,
            "terminal survey worker deadline remains armed")
    require(failures,
            terminal.get("adapter_heap_free_before_init") ==
                running.get("adapter_heap_free_before_init") and
            terminal.get("adapter_heap_largest_before_init") ==
                running.get("adapter_heap_largest_before_init"),
            "adapter pre-init heap snapshot changed during capture")
    verify_ingress(failures, terminal)
    verify_ambient_and_synthetic_proofs(failures, run, root)
    verify_synthetic_terminal_back_cleanup(
        failures, run, candidate.get("app_elf_sha256"), args.expected_version)

    for name, state, expected_state, cleanup in (
            ("running", capture_running, "running", False),
            ("terminal", capture_terminal, "complete", True)):
        require(failures,
                state.get("state") == expected_state and
                state.get("passive_only") is True and
                state.get("rx_only") is True and
                state.get("application_connect_calls") == 0 and
                state.get("application_raw_tx_calls") == 0 and
                state.get("physical_no_tx_verified") is False and
                state.get("channel_plan") == detail.get("channel") and
                state.get("current_channel") == detail.get("channel") and
                state.get("duration_ms") == CAPTURE_DURATION_MS and
                state.get("snap_length") == 256 and
                state.get("maximum_frames") == 16 and
                state.get("cleanup_complete") is cleanup and
                state.get("lease_mask") == 15,
                f"capture {name} RX-only contract mismatch")
    require(failures,
            capture_terminal.get("frames_reported") ==
                terminal.get("candidates") and
            capture_terminal.get("frames_accepted") ==
                terminal.get("candidates_accepted") and
            capture_terminal.get("frames_dropped_capacity") ==
                terminal.get("candidates_dropped") and
            capture_terminal.get("frames_dropped_invalid") ==
                terminal.get("frames_dropped_invalid"),
            "terminal capture/auth accounting differs")
    started_us = capture_terminal.get("started_us")
    ended_us = capture_terminal.get("ended_us")
    require(failures,
            isinstance(started_us, int) and not isinstance(started_us, bool) and
            isinstance(ended_us, int) and not isinstance(ended_us, bool) and
            CAPTURE_DURATION_MS * 1000 <= ended_us - started_us <=
                CAPTURE_DURATION_MS * 1000 + CAPTURE_TERMINAL_SLACK_US,
            "physical capture was not a bounded 10-second run")
    host_elapsed = run.get("host_capture_elapsed_ms")
    require(failures, isinstance(host_elapsed, (int, float)) and
            not isinstance(host_elapsed, bool) and 0 < host_elapsed <= 13_000,
            "host did not observe a bounded terminal transition")
    verify_repaint_delta(failures, render_before, render_after)
    require(failures, run.get("terminal_repaint_delta") == {
        "content_repaints": terminal.get("content_repaints", 0) -
            render_after.get("content_repaints", 0),
        "full_repaints": terminal.get("full_repaints", 0) -
            render_after.get("full_repaints", 0),
        "chrome_repaints": terminal.get("chrome_repaints", 0) -
            render_after.get("chrome_repaints", 0),
    } and run.get("terminal_repaint_delta", {}).get(
        "content_repaints", 0) > 0 and
        run.get("terminal_repaint_delta", {}).get("full_repaints") == 0 and
        run.get("terminal_repaint_delta", {}).get("chrome_repaints") == 1,
        "terminal transition did not repaint one localized header region")
    repaint_delta = run.get("repaint_delta", {})
    if all(non_negative_integer(state.get(name))
           for state in (render_before, render_after)
           for name in ("content_repaints", "full_repaints",
                        "chrome_repaints")):
        require(failures, repaint_delta == {
            "content_repaints": render_after["content_repaints"] -
                render_before["content_repaints"],
            "full_repaints": render_after["full_repaints"] -
                render_before["full_repaints"],
            "chrome_repaints": render_after["chrome_repaints"] -
                render_before["chrome_repaints"],
        }, "retained repaint delta mismatch")

    after_back = run.get("auth_after_back", {})
    menu = run.get("menu_after_back", {})
    home = run.get("home_after_back", {})
    back_proof = run.get("synthetic_back_cleanup", {})
    back_state = back_proof.get("back_state", {})
    require(failures,
            menu.get("wifi_product_view") == "menu" and
            menu.get("runtime_owner") == "wifi" and menu.get("lease_mask") == 15,
            "Back did not leave capture for Wi-Fi menu")
    require(failures,
            after_back.get("view") == "menu" and
            after_back.get("state") == "idle" and
            after_back.get("generation") == back_state.get("generation") and
            after_back.get("synthetic") is False and
            after_back.get("report_origin") == NO_REPORT_ORIGIN and
            after_back.get("repeat_requested") is False and
            after_back.get("cancel_pending") is False and
            after_back.get("back_during_wait_observed") is False and
            after_back.get("failure") == "none" and
            after_back.get("capture_state") == "complete" and
            after_back.get("capture_active") is False and
            after_back.get("capture_cleanup_complete") is True and
            after_back.get("adapter_cleanup_complete") is True and
            after_back.get("survey_worker_deadline_armed") is False,
            "direct synthetic terminal Back cleanup mismatch")
    require(failures, home.get("page") == "home" and
            home.get("runtime_owner") == "none" and home.get("lease_mask") == 0,
            "second Back did not release the foreground lease")

    trace = run.get("trace")
    require(failures, isinstance(trace, list) and len(trace) >= 6,
            "navigation trace missing")
    if isinstance(trace, list):
        for index, record in enumerate(trace):
            require(failures, isinstance(record, dict) and
                    record.get("host_navigation_action_writes") == 1 and
                    record.get("host_navigation_action_replays") == 0 and
                    isinstance(record.get("host_navigation_ack_received"), bool),
                    f"trace[{index}] is not lost-ACK-safe")

    actual_delta = pixel_changes(root / "frames")
    require(failures, actual_delta is not None,
            "running screenshot delta cannot be recomputed")
    if actual_delta is not None:
        require(failures, actual_delta == run.get("pixel_delta") and
                actual_delta.get("content_changed_pixels", 0) > 0 and
                actual_delta.get("static_chrome_changed_pixels") == 0,
                "live redraw lacks content delta or changed static chrome")
    actual_terminal_delta = terminal_pixel_changes(root / "frames")
    verify_terminal_pixel_delta(failures, actual_terminal_delta)
    require(failures,
            actual_terminal_delta is not None and
            actual_terminal_delta == run.get("terminal_pixel_delta"),
            "retained terminal screenshot delta mismatch")
    require(failures, set(run.get("screens", {})) == set(SCREEN_NAMES),
            "screenshot inventory mismatch")
    for key, name in SCREEN_NAMES.items():
        screen = run.get("screens", {}).get(key, {})
        for suffix, hash_name in (("png", "png_sha256"),
                                  ("rgb565", "rgb565_sha256"),
                                  ("json", None)):
            path = root / "frames" / f"{name}.{suffix}"
            require(failures, path.is_file(), f"screenshot artifact missing: {path.name}")
            if path.is_file() and hash_name is not None:
                require(failures, screen.get(hash_name) == digest(path),
                        f"screenshot hash mismatch: {path.name}")

    scope = run.get("scope", {})
    require(failures,
            scope.get("single_flash") is True and
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("application_rx_only") is True and
            scope.get("application_wifi_connect_calls") == 0 and
            scope.get("application_raw_tx_calls") == 0 and
            scope.get("physical_no_tx_instrumented") is False and
            scope.get("ambient_eapol_required") is False and
            scope.get("ambient_capture_lifecycle_proven") is True and
            isinstance(scope.get(
                "ambient_authentication_evidence_observed"), bool) and
            scope.get("synthetic_ui_proven") is True and
            scope.get("synthetic_fixture_display_touched") is True and
            scope.get("synthetic_fixture_rf_hardware_touched") is False and
            scope.get("synthetic_fixture_radio_started") is False and
            scope.get("synthetic_fixture_connect_calls") == 0 and
            scope.get("synthetic_fixture_raw_tx_calls") == 0 and
            scope.get("synthetic_label_visible") is True and
            scope.get("synthetic_production_continuity_proven") is True and
            scope.get("synthetic_boot_recovery_continuity_proven") is True and
            scope.get("product_storage_writes_measured") is False and
            scope.get("static_no_storage_api_contract_required") is True and
            scope.get("synthetic_replay_rejected") is True and
            scope.get("right_select_equivalent") is True and
            scope.get("left_back_equivalent") is True and
            scope.get("repeat_request_proven") is True and
            scope.get("repeat_delayed_stable") is True and
            scope.get("terminal_back_cleanup_proven") is True and
            scope.get("production_continuity_proven") is True and
            scope.get("post_hil_end_proven") is True and
            scope.get("export_eligibility") == "not_evaluated" and
            scope.get("mac_wifi_control_calls") == 0 and
            scope.get("mac_ble_fixture_calls") == 0 and
            scope.get("fixture_ports_opened") == [] and
            scope.get("fixed_target_continuity") is True and
            scope.get("fixed_channel_continuity") is True and
            scope.get("capture_duration_ms") == CAPTURE_DURATION_MS and
            scope.get("back_during_wait_proven") is True and
            scope.get("survey_stop_hold_bounded") is True and
            scope.get("generation_advanced_after_cancel") is True and
            isinstance(scope.get("content_changed_pixels"), int) and
            scope.get("content_changed_pixels", 0) > 0 and
            scope.get("static_chrome_changed_pixels") == 0 and
            isinstance(scope.get("live_content_repaints"), int) and
            scope.get("live_content_repaints", 0) > 0 and
            scope.get("live_full_repaints") == 0 and
            scope.get("live_chrome_repaints") == 0 and
            isinstance(scope.get("terminal_content_changed_pixels"), int) and
            scope.get("terminal_content_changed_pixels", 0) > 0 and
            isinstance(scope.get("terminal_title_changed_pixels"), int) and
            scope.get("terminal_title_changed_pixels", 0) > 0 and
            isinstance(scope.get("terminal_status_changed_pixels"), int) and
            scope.get("terminal_status_changed_pixels", 0) > 0 and
            scope.get(
                "terminal_unexpected_static_chrome_changed_pixels") == 0 and
            scope.get("complete_cleanup") is True and
            scope.get("final_lease_mask") == 0,
            "CAP049 HIL scope mismatch")
    require(failures, "storage_write_authorized" not in scope,
            "CAP049 scope retains global storage-write overclaim")
    require(failures, run.get("privacy") == {
        "generic_target_ui": True,
        "private_target_identifiers_retained": False,
    }, "CAP049 privacy declaration mismatch")
    verify_private_target_absent(failures, run)
    require(failures, run.get("start_failure_diagnostics") == {},
            "passing run retained unexpected start-failure diagnostics")
    require(failures, run.get("final_diagnostic_errors") == [],
            "passing run retained final diagnostic read errors")
    require(failures, run.get("input", {}).get("status") == "ready" and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0,
            "input frontend mismatch")
    require(failures,
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("safe_outputs", {}).get("nrf_ce_inactive") is True and
            run.get("safe_outputs", {}).get("software_quiesce_complete") is True,
            "safe outputs mismatch")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures, run.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "final Home/zero-lease cleanup missing")

    verify_manifest(failures, root)
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "status": "pass",
        "board": BOARD_ID,
        "version": args.expected_version,
        "outcome": terminal.get("outcome"),
        "channel": terminal.get("channel"),
        "static_chrome_changed_pixels": 0,
        "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
