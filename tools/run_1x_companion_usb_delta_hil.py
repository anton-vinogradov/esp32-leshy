#!/usr/bin/env python3
"""Focused one-flash HIL for the S6.5 read-only native-USB companion."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    query,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.companion_usb_delta_hil.run.v1"
PROTOCOL_SCHEMA = "leshy.companion.response.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
READ_SCOPES = ["session.read", "target.read", "target.compare"]
READ_CAPABILITIES = [
    "session.list",
    "session.detail",
    "target.list",
    "target.detail",
    "target.compare",
]


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def checkpoint(path: Path, record: dict[str, Any], name: str) -> None:
    record["checkpoint"] = name
    write_json(path / "run.json", record)


def companion_request(device: PassiveSerial, payload: bytes,
                      timeout: float = 5.0) -> dict[str, Any]:
    device.write(payload + b"\n")
    device.flush()
    deadline = time.monotonic() + timeout
    ignored: list[str] = []
    while time.monotonic() < deadline:
        line = device.readline()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            ignored.append(repr(line[:160]))
            ignored = ignored[-8:]
            continue
        if (isinstance(value, dict) and
                value.get("schema") == PROTOCOL_SCHEMA):
            return value
        ignored.append(repr(line[:160]))
        ignored = ignored[-8:]
    raise TimeoutError(
        f"timed out waiting for companion response; ignored={ignored}")


def request(kind: str, request_id: str, **fields: Any) -> bytes:
    value: dict[str, Any] = {
        "schema": "leshy.companion.request.v1",
        "kind": kind,
        "request_id": request_id,
    }
    value.update(fields)
    return json.dumps(value, separators=(",", ":")).encode("ascii")


def connect(device: PassiveSerial, request_id: str,
            scopes: list[str]) -> dict[str, Any]:
    return companion_request(device, request(
        "connect", request_id, protocol=1, scopes=scopes))


def collect_pages(device: PassiveSerial, kind: str, request_prefix: str,
                  fixed: dict[str, Any], item_key: str = "items",
                  maximum_pages: int = 64) -> tuple[list[Any], list[dict[str, Any]]]:
    offset = 0
    items: list[Any] = []
    pages: list[dict[str, Any]] = []
    for page_number in range(maximum_pages):
        response = companion_request(device, request(
            kind, f"{request_prefix}-{page_number}", offset=offset, **fixed))
        require(response.get("status") == "ok" and
                response.get("reason") == "none",
                f"{kind} page rejected: {response}")
        page_items = response.get(item_key, [])
        require(isinstance(page_items, list),
                f"{kind} page does not contain a list: {response}")
        items.extend(page_items)
        pages.append(response)
        next_offset = response.get("next_offset")
        if next_offset is None:
            return items, pages
        require(isinstance(next_offset, int) and next_offset > offset,
                f"{kind} pagination did not advance: {response}")
        offset = next_offset
    raise RuntimeError(f"{kind} exceeded bounded pagination")


def collect_note_pages(device: PassiveSerial, target_id: str) -> list[dict[str, Any]]:
    offset = 0
    pages: list[dict[str, Any]] = []
    for page_number in range(4):
        response = companion_request(device, request(
            "target.detail", f"notes-{page_number}", target_id=target_id,
            section="notes", offset=offset))
        require(response.get("status") == "ok" and
                response.get("encoding") == "hex",
                f"notes page rejected: {response}")
        value = response.get("value")
        require(isinstance(value, str) and len(value) <= 160 and
                len(value) % 2 == 0,
                f"notes page is not bounded hex: {response}")
        pages.append(response)
        next_offset = response.get("next_offset")
        if next_offset is None:
            return pages
        require(isinstance(next_offset, int) and next_offset > offset,
                f"notes pagination did not advance: {response}")
        offset = next_offset
    raise RuntimeError("notes exceeded bounded pagination")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="verify and reuse an already flashed exact candidate")
    args = parser.parse_args()

    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.elf, retained_elf)
    shutil.copyfile(args.map, retained_map)
    app_identity = app_elf_sha256(candidate)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
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
            "app_elf_sha256": app_identity,
        },
        "flash_count": 0,
        "exact_flash_reused": args.reuse_exact_flash,
    }
    write_json(args.output / "run.json", record)
    cleanup: dict[str, Any] = {"attempted": False}

    try:
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            record["flash_count"] = 1
            write_json(args.output / "run.json", record)
            time.sleep(1.0)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            checkpoint(args.output, record, "console_sync")
            synchronize_console(device, 30.0)
            checkpoint(args.output, record, "boot_identity")
            metrics_before = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics_before.get("version") == args.expected_version and
                    metrics_before.get("app_elf_sha256") == app_identity,
                    f"wrong candidate booted: {metrics_before}")
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == EXPECTED_CID and
                    recovery.get("observed_fingerprint") == EXPECTED_CID and
                    recovery.get("fingerprint_matched") is True and
                    recovery.get("mounted_read_only") is True and
                    recovery.get("read_only_guaranteed") is True and
                    recovery.get("blocked_write_attempts") == 0 and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"exact product media unavailable: {recovery}")

            checkpoint(args.output, record, "home_denials")
            before_connect = companion_request(device, request(
                "session.list", "before-connect", offset=0))
            require(before_connect.get("reason") == "not_connected",
                    f"pre-connect read did not fail closed: {before_connect}")
            home_connect = connect(device, "home-connect", READ_SCOPES)
            require(home_connect.get("status") == "denied" and
                    home_connect.get("reason") == "scope_unavailable" and
                    home_connect.get("scopes") == [] and
                    home_connect.get("capabilities") == [],
                    f"Home exposed Targets data: {home_connect}")

            checkpoint(args.output, record, "open_targets")
            home = normalize_home(device)
            for _ in range(5):
                home = action(device, "down")
            require(home.get("page") == "home" and
                    home.get("selection") == 5 and
                    home.get("selected_id") == "targets",
                    f"cannot focus Targets: {home}")
            opened = action(device, "right")
            require(opened.get("page") == "targets" and
                    opened.get("runtime_owner") == "targets" and
                    opened.get("lease_mask") == 13,
                    f"cannot open Targets: {opened}")
            targets_state = query(
                device, b"targets.state", "leshy.targets.product.v1", "state")
            require(targets_state.get("status") == "ready" and
                    targets_state.get("compare_available") is True and
                    targets_state.get("write_enabled") is False and
                    1 <= targets_state.get("identity_attempts", 0) <= 8 and
                    targets_state.get("identity_transient_retries") ==
                    targets_state.get("identity_attempts") - 1 and
                    targets_state.get("identity_cleanup_complete") is True and
                    targets_state.get("blocked_write_attempts") == 0,
                    f"Targets snapshot is not exact/read-only: {targets_state}")

            checkpoint(args.output, record, "targets_connect")
            ready = connect(device, "targets-connect", READ_SCOPES)
            require(ready.get("status") == "ready" and
                    ready.get("reason") == "none" and
                    ready.get("transport") == "usb_serial_ndjson" and
                    ready.get("scopes") == READ_SCOPES and
                    ready.get("capabilities") == READ_CAPABILITIES and
                    ready.get("max_frame_bytes") == 512,
                    f"read connection was not granted exactly: {ready}")

            checkpoint(args.output, record, "session_list_detail")
            session_list = companion_request(device, request(
                "session.list", "session-list", offset=0))
            sessions = session_list.get("items")
            require(session_list.get("status") == "ok" and
                    isinstance(sessions, list) and len(sessions) == 2 and
                    session_list.get("next_offset") is None,
                    f"session.list is incomplete: {session_list}")
            session_details = []
            for index, session in enumerate(sessions):
                detail = companion_request(device, request(
                    "session.detail", f"session-detail-{index}",
                    source_id=session["source_id"],
                    generation=session["generation"]))
                require(detail.get("status") == "ok" and
                        detail.get("state") == "stopped" and
                        detail.get("source_id") == session["source_id"] and
                        detail.get("generation") == session["generation"],
                        f"session.detail mismatch: {detail}")
                session_details.append(detail)

            checkpoint(args.output, record, "target_list")
            targets, target_pages = collect_pages(
                device, "target.list", "target-list", {})
            require(1 <= len(targets) <= 16 and
                    len(targets) == targets_state.get("catalog_count"),
                    f"target.list count mismatch: {len(targets)} {targets_state}")
            first_target = targets[0]["target_id"]
            checkpoint(args.output, record, "target_summary")
            summary = companion_request(device, request(
                "target.detail", "target-summary", target_id=first_target,
                section="summary", offset=0))
            require(summary.get("status") == "ok" and
                    summary.get("section") == "summary" and
                    summary.get("target_id") == first_target,
                    f"target summary mismatch: {summary}")
            checkpoint(args.output, record, "target_notes")
            notes_pages = collect_note_pages(device, first_target)
            detail_pages: dict[str, list[dict[str, Any]]] = {}
            for section in ("tags", "identities", "evidence"):
                checkpoint(args.output, record, f"target_{section}")
                _, pages = collect_pages(
                    device, "target.detail", section,
                    {"target_id": first_target, "section": section})
                detail_pages[section] = pages

            baseline, current = sessions
            checkpoint(args.output, record, "target_compare")
            compared, compare_pages = collect_pages(
                device, "target.compare", "target-compare", {
                    "baseline_source_id": baseline["source_id"],
                    "baseline_generation": baseline["generation"],
                    "current_source_id": current["source_id"],
                    "current_generation": current["generation"],
                })
            require(len(compared) == targets_state.get("comparison_count"),
                    f"target.compare count mismatch: {len(compared)}")

            checkpoint(args.output, record, "negative_frames")
            invalid_offset = companion_request(device, request(
                "target.detail", "invalid-offset", target_id=first_target,
                section="summary", offset=1))
            require(invalid_offset.get("reason") == "offset_out_of_range",
                    f"invalid offset did not fail closed: {invalid_offset}")
            unknown = companion_request(
                device,
                b'{"schema":"leshy.companion.request.v1","kind":'
                b'"session.list","request_id":"unknown","offset":0,'
                b'"extra":1}')
            require(unknown.get("reason") == "unknown_field",
                    f"unknown field did not fail closed: {unknown}")
            truncated = companion_request(
                device, b'{"schema":"leshy.companion.request.v1"')
            require(truncated.get("reason") == "malformed_json",
                    f"truncated frame did not fail closed: {truncated}")

            exact_512 = request(
                "session.list", "exact-512", offset=0)
            exact_512 += b" " * (512 - len(exact_512))
            require(len(exact_512) == 512,
                    "test construction did not produce an exact 512-byte frame")
            max_frame = companion_request(device, exact_512)
            require(max_frame.get("status") == "ok",
                    f"exact 512-byte frame was rejected: {max_frame}")
            oversized = companion_request(device, exact_512 + b" ")
            require(oversized.get("reason") == "frame_too_large",
                    f"513-byte frame did not fail closed: {oversized}")

            checkpoint(args.output, record, "scope_denial")
            denied = connect(device, "mutation-denied", ["target.mutate"])
            require(denied.get("status") == "denied" and
                    denied.get("reason") == "scope_denied" and
                    denied.get("capabilities") == [],
                    f"mutation scope was not denied: {denied}")
            ready_again = connect(device, "targets-reconnect", READ_SCOPES)
            require(ready_again.get("status") == "ready",
                    f"read reconnect failed: {ready_again}")

            checkpoint(args.output, record, "targets_teardown")
            exited = action(device, "left")
            require(exited.get("page") == "home" and
                    exited.get("runtime_owner") == "none" and
                    exited.get("lease_mask") == 0,
                    f"Targets did not release cleanly: {exited}")
            after_exit = companion_request(device, request(
                "session.list", "after-exit", offset=0))
            require(after_exit.get("reason") == "not_connected",
                    f"grant survived Targets teardown: {after_exit}")
            released = query(
                device, b"targets.state", "leshy.targets.product.v1", "state")
            require(released.get("status") == "not_loaded" and
                    released.get("workspace_allocated") is False and
                    released.get("write_enabled") is False and
                    released.get("blocked_write_attempts") == 0 and
                    released.get("lease_mask") == 0,
                    f"Targets resources leaked: {released}")
            checkpoint(args.output, record, "final_invariants")
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
            cleanup = best_effort_cleanup(device)
            require(cleanup.get("complete") is True,
                    f"final cleanup unproven: {cleanup}")

        record.update({
            "status": "pass",
            "checkpoint": "complete",
            "exact_cid": EXPECTED_CID,
            "boot_recovery": recovery,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "home_denial": home_connect,
            "connection": ready,
            "sessions": {"list": session_list, "details": session_details},
            "targets": {
                "count": len(targets),
                "list_pages": target_pages,
                "summary": summary,
                "notes_pages": notes_pages,
                "detail_pages": detail_pages,
                "compare_count": len(compared),
                "compare_pages": compare_pages,
                "released": released,
            },
            "negative": {
                "invalid_offset": invalid_offset,
                "unknown_field": unknown,
                "truncated": truncated,
                "exact_512": max_frame,
                "oversized_513": oversized,
                "mutation_denied": denied,
                "after_exit": after_exit,
            },
            "safe_outputs": safe,
            "input": inputs,
            "cleanup": cleanup,
            "radio_tx_commands": 0,
            "storage_write_commands": 0,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({
            "schema": SCHEMA,
            "status": "pass",
            "run": str(args.output / "run.json"),
            "sessions": len(sessions),
            "targets": len(targets),
            "compare_items": len(compared),
            "ports_opened": [args.port],
        }, sort_keys=True))
        return 0
    except Exception as error:
        if not cleanup.get("attempted"):
            try:
                with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                    synchronize_console(device, 10.0)
                    cleanup = best_effort_cleanup(device)
            except Exception as cleanup_error:
                cleanup = {
                    "attempted": True,
                    "complete": False,
                    "errors": [
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    ],
                }
        record.update({
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "cleanup": cleanup,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
