#!/usr/bin/env python3
"""Retain a privacy-minimal snapshot of the sole post-idle physical action."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from run_1x_product_survey_hil import query


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--factory", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator-confirmed-fixed", action="store_true")
    args = parser.parse_args()
    artifacts = (args.firmware, args.factory, args.elf)
    if any(not path.is_file() for path in artifacts):
        parser.error("candidate artifact missing")

    with PassiveSerial(args.port, 115200, timeout=0.1) as device:
        synchronize_console(device, 10.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        input_state = query(
            device, b"input.state", "leshy.input.frontend.v1", "state")
        touch_state = query(
            device, b"touch.state", "leshy.touch.frontend.v1", "state")
        ui_state = query(device, b"ui.state", "leshy.ui.v1", "state")
        safety_state = query(
            device, b"safety.state", "leshy.safety.v1", "state")

    if (metrics.get("version") != args.expected_version or
            metrics.get("app_elf_sha256") != args.expected_app_elf_sha256):
        raise RuntimeError(f"running candidate mismatch: {metrics}")
    valid_samples = int(input_state.get("valid_samples", -1))
    poll_period_ms = int(input_state.get("poll_period_ms", -1))
    sample_coverage_ms = valid_samples * poll_period_ms
    presses = input_state.get("presses", {})
    if not isinstance(presses, dict):
        raise RuntimeError("physical press counters unavailable")
    physical_pass = (
        input_state.get("status") == "ready" and
        input_state.get("task_started") is True and
        input_state.get("press_events") == 1 and
        input_state.get("release_events") == 1 and
        input_state.get("dispatched_press_events") == 1 and
        presses.get("select") == 1 and
        input_state.get("last_dispatched_action") == "select" and
        input_state.get("last_dispatched_changed") is True and
        input_state.get("read_errors") == 0 and
        input_state.get("ambiguous_presses") == 0 and
        input_state.get("queue_drops") == 0 and
        sample_coverage_ms >= 3_600_000)
    if not physical_pass:
        raise RuntimeError(f"sole long-idle action contract failed: {input_state}")
    if not (touch_state.get("status") == "ready" and
            touch_state.get("press_events") == 0 and
            touch_state.get("handled_presses") == 0 and
            touch_state.get("synthetic_presses") == 0):
        raise RuntimeError(f"touch provenance boundary failed: {touch_state}")
    if not (safety_state.get("state") == "armed" and
            safety_state.get("reason") == "none"):
        raise RuntimeError(f"safety is not armed: {safety_state}")

    result = {
        "schema": "leshy.long_idle_first_action.observation.v1",
        "status": "pass_physical_key_observation",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "version": args.expected_version,
            "firmware_source_commit": args.firmware_source_commit,
            "app_elf_sha256": args.expected_app_elf_sha256,
            "firmware_sha256": digest(args.firmware),
            "factory_sha256": digest(args.factory),
            "elf_file_sha256": digest(args.elf),
        },
        "capture": {
            "capture_tool_sha256": digest(Path(__file__).resolve()),
            "read_only": True,
            "device_reset": False,
            "device_reflashed": False,
            "cardputer_connected_or_opened": False,
            "active_host_wifi_touched": False,
            "ambient_identifiers_retained": False,
            "raw_capture_retained": False,
        },
        "operator_report": {
            "original_symptom": "first_action_ignored_after_very_long_home_idle",
            "operator_confirmed_fixed": args.operator_confirmed_fixed,
            "screen_touch_claimed": False,
        },
        "physical_input": {
            **project(input_state, (
                "status", "task_started", "poll_period_ms", "debounce_ms",
                "valid_samples", "maximum_sample_gap_ms", "read_errors",
                "raw_transitions", "stable_transitions", "press_events",
                "release_events", "ambiguous_presses", "queue_capacity",
                "queue_high_water", "queue_drops", "last_queue_latency_us",
                "maximum_queue_latency_us", "last_repaint_us",
                "last_end_to_end_us", "maximum_end_to_end_us",
                "hot_path_serial_writes", "dispatched_press_events",
                "last_dispatched_action", "last_dispatched_changed")),
            "select_presses": presses.get("select"),
            "minimum_sample_coverage_ms": sample_coverage_ms,
        },
        "touch_input": project(touch_state, (
            "status", "pressure_threshold", "candidate_pressure_threshold",
            "raw_pressure", "press_events", "release_events",
            "handled_presses", "missed_presses", "rejected_coordinates",
            "synthetic_presses", "pressed")),
        "final_state": {
            "ui": project(ui_state, (
                "page", "selected_id", "runtime_event", "runtime_owner",
                "lease_mask", "safety_state", "safety_reason")),
            "safety": project(safety_state, (
                "state", "reason", "armed", "latched", "runtime_owner",
                "lease_mask", "buzzer_inactive", "nrf_ce_inactive")),
        },
        "interpretation": {
            "physical_first_action_observed": True,
            "physical_first_action_changed_ui": True,
            "input_loss_observed": False,
            "touch_fix_physical_acceptance": False,
            "reason": (
                "The sole physical Select since boot was debounced, dispatched "
                "and changed UI after over one hour of machine-counted 5 ms "
                "samples. Touch counters remained zero, so this observation "
                "does not claim physical acceptance of the touch-path change."),
        },
    }
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "minimum_sample_coverage_ms": sample_coverage_ms,
        "output": str(args.output),
        "sha256": hashlib.sha256(serialized.encode()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
