#!/usr/bin/env python3
"""Flash once and prove the bounded persistent S5 Settings workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from capture_1x_boot import reset_and_capture_reconnecting
from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import action, artifact_manifest, capture, query
from run_1x_ui_typography_hil import normalize_home


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "leshy.interface_settings_hil.run.v1"
BRIGHTNESS = (100, 69, 44, 25, 9)


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def enter_settings(device: PassiveSerial, trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(6):
        state = action(device, "down")
        trace.append(state)
    require(state, "select Device", page="home", selection=6,
            selected_id="device")
    state = action(device, "right")
    trace.append(state)
    require(state, "open Device", page="device", device_selection=0,
            render_mode="full")
    state = action(device, "down")
    trace.append(state)
    require(state, "select Settings", page="device", device_selection=1,
            render_mode="incremental")
    state = action(device, "right")
    trace.append(state)
    require(state, "open Settings", page="settings", settings_selection=0,
            render_mode="full")
    return state


def reset_and_reopen(port: str, output: Path, name: str) -> PassiveSerial:
    raw, ready_ms, disconnects, attempts = reset_and_capture_reconnecting(port, 20.0)
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


def restore_preferences(device: PassiveSerial, trace: list[dict[str, Any]],
                        initial: dict[str, Any]) -> None:
    state = enter_settings(device, trace)
    if state.get("language") != initial["language"]:
        state = action(device, "right")
        trace.append(state)
    state = action(device, "down")
    trace.append(state)
    for _ in range(len(BRIGHTNESS)):
        if state.get("brightness_percent") == initial["brightness_percent"]:
            break
        state = action(device, "right")
        trace.append(state)
    if state.get("brightness_percent") != initial["brightness_percent"]:
        raise RuntimeError("could not restore initial brightness")
    state = action(device, "down")
    trace.append(state)
    if state.get("theme") != initial["theme"]:
        state = action(device, "right")
        trace.append(state)
    if state.get("theme") != initial["theme"]:
        raise RuntimeError("could not restore initial theme")
    trace.append(action(device, "left"))
    trace.append(action(device, "left"))


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
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
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

    try:
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 30.0)
            metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics, "candidate identity", version=args.expected_version,
                    app_elf_sha256=app_identity)
            initial = query(device, b"ui.state", "leshy.ui.v1", "state")
            initial = {
                key: initial[key] for key in (
                    "language", "brightness_percent", "brightness_duty", "theme"
                )
            }
            state = enter_settings(device, trace)
            screens["settings_initial"] = capture(
                device, frames, "settings-initial")

            changed_language = action(device, "right")
            trace.append(changed_language)
            require(changed_language, "language toggle", page="settings",
                    changed=True, render_mode="full")

            state = action(device, "down")
            trace.append(state)
            require(state, "brightness selection", settings_selection=1,
                    render_mode="incremental")
            before_brightness = int(state["brightness_percent"])
            brightness = action(device, "right")
            trace.append(brightness)
            expected_brightness = BRIGHTNESS[(BRIGHTNESS.index(before_brightness) + 1)
                                             % len(BRIGHTNESS)]
            require(brightness, "brightness toggle", changed=True,
                    brightness_percent=expected_brightness,
                    render_mode="incremental")

            state = action(device, "down")
            trace.append(state)
            require(state, "theme selection", settings_selection=2,
                    render_mode="incremental")
            before_theme = state["theme"]
            theme = action(device, "right")
            trace.append(theme)
            require(theme, "theme toggle", changed=True, render_mode="full")
            if theme.get("theme") == before_theme:
                raise RuntimeError("theme did not toggle")
            screens["settings_changed"] = capture(
                device, frames, "settings-changed")

            state = action(device, "down")
            trace.append(state)
            require(state, "sound selection", settings_selection=3,
                    sound_available=False, render_mode="incremental")
            sound = action(device, "right")
            trace.append(sound)
            require(sound, "sound fail-closed", changed=False,
                    sound_available=False)

        device = reset_and_reopen(args.port, args.output, "persistence-reset")
        with device:
            persisted = query(device, b"ui.state", "leshy.ui.v1", "state")
            require(persisted, "persisted language",
                    language=changed_language["language"])
            require(persisted, "persisted brightness",
                    brightness_percent=brightness["brightness_percent"],
                    brightness_duty=brightness["brightness_duty"])
            require(persisted, "persisted theme", theme=theme["theme"])
            restore_preferences(device, trace, initial)

        device = reset_and_reopen(args.port, args.output, "restore-reset")
        with device:
            final = query(device, b"ui.state", "leshy.ui.v1", "state")
            for key, value in initial.items():
                if final.get(key) != value:
                    raise RuntimeError(
                        f"restored {key}: expected={value}, actual={final.get(key)}")
            require(final, "final Home", page="home", lease_mask=0,
                    runtime_owner="none", sound_available=False)
            safe = query(device, b"hardware.safe-outputs",
                         "leshy.hardware.safe-outputs.v1", "state")
            require(safe, "safe outputs", buzzer_inactive=True,
                    nrf_ce_inactive=True, software_quiesce_complete=True)
            inputs = query(device, b"input.state",
                           "leshy.input.frontend.v1", "state")
            require(inputs, "input frontend", status="ready", read_errors=0,
                    queue_drops=0)
            screens["home_restored"] = capture(
                device, frames, "home-restored")

        record.update({
            "status": "pass",
            "initial": initial,
            "persisted": {key: persisted[key] for key in initial},
            "final": {key: final[key] for key in (
                *initial.keys(), "page", "runtime_owner", "lease_mask",
                "sound_available")},
            "safe_outputs": safe,
            "input": inputs,
            "trace": trace,
            "screens": screens,
            "flash_count": 1,
            "hardware_reset_count": 2,
            "radio_tx_commands": 0,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({
            "schema": SCHEMA, "status": "pass",
            "run": str(args.output / "run.json"),
            "flash_count": 1, "screens": len(screens),
        }, sort_keys=True))
        return 0
    except Exception as error:
        record.update({"status": "failed", "error": str(error), "trace": trace,
                       "screens": screens})
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
