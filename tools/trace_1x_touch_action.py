#!/usr/bin/env python3
"""Capture one physical-touch UI transition after a bounded idle guard."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from run_1x_product_survey_hil import query


def touch_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "status",
            "pressure_threshold",
            "candidate_pressure_threshold",
            "raw_pressure",
            "release_debounce_ms",
            "samples",
            "touched_samples",
            "press_events",
            "release_events",
            "handled_presses",
            "missed_presses",
            "rejected_coordinates",
            "synthetic_presses",
            "pressed",
            "last_x",
            "last_y",
            "last_changed",
        )
    }


def ui_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "page",
            "parent_page",
            "selection",
            "selected_id",
            "selected_enabled",
            "revision",
            "render_mode",
            "render_us",
            "render_outcome",
            "runtime_event",
            "runtime_owner",
            "lease_mask",
            "wifi_product_view",
            "wifi_product_selection",
            "safety_state",
            "safety_reason",
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--idle-seconds", type=float, default=60.0)
    parser.add_argument("--touch-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--expected-page", default="home")
    args = parser.parse_args()
    if not 0.0 <= args.idle_seconds <= 3600.0:
        parser.error("idle-seconds must be in [0, 3600]")
    if not 0.0 < args.touch_timeout_seconds <= 3600.0:
        parser.error("touch-timeout-seconds must be in (0, 3600]")

    with PassiveSerial(args.port, 115200, timeout=0.1) as device:
        synchronize_console(device, 10.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        before_touch_raw = query(
            device, b"touch.state", "leshy.touch.frontend.v1", "state")
        before_ui_raw = query(device, b"ui.state", "leshy.ui.v1", "state")
        if before_touch_raw.get("status") != "ready":
            raise RuntimeError(f"touch is not ready: {before_touch_raw}")
        if before_ui_raw.get("page") != args.expected_page:
            raise RuntimeError(
                f"expected {args.expected_page}, got {before_ui_raw.get('page')}")
        baseline_presses = int(before_touch_raw.get("press_events", -1))
        baseline_handled = int(before_touch_raw.get("handled_presses", -1))

        idle_deadline = time.monotonic() + args.idle_seconds
        idle_samples = 0
        idle_max_pressure = int(before_touch_raw.get("raw_pressure", 0))
        idle_final_raw = before_touch_raw
        while time.monotonic() < idle_deadline:
            idle_final_raw = query(
                device, b"touch.state", "leshy.touch.frontend.v1", "state")
            idle_samples += 1
            idle_max_pressure = max(
                idle_max_pressure, int(idle_final_raw.get("raw_pressure", 0)))
            if (int(idle_final_raw.get("press_events", -1)) !=
                    baseline_presses or
                    int(idle_final_raw.get("handled_presses", -1)) !=
                    baseline_handled):
                raise RuntimeError(
                    f"unexpected physical touch during idle guard: {idle_final_raw}")
            time.sleep(0.1)

        print(json.dumps({
            "kind": "ready_for_one_physical_touch",
            "page": before_ui_raw.get("page"),
            "selected_id": before_ui_raw.get("selected_id"),
            "idle_seconds": args.idle_seconds,
            "idle_samples": idle_samples,
            "idle_max_pressure": idle_max_pressure,
        }, sort_keys=True), flush=True)

        started = time.monotonic()
        deadline = started + args.touch_timeout_seconds
        detected_touch_raw: dict[str, Any] = {}
        while time.monotonic() < deadline:
            detected_touch_raw = query(
                device, b"touch.state", "leshy.touch.frontend.v1", "state")
            if (int(detected_touch_raw.get("press_events", -1)) >
                    baseline_presses):
                break
            time.sleep(0.05)
        else:
            raise TimeoutError("no physical touch observed")

        after_ui_raw = query(device, b"ui.state", "leshy.ui.v1", "state")
        after_touch_raw = query(
            device, b"touch.state", "leshy.touch.frontend.v1", "state")
        press_delta = int(after_touch_raw.get("press_events", -1)) - baseline_presses
        handled_delta = (
            int(after_touch_raw.get("handled_presses", -1)) - baseline_handled)
        result = {
            "schema": "leshy.physical_touch_action_trace.v1",
            "status": (
                "captured" if press_delta == 1 and handled_delta == 1
                else "ambiguous_action_count"),
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
            "idle_guard": {
                "seconds": args.idle_seconds,
                "samples": idle_samples,
                "maximum_raw_pressure": idle_max_pressure,
                "false_press_events": 0,
                "false_handled_presses": 0,
                "final": touch_projection(idle_final_raw),
            },
            "wait_seconds": round(time.monotonic() - started, 6),
            "press_count_delta": press_delta,
            "handled_count_delta": handled_delta,
            "before": {
                "touch": touch_projection(before_touch_raw),
                "ui": ui_projection(before_ui_raw),
            },
            "at_detection": touch_projection(detected_touch_raw),
            "after": {
                "touch": touch_projection(after_touch_raw),
                "ui": ui_projection(after_ui_raw),
            },
        }
        serialized = json.dumps(
            result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(json.dumps({
            "kind": "physical_touch_captured",
            "status": result["status"],
            "changed": result["after"]["touch"]["last_changed"],
            "page_before": result["before"]["ui"]["page"],
            "page_after": result["after"]["ui"]["page"],
            "press_count_delta": press_delta,
            "handled_count_delta": handled_delta,
            "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "output": str(args.output),
        }, ensure_ascii=False, sort_keys=True), flush=True)
        return 0 if result["status"] == "captured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
