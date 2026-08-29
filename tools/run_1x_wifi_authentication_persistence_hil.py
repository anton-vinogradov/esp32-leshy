#!/usr/bin/env python3
"""CAP049 delta: persist a public M1/M2 fixture, reboot, and export it.

The only ambient-RF part is the already-authorized product navigation needed
to reach an authentication result.  The persistence fixture itself is public,
deterministic, RX/TX inert, and exercises the production analyzer/store/export
path.  Raw PCAP/hc22000 bytes stay in process memory; run.json retains hashes
and counts only.
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

from capture_1x_boot import reset_and_capture_reconnecting
from capture_1x_ui import (
    PassiveSerial,
    read_exact,
    read_json,
    synchronize_console,
)
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    action,
    begin_hil_session,
    end_hil_session,
    robust_cleanup,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    expect,
    query,
    valid_cid,
)
from run_1x_wifi_authentication_capture_hil import (
    AUTH_SCHEMA,
    BOARD_ID,
    BOARD_PORT,
    FORBIDDEN_FIXTURE_PORT,
    auth_state,
    home_wifi,
    private_target_failures,
    privacy_safe_exception,
    run_minimal_ambient_terminal,
    scrub_private_target_identifiers,
)
from run_1x_wifi_frame_capture_hil import parse_pcap


RUN_SCHEMA = "leshy.wifi.authentication_persistence_hil.run.v1"
FIXTURE_SCHEMA = "leshy.wifi.authentication.persistence_fixture.v1"
FIXTURE_COMMAND = b"wifi.authentication.hil-load-persistence-fixture once"
PERSISTENCE_SCHEMA = "leshy.wifi.authentication_persistence.v1"
PCAP_SCHEMA = "leshy.library.pcap.v1"
HC22000_SCHEMA = "leshy.library.hc22000.v1"
RECOVERY_SCHEMA = "leshy.storage.product_boot_recovery.v1"
METADATA_SCHEMA = "leshy.capture.metadata.v1"
UI_SCHEMA = "leshy.ui.v1"


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def wait_query(device: PassiveSerial, command: bytes, schema: str,
               predicate: Callable[[dict[str, Any]], bool], timeout: float,
               description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, command, schema, "state", timeout=3.0)
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: terminal state not observed")


def read_binary_artifact(
        device: PassiveSerial, command: bytes, schema: str,
        begin_kind: str, end_kind: str, maximum_bytes: int,
        ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    device.reset_input_buffer()
    device.write(command + b"\n")
    device.flush()
    begin = read_json(device, schema, begin_kind, timeout=20.0)
    size = begin.get("bytes")
    if (not isinstance(size, int) or isinstance(size, bool) or
            size <= 0 or size > maximum_bytes):
        raise ValueError(f"{begin_kind}: invalid bounded byte count")
    payload = read_exact(device, size, timeout=20.0)
    end = read_json(device, schema, end_kind, timeout=20.0)
    return begin, payload, end


def hc22000_summary(payload: bytes) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return {}, ["hc22000 payload is not ASCII"]
    lines = [line for line in text.splitlines() if line]
    if len(lines) != 1:
        failures.append("hc22000 payload must contain exactly one record")
    record = lines[0] if lines else ""
    fields = record.split("*")
    if len(fields) != 9 or fields[:2] != ["WPA", "02"]:
        failures.append("hc22000 payload is not one WPA*02 EAPOL record")
    if record and re.fullmatch(r"[A-Z0-9*]+", record) is None:
        failures.append("hc22000 payload contains unexpected characters")
    return {
        "records": len(lines),
        "format": "WPA*02",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }, failures


def safe_ambient_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    terminal = workflow.get("terminal", {})
    capture = workflow.get("capture_terminal", {})
    network_list = workflow.get("network_list", {})
    selector = network_list.get("authorized_selector", {})
    return {
        "authorized_selector_selected":
            selector.get("status") == "selected",
        "selector_attempts": selector.get("host_selector_attempts", 0),
        "selector_transient_retries":
            selector.get("host_selector_transient_retries", 0),
        "terminal_state": terminal.get("state"),
        "report_origin": terminal.get("report_origin"),
        "outcome": terminal.get("outcome"),
        "capture_cleanup_complete": terminal.get(
            "capture_cleanup_complete"),
        "adapter_cleanup_complete": terminal.get(
            "adapter_cleanup_complete"),
        "connect_calls": capture.get("application_connect_calls"),
        "raw_tx_calls": capture.get("application_raw_tx_calls"),
        "private_target_identifiers_retained": False,
    }


def open_home_item(device: PassiveSerial, item_id: str,
                   destination_page: str) -> dict[str, Any]:
    """Open a Home item by stable identity, independent of menu order."""
    state = query(device, b"ui.state", UI_SCHEMA, "state")
    if state.get("page") != "home":
        raise RuntimeError("Home expected before semantic navigation")
    for _ in range(8):
        if state.get("selected_id") == item_id:
            opened = action(device, "right")
            if opened.get("page") != destination_page:
                raise RuntimeError(
                    f"{item_id} opened {opened.get('page')!r}, "
                    f"expected {destination_page!r}")
            return opened
        state = action(device, "down")
    raise RuntimeError(f"Home item {item_id!r} was not found")


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
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if args.port == FORBIDDEN_FIXTURE_PORT:
        parser.error("board-02/clone is forbidden for CAP049 persistence")
    if args.port != BOARD_PORT:
        parser.error(f"CAP049 persistence is bound to {BOARD_ID} at {BOARD_PORT}")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not args.flash:
        parser.error("CAP049 persistence requires one fresh app flash")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if re.fullmatch(r"[0-9a-fA-F]{40}", args.source_commit) is None:
        parser.error("--source-commit must be a full hexadecimal Git commit ID")
    if (re.fullmatch(r"[0-9a-fA-F]{16}", args.allowed_ssid_fnv1a64) is None or
            int(args.allowed_ssid_fnv1a64, 16) == 0):
        parser.error("--allowed-ssid-fnv1a64 must be one non-zero 64-bit hex")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    fixture_ack: dict[str, Any] = {}
    fixture_replay: dict[str, Any] = {}
    fixture_state: dict[str, Any] = {}
    actions_state: dict[str, Any] = {}
    save_state: dict[str, Any] = {}
    confirm_state: dict[str, Any] = {}
    persisted: dict[str, Any] = {}
    ambient_summary: dict[str, Any] = {}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_saved: dict[str, Any] = {"attempted": False}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    pcap_begin: dict[str, Any] = {}
    pcap_end: dict[str, Any] = {}
    pcap_summary: dict[str, Any] = {}
    hc_begin: dict[str, Any] = {}
    hc_end: dict[str, Any] = {}
    hc_summary: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_after: dict[str, Any] = {"attempted": False}
    generation = 0
    pcap_payload = b""
    hc_payload = b""

    try:
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot_before, _ = stabilized_boot_metrics(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    RECOVERY_SCHEMA, "state")
                failures.extend(boot_failures(
                    boot_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                previous_generation = int(recovery_before["generation"])
                cleanup_before = robust_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)

                private_trace: list[dict[str, Any]] = []
                ambient = run_minimal_ambient_terminal(
                    device, private_trace, "persistence",
                    args.allowed_ssid_fnv1a64.lower(), {})
                ambient_summary = safe_ambient_summary(ambient)
                del ambient
                private_trace.clear()

                fixture_ack = query(
                    device, FIXTURE_COMMAND, FIXTURE_SCHEMA, "loaded")
                require_exact(fixture_ack, {
                    "status": "loaded", "loaded": True,
                    "synthetic": True,
                    "profile": "strict-m1-m2-raw-v1",
                    "report_origin": "synthetic_hil_persistence",
                    "one_shot": True, "replayed": False,
                    "hil_active": True, "fixture_frames": 2,
                    "strict_message_pair": True,
                    "display_touched": True,
                    "rf_hardware_touched": False,
                    "radio_started": False,
                    "persistence_allowed": True,
                    "export_allowed": True,
                    "storage_mounted": False,
                    "storage_written": False,
                    "connect_calls": 0, "raw_tx_calls": 0,
                    "raw_payload_disclosed": False,
                    "public_test_identifiers_only": True,
                    "response_complete": True,
                }, "fixture_ack")
                fixture_state = auth_state(device)
                require_exact(fixture_state, {
                    "view": "authentication_capture", "state": "result",
                    "synthetic": True,
                    "report_origin": "synthetic_hil_persistence",
                    "passive": True, "tx_path": False,
                    "connect_path": False, "target_selected": True,
                    "target_selection_continuity": True, "channel": 6,
                    "capture_state": "complete", "frames_reported": 2,
                    "frames_accepted": 2, "capture_active": False,
                    "analysis_accounting_valid": True,
                    "capture_cleanup_complete": True,
                    "adapter_cleanup_complete": True,
                    "presenter_synthetic": True,
                    "presenter_synthetic_label_visible": True,
                    "synthetic_persistence_allowed": True,
                    "synthetic_export_allowed": True,
                    "controller_ready": True,
                    "controller_view": "outcome",
                    "controller_action_count": 3,
                    "controller_selected_action": "details",
                    "controller_peer_count": 1,
                    "controller_selected_peer_mask": 3,
                    "evidence": 2, "peers": 1,
                    # M1+M2 is the minimum exportable hc22000 pair, not a
                    # complete four-message exchange in the UI vocabulary.
                    "complete_peers": 0, "partial_peers": 1,
                    "source_frames": 2, "frames_read": 2,
                    "data_frames": 2, "eapol_frames": 2,
                    "eapol_key_frames": 2,
                    "classified_key_frames": 2,
                    "report_capture_frames_reported": 2,
                    "report_capture_frames_accepted": 2,
                    "esp_rf_owned_by_foreground": True,
                }, "fixture_state")
                fixture_replay = query(
                    device, FIXTURE_COMMAND, FIXTURE_SCHEMA, "error")
                require_exact(fixture_replay, {
                    "status": "replay_rejected", "loaded": False,
                    "synthetic": True, "one_shot": True,
                    "replayed": True, "hil_active": True,
                    "rf_hardware_touched": False,
                    "radio_started": False,
                    "persistence_allowed": False,
                    "export_allowed": False,
                    "storage_mounted": False,
                    "storage_written": False,
                    "connect_calls": 0, "raw_tx_calls": 0,
                    "raw_payload_disclosed": False,
                    "public_test_identifiers_only": True,
                    "response_complete": True,
                }, "fixture_replay")

                action(device, "right")
                actions_state = auth_state(device)
                require_exact(actions_state, {
                    "controller_view": "actions",
                    "controller_selected_action": "details",
                    "synthetic_persistence_allowed": True,
                }, "actions_state")
                action(device, "down")
                save_state = auth_state(device)
                require_exact(save_state, {
                    "controller_view": "actions",
                    "controller_selected_action": "save",
                    "controller_action_selection": 1,
                }, "save_state")
                action(device, "right")
                confirm_state = query(
                    device, b"wifi.authentication.persistence.state",
                    PERSISTENCE_SCHEMA, "state")
                require_exact(confirm_state, {
                    "state": "confirm", "status": "awaiting_confirmation",
                    "generation": 0, "pcap_ready": False,
                    "hc22000_ready": False, "capture_complete": True,
                    "capture_frames": 2, "cleanup_complete": True,
                    "worker_active": False,
                    "store_kind": "authentication",
                    "explicit_save": True, "atomic_commit": True,
                    "reopen_verified": False,
                    "radio_touched_by_query": False,
                }, "confirm_state")
                action(device, "right")
                persisted = wait_query(
                    device, b"wifi.authentication.persistence.state",
                    PERSISTENCE_SCHEMA,
                    lambda value: value.get("state") in ("saved", "failed"),
                    35.0, "authentication persistence")
                generation = int(persisted.get("generation", 0))
                require_exact(persisted, {
                    "state": "saved", "status": "saved",
                    "generation": previous_generation + 1,
                    "pcap_ready": True, "hc22000_ready": True,
                    "capture_complete": True, "capture_frames": 2,
                    "cleanup_complete": True, "worker_active": False,
                    "store_kind": "authentication",
                    "explicit_save": True, "atomic_commit": True,
                    "reopen_verified": True,
                    "radio_touched_by_query": False,
                }, "persisted")

                # Actions -> Outcome -> Wi-Fi menu -> Home.  Each mutation is
                # issued once; semantic cleanup proves the terminal state.
                action(device, "left")
                action(device, "left")
                cleanup_saved = robust_cleanup(device)
                if not cleanup_saved.get("complete"):
                    raise RuntimeError("saved capture did not return Home")
                hil_end = end_hil_session(device, run_id, app_identity)
            except Exception as error:
                failures.append(
                    f"persist_phase: {privacy_safe_exception(error)}")
                cleanup_saved = robust_cleanup(device)
                try:
                    hil_end = end_hil_session(device, run_id, app_identity)
                except Exception as cleanup_error:
                    failures.append(
                        "hil_cleanup: " + privacy_safe_exception(cleanup_error))

        if not failures:
            reset_and_capture_reconnecting(args.port, 20.0)
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                try:
                    synchronize_console(device, 30.0)
                    boot_after, _ = stabilized_boot_metrics(device)
                    recovery_after = query(
                        device, b"storage.product.boot-recovery",
                        RECOVERY_SCHEMA, "state")
                    failures.extend(boot_failures(
                        boot_after, recovery_after, args.expected_version,
                        app_identity, args.expected_cid))
                    require_exact(recovery_after, {
                        "status": "admitted", "generation": generation,
                        "observations": 0, "mounted_read_only": True,
                        "read_only_guaranteed": True,
                        "blocked_write_attempts": 0,
                        "physical_write_calls": 0,
                        "cleanup_complete": True, "owned_after": 0,
                    }, "cold_recovery")

                    # Resolve Library by stable identity; product menu order is
                    # intentionally free to evolve.
                    open_home_item(device, "library", "library")
                    action(device, "right")
                    action(device, "right")
                    metadata = query(
                        device, b"library.capture", METADATA_SCHEMA,
                        "capture")
                    payload = metadata.get("payload", {})
                    exports = metadata.get("exports", {})
                    require_exact(metadata, {
                        "status": "valid", "generation": generation,
                        "integrity": "valid", "persistent": True,
                        "immutable": True, "observations": 0,
                        "dropped": 0, "radio_touched": False,
                    }, "metadata")
                    require_exact(payload, {
                        "status": "captured_raw_80211", "records": 2,
                        "snap_length": 256, "format": "ieee80211",
                    }, "metadata_payload")
                    if payload.get("bytes") != 284:
                        raise RuntimeError("metadata payload byte count != 284")
                    if exports.get("pcap") != "available_radiotap":
                        raise RuntimeError("metadata PCAP export unavailable")

                    pcap_begin, pcap_payload, pcap_end = read_binary_artifact(
                        device, b"library.export.pcap", PCAP_SCHEMA,
                        "pcap_begin", "pcap_end", 4096)
                    require_exact(pcap_begin, {
                        "status": "valid", "generation": generation,
                        "frames": 2, "linktype": 127,
                        "timebase": "monotonic_us", "streaming": True,
                        "persistent": True, "radio_touched": False,
                    }, "pcap_begin")
                    require_exact(pcap_end, {
                        "status": "valid", "bytes": len(pcap_payload),
                        "frames": 2, "persistent": True,
                        "radio_touched": False,
                    }, "pcap_end")
                    pcap_summary, pcap_failures = parse_pcap(pcap_payload)
                    failures.extend(pcap_failures)
                    pcap_summary["sha256"] = hashlib.sha256(
                        pcap_payload).hexdigest()
                    if pcap_summary.get("records") != 2:
                        failures.append("PCAP parser did not recover two frames")

                    hc_begin, hc_payload, hc_end = read_binary_artifact(
                        device, b"library.export.hc22000", HC22000_SCHEMA,
                        "hc22000_begin", "hc22000_end", 4096)
                    require_exact(hc_begin, {
                        "status": "valid", "generation": generation,
                        "streaming": True, "persistent": True,
                        "radio_touched": False,
                    }, "hc22000_begin")
                    require_exact(hc_end, {
                        "status": "valid", "bytes": len(hc_payload),
                        "records": 1, "pmkid_records": 0,
                        "eapol_records": 1, "persistent": True,
                        "radio_touched": False,
                    }, "hc22000_end")
                    hc_summary, hc_failures = hc22000_summary(hc_payload)
                    failures.extend(hc_failures)

                    action(device, "left")
                    action(device, "left")
                    action(device, "left")
                    final = query(device, b"ui.state", UI_SCHEMA, "state")
                    require_exact(final, {
                        "page": "home", "runtime_owner": "none",
                        "lease_mask": 0,
                    }, "final")
                except Exception as error:
                    failures.append(
                        f"cold_phase: {privacy_safe_exception(error)}")
                finally:
                    cleanup_after = robust_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("cold cleanup did not prove Home/lease0")
    except Exception as error:
        failures.append(f"runner: {privacy_safe_exception(error)}")

    # Never serialize raw artifacts, the authorized SSID hash, or ambient
    # target identifiers.  The firmware copy remains only in ignored work/.
    result: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": not failures,
        "gate_eligible": not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": True,
        },
        "board": {"id": BOARD_ID, "expected_cid": args.expected_cid},
        "boot_before": {
            "ready": boot_before, "recovery": recovery_before,
        },
        "ambient_admission": ambient_summary,
        "fixture": {
            "load": fixture_ack, "replay": fixture_replay,
            "state": fixture_state, "actions": actions_state,
            "save_selected": save_state, "confirm": confirm_state,
            "persisted": persisted,
        },
        "hil": {"begin": hil_begin, "end": hil_end},
        "cleanup_before": cleanup_before,
        "cleanup_after_save": cleanup_saved,
        "boot_after": {
            "ready": boot_after, "recovery": recovery_after,
        },
        "library": {
            "metadata": metadata,
            "pcap": {
                "begin": pcap_begin, "end": pcap_end,
                "summary": pcap_summary,
            },
            "hc22000": {
                "begin": hc_begin, "end": hc_end,
                "summary": hc_summary,
            },
        },
        "final": final,
        "cleanup_after": cleanup_after,
        "privacy": {
            "authorized_ssid_hash_retained": False,
            "ambient_target_identifiers_retained": False,
            "raw_pcap_retained": False,
            "raw_hc22000_retained": False,
            "artifact_retention": "hashes_counts_and_format_only",
            "fixture_identifiers": "public_locally_administered_test_only",
        },
    }
    result = scrub_private_target_identifiers(result)
    privacy_failures = private_target_failures(result)
    if privacy_failures:
        result["failures"].extend(privacy_failures)
        result["passed"] = False
        result["gate_eligible"] = False
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": result["failures"],
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
