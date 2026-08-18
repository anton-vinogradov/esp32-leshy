#!/usr/bin/env python3
"""Exercise physical XPT2046 input and deterministic touch hit targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import (
    PassiveSerial,
    read_exact,
    read_json,
    rgb565be_to_png,
    synchronize_console,
)


ROOT = Path(__file__).resolve().parents[1]
HOME_X = 120
HOME_ROW_Y = (105, 156, 207)
CHOICE_ROW_Y = (105, 157, 209)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def request(device: PassiveSerial, command: str, schema: str, kind: str,
            timeout: float = 5.0) -> dict[str, Any]:
    device.write((command + "\n").encode("ascii"))
    device.flush()
    return read_json(device, schema, kind, timeout=timeout)


def ui_state(device: PassiveSerial) -> dict[str, Any]:
    return request(device, "ui.state", "leshy.ui.v1", "state")


def action(device: PassiveSerial, name: str) -> dict[str, Any]:
    return request(device, f"ui.key {name}", "leshy.ui.v1", "state")


def touch(device: PassiveSerial, x: int, y: int) -> dict[str, Any]:
    return request(device, f"ui.touch {x} {y}",
                   "leshy.touch.frontend.v1", "state")


def touch_state(device: PassiveSerial) -> dict[str, Any]:
    return request(device, "touch.state", "leshy.touch.frontend.v1", "state")


def normalize_home(device: PassiveSerial) -> dict[str, Any]:
    state = ui_state(device)
    for _ in range(8):
        if state.get("page") == "home":
            break
        state = action(device, "left")
    if state.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {state}")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            break
        state = action(device, "up")
    if int(state.get("selection", -1)) != 0:
        raise RuntimeError(f"cannot normalize Home selection: {state}")
    return state


def retain(output: Path, name: str, value: dict[str, Any]) -> dict[str, Any]:
    path = output / f"{name}.json"
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": write_json(path, value),
        "value": value,
    }


def capture(device: PassiveSerial, output: Path, name: str) -> dict[str, Any]:
    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    frame = read_exact(device, int(begin["bytes"]))
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    state = ui_state(device)
    if (int(begin["width"]), int(begin["height"]), len(frame)) != \
            (240, 320, 153600):
        raise RuntimeError(f"invalid TFT frame: {begin}/{len(frame)}")
    png = rgb565be_to_png(frame, 240, 320)
    png_path = output / f"{name}.png"
    png_path.write_bytes(png)
    record = {
        "frame_begin": begin,
        "frame_end": end,
        "post_capture_state": state,
        "rgb565_sha256": hashlib.sha256(frame).hexdigest(),
        "png_path": str(png_path.relative_to(ROOT)),
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "png_bytes": len(png),
    }
    trace_path = output / f"{name}.json"
    record["trace_path"] = str(trace_path.relative_to(ROOT))
    record["trace_sha256"] = write_json(trace_path, record)
    return record


def wait_for_physical_home_press(device: PassiveSerial,
                                 baseline: dict[str, Any],
                                 timeout: float) -> tuple[dict[str, Any],
                                                          dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = touch_state(device)
        ui = ui_state(device)
        if (int(state.get("press_events", 0)) >
                int(baseline.get("press_events", 0)) and
                int(state.get("handled_presses", 0)) >
                int(baseline.get("handled_presses", 0))):
            return state, ui
        time.sleep(0.1)
    raise TimeoutError("no handled physical touch press observed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--physical-timeout", type=float, default=0.0)
    args = parser.parse_args()
    args.output = args.output.resolve()
    artifacts = [args.firmware.resolve(), args.factory.resolve(),
                 args.elf.resolve()]
    if any(not path.is_file() for path in artifacts):
        parser.error("candidate artifact missing")
    args.output.mkdir(parents=True, exist_ok=False)

    candidate = {
        "version": args.expected_version,
        "app_elf_sha256": args.expected_app_elf_sha256,
        "firmware_sha256": digest(artifacts[0]),
        "factory_sha256": digest(artifacts[1]),
        "elf_file_sha256": digest(artifacts[2]),
        "runner_sha256": digest(Path(__file__).resolve()),
    }
    records: dict[str, dict[str, Any]] = {}
    screens: dict[str, dict[str, Any]] = {}

    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    device.open()
    with device:
        synchronize_console(device)
        metrics_before = request(device, "metrics", "leshy.boot.v1", "ready")
        if (metrics_before.get("version") != args.expected_version or
                metrics_before.get("app_elf_sha256") !=
                args.expected_app_elf_sha256):
            raise RuntimeError(f"running candidate mismatch: {metrics_before}")
        records["metrics_before"] = retain(
            args.output, "metrics-before", metrics_before)

        normalize_home(device)
        initial = touch_state(device)
        if initial.get("status") != "ready":
            raise RuntimeError(f"touch is not calibrated: {initial}")
        records["touch_initial"] = retain(
            args.output, "touch-initial", initial)
        screens["home_three_targets"] = capture(
            device, args.output, "home-three-targets")

        physical: dict[str, Any] | None = None
        physical_ui: dict[str, Any] | None = None
        if args.physical_timeout > 0:
            print(json.dumps({"status": "waiting_physical_touch",
                              "instruction": "tap_top_home_row"}), flush=True)
            physical, physical_ui = wait_for_physical_home_press(
                device, initial, args.physical_timeout)
            if physical_ui.get("page") != "diagnostics":
                raise RuntimeError(
                    f"physical touch did not open top Home row: {physical_ui}")
            records["touch_physical"] = retain(
                args.output, "touch-physical", physical)
            records["touch_physical_ui"] = retain(
                args.output, "touch-physical-ui", physical_ui)
            normalize_home(device)

        before_miss = ui_state(device)
        touch(device, HOME_X, 20)
        after_header = ui_state(device)
        touch(device, HOME_X, 307)
        after_footer = ui_state(device)
        stable_fields = ("page", "selection", "revision")
        if any(before_miss.get(key) != after_header.get(key) or
               before_miss.get(key) != after_footer.get(key)
               for key in stable_fields):
            raise RuntimeError("header/footer unexpectedly changed UI state")

        touch(device, HOME_X, HOME_ROW_Y[2])
        if ui_state(device).get("page") != "library":
            raise RuntimeError("third visible Home target did not open Library")
        screens["library_from_touch"] = capture(
            device, args.output, "library-from-touch")
        normalize_home(device)

        state = ui_state(device)
        for _ in range(5):
            state = action(device, "down")
        if int(state.get("selection", -1)) != 5:
            raise RuntimeError(f"cannot expose last Home window: {state}")
        touch(device, HOME_X, HOME_ROW_Y[2])
        state = ui_state(device)
        if state.get("page") != "self_test" or \
                state.get("self_test_view") != "mode_menu":
            raise RuntimeError(f"touch did not open Self-Test: {state}")
        screens["self_test_from_touch"] = capture(
            device, args.output, "self-test-from-touch")

        touch(device, HOME_X, CHOICE_ROW_Y[0])
        quick = request(device, "self-test.report",
                        "leshy.self_test.report.v1", "report")
        checks = {item.get("id"): item.get("status")
                  for item in quick.get("checks", [])}
        if (quick.get("status"), quick.get("plan_version"),
                quick.get("passed"), quick.get("failed"),
                quick.get("blocked")) != ("pass", 8, 9, 0, 0) or \
                checks.get("quick.input.touch") != "pass":
            raise RuntimeError(f"Quick touch regression: {quick}")
        records["quick"] = retain(args.output, "quick", quick)
        screens["quick_touch_pass"] = capture(
            device, args.output, "quick-touch-pass")
        normalize_home(device)

        touch_final = touch_state(device)
        metrics_after = request(device, "metrics", "leshy.boot.v1", "ready")
        records["touch_final"] = retain(
            args.output, "touch-final", touch_final)
        records["metrics_after"] = retain(
            args.output, "metrics-after", metrics_after)
        final_ui = ui_state(device)

    if touch_final.get("footer_interactive") is not False or \
            touch_final.get("touch_back_enabled") is not False or \
            int(touch_final.get("missed_presses", 0)) < \
            int(initial.get("missed_presses", 0)) + 2:
        raise RuntimeError(f"touch chrome contract failed: {touch_final}")
    if final_ui.get("runtime_owner") != "none" or \
            final_ui.get("lease_mask") != 0:
        raise RuntimeError(f"final resource leak: {final_ui}")
    if metrics_before.get("heap_free") != metrics_after.get("heap_free") or \
            metrics_before.get("heap_min_free") != metrics_after.get("heap_min_free"):
        raise RuntimeError("heap changed during touch HIL")

    result = {
        "schema": "leshy.touch_hil.v1",
        "status": "pass",
        "candidate": candidate,
        "physical_touch_required": args.physical_timeout > 0,
        "physical_touch_observed": physical is not None,
        "physical_ui": physical_ui,
        "records": records,
        "screens": screens,
        "touch_contract": {
            "visible_home_targets": 3,
            "minimum_target_height_px": 44,
            "footer_interactive": False,
            "header_interactive": False,
            "touch_back_enabled": False,
            "physical_left_is_back": True,
        },
        "quick": {"plan_version": 8, "passed": 9},
        "heap_invariant": True,
        "final_owner": "none",
        "final_lease_mask": 0,
    }
    run_path = args.output / "run.json"
    write_json(run_path, result)
    print(json.dumps({"status": "pass", "run": str(run_path),
                      "run_sha256": digest(run_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
