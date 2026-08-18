#!/usr/bin/env python3
"""Prove the first S4 user-facing Survey source-plan slice on the real TFT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_ui_typography_hil import (
    action,
    capture,
    normalize_home,
    request,
    retain_record,
    set_language,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(state: dict[str, Any], **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"state mismatch: expected={expected}, actual={actual}")


def perform(device: PassiveSerial, name: str, **expected: Any) -> dict[str, Any]:
    state = action(device, name)
    require(state, **expected)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.firmware = args.firmware.resolve()
    args.factory = args.factory.resolve()
    args.map = args.map.resolve()
    args.output = args.output.resolve()

    for path in (args.firmware, args.factory, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    args.output.mkdir(parents=True)

    runner = Path(__file__).resolve()
    app_identity = app_elf_sha256(args.firmware)
    candidate = {
        "version": args.expected_version,
        "firmware_path": str(args.firmware.relative_to(ROOT)),
        "firmware_sha256": digest(args.firmware),
        "firmware_bytes": args.firmware.stat().st_size,
        "factory_path": str(args.factory.relative_to(ROOT)),
        "factory_sha256": digest(args.factory),
        "factory_bytes": args.factory.stat().st_size,
        "app_elf_sha256": app_identity,
        "map_path": str(args.map.relative_to(ROOT)),
        "map_sha256": digest(args.map),
        "runner_path": str(runner.relative_to(ROOT)),
        "runner_sha256": digest(runner),
    }
    transitions: dict[str, dict[str, Any]] = {}
    screens: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, Any]] = {}

    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    device.open()
    with device:
        synchronize_console(device)
        before = request(device, "metrics", "leshy.boot.v1", "ready")
        require(before, version=args.expected_version,
                app_elf_sha256=app_identity)
        records["metrics_before"] = retain_record(
            args.output, "metrics-before", before)

        normalize_home(device)
        set_language(device, "ru")
        transitions["select_survey"] = perform(
            device, "down", page="home", selection=1, changed=True,
            render_mode="incremental")
        transitions["open_plan"] = perform(
            device, "right", page="survey", changed=True,
            survey_setup_view="plan", survey_setup_selection=0,
            survey_source_selected_mask=1,
            survey_source_selected_count=1,
            survey_source_can_start=True,
            survey_source_wifi_state="available",
            survey_source_ble_state="unavailable")
        screens["plan_ready"] = capture(
            device, args.output, "plan-ready", page="survey", language="ru")

        transitions["open_sources"] = perform(
            device, "right", page="survey", changed=True,
            survey_setup_view="sources", survey_setup_selection=0,
            survey_source_selected_mask=1)
        screens["sources_ready"] = capture(
            device, args.output, "sources-ready", page="survey", language="ru")
        transitions["disable_wifi"] = perform(
            device, "right", page="survey", changed=True,
            runtime_event="source_changed", survey_setup_view="sources",
            survey_source_selected_mask=0,
            survey_source_selected_count=0,
            survey_source_can_start=False)
        screens["sources_none"] = capture(
            device, args.output, "sources-none", page="survey", language="ru")
        transitions["select_ble"] = perform(
            device, "down", page="survey", changed=True,
            render_mode="incremental", survey_setup_selection=1)
        transitions["reject_unavailable_ble"] = perform(
            device, "right", page="survey", changed=False,
            runtime_event="source_unavailable",
            survey_source_selected_mask=0,
            survey_source_ble_state="unavailable")
        transitions["back_to_plan"] = perform(
            device, "left", page="survey", changed=True,
            survey_setup_view="plan", survey_setup_selection=0,
            survey_source_can_start=False)
        transitions["select_start"] = perform(
            device, "down", page="survey", changed=True,
            render_mode="incremental", survey_setup_selection=1)
        transitions["block_empty_start"] = perform(
            device, "right", page="survey", changed=False,
            runtime_event="start_blocked", survey_workflow_state="setup",
            survey_source_selected_mask=0,
            survey_source_can_start=False)
        screens["plan_blocked"] = capture(
            device, args.output, "plan-blocked", page="survey", language="ru")

        perform(device, "up", page="survey", changed=True,
                render_mode="incremental", survey_setup_selection=0)
        perform(device, "right", page="survey", changed=True,
                survey_setup_view="sources", survey_setup_selection=0)
        transitions["restore_wifi"] = perform(
            device, "right", page="survey", changed=True,
            runtime_event="source_changed", survey_source_selected_mask=1,
            survey_source_selected_count=1, survey_source_can_start=True)
        perform(device, "left", page="survey", changed=True,
                survey_setup_view="plan")
        screens["plan_restored"] = capture(
            device, args.output, "plan-restored", page="survey", language="ru")
        transitions["leave_plan"] = perform(
            device, "left", page="home", selection=1, changed=True,
            runtime_owner="none", lease_mask=0)

        input_state = request(
            device, "input.state", "leshy.input.frontend.v1", "state")
        safe = request(device, "hardware.safe-outputs",
                       "leshy.hardware.safe-outputs.v1", "state")
        after = request(device, "metrics", "leshy.boot.v1", "ready")
        records["input"] = retain_record(args.output, "input", input_state)
        records["safe_outputs"] = retain_record(
            args.output, "safe-outputs", safe)
        records["metrics_after"] = retain_record(
            args.output, "metrics-after", after)

    if (input_state.get("status") != "ready" or
            input_state.get("read_errors") != 0 or
            input_state.get("queue_drops") != 0):
        raise RuntimeError(f"input regression: {input_state}")
    if safe.get("buzzer_inactive") is not True or safe.get("buzzer_level") != "low":
        raise RuntimeError(f"safe-output regression: {safe}")
    if (before.get("heap_free") != after.get("heap_free") or
            before.get("heap_min_free") != after.get("heap_min_free")):
        raise RuntimeError(f"heap changed: before={before}, after={after}")

    incremental = [
        int(state["render_us"]) for state in transitions.values()
        if state.get("changed") is True and
        state.get("render_mode") == "incremental"
    ]
    if not incremental or max(incremental) > 40_000:
        raise RuntimeError(f"incremental render regression: {incremental}")

    result = {
        "schema": "leshy.survey_source_plan_hil.v1",
        "status": "pass",
        "passed": True,
        "port": args.port,
        "candidate": candidate,
        "contract": {
            "setup_is_interactive": True,
            "available_sources_user_selectable": True,
            "unavailable_sources_explained": True,
            "empty_plan_start_blocked": True,
            "hidden_fallback": False,
            "radio_started": False,
            "storage_opened": False,
        },
        "screens": screens,
        "transitions": transitions,
        "records": records,
        "maximum_incremental_render_us": max(incremental),
        "heap_invariant": True,
        "final_owner": "none",
        "final_lease_mask": 0,
    }
    run_path = args.output / "run.json"
    write_json(run_path, result)
    print(json.dumps({
        "status": "pass",
        "screens": len(screens),
        "transitions": len(transitions),
        "maximum_incremental_render_us": max(incremental),
        "run": str(run_path),
        "run_sha256": digest(run_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
