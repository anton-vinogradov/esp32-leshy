#!/usr/bin/env python3
"""Exercise bounded RX-only Wi-Fi frame Capture and validate streamed PCAP."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import struct
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_exact, read_json, synchronize_console
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


RUN_SCHEMA = "leshy.wifi_frame_capture_hil.run.v1"
STATE_SCHEMA = "leshy.capture.wifi_frame.v1"
PCAP_SCHEMA = "leshy.capture.pcap.v1"


def select_home_app(device: Any, app_id: str,
                    trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(10):
        if state.get("selection") == 0:
            break
        state = action(device, "up")
        trace.append(state)
    for _ in range(10):
        if state.get("selected_id") == app_id:
            return state
        state = action(device, "down")
        trace.append(state)
    raise RuntimeError(f"Home app {app_id!r} is not reachable: {state!r}")


def wait_capture(device: Any, predicate: Any, timeout: float,
                 description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"capture.state", STATE_SCHEMA, "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def read_pcap(device: Any, timeout: float = 20.0
              ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    device.reset_input_buffer()
    device.write(b"capture.export.pcap\n")
    device.flush()
    begin = read_json(device, PCAP_SCHEMA, "pcap_begin", timeout=timeout)
    size = int(begin.get("bytes", 0))
    if size < 24 or size > 16 * (16 + 15 + 256) + 24:
        raise ValueError(f"PCAP byte bound invalid: {size}")
    payload = read_exact(device, size, timeout=timeout)
    end = read_json(device, PCAP_SCHEMA, "pcap_end", timeout=timeout)
    return begin, payload, end


def parse_pcap(payload: bytes) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    summary: dict[str, Any] = {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "payload_retained": False,
        "records": 0,
        "captured_frame_bytes": 0,
        "original_frame_bytes": 0,
        "frequencies_mhz": [],
        "rssi_min_dbm": None,
        "rssi_max_dbm": None,
        "frame_types": {"management": 0, "control": 0, "data": 0,
                        "reserved": 0},
    }
    if len(payload) < 24:
        return summary, ["pcap: global header truncated"]
    magic, major, minor, zone, sigfigs, snaplen, linktype = struct.unpack_from(
        "<IHHIIII", payload, 0
    )
    summary.update({
        "magic": f"{magic:08x}", "version": f"{major}.{minor}",
        "zone": zone, "sigfigs": sigfigs, "snaplen": snaplen,
        "linktype": linktype,
    })
    if (magic, major, minor, zone, sigfigs, snaplen, linktype) != (
            0xA1B2C3D4, 2, 4, 0, 0, 271, 127):
        failures.append("pcap: global header mismatch")

    position = 24
    previous_us = 0
    frequencies: set[int] = set()
    rssis: list[int] = []
    while position < len(payload):
        if position + 16 > len(payload):
            failures.append("pcap: record header truncated")
            break
        seconds, microseconds, captured, original = struct.unpack_from(
            "<IIII", payload, position
        )
        position += 16
        if microseconds >= 1_000_000 or captured < 15 or original < captured:
            failures.append("pcap: record lengths/timestamp invalid")
            break
        if position + captured > len(payload):
            failures.append("pcap: record payload truncated")
            break
        record = payload[position:position + captured]
        position += captured
        timestamp_us = seconds * 1_000_000 + microseconds
        if timestamp_us < previous_us:
            failures.append("pcap: timestamps are not monotonic")
        previous_us = timestamp_us
        version, pad, radiotap_length, present = struct.unpack_from(
            "<BBHI", record, 0
        )
        if (version, pad, radiotap_length, present) != (0, 0, 15, 0x2A):
            failures.append("pcap: radiotap header mismatch")
            break
        flags = record[8]
        frequency, channel_flags = struct.unpack_from("<HH", record, 10)
        rssi = struct.unpack_from("<b", record, 14)[0]
        if flags & 0x10 == 0 or channel_flags & 0x0080 == 0:
            failures.append("pcap: FCS/2GHz radiotap flags missing")
        if not 2412 <= frequency <= 2472:
            failures.append(f"pcap: unexpected frequency {frequency}")
        frequencies.add(frequency)
        rssis.append(rssi)
        frame_payload = record[15:]
        if not frame_payload:
            failures.append("pcap: empty 802.11 frame")
            break
        frame_type = (frame_payload[0] >> 2) & 0x03
        names = ("management", "control", "data", "reserved")
        summary["frame_types"][names[frame_type]] += 1
        summary["records"] += 1
        summary["captured_frame_bytes"] += captured - 15
        summary["original_frame_bytes"] += original - 15

    if position != len(payload):
        failures.append("pcap: trailing or unparsed bytes")
    summary["frequencies_mhz"] = sorted(frequencies)
    if rssis:
        summary["rssi_min_dbm"] = min(rssis)
        summary["rssi_max_dbm"] = max(rssis)
    return summary, failures


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
    parser.add_argument(
        "--visual-only", action="store_true",
        help="verify the TFT flow without exporting captured 802.11 payload",
    )
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")
    if args.flash and args.reuse_exact_flash:
        parser.error("--flash and --reuse-exact-flash are mutually exclusive")
    if not args.flash and not args.reuse_exact_flash:
        parser.error("use --flash or explicitly acknowledge --reuse-exact-flash")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    ready: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    setup: dict[str, Any] = {}
    running: dict[str, Any] = {}
    complete: dict[str, Any] = {}
    final: dict[str, Any] = {}
    scrubbed: dict[str, Any] = {}
    pcap_begin: dict[str, Any] = {}
    pcap_end: dict[str, Any] = {}
    pcap_summary: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                ready = query(device, b"metrics", "leshy.boot.v1", "ready")
                recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                failures.extend(boot_failures(
                    ready, recovery, args.expected_version, app_identity,
                    args.expected_cid,
                ))
                if failures:
                    raise RuntimeError("boot contract failed")

                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial cleanup did not reach Home/lease 0")
                home_capture = select_home_app(device, "capture", trace)
                failures.extend(expect(home_capture, {
                    "page": "home", "selection": 4,
                    "selected_id": "capture", "selected_enabled": True,
                    "runtime_owner": "none", "lease_mask": 0,
                }, "home_capture"))
                source_menu = action(device, "right")
                trace.append(source_menu)
                failures.extend(expect(source_menu, {
                    "page": "capture", "selected_id": "capture",
                    "runtime_event": "started", "runtime_owner": "capture",
                    "lease_mask": 11,
                }, "source_menu"))
                captures["source_menu"] = capture(
                    device, frames, "source-menu")
                trace.append(action(device, "right"))
                setup = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(setup, {
                    "state": "idle", "passive_only": True, "rx_only": True,
                    "volatile_ram": True, "storage_written": False,
                    "pcap_available": False, "pcap_bytes": 0,
                    "lease_mask": 11,
                }, "setup"))
                captures["setup"] = capture(device, frames, "setup")

                trace.append(action(device, "right"))
                running = wait_capture(
                    device,
                    lambda value: value.get("state") == "running" and
                    value.get("frames_accepted", 0) >= 1,
                    5.0, "passive frame capture did not receive a frame",
                )
                failures.extend(expect(running, {
                    "state": "running", "passive_only": True,
                    "rx_only": True, "application_connect_calls": 0,
                    "application_raw_tx_calls": 0,
                    "physical_no_tx_verified": False,
                    "storage_written": False, "volatile_ram": True,
                    "channel_plan": 0, "duration_ms": 10000,
                    "channel_dwell_ms": 120, "snap_length": 256,
                    "maximum_frames": 16, "driver_error": 0,
                    "pcap_available": False, "pcap_bytes": 0,
                    "lease_mask": 11,
                }, "running"))
                # Let the bounded 500 ms UI refresh publish live counters before
                # taking the real-TFT frame; the capture itself keeps receiving.
                time.sleep(0.7)
                running = wait_capture(
                    device,
                    lambda value: value.get("state") == "running" and
                    value.get("frames_accepted", 0) >= 1,
                    2.0, "running UI refresh lost capture state",
                )
                captures["running"] = capture(device, frames, "running")

                trace.append(action(device, "right"))
                complete = wait_capture(
                    device, lambda value: value.get("state") == "complete",
                    5.0, "manual Stop did not complete capture",
                )
                failures.extend(expect(complete, {
                    "state": "complete", "driver_error": 0,
                    "pcap_available": True, "cleanup_complete": True,
                    "storage_written": False, "lease_mask": 9,
                }, "complete"))
                reported = complete.get("frames_reported")
                accepted = complete.get("frames_accepted")
                dropped_capacity = complete.get("frames_dropped_capacity")
                dropped_invalid = complete.get("frames_dropped_invalid")
                payload_bytes = complete.get("payload_bytes")
                if (not all(isinstance(value, int) for value in (
                        reported, accepted, dropped_capacity, dropped_invalid,
                        payload_bytes)) or not 1 <= accepted <= 16 or
                        reported != accepted + dropped_capacity + dropped_invalid or
                        not accepted <= payload_bytes <= accepted * 256):
                    failures.append("complete: bounded frame accounting invalid")
                if not isinstance(complete.get("ended_us"), int) or complete[
                        "ended_us"] < complete.get("started_us", 1):
                    failures.append("complete: monotonic bounds invalid")
                captures["result"] = capture(device, frames, "result")

                if args.visual_only:
                    pcap_summary = {
                        "exported_to_host": False,
                        "reason": "visual_only_product_content_review",
                        "advertised_bytes": complete.get("pcap_bytes"),
                        "advertised_frames": accepted,
                    }
                else:
                    pcap_begin, pcap_payload, pcap_end = read_pcap(device)
                    pcap_summary, pcap_failures = parse_pcap(pcap_payload)
                    failures.extend(pcap_failures)
                    failures.extend(expect(pcap_begin, {
                        "bytes": len(pcap_payload), "frames": accepted,
                        "linktype": 127, "timebase": "monotonic_us",
                        "streaming": True, "storage_written": False,
                    }, "pcap_begin"))
                    failures.extend(expect(pcap_end, {
                        "status": "valid", "bytes": len(pcap_payload),
                        "frames": accepted, "storage_written": False,
                    }, "pcap_end"))
                    if pcap_summary.get("records") != accepted:
                        failures.append(
                            "pcap: record count differs from Capture")
                    if pcap_summary.get("captured_frame_bytes") != payload_bytes:
                        failures.append(
                            "pcap: captured byte count differs from Capture")
                    if complete.get("pcap_bytes") != len(pcap_payload):
                        failures.append("pcap: advertised byte count mismatch")

                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                failures.extend(expect(final, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final"))
                scrubbed = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(scrubbed, {
                    "state": "idle", "frames_reported": 0,
                    "frames_accepted": 0, "frames_dropped_capacity": 0,
                    "frames_dropped_invalid": 0, "payload_bytes": 0,
                    "pcap_available": False, "pcap_bytes": 0,
                    "lease_mask": 0,
                }, "scrubbed"))
                captures["home"] = capture(device, frames, "home")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup = best_effort_cleanup(device)
                if not cleanup.get("complete"):
                    failures.append("cleanup: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "exact_flash_reused": args.reuse_exact_flash,
        },
        "expected_cid": args.expected_cid,
        "boot": {"ready": ready, "recovery": recovery},
        "setup": setup,
        "running": running,
        "complete": complete,
        "pcap": {"begin": pcap_begin, "end": pcap_end,
                 "summary": pcap_summary},
        "scrubbed": scrubbed,
        "final": final,
        "cleanup": cleanup,
        "captures": captures,
        "trace": trace,
        "privacy": {
            "visual_only": args.visual_only,
            "pcap_exported_to_host": not args.visual_only,
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "retained_pcap_summary": "hash_counts_tuning_rssi_range_only",
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "passed": result["passed"],
        "failures": failures, "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
