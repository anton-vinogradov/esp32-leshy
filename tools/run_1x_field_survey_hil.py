#!/usr/bin/env python3
"""Flash once and prove first/revisit Field Survey product behavior."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action as raw_action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    committed_failures,
    expect,
    focus_survey_start,
    open_product_survey_visit,
    paused_failures,
    query,
    reset_capture,
    return_home_after_commit,
    setup_failures,
    valid_cid,
)


RUN_SCHEMA = "leshy.field_survey_hil.run.v1"
FIELD_SCHEMA = "leshy.survey.field_visit.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
NATIVE_SCHEMA = "leshy.field_survey.native_csv.v1"
WIGLE_SCHEMA = "leshy.field_survey.wigle_csv.v1"
FIELD_SESSION_ID = "field-visit-live"
MAC_PATTERN = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")
NATIVE_COLUMNS = [
    "entity_kind", "identity", "label", "first_seen_monotonic_us",
    "last_seen_monotonic_us", "observations", "strongest_frequency_khz",
    "strongest_channel", "strongest_rssi_dbm", "latest_rssi_dbm",
    "wifi_authentication", "wifi_pairwise_cipher", "wifi_group_cipher",
    "ble_company_id",
]
WIGLE_COLUMNS = [
    "MAC", "SSID", "AuthMode", "FirstSeen", "Channel", "Frequency",
    "RSSI", "CurrentLatitude", "CurrentLongitude", "AltitudeMeters",
    "AccuracyMeters", "RCOIs", "MfgrId", "Type",
]


def require(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def synchronize_console(device: Any, timeout: float) -> None:
    from capture_1x_ui import synchronize_console as synchronize

    synchronize(device, timeout)


def read_only_query(device: Any, command: bytes, schema: str,
                    kind: str, maximum_attempts: int = 3) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = query(device, command, schema, kind)
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
    raise RuntimeError("unreachable read-only retry state")


def action(device: Any, name: str,
           timeout: float = 15.0) -> dict[str, Any]:
    """Never replay a navigation write after a lost acknowledgement."""
    try:
        state = raw_action(device, name, timeout=timeout)
        state["host_navigation_ack_received"] = True
    except TimeoutError as error:
        state = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state")
        state["host_navigation_ack_received"] = False
        state["host_navigation_ack_error"] = str(error)
    state["host_navigation_action_writes"] = 1
    state["host_navigation_action_replays"] = 0
    return state


def wait_state(device: Any,
               predicate: Callable[[dict[str, Any]], bool],
               timeout: float, description: str,
               trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = read_only_query(
            device, b"ui.state", "leshy.ui.v1", "state")
        if last.get("safety_latched") is True:
            safety = read_only_query(
                device, b"safety.state", "leshy.safety.v1", "state")
            if trace is not None:
                trace.append({
                    "checkpoint": "safety_latched",
                    "ui": last,
                    "safety": safety,
                })
            raise RuntimeError(
                f"{description}: safety latch: "
                f"worker={safety.get('worker_last_expired')!r} "
                f"stage={safety.get('product_survey_preparation_stage')!r} "
                f"age_ms={safety.get('worker_age_ms')!r}")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last={last!r}")


def field_state(device: Any) -> dict[str, Any]:
    return read_only_query(
        device, b"survey.field-visit", FIELD_SCHEMA, "state")


def read_framed_csv(device: Any, command: bytes, schema: str,
                    timeout: float = 20.0
                    ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Read begin/payload/end without retaining ambient identities on disk."""
    device.reset_input_buffer()
    device.write(command + b"\n")
    device.flush()
    deadline = time.monotonic() + timeout
    begin: dict[str, Any] | None = None
    end: dict[str, Any] | None = None
    payload = bytearray()
    while time.monotonic() < deadline:
        line = device.readline()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("schema") == schema:
            if value.get("kind") == "begin":
                begin = value
                continue
            if value.get("kind") == "end" and begin is not None:
                end = value
                break
        if begin is not None:
            payload.extend(line)
    if begin is None or end is None:
        raise TimeoutError(f"{schema}: incomplete begin/end framing")
    return begin, bytes(payload), end


def parse_csv(payload: bytes, columns: list[str], label: str
              ) -> tuple[list[str], list[dict[str, str]]]:
    failures: list[str] = []
    rows: list[dict[str, str]] = []
    try:
        text = payload.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != columns:
            failures.append(
                f"{label}.columns: {reader.fieldnames!r} != {columns!r}")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as error:
        failures.append(f"{label}.parse: {error}")
    return failures, rows


def native_export_failures(begin: dict[str, Any], payload: bytes,
                           end: dict[str, Any], *, generation: int,
                           records: int, wifi_stations: int = 0
                           ) -> tuple[list[str], dict[str, Any]]:
    failures = expect(begin, {
        "status": "valid", "generation": generation,
        "session_id": FIELD_SESSION_ID, "records": records,
        "columns": len(NATIVE_COLUMNS), "line_endings": "crlf",
        "deduplicated": True, "persistent": True,
        "radio_touched": False,
    }, "native.begin")
    failures.extend(expect(end, {
        "status": "complete", "records": records,
        "bytes": len(payload), "radio_touched": False,
    }, "native.end"))
    parsed_failures, rows = parse_csv(payload, NATIVE_COLUMNS, "native")
    failures.extend(parsed_failures)
    if len(rows) != records:
        failures.append(f"native.rows: {len(rows)} != {records}")
    identities: set[tuple[str, str]] = set()
    kinds: dict[str, int] = {
        "wifi_access_point": 0, "wifi_station": 0, "ble_device": 0,
    }
    observations = 0
    for index, row in enumerate(rows, start=1):
        prefix = f"native.row[{index}]"
        kind = row.get("entity_kind", "")
        identity = row.get("identity", "")
        if kind not in kinds:
            failures.append(f"{prefix}.entity_kind: {kind!r}")
        else:
            kinds[kind] += 1
        if MAC_PATTERN.fullmatch(identity) is None:
            failures.append(f"{prefix}.identity: invalid canonical MAC")
        key = (kind, identity)
        if key in identities:
            failures.append(f"{prefix}: duplicate deduplicated identity")
        identities.add(key)
        try:
            first = int(row.get("first_seen_monotonic_us", ""))
            last = int(row.get("last_seen_monotonic_us", ""))
            count = int(row.get("observations", ""))
            strongest = int(row.get("strongest_rssi_dbm", ""))
            latest = int(row.get("latest_rssi_dbm", ""))
        except ValueError:
            failures.append(f"{prefix}: invalid numeric evidence")
            continue
        if first < 1 or last < first or count < 1:
            failures.append(f"{prefix}: invalid lifecycle evidence")
        if not -127 <= strongest <= 0 or not -127 <= latest <= 0:
            failures.append(f"{prefix}: invalid RSSI evidence")
        observations += count
    if kinds["wifi_station"] != wifi_stations:
        failures.append(
            "native.wifi_stations: "
            f"{kinds['wifi_station']} != {wifi_stations}")
    return failures, {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_bytes": len(payload), "records": len(rows),
        "observations": observations, "entity_counts": kinds,
        "ambient_identifiers_retained": False,
    }


def wigle_export_failures(begin: dict[str, Any], payload: bytes,
                          end: dict[str, Any], *, generation: int,
                          records: int, wifi_stations: int = 0
                          ) -> tuple[list[str], dict[str, Any]]:
    exported_records = records - wifi_stations
    if exported_records < 0:
        return [
            f"wigle.records: source {records} < stations {wifi_stations}"
        ], {}
    failures = expect(begin, {
        "status": "valid", "generation": generation,
        "session_id": FIELD_SESSION_ID, "format": "wigle_wifi_1.6",
        "records": exported_records,
        "skipped_wifi_stations": wifi_stations,
        "readiness": "untimed_unlocated", "trusted_utc": False,
        "trusted_location": False, "upload_ready": False,
        "persistent": True, "radio_touched": False,
    }, "wigle.begin")
    failures.extend(expect(end, {
        "status": "complete", "records": exported_records,
        "bytes": len(payload),
        "skipped_wifi_stations": wifi_stations,
        "readiness": "untimed_unlocated", "upload_ready": False,
        "radio_touched": False,
    }, "wigle.end"))
    lines = payload.splitlines(keepends=True)
    if not lines or not lines[0].startswith(b"WigleWifi-1.6,"):
        failures.append("wigle.metadata: canonical WiGLE 1.6 line missing")
        csv_payload = b""
    else:
        csv_payload = b"".join(lines[1:])
    parsed_failures, rows = parse_csv(csv_payload, WIGLE_COLUMNS, "wigle")
    failures.extend(parsed_failures)
    if len(rows) != exported_records:
        failures.append(f"wigle.rows: {len(rows)} != {exported_records}")
    types = {"WIFI": 0, "BLE": 0}
    identities: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"wigle.row[{index}]"
        kind = row.get("Type", "")
        mac = row.get("MAC", "")
        if kind not in types:
            failures.append(f"{prefix}.Type: {kind!r}")
        else:
            types[kind] += 1
        if MAC_PATTERN.fullmatch(mac) is None:
            failures.append(f"{prefix}.MAC: invalid canonical MAC")
        key = (kind, mac)
        if key in identities:
            failures.append(f"{prefix}: duplicate exported identity")
        identities.add(key)
        for field in (
                "FirstSeen", "CurrentLatitude", "CurrentLongitude",
                "AltitudeMeters", "AccuracyMeters"):
            if row.get(field) != "":
                failures.append(f"{prefix}.{field}: must be truthfully empty")
    return failures, {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_bytes": len(payload), "records": len(rows),
        "entity_counts": types, "readiness": "untimed_unlocated",
        "upload_ready": False, "ambient_identifiers_retained": False,
    }


def run_exports(device: Any, frames: Path, trace: list[dict[str, Any]],
                generation: int, records: int, wifi_stations: int = 0
                ) -> tuple[dict[str, Any], list[str]]:
    from run_1x_product_survey_hil import open_latest_library

    failures: list[str] = []
    library = open_latest_library(device, trace)
    failures.extend(expect(library, {
        "page": "library", "library_view": "list",
        "library_entries": 1, "library_generation": generation,
        "library_persistent": True, "runtime_owner": "library",
        "lease_mask": 5,
    }, "export.library"))
    detail = action(device, "right")
    trace.append(detail)
    failures.extend(expect(detail, {
        "page": "library", "library_view": "detail",
        "library_generation": generation, "runtime_owner": "library",
        "lease_mask": 5,
    }, "export.detail"))
    export_ready = action(device, "right")
    trace.append(export_ready)
    failures.extend(expect(export_ready, {
        "page": "library", "library_view": "export_ready",
        "library_generation": generation, "runtime_owner": "library",
        "lease_mask": 5,
    }, "export.ready"))
    screenshot = capture(device, frames, "field-survey-export-ready")

    native_begin, native_payload, native_end = read_framed_csv(
        device, b"library.field-survey.export.native", NATIVE_SCHEMA)
    native_failures, native_summary = native_export_failures(
        native_begin, native_payload, native_end,
        generation=generation, records=records,
        wifi_stations=wifi_stations)
    failures.extend(native_failures)
    wigle_begin, wigle_payload, wigle_end = read_framed_csv(
        device, b"library.field-survey.export.wigle", WIGLE_SCHEMA)
    wigle_failures, wigle_summary = wigle_export_failures(
        wigle_begin, wigle_payload, wigle_end,
        generation=generation, records=records,
        wifi_stations=wifi_stations)
    failures.extend(wigle_failures)

    return {
        "library": library, "detail": detail,
        "export_ready": export_ready, "screenshot": screenshot,
        "native": {"begin": native_begin, "end": native_end,
                   "summary": native_summary},
        "wigle": {"begin": wigle_begin, "end": wigle_end,
                  "summary": wigle_summary},
    }, failures


def field_result_failures(record: dict[str, Any], status: str,
                          baseline_unique: int | None = None,
                          require_wifi_station: bool = False) -> list[str]:
    failures = expect(record, {
        "active": True,
        "status": status,
        "build_status": "complete",
        "complete": True,
        "session_id_exact": True,
        "session_stopped": True,
        "radio_touched": False,
        "storage_touched": False,
    }, status)
    current = record.get("current_unique")
    wifi_ap = record.get("wifi_access_points")
    wifi_sta = record.get("wifi_stations")
    ble = record.get("ble_devices")
    if not isinstance(current, int) or current < 1:
        failures.append(f"{status}.current_unique: expected >= 1")
        return failures
    if not all(isinstance(value, int) and value >= 0
               for value in (wifi_ap, wifi_sta, ble)):
        failures.append(f"{status}.radio_counts: invalid")
    elif wifi_ap + wifi_sta + ble != current:
        failures.append(f"{status}.radio_counts: do not total current_unique")
    if require_wifi_station and (not isinstance(wifi_sta, int) or wifi_sta < 1):
        failures.append(f"{status}.wifi_stations: expected >= 1")
    if status == "first_visit":
        failures.extend(expect(record, {
            "compare_previous": False,
            "baseline_unique": 0,
            "seen_again": 0,
            "new_this_visit": current,
            "missing_this_visit": 0,
        }, status))
    elif status == "compared":
        if baseline_unique is None or baseline_unique < 1:
            failures.append("compared.baseline_unique: missing expected baseline")
        else:
            failures.extend(expect(record, {
                "previous_available": True,
                "compare_previous": True,
                "baseline_unique": baseline_unique,
            }, status))
            seen = record.get("seen_again")
            new = record.get("new_this_visit")
            missing = record.get("missing_this_visit")
            if not all(isinstance(value, int) and value >= 0
                       for value in (seen, new, missing)):
                failures.append("compared.delta_counts: invalid")
            elif seen + new != current or seen + missing != baseline_unique:
                failures.append("compared.delta_counts: inconsistent set arithmetic")
    return failures


def auto_paused_failures(state: dict[str, Any], expected_cid: str,
                         label: str) -> list[str]:
    observations = state.get("survey_observations")
    scan_cycles = state.get("survey_product_scan_cycles")
    failures: list[str] = []
    if not isinstance(observations, int) or observations < 1:
        failures.append(f"{label}.survey_observations: expected >= 1")
        return failures
    if not isinstance(scan_cycles, int) or scan_cycles != 1:
        failures.append(f"{label}.survey_product_scan_cycles: expected 1")
        return failures
    failures.extend(paused_failures(
        state, observations, scan_cycles, "wifi"))
    failures.extend(expect(state, {
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_product_identity_status": "valid",
        "survey_product_selected_source_mask": 3,
        "survey_product_active_source_mask": 3,
        "survey_product_wifi_scan_cycles": 1,
        "survey_product_ble_scan_cycles": 1,
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_ble_scan_rejected": 0,
        "survey_ble_scan_dropped": 0,
        "survey_dropped": 0,
    }, label))
    wifi_accepted = state.get("survey_scan_accepted")
    ble_accepted = state.get("survey_ble_scan_accepted")
    forwarded = state.get("survey_forwarded")
    if (not isinstance(wifi_accepted, int) or
            not isinstance(ble_accepted, int) or
            wifi_accepted + ble_accepted != observations or
            forwarded != observations):
        failures.append(
            f"{label}.observation_accounting: "
            "wifi+ble accepted/forwarded/observations differ")
    return failures


def post_commit_recovery_failures(record: dict[str, Any], expected_cid: str,
                                  expected_generation: int,
                                  label: str) -> list[str]:
    failures = expect(record, {
        "status": "admitted",
        "catalog_admitted": True,
        "integrity": "valid",
        "expected_fingerprint": expected_cid,
        "observed_fingerprint": expected_cid,
        "fingerprint_matched": True,
        "generation": expected_generation,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
        "owned_after": 0,
    }, label)
    observations = record.get("observations")
    if not isinstance(observations, int) or observations < 1:
        failures.append(f"{label}.observations: expected >= 1")
    return failures


def begin_hil(device: Any, run_id: str, app_sha: str,
              version: str) -> dict[str, Any]:
    try:
        begun = query(
            device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
            HIL_SCHEMA, "begun")
        begun["host_begin_ack_received"] = True
    except TimeoutError as error:
        begun = read_only_query(device, b"hil.state", HIL_SCHEMA, "state")
        begun["host_begin_ack_received"] = False
        begun["host_begin_ack_error"] = str(error)
    require(begun, {
        "session_id": run_id, "active": True,
        "app_elf_sha256": app_sha, "firmware_version": version,
    }, "hil_begin")
    begun["host_begin_action_writes"] = 1
    begun["host_begin_action_replays"] = 0
    return begun


def end_hil(device: Any, run_id: str, app_sha: str) -> dict[str, Any]:
    try:
        ended = query(
            device, f"hil.end {run_id}".encode("ascii"),
            HIL_SCHEMA, "ended")
        ended["host_end_ack_received"] = True
    except TimeoutError as error:
        ended = read_only_query(device, b"hil.state", HIL_SCHEMA, "state")
        ended["host_end_ack_received"] = False
        ended["host_end_ack_error"] = str(error)
    require(ended, {
        "active": False, "app_elf_sha256": app_sha,
    }, "hil_end")
    if ended.get("session_id") not in (None, "", run_id):
        raise RuntimeError("hil_end: unexpected terminal session id")
    ended["host_end_action_writes"] = 1
    ended["host_end_action_replays"] = 0
    ended["host_end_requested_session_id"] = run_id
    return ended


def run_visit(device: Any, frames: Path, name: str,
              before_generation: int, first: bool,
              trace: list[dict[str, Any]], expected_cid: str,
              baseline_unique: int | None = None,
              run_incomplete_negative: bool = False,
              require_wifi_station: bool = False) -> dict[str, Any]:
    setup = open_product_survey_visit(device, trace)
    failures = setup_failures(setup, "wifi")
    failures.extend(expect(setup, {
        "survey_source_selected_mask": 3,
        "survey_source_selected_count": 2,
        "survey_source_can_start": True,
    }, f"{name}.all_receivers"))
    if failures:
        raise RuntimeError("; ".join(failures))

    setup_field = field_state(device)
    require(setup_field, {"active": True}, f"{name}.field_setup")
    if first and setup_field.get("compare_previous") is True:
        selection = action(device, "down")
        trace.append(selection)
        require(selection, {"survey_setup_selection": 1},
                f"{name}.compare_row")
        toggled = action(device, "select")
        trace.append(toggled)
        setup_field = field_state(device)
    comparison_expected: dict[str, Any] = {
        "compare_previous": not first,
        "status": "empty",
    }
    if not first:
        comparison_expected["previous_available"] = True
    require(setup_field, comparison_expected, f"{name}.comparison_mode")
    setup_capture = capture(device, frames, f"{name}-setup")

    start = focus_survey_start(device)
    trace.append(start)
    started = action(device, "select")
    trace.append(started)
    require(started, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_status": "preparing",
    }, f"{name}.start_ack")
    paused = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False and
            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
            state.get("survey_observations", 0) >= 1
        ), 35.0, f"{name}: one receive pass did not auto-pause",
        trace)
    trace.append(paused)
    failures = auto_paused_failures(
        paused, expected_cid, f"{name}.auto_paused")
    if failures:
        raise RuntimeError("; ".join(failures))

    incomplete: dict[str, Any] = {}
    if run_incomplete_negative:
        incomplete = query(
            device, b"survey.field-visit.test-incomplete once",
            FIELD_SCHEMA, "state")
        require(incomplete, {
            "active": True,
            "status": "incomplete",
            "build_status": "session_not_stopped",
            "complete": False,
            "session_id_exact": True,
            "session_stopped": False,
            "radio_touched": False,
            "storage_touched": False,
        }, f"{name}.incomplete_negative")

    paused_observations = int(paused["survey_observations"])
    paused_cycles = int(paused["survey_product_scan_cycles"])
    failures = paused_failures(
        paused, paused_observations, paused_cycles, "wifi")
    time.sleep(0.25)
    paused_stable = read_only_query(
        device, b"ui.state", "leshy.ui.v1", "state")
    failures.extend(expect(paused_stable, {
        "survey_product_status": "paused",
        "survey_product_source_active": False,
        "survey_observations": paused_observations,
        "survey_product_scan_cycles": paused_cycles,
    }, f"{name}.paused_stable"))
    if failures:
        raise RuntimeError("; ".join(failures))

    trace.append(action(device, "down"))
    trace.append(action(device, "right"))
    committed = action(device, "select", timeout=40.0)
    trace.append(committed)
    if committed.get("survey_product_status") != "committed":
        committed = wait_state(
            device,
            lambda state: state.get("survey_product_status") == "committed",
            20.0, f"{name}: did not commit", trace)
        trace.append(committed)
    failures = committed_failures(
        committed, before_generation, "wifi", automatic_pause=True)
    if failures:
        raise RuntimeError("; ".join(failures))

    result = field_state(device)
    result_failures = field_result_failures(
        result, "first_visit" if first else "compared",
        None if first else baseline_unique,
        require_wifi_station=require_wifi_station)
    if result_failures:
        raise RuntimeError("; ".join(result_failures))
    result_capture = capture(device, frames, f"{name}-result")
    home = return_home_after_commit(device, trace)
    require(home, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_source_active": False,
    }, f"{name}.home")
    return {
        "setup": setup,
        "setup_field": setup_field,
        "setup_capture": setup_capture,
        "auto_paused": paused,
        "incomplete_negative": incomplete,
        "paused": paused,
        "committed": committed,
        "result": result,
        "result_capture": result_capture,
        "home": home,
    }


def run_preflight(device: Any, frames: Path,
                  trace: list[dict[str, Any]],
                  expected_cid: str) -> dict[str, Any]:
    """Prove one live Wi-Fi+BLE cycle without committing a field visit."""
    setup = open_product_survey_visit(device, trace)
    failures = setup_failures(setup, "wifi")
    failures.extend(expect(setup, {
        "survey_source_selected_mask": 3,
        "survey_source_selected_count": 2,
        "survey_source_can_start": True,
    }, "preflight.all_receivers"))
    if failures:
        raise RuntimeError("; ".join(failures))
    setup_capture = capture(device, frames, "preflight-setup")

    start = focus_survey_start(device)
    trace.append(start)
    started = action(device, "select")
    trace.append(started)
    require(started, {
        "page": "survey", "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_status": "preparing",
    }, "preflight.start_ack")
    paused = wait_state(
        device,
        lambda state: (
            state.get("survey_product_status") == "paused" and
            state.get("survey_product_source_active") is False and
            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
            state.get("survey_observations", 0) >= 1
        ), 35.0, "preflight: one receive pass did not auto-pause",
        trace)
    trace.append(paused)
    failures = auto_paused_failures(
        paused, expected_cid, "preflight.auto_paused")
    if failures:
        raise RuntimeError("; ".join(failures))
    paused_capture = capture(device, frames, "preflight-auto-paused")
    return {
        "setup": setup,
        "setup_capture": setup_capture,
        "start": start,
        "started": started,
        "auto_paused": paused,
        "auto_paused_capture": paused_capture,
        "writes_committed": 0,
    }


def main() -> int:
    from capture_1x_ui import PassiveSerial

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="reuse the already-flashed exact candidate after boot identity proof",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only", action="store_true",
        help=("run one live Wi-Fi+BLE cycle, cancel to Home, and never commit "
              "a field visit"),
    )
    mode.add_argument(
        "--recovery-only", action="store_true",
        help=("cold-reset and prove the already-committed exact generation "
              "read-only without scanning or writing"),
    )
    mode.add_argument(
        "--export-only", action="store_true",
        help=("cold-reset and prove bounded native/WiGLE Library exports "
              "without scanning or writing"),
    )
    parser.add_argument(
        "--expected-generation", type=int,
        help=("exact retained generation required by --recovery-only or "
              "--export-only"),
    )
    parser.add_argument(
        "--expected-records", type=int,
        help="exact deduplicated record count required by --export-only",
    )
    parser.add_argument(
        "--expected-wifi-stations", type=int, default=0,
        help=("exact native station count and WiGLE exclusion count required "
              "by --export-only"),
    )
    parser.add_argument(
        "--require-wifi-station", action="store_true",
        help="require at least one live passive station in each committed visit",
    )
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hex characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit")
    if ((args.recovery_only or args.export_only) and
            args.expected_generation is None):
        parser.error(
            "--recovery-only/--export-only require --expected-generation")
    if (not args.recovery_only and not args.export_only and
            args.expected_generation is not None):
        parser.error(
            "--expected-generation is valid only with recovery/export mode")
    if args.export_only and args.expected_records is None:
        parser.error("--export-only requires --expected-records")
    if not args.export_only and args.expected_records is not None:
        parser.error("--expected-records is valid only with --export-only")
    if args.expected_wifi_stations < 0:
        parser.error("--expected-wifi-stations must be non-negative")
    if not args.export_only and args.expected_wifi_stations != 0:
        parser.error(
            "--expected-wifi-stations is valid only with --export-only")
    if args.require_wifi_station and (
            args.preflight_only or args.recovery_only or args.export_only):
        parser.error("--require-wifi-station is valid only in full mode")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_sha = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    begun: dict[str, Any] = {}
    ended: dict[str, Any] = {}
    first: dict[str, Any] = {}
    revisit: dict[str, Any] = {}
    preflight: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    boot: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    boot_timing: dict[str, Any] = {}
    post_commit_boot: dict[str, Any] = {}
    post_commit_recovery: dict[str, Any] = {}
    post_commit_boot_timing: dict[str, Any] = {}
    flashed = False
    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "run_id": run_id,
        "source_commit": args.source_commit,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_sha,
        },
    }
    write_json(args.output / "run.json", record)

    try:
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flashed = True
            time.sleep(0.75)
        boot, recovery, boot_timing = reset_capture(
            args.port, args.output, "boot", 20.0, maximum_attempts=1)

        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 20.0)
            try:
                recovery = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery, args.expected_version, app_sha,
                    args.expected_cid))
                if failures:
                    raise RuntimeError("; ".join(failures))
                if args.recovery_only:
                    failures.extend(post_commit_recovery_failures(
                        recovery, args.expected_cid,
                        int(args.expected_generation), "post_commit_recovery"))
                    if failures:
                        raise RuntimeError("; ".join(failures))
                    cleanup = best_effort_cleanup(device)
                    if not cleanup.get("complete"):
                        raise RuntimeError(
                            "recovery cleanup: terminal Home/none/lease0 unproven")
                else:
                    begun = begin_hil(device, run_id, app_sha,
                                      args.expected_version)
                    generation = int(recovery["generation"])
                if args.export_only:
                    failures.extend(post_commit_recovery_failures(
                        recovery, args.expected_cid,
                        int(args.expected_generation), "export_recovery"))
                    if recovery.get("observations") != args.expected_records:
                        failures.append(
                            "export_recovery.observations: "
                            f"{recovery.get('observations')!r} != "
                            f"{args.expected_records}")
                    if failures:
                        raise RuntimeError("; ".join(failures))
                    exports, export_failures = run_exports(
                        device, frames, trace, int(args.expected_generation),
                        int(args.expected_records),
                        args.expected_wifi_stations)
                    failures.extend(export_failures)
                    cleanup = best_effort_cleanup(device)
                    if not cleanup.get("complete"):
                        raise RuntimeError(
                            "export cleanup: terminal Home/none/lease0 unproven")
                elif args.preflight_only:
                    preflight = run_preflight(
                        device, frames, trace, args.expected_cid)
                    cleanup = best_effort_cleanup(device)
                    if not cleanup.get("complete"):
                        raise RuntimeError(
                            "preflight cleanup: terminal Home/none/lease0 unproven")
                elif not args.recovery_only:
                    first = run_visit(
                        device, frames, "first", generation, True, trace,
                        args.expected_cid,
                        run_incomplete_negative=True,
                        require_wifi_station=args.require_wifi_station)
                    first_result = first["result"]
                    first_unique = int(first_result["current_unique"])
                    generation += 1
                    revisit = run_visit(
                        device, frames, "revisit", generation, False, trace,
                        args.expected_cid, baseline_unique=first_unique,
                        require_wifi_station=args.require_wifi_station)
                if not args.recovery_only:
                    ended = end_hil(device, run_id, app_sha)
            finally:
                if not cleanup.get("complete"):
                    cleanup = best_effort_cleanup(device)
                if not ended and not args.recovery_only:
                    try:
                        hil_state = read_only_query(
                            device, b"hil.state", HIL_SCHEMA, "state")
                        if (hil_state.get("active") is True and
                                hil_state.get("session_id") == run_id):
                            ended = end_hil(device, run_id, app_sha)
                        elif hil_state.get("active") is True:
                            failures.append(
                                "hil_cleanup: another session is active")
                        else:
                            ended = hil_state
                    except Exception as error:
                        failures.append(f"hil_cleanup: {type(error).__name__}: {error}")
                if not cleanup.get("complete"):
                    failures.append("cleanup: terminal Home/none/lease0 unproven")
        if (not args.preflight_only and not args.recovery_only and
                not args.export_only and not failures):
            expected_generation = int(revisit["committed"]["library_generation"])
            post_commit_boot, post_commit_recovery, post_commit_boot_timing = (
                reset_capture(
                    args.port, args.output, "post-commit-cold", 20.0,
                    maximum_attempts=1))
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                synchronize_console(device, 20.0)
                post_commit_recovery = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    post_commit_boot, post_commit_recovery,
                    args.expected_version, app_sha, args.expected_cid))
                failures.extend(post_commit_recovery_failures(
                    post_commit_recovery, args.expected_cid,
                    expected_generation, "post_commit_recovery"))
                cleanup = best_effort_cleanup(device)
                if not cleanup.get("complete"):
                    failures.append(
                        "post_commit_cleanup: terminal Home/none/lease0 unproven")
    except Exception as error:
        message = f"workflow: {type(error).__name__}: {error}"
        if message not in failures:
            failures.append(message)

    record.update({
        "status": "pass" if not failures else "failed",
        "passed": not failures,
        "mode": ("preflight" if args.preflight_only else
                 "recovery" if args.recovery_only else
                 "export" if args.export_only else "full"),
        "gate_eligible": (
            (flashed or args.reuse_exact_flash) and not failures and (
                (args.export_only and bool(exports)) or
                (not args.preflight_only and not args.recovery_only and
                 not args.export_only and bool(post_commit_recovery) and
                 bool(revisit)))
        ),
        "failures": failures,
        "flashed": flashed,
        "reused_exact_flash": args.reuse_exact_flash,
        "boot": {"ready": boot, "recovery": recovery,
                 "timing": boot_timing},
        "post_commit_boot": {
            "ready": post_commit_boot,
            "recovery": post_commit_recovery,
            "timing": post_commit_boot_timing,
        },
        "hil_begin": begun,
        "preflight": preflight,
        "exports": exports,
        "first_visit": first,
        "revisit": revisit,
        "hil_end": ended,
        "cleanup": cleanup,
        "trace": trace,
    })
    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "status": record["status"],
        "passed": record["passed"], "failures": failures,
        "output": str(args.output),
    }, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
