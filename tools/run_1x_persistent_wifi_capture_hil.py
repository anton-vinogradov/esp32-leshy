#!/usr/bin/env python3
"""Prove explicit raw Wi-Fi Capture persistence and cold Library PCAP reopen."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

import serial

from capture_1x_ui import PassiveSerial, read_exact, read_json, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import (
    flash_candidate,
    reset_and_capture,
    sha256_file,
    write_json,
)
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
from run_1x_wifi_frame_capture_hil import parse_pcap


RUN_SCHEMA = "leshy.persistent_wifi_capture_hil.run.v1"
STATE_SCHEMA = "leshy.capture.wifi_frame.v1"
LIVE_PCAP_SCHEMA = "leshy.capture.pcap.v1"
LIBRARY_PCAP_SCHEMA = "leshy.library.pcap.v1"


def wait_state(device: Any, predicate: Any, timeout: float,
               description: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"capture.state", STATE_SCHEMA, "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def read_pcap(device: Any, command: bytes, schema: str,
              timeout: float = 20.0
              ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    device.reset_input_buffer()
    device.write(command + b"\n")
    device.flush()
    begin = read_json(device, schema, "pcap_begin", timeout=timeout)
    size = int(begin.get("bytes", 0))
    maximum = 16 * (16 + 15 + 256) + 24
    if size < 24 or size > maximum:
        raise ValueError(f"PCAP byte bound invalid: {size}")
    payload = read_exact(device, size, timeout=timeout)
    end = read_json(device, schema, "pcap_end", timeout=timeout)
    return begin, payload, end


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
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
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    setup: dict[str, Any] = {}
    running: dict[str, Any] = {}
    complete: dict[str, Any] = {}
    confirm: dict[str, Any] = {}
    saved: dict[str, Any] = {}
    scrubbed: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    live_begin: dict[str, Any] = {}
    live_end: dict[str, Any] = {}
    library_begin: dict[str, Any] = {}
    library_end: dict[str, Any] = {}
    pcap_summary: dict[str, Any] = {}
    live_payload = b""
    library_payload = b""

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot_before = query(device, b"metrics", "leshy.boot.v1", "ready")
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                failures.extend(boot_failures(
                    boot_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid,
                ))
                if failures:
                    raise RuntimeError("boot contract failed")
                previous_generation = int(recovery_before.get("generation", 0))

                for _ in range(3):
                    trace.append(action(device, "down"))
                trace.append(action(device, "right"))
                setup = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(setup, {
                    "state": "idle", "storage_written": False,
                    "persist_state": "volatile", "persist_generation": 0,
                    "lease_mask": 3,
                }, "setup"))
                captures["setup"] = capture(device, frames, "setup")

                trace.append(action(device, "right"))
                running = wait_state(
                    device,
                    lambda value: value.get("state") == "running" and
                    int(value.get("frames_accepted", 0)) >= 1,
                    5.0, "passive capture received no frame",
                )
                time.sleep(0.7)
                captures["running"] = capture(device, frames, "running")
                trace.append(action(device, "right"))
                complete = wait_state(
                    device, lambda value: value.get("state") == "complete",
                    5.0, "Stop did not complete capture",
                )
                accepted = int(complete.get("frames_accepted", 0))
                payload_bytes = int(complete.get("payload_bytes", 0))
                failures.extend(expect(complete, {
                    "state": "complete", "storage_written": False,
                    "persist_state": "volatile", "persist_generation": 0,
                    "cleanup_complete": True, "lease_mask": 1,
                }, "complete"))
                if not 1 <= accepted <= 16 or not accepted <= payload_bytes <= accepted * 256:
                    failures.append("complete: bounded payload accounting invalid")
                captures["result"] = capture(device, frames, "result")

                live_begin, live_payload, live_end = read_pcap(
                    device, b"capture.export.pcap", LIVE_PCAP_SCHEMA,
                )
                pcap_summary, parse_failures = parse_pcap(live_payload)
                failures.extend(parse_failures)
                failures.extend(expect(live_end, {
                    "status": "valid", "bytes": len(live_payload),
                    "frames": accepted, "storage_written": False,
                }, "live_pcap_end"))

                trace.append(action(device, "right"))
                confirm = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(confirm, {
                    "persist_state": "confirm",
                    "persist_status": "awaiting_confirmation",
                    "storage_written": False, "lease_mask": 1,
                }, "confirm"))
                captures["confirm"] = capture(device, frames, "confirm")
                trace.append(action(device, "right"))
                saved = wait_state(
                    device,
                    lambda value: value.get("persist_state") in ("saved", "failed"),
                    35.0, "persistent save did not reach a terminal state",
                )
                generation = int(saved.get("persist_generation", 0))
                failures.extend(expect(saved, {
                    "persist_state": "saved", "persist_status": "saved",
                    "storage_written": True, "lease_mask": 1,
                }, "saved"))
                if generation != previous_generation + 1:
                    failures.append(
                        f"saved generation {generation} != {previous_generation + 1}"
                    )
                captures["saved"] = capture(device, frames, "saved")

                trace.append(action(device, "left"))
                scrubbed = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(scrubbed, {
                    "state": "idle", "frames_accepted": 0,
                    "payload_bytes": 0, "storage_written": False,
                    "lease_mask": 0,
                }, "scrubbed"))
                captures["home"] = capture(device, frames, "home")
            except Exception as error:
                failures.append(f"persist_phase: {type(error).__name__}: {error}")
            finally:
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    failures.append("cleanup_before: terminal zero lease unproven")

        if not failures:
            with serial.Serial(args.port, 115200, timeout=0.05) as reset_device:
                reset_and_capture(reset_device, 8.0)
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                try:
                    synchronize_console(device, 30.0)
                    boot_after = query(device, b"metrics", "leshy.boot.v1", "ready")
                    recovery_after = query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state",
                    )
                    failures.extend(boot_failures(
                        boot_after, recovery_after, args.expected_version,
                        app_identity, args.expected_cid,
                    ))
                    generation = int(saved.get("persist_generation", 0))
                    failures.extend(expect(recovery_after, {
                        "status": "admitted", "generation": generation,
                        "observations": 0, "mounted_read_only": True,
                        "physical_write_calls": 0, "cleanup_complete": True,
                        "owned_after": 0,
                    }, "cold_recovery"))

                    trace.append(action(device, "down"))
                    trace.append(action(device, "down"))
                    trace.append(action(device, "right"))
                    captures["library_list"] = capture(device, frames, "library-list")
                    trace.append(action(device, "right"))
                    captures["library_detail"] = capture(device, frames, "library-detail")
                    trace.append(action(device, "right"))
                    captures["library_export"] = capture(device, frames, "library-export")
                    metadata = query(
                        device, b"library.capture",
                        "leshy.capture.metadata.v1", "capture",
                    )
                    payload = metadata.get("payload", {})
                    exports = metadata.get("exports", {})
                    failures.extend(expect(metadata, {
                        "status": "valid", "generation": generation,
                        "persistent": True, "immutable": True,
                        "observations": 0, "radio_touched": False,
                    }, "metadata"))
                    failures.extend(expect(payload, {
                        "status": "captured_raw_80211", "bytes": payload_bytes,
                        "records": accepted, "snap_length": 256,
                        "format": "ieee80211",
                    }, "metadata.payload"))
                    if exports.get("pcap") != "available_radiotap":
                        failures.append("metadata.exports.pcap is not available")

                    library_begin, library_payload, library_end = read_pcap(
                        device, b"library.export.pcap", LIBRARY_PCAP_SCHEMA,
                    )
                    failures.extend(expect(library_begin, {
                        "status": "valid", "generation": generation,
                        "bytes": len(live_payload), "frames": accepted,
                        "linktype": 127, "persistent": True,
                        "radio_touched": False,
                    }, "library_pcap_begin"))
                    failures.extend(expect(library_end, {
                        "status": "valid", "bytes": len(live_payload),
                        "frames": accepted, "persistent": True,
                        "radio_touched": False,
                    }, "library_pcap_end"))
                    if library_payload != live_payload:
                        failures.append("cold Library PCAP differs from live Capture PCAP")

                    trace.append(action(device, "left"))
                    trace.append(action(device, "left"))
                    trace.append(action(device, "left"))
                    final = query(device, b"ui.state", "leshy.ui.v1", "state")
                    failures.extend(expect(final, {
                        "page": "home", "runtime_owner": "none", "lease_mask": 0,
                    }, "final"))
                except Exception as error:
                    failures.append(f"cold_phase: {type(error).__name__}: {error}")
                finally:
                    cleanup_after = best_effort_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("cleanup_after: terminal zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "boot_before": {"ready": boot_before, "recovery": recovery_before},
        "capture": {
            "setup": setup, "running": running, "complete": complete,
            "confirm": confirm, "saved": saved, "scrubbed": scrubbed,
        },
        "live_pcap": {"begin": live_begin, "end": live_end,
                      "summary": pcap_summary},
        "boot_after": {"ready": boot_after, "recovery": recovery_after},
        "library": {"metadata": metadata, "pcap_begin": library_begin,
                    "pcap_end": library_end},
        "pcap_equivalence": {
            "byte_exact": bool(live_payload) and library_payload == live_payload,
            "bytes": len(live_payload),
            "sha256": hashlib.sha256(live_payload).hexdigest()
                if live_payload else "",
        },
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "final": final,
        "captures": captures,
        "trace": trace,
        "privacy": {
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "persistent_payload_location": "enrolled_product_sd_only",
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
