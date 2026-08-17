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
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json


RUN_SCHEMA = "leshy.product_survey_hil.run.v1"


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


def boot_failures(ready: dict[str, Any], recovery: dict[str, Any],
                  expected_version: str, app_identity: str,
                  expected_cid: str) -> list[str]:
    failures = expect(ready, {
        "version": expected_version,
        "app_elf_sha256": app_identity,
        "buzzer_inactive": True,
        "input_detected": True,
    }, "boot")
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
    return failures


def setup_failures(state: dict[str, Any]) -> list[str]:
    return expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_simulated": False,
        "survey_persistent": True,
        "survey_product_selected": True,
        "survey_workflow_state": "setup",
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
    }, "setup")


def running_failures(state: dict[str, Any], expected_cid: str) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_simulated": False,
        "survey_persistent": True,
        "survey_workflow_state": "running",
        "survey_pipeline_status": "drained",
        "survey_product_status": "running",
        "survey_product_backend_open": True,
        "survey_product_store_status": "permitted",
        "survey_product_admission_status": "permitted",
        "survey_product_expected_cid": expected_cid,
        "survey_product_observed_cid": expected_cid,
        "survey_scan_status": "valid",
        "survey_scan_rejected": 0,
        "survey_scan_dropped": 0,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_product_cleanup_complete": False,
    }, "running")
    observations = state.get("survey_observations")
    accepted = state.get("survey_scan_accepted")
    forwarded = state.get("survey_forwarded")
    if not isinstance(observations, int) or observations < 1:
        failures.append("running.survey_observations: expected >= 1")
    if accepted != observations or forwarded != observations:
        failures.append(
            "running.observation_accounting: accepted/forwarded/observations differ"
        )
    free_bytes = state.get("survey_product_cached_free_bytes")
    capacity = state.get("survey_product_capacity_bytes")
    if not isinstance(free_bytes, int) or free_bytes < 64 * 1024 + 1024 * 1024:
        failures.append("running.survey_product_cached_free_bytes: insufficient")
    if not isinstance(capacity, int) or capacity <= 0 or free_bytes > capacity:
        failures.append("running.survey_product_capacity_bytes: invalid geometry")
    return failures


def committed_failures(state: dict[str, Any], before_generation: int) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "result",
        "survey_workflow_status": "committed",
        "survey_pipeline_status": "committed",
        "survey_product_status": "committed",
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
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
            "id": "product-wifi-live",
            "observations": observations,
            "dropped": 0,
        }, "library_export.session"))
    return failures


def action(device: Any, name: str, timeout: float = 15.0) -> dict[str, Any]:
    from capture_1x_ui import read_json

    device.write(f"ui.key {name}\n".encode("ascii"))
    device.flush()
    return read_json(device, "leshy.ui.v1", "state", timeout=timeout)


def query(device: Any, command: bytes, schema: str, kind: str,
          timeout: float = 5.0) -> dict[str, Any]:
    from capture_1x_ui import read_json

    device.write(command + b"\n")
    device.flush()
    return read_json(device, schema, kind, timeout=timeout)


def capture(device: Any, output: Path, name: str) -> dict[str, Any]:
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
    write_json(output / f"{name}.json", record)
    return record


def reset_capture(port: str, output: Path, name: str,
                  seconds: float) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    import serial
    from capture_1x_boot import reset_and_capture

    with serial.Serial(port, 115200, timeout=0.05) as device:
        raw, first_byte_ms, ready_marker_ms = reset_and_capture(device, seconds)
    (output / f"{name}.ndjson").write_bytes(raw)
    ready, recovery = parse_boot_records(raw)
    return ready, recovery, {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "first_byte_ms": first_byte_ms,
        "ready_marker_ms": ready_marker_ms,
    }


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
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0), default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if (len(args.expected_cid) != 32 or args.expected_cid.upper() != args.expected_cid or
            any(value not in "0123456789ABCDEF" for value in args.expected_cid)):
        parser.error("--expected-cid must be exactly 32 uppercase hexadecimal characters")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    if args.flash:
        flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)

    failures: list[str] = []
    run_id = secrets.token_hex(16)
    before_ready, before_recovery, before_timing = reset_capture(
        args.port, args.output, "boot-before", args.boot_seconds
    )
    before_generation = 0
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    committed: dict[str, Any] = {}
    post_ready: dict[str, Any] = {}
    post_recovery: dict[str, Any] = {}
    export: dict[str, Any] = {}
    final: dict[str, Any] = {}

    device = PassiveSerial(args.port, 115200, timeout=0.25)
    with device:
        synchronize_console(device)
        before_recovery = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state"
        )
        failures.extend(boot_failures(
            before_ready, before_recovery, args.expected_version,
            app_identity, args.expected_cid
        ))
        before_generation = int(before_recovery.get("generation", 0))
        if not failures:
            trace.append(action(device, "down"))
            setup = action(device, "select")
            trace.append(setup)
            failures.extend(setup_failures(setup))
            captures["setup"] = capture(device, frames, "setup")
        if not failures:
            running = action(device, "select")
            trace.append(running)
            precommit = running_failures(running, args.expected_cid)
            failures.extend(precommit)
            captures["running"] = capture(device, frames, "running")
            if precommit:
                trace.append(action(device, "back"))
        if not failures:
            committed = action(device, "right")
            trace.append(committed)
            failures.extend(committed_failures(committed, before_generation))
            captures["committed"] = capture(device, frames, "committed")
            trace.append(action(device, "back"))
            final = query(device, b"ui.state", "leshy.ui.v1", "state")
            failures.extend(expect(final, {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
                "survey_product_backend_open": False,
                "survey_product_cleanup_complete": True,
            }, "after_commit_home"))

    if committed and not failures:
        post_ready, post_recovery, post_timing = reset_capture(
            args.port, args.output, "boot-after", args.boot_seconds
        )
        generation = int(committed["survey_generation"])
        observations = int(committed["survey_observations"])
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        with device:
            synchronize_console(device)
            post_recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state"
            )
            failures.extend(boot_failures(
                post_ready, post_recovery, args.expected_version,
                app_identity, args.expected_cid
            ))
            failures.extend(recovered_failures(
                post_recovery, generation, observations, args.expected_cid
            ))
            trace.append(action(device, "down"))
            trace.append(action(device, "down"))
            library = action(device, "select")
            trace.append(library)
            failures.extend(expect(library, {
                "page": "library", "runtime_owner": "library", "lease_mask": 5,
                "library_persistent": True, "library_simulated": False,
                "library_generation": generation,
            }, "library"))
            trace.append(action(device, "select"))
            trace.append(action(device, "right"))
            captures["export"] = capture(device, frames, "export")
            export = query(
                device, b"library.export",
                "leshy.library.export.v1", "artifact"
            )
            failures.extend(export_failures(export, generation, observations))
            trace.append(action(device, "back"))
            trace.append(action(device, "back"))
            trace.append(action(device, "back"))
            final = query(device, b"ui.state", "leshy.ui.v1", "state")
            failures.extend(expect(final, {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
            }, "final"))
    else:
        post_timing = {}

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "version": args.expected_version,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "boot_before": {"ready": before_ready, "recovery": before_recovery,
                        "timing": before_timing},
        "committed": committed,
        "boot_after": {"ready": post_ready, "recovery": post_recovery,
                       "timing": post_timing},
        "library_export": export,
        "final_state": final,
        "captures": captures,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
