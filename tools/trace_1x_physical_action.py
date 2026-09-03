#!/usr/bin/env python3
"""Capture one physical-key UI transition without resetting the board."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from run_1x_product_survey_hil import query


def input_projection(value: dict[str, Any]) -> dict[str, Any]:
    presses = value.get("presses", {})
    if not isinstance(presses, dict):
        presses = {}
    return {
        "valid_samples": value.get("valid_samples"),
        "read_errors": value.get("read_errors"),
        "raw_transitions": value.get("raw_transitions"),
        "stable_transitions": value.get("stable_transitions"),
        "press_events": value.get("press_events"),
        "release_events": value.get("release_events"),
        "ambiguous_presses": value.get("ambiguous_presses"),
        "presses": {
            key: presses.get(key)
            for key in ("select", "up", "down", "left", "right")
        },
        "queue_depth": value.get("queue_depth"),
        "queue_high_water": value.get("queue_high_water"),
        "queue_drops": value.get("queue_drops"),
        "dispatched_press_events": value.get("dispatched_press_events"),
        "last_dispatched_action": value.get("last_dispatched_action"),
        "last_dispatched_changed": value.get("last_dispatched_changed"),
        "last_queue_latency_us": value.get("last_queue_latency_us"),
        "maximum_queue_latency_us": value.get("maximum_queue_latency_us"),
        "last_repaint_us": value.get("last_repaint_us"),
        "last_end_to_end_us": value.get("last_end_to_end_us"),
        "maximum_end_to_end_us": value.get("maximum_end_to_end_us"),
    }


def ui_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": value.get("page"),
        "parent_page": value.get("parent_page"),
        "selection": value.get("selection"),
        "selected_id": value.get("selected_id"),
        "selected_enabled": value.get("selected_enabled"),
        "revision": value.get("revision"),
        "render_mode": value.get("render_mode"),
        "render_us": value.get("render_us"),
        "render_outcome": value.get("render_outcome"),
        "runtime_event": value.get("runtime_event"),
        "runtime_owner": value.get("runtime_owner"),
        "lease_mask": value.get("lease_mask"),
        "wifi_product_view": value.get("wifi_product_view"),
        "wifi_product_selection": value.get("wifi_product_selection"),
        "safety_state": value.get("safety_state"),
        "safety_reason": value.get("safety_reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--expected-page", default="home")
    args = parser.parse_args()

    if args.timeout_seconds <= 0.0 or args.timeout_seconds > 3600.0:
        raise SystemExit("timeout must be in (0, 3600] seconds")

    with PassiveSerial(args.port, 115200, timeout=0.1) as device:
        synchronize_console(device, 10.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        before_input_raw = query(
            device, b"input.state", "leshy.input.frontend.v1", "state")
        before_ui_raw = query(device, b"ui.state", "leshy.ui.v1", "state")
        before_count = before_input_raw.get("dispatched_press_events")
        if not isinstance(before_count, int) or isinstance(before_count, bool):
            raise RuntimeError("input dispatch count is unavailable")
        if before_ui_raw.get("page") != args.expected_page:
            raise RuntimeError(
                f"expected {args.expected_page}, got {before_ui_raw.get('page')}")

        print(json.dumps({
            "kind": "ready_for_one_physical_action",
            "page": before_ui_raw.get("page"),
            "selected_id": before_ui_raw.get("selected_id"),
            "dispatched_press_events": before_count,
        }, sort_keys=True), flush=True)

        started = time.monotonic()
        deadline = started + args.timeout_seconds
        observed_input_raw: dict[str, Any] = {}
        while time.monotonic() < deadline:
            observed_input_raw = query(
                device, b"input.state", "leshy.input.frontend.v1", "state")
            current = observed_input_raw.get("dispatched_press_events")
            if isinstance(current, int) and not isinstance(current, bool) and \
                    current != before_count:
                break
            time.sleep(0.05)
        else:
            raise TimeoutError("no physical input action observed")

        after_ui_raw = query(device, b"ui.state", "leshy.ui.v1", "state")
        after_input_raw = query(
            device, b"input.state", "leshy.input.frontend.v1", "state")
        after_count = after_input_raw.get("dispatched_press_events")
        delta = after_count - before_count \
            if isinstance(after_count, int) and not isinstance(after_count, bool) \
            else None
        result = {
            "schema": "leshy.physical_action_trace.v1",
            "status": "captured" if delta == 1 else "ambiguous_action_count",
            "candidate": {
                "version": metrics.get("version"),
                "app_elf_sha256": metrics.get("app_elf_sha256"),
                "reset_reason_code": metrics.get("reset_reason_code"),
            },
            "scope": {
                "read_only": True,
                "device_reset": False,
                "device_reflashed": False,
                "host_wifi_touched": False,
                "ambient_identifiers_retained": False,
            },
            "wait_seconds": round(time.monotonic() - started, 6),
            "action_count_delta": delta,
            "before": {
                "input": input_projection(before_input_raw),
                "ui": ui_projection(before_ui_raw),
            },
            "after": {
                "input_at_detection": input_projection(observed_input_raw),
                "input": input_projection(after_input_raw),
                "ui": ui_projection(after_ui_raw),
            },
        }
        serialized = json.dumps(
            result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(json.dumps({
            "kind": "physical_action_captured",
            "status": result["status"],
            "action": result["after"]["input"]["last_dispatched_action"],
            "changed": result["after"]["input"]["last_dispatched_changed"],
            "page_before": result["before"]["ui"]["page"],
            "page_after": result["after"]["ui"]["page"],
            "runtime_event": result["after"]["ui"]["runtime_event"],
            "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "output": str(args.output),
        }, ensure_ascii=False, sort_keys=True), flush=True)
        return 0 if delta == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
