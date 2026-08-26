#!/usr/bin/env python3
"""Flash once and verify persisted CC/N1/N2/N3 antenna status LEDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from capture_1x_boot import reset_and_capture_reconnecting
from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    query,
    valid_cid,
)
from run_1x_ui_typography_hil import normalize_home


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "leshy.antenna_status_leds_hil.run.v1"
NRF_SCHEMA = "leshy.nrf24.spectrum.v1"
CC_SCHEMA = "leshy.cc1101.spectrum.v1"
BRIGHTNESS_RAW = (0, 2, 3, 5, 8, 12)


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def enter_settings(device: PassiveSerial,
                   trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = home_item(device, trace, "device")
    state = action(device, "right")
    trace.append(state)
    require(state, "open Device", page="device", device_selection=0)
    state = action(device, "down")
    trace.append(state)
    require(state, "select Settings", page="device", device_selection=1,
            render_mode="incremental")
    state = action(device, "right")
    trace.append(state)
    require(state, "open Settings", page="settings", settings_selection=0,
            render_mode="full")
    for selection in range(1, 4):
        state = action(device, "down")
        trace.append(state)
        require(state, f"settings selection {selection}",
                settings_selection=selection, render_mode="incremental")
    return state


def set_led_brightness(device: PassiveSerial, trace: list[dict[str, Any]],
                       target: int) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(len(BRIGHTNESS_RAW)):
        if state.get("antenna_led_brightness_raw") == target:
            return state
        state = action(device, "right")
        trace.append(state)
        require(state, "cycle antenna brightness", page="settings",
                settings_selection=3, changed=True,
                render_mode="incremental")
    raise RuntimeError(f"could not select antenna LED brightness {target}")


def reset_and_reopen(port: str, output: Path, name: str) -> PassiveSerial:
    raw, ready_ms, disconnects, attempts = reset_and_capture_reconnecting(
        port, 20.0)
    (output / f"{name}.ndjson").write_bytes(raw)
    write_json(output / f"{name}.json", {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "ready_ms": ready_ms,
        "disconnects": disconnects,
        "open_attempts": attempts,
    })
    if ready_ms is None:
        raise RuntimeError(f"{name}: ready marker missing")
    device = PassiveSerial(port, 115200, timeout=0.25)
    synchronize_console(device, 10.0)
    return device


def external_camera(camera_id: str | None, output: Path) -> dict[str, Any]:
    if camera_id is None:
        return {"status": "not_requested"}
    result = subprocess.run([
        sys.executable, str(ROOT / "tools/capture_macos_camera.py"),
        "capture", "--device-id", camera_id, "--output", str(output),
        "--warmup-ms", "1200",
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"camera capture failed: {result.stdout.strip()}")
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    if not lines:
        raise RuntimeError("camera capture emitted no receipt")
    receipt = json.loads(lines[-1])
    receipt["png_sha256"] = sha256_file(output)
    return receipt


def home_item(device: PassiveSerial, trace: list[dict[str, Any]],
              selected_id: str) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(8):
        if state.get("selected_id") == selected_id:
            break
        state = action(device, "down")
        trace.append(state)
    require(state, f"Home {selected_id}", page="home",
            selected_id=selected_id, runtime_owner="none", lease_mask=0)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--camera-id")
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    photos = args.output / "camera"
    frames.mkdir()
    photos.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    camera: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
        },
    }
    write_json(args.output / "run.json", record)

    initial_raw = 0
    persisted: dict[str, Any] = {}
    final: dict[str, Any] = {}
    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 30.0)
            boot, boot_samples = stabilized_boot_metrics(device)
            recovery_before = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            failures = boot_failures(
                boot, recovery_before, args.expected_version,
                app_identity, args.expected_cid)
            if failures:
                raise RuntimeError("; ".join(failures))
            cleanup_before = best_effort_cleanup(device)
            if not cleanup_before.get("complete"):
                raise RuntimeError("initial cleanup did not reach Home/lease 0")

            initial = query(device, b"ui.state", "leshy.ui.v1", "state")
            initial_raw = int(initial.get("antenna_led_brightness_raw", -1))
            if initial_raw not in BRIGHTNESS_RAW:
                raise RuntimeError(f"invalid initial LED brightness: {initial_raw}")
            state = enter_settings(device, trace)
            require(state, "antenna LED setting", settings_selection=3,
                    antenna_led_brightness_raw=initial_raw)
            screens["settings_initial"] = capture(
                device, frames, "settings-initial")

            observed = [initial_raw]
            for _ in range(len(BRIGHTNESS_RAW)):
                state = action(device, "right")
                trace.append(state)
                require(state, "brightness ladder", changed=True,
                        page="settings", settings_selection=3,
                        render_mode="incremental")
                observed.append(int(state["antenna_led_brightness_raw"]))
            expected = [initial_raw]
            cursor = BRIGHTNESS_RAW.index(initial_raw)
            for offset in range(1, len(BRIGHTNESS_RAW) + 1):
                expected.append(BRIGHTNESS_RAW[
                    (cursor + offset) % len(BRIGHTNESS_RAW)])
            if observed != expected:
                raise RuntimeError(
                    f"brightness ladder differs: {observed} != {expected}")
            state = set_led_brightness(device, trace, 12)
            screens["settings_12"] = capture(device, frames, "settings-12")

        device = reset_and_reopen(args.port, args.output, "persistence-reset")
        with device:
            persisted = query(device, b"ui.state", "leshy.ui.v1", "state")
            require(persisted, "persisted LED brightness",
                    antenna_led_brightness_raw=12)
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("post-reset cleanup failed")

            home_item(device, trace, "spectrum24")
            trace.append(action(device, "right"))
            started = action(device, "right")
            trace.append(started)
            require(started, "nRF24 spectrum start",
                    runtime_event="nrf24_spectrum_running",
                    runtime_owner="spectrum24", lease_mask=9)
            time.sleep(0.7)
            reports["nrf24"] = query(
                device, b"hardware.nrf24.spectrum", NRF_SCHEMA, "state")
            nrf_slots = int(reports["nrf24"].get("active_slot_mask", 0))
            # Older report versions expose the same fact only as detected
            # modules. On stock board-01 those modules occupy slots from zero.
            if nrf_slots == 0:
                modules = int(reports["nrf24"].get("modules", 0))
                nrf_slots = (1 << modules) - 1 if 0 < modules <= 3 else 0
            if nrf_slots == 0:
                raise RuntimeError("nRF24 receiver started without active slots")
            nrf_state = query(device, b"ui.state", "leshy.ui.v1", "state")
            require(nrf_state, "nRF24 LED state",
                    antenna_led_brightness_raw=12,
                    antenna_led_receive_mask=(nrf_slots & 0x07) << 1,
                    antenna_led_fault_mask=0)
            camera["nrf24"] = external_camera(
                args.camera_id, photos / "nrf24-green.png")
            trace.append(action(device, "left"))
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("nRF24 cleanup failed")

            home_item(device, trace, "subghz")
            trace.append(action(device, "right"))
            trace.append(action(device, "right"))
            started = action(device, "right")
            trace.append(started)
            require(started, "CC1101 spectrum start",
                    runtime_event="cc1101_spectrum_running",
                    runtime_owner="subghz", lease_mask=9)
            time.sleep(0.7)
            reports["cc1101"] = query(
                device, b"hardware.cc1101.spectrum", CC_SCHEMA, "state")
            cc_state = query(device, b"ui.state", "leshy.ui.v1", "state")
            require(cc_state, "CC1101 LED state",
                    antenna_led_brightness_raw=12,
                    antenna_led_receive_mask=1,
                    antenna_led_fault_mask=0)
            camera["cc1101"] = external_camera(
                args.camera_id, photos / "cc1101-green.png")
            trace.append(action(device, "left"))
            cleanup_after = best_effort_cleanup(device)
            if not cleanup_after.get("complete"):
                raise RuntimeError("CC1101 cleanup failed")

            enter_settings(device, trace)
            set_led_brightness(device, trace, initial_raw)

        device = reset_and_reopen(args.port, args.output, "restore-reset")
        with device:
            final = query(device, b"ui.state", "leshy.ui.v1", "state")
            require(final, "restored LED brightness", page="home",
                    antenna_led_brightness_raw=initial_raw,
                    antenna_led_receive_mask=0,
                    antenna_led_fault_mask=0,
                    runtime_owner="none", lease_mask=0)
            safe = query(device, b"hardware.safe-outputs",
                         "leshy.hardware.safe-outputs.v1", "state")
            require(safe, "safe outputs", buzzer_inactive=True,
                    nrf_ce_inactive=True, software_quiesce_complete=True)
            inputs = query(device, b"input.state",
                           "leshy.input.frontend.v1", "state")
            require(inputs, "input frontend", status="ready", read_errors=0,
                    queue_drops=0)
            recovery_after = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            if (recovery_after.get("generation") !=
                    recovery_before.get("generation") or
                    recovery_after.get("observations") !=
                    recovery_before.get("observations") or
                    recovery_after.get("physical_write_calls") != 0):
                raise RuntimeError("LED delta changed persistent product data")
            screens["home_restored"] = capture(
                device, frames, "home-restored")

        record.update({
            "status": "pass",
            "initial_brightness_raw": initial_raw,
            "persisted_brightness_raw": persisted["antenna_led_brightness_raw"],
            "final_brightness_raw": final["antenna_led_brightness_raw"],
            "brightness_ladder": list(BRIGHTNESS_RAW),
            "reports": reports,
            "camera": camera,
            "screens": screens,
            "trace": trace,
            "safe_outputs": safe,
            "input": inputs,
            "boot_samples": boot_samples,
            "flash_count": 1 if args.flash else 0,
            "hardware_reset_count": 2,
            "radio_tx_commands": 0,
            "cardputer_ports_opened": [],
            "storage_before": recovery_before,
            "storage_after": recovery_after,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({
            "schema": SCHEMA,
            "status": "pass",
            "run": str(args.output / "run.json"),
            "camera": args.camera_id is not None,
        }, sort_keys=True))
        return 0
    except Exception as error:
        record.update({
            "status": "failed", "error": str(error), "trace": trace,
            "screens": screens, "camera": camera, "reports": reports,
            "initial_brightness_raw": initial_raw,
            "cardputer_ports_opened": [],
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
