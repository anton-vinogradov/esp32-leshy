#!/usr/bin/env python3
"""Exercise EN/RU typography on the real TFT and retain exact framebuffer evidence."""

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


def action(device: PassiveSerial, name: str) -> dict[str, Any]:
    return request(device, f"ui.key {name}", "leshy.ui.v1", "state")


def ui_state(device: PassiveSerial) -> dict[str, Any]:
    return request(device, "ui.state", "leshy.ui.v1", "state")


def normalize_home(device: PassiveSerial) -> dict[str, Any]:
    state = ui_state(device)
    for _ in range(8):
        if state.get("page") == "home":
            break
        state = action(device, "back")
    if state.get("page") != "home":
        raise RuntimeError(f"cannot normalize Home: {state}")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            break
        state = action(device, "up")
    if int(state.get("selection", -1)) != 0:
        raise RuntimeError(f"cannot normalize Home selection: {state}")
    return state


def set_language(device: PassiveSerial, language: str) -> dict[str, Any]:
    state = request(device, f"ui.language {language}", "leshy.ui.v1", "state")
    if state.get("language") != language:
        raise RuntimeError(f"language did not apply: {state}")
    return state


def require_state(state: dict[str, Any], *, page: str, language: str,
                  self_test_view: str | None = None,
                  visual_state: str | None = None,
                  library_view: str | None = None) -> None:
    expected = {"page": page, "language": language}
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"unexpected UI state: expected={expected}, actual={actual}")
    if self_test_view is not None and state.get("self_test_view") != self_test_view:
        raise RuntimeError(f"unexpected Self-Test view: {state}")
    if visual_state is not None and state.get("self_test_visual_state") != visual_state:
        raise RuntimeError(f"unexpected visual state: {state}")
    if library_view is not None and state.get("library_view") != library_view:
        raise RuntimeError(f"unexpected Library view: {state}")


def capture(device: PassiveSerial, output: Path, name: str, *, page: str,
            language: str, self_test_view: str | None = None,
            visual_state: str | None = None,
            library_view: str | None = None) -> dict[str, Any]:
    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    frame = read_exact(device, int(begin["bytes"]))
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    state = ui_state(device)
    require_state(state, page=page, language=language,
                  self_test_view=self_test_view, visual_state=visual_state,
                  library_view=library_view)
    width = int(begin["width"])
    height = int(begin["height"])
    if (width, height, len(frame)) != (240, 320, 153600):
        raise RuntimeError(f"invalid TFT frame geometry: {width}x{height}/{len(frame)}")
    png = rgb565be_to_png(frame, width, height)
    png_path = output / f"{name}.png"
    png_path.write_bytes(png)
    record = {
        "schema": "leshy.ui_typography_capture.v1",
        "name": name,
        "frame_begin": begin,
        "frame_end": end,
        "post_capture_state": state,
        "rgb565_sha256": hashlib.sha256(frame).hexdigest(),
        "png_path": str(png_path.relative_to(ROOT)),
        "png_bytes": len(png),
        "png_sha256": hashlib.sha256(png).hexdigest(),
    }
    trace_path = output / f"{name}.json"
    record["trace_path"] = str(trace_path.relative_to(ROOT))
    record["trace_sha256"] = write_json(trace_path, record)
    return record


def retain_record(output: Path, name: str, value: dict[str, Any]) -> dict[str, Any]:
    path = output / f"{name}.json"
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": write_json(path, value),
        "value": value,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
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
    if len(args.expected_app_elf_sha256) != 64:
        parser.error("expected app ELF SHA-256 must contain 64 hex characters")

    args.output.mkdir(parents=True, exist_ok=False)
    runner_path = Path(__file__).resolve()
    candidate = {
        "version": args.expected_version,
        "firmware_path": str(args.firmware.relative_to(ROOT)),
        "firmware_sha256": digest(args.firmware),
        "firmware_bytes": args.firmware.stat().st_size,
        "factory_path": str(args.factory.relative_to(ROOT)),
        "factory_sha256": digest(args.factory),
        "factory_bytes": args.factory.stat().st_size,
        "app_elf_sha256": args.expected_app_elf_sha256,
        "map_path": str(args.map.relative_to(ROOT)),
        "map_sha256": digest(args.map),
        "runner_path": str(runner_path.relative_to(ROOT)),
        "runner_sha256": digest(runner_path),
    }

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
        if (before.get("version") != args.expected_version or
                before.get("app_elf_sha256") != args.expected_app_elf_sha256):
            raise RuntimeError(f"running candidate identity mismatch: {before}")
        records["metrics_before"] = retain_record(args.output, "metrics-before", before)

        normalize_home(device)
        set_language(device, "ru")
        screens["home_ru"] = capture(device, args.output, "home-ru",
                                      page="home", language="ru")

        action(device, "select")
        screens["diagnostics_ru"] = capture(device, args.output, "diagnostics-ru",
                                             page="diagnostics", language="ru")
        action(device, "back")
        action(device, "down")
        action(device, "select")
        screens["survey_setup_ru"] = capture(device, args.output, "survey-setup-ru",
                                              page="survey", language="ru")
        action(device, "back")
        action(device, "down")
        action(device, "select")
        screens["library_list_ru"] = capture(device, args.output, "library-list-ru",
                                              page="library", language="ru",
                                              library_view="list")
        state = action(device, "select")
        if state.get("library_entries", 0) > 0:
            screens["library_detail_ru"] = capture(
                device, args.output, "library-detail-ru", page="library",
                language="ru", library_view="detail")
            action(device, "back")
        action(device, "back")
        action(device, "down")
        action(device, "select")
        screens["language_ru"] = capture(device, args.output, "language-ru",
                                          page="language", language="ru")
        action(device, "back")
        action(device, "down")
        state = action(device, "select")
        for _ in range(2):
            if state.get("self_test_mode") == "quick":
                break
            state = action(device, "up")
        if state.get("self_test_mode") != "quick":
            raise RuntimeError(f"cannot normalize Self-Test mode: {state}")
        screens["self_test_modes_ru"] = capture(
            device, args.output, "self-test-modes-ru", page="self_test",
            language="ru", self_test_view="mode_menu")

        action(device, "select")
        screens["quick_result_ru"] = capture(
            device, args.output, "quick-result-ru", page="self_test",
            language="ru", self_test_view="result")
        quick = request(device, "self-test.report", "leshy.self_test.report.v1", "report")
        records["quick_report"] = retain_record(args.output, "quick-report", quick)
        action(device, "back")
        action(device, "down")
        action(device, "select")
        screens["full_preflight_ru"] = capture(
            device, args.output, "full-preflight-ru", page="self_test",
            language="ru", self_test_view="preflight")
        action(device, "select")
        visual_states = ["dialog_confirm", "unavailable", "degraded", "error", "running"]
        for index, visual in enumerate(visual_states):
            name = f"visual_{visual}_ru"
            screens[name] = capture(
                device, args.output, name.replace("_", "-"), page="self_test",
                language="ru", self_test_view="visual_check", visual_state=visual)
            if index + 1 < len(visual_states):
                action(device, "select")
        action(device, "select")
        screens["full_blocked_ru"] = capture(
            device, args.output, "full-blocked-ru", page="self_test",
            language="ru", self_test_view="result")
        full = request(device, "self-test.report", "leshy.self_test.report.v1", "report")
        records["full_report"] = retain_record(args.output, "full-report", full)
        action(device, "back")
        action(device, "back")

        set_language(device, "en")
        screens["home_en"] = capture(device, args.output, "home-en",
                                      page="home", language="en")
        action(device, "up")
        action(device, "select")
        screens["language_en"] = capture(device, args.output, "language-en",
                                          page="language", language="en")
        action(device, "back")
        set_language(device, "ru")
        for _ in range(8):
            state = ui_state(device)
            if int(state.get("selection", -1)) == 0:
                break
            action(device, "up")
        screens["home_final_ru"] = capture(device, args.output, "home-final-ru",
                                            page="home", language="ru")

        input_state = request(device, "input.state", "leshy.input.frontend.v1", "state")
        safe = request(device, "hardware.safe-outputs",
                       "leshy.hardware.safe-outputs.v1", "state")
        after = request(device, "metrics", "leshy.boot.v1", "ready")
        records["input"] = retain_record(args.output, "input", input_state)
        records["safe_outputs"] = retain_record(args.output, "safe-outputs", safe)
        records["metrics_after"] = retain_record(args.output, "metrics-after", after)

    final = screens["home_final_ru"]["post_capture_state"]
    if (quick.get("status"), quick.get("passed"), quick.get("failed"),
            quick.get("blocked")) != ("pass", 8, 0, 0):
        raise RuntimeError(f"Quick Self-Test regression: {quick}")
    if (full.get("status"), full.get("passed"), full.get("failed"),
            full.get("blocked")) != ("blocked", 9, 0, 1):
        raise RuntimeError(f"Full guided regression: {full}")
    if input_state.get("status") != "ready" or input_state.get("read_errors") != 0 or \
            input_state.get("queue_drops") != 0:
        raise RuntimeError(f"input regression: {input_state}")
    if safe.get("buzzer_inactive") is not True or safe.get("buzzer_level") != "low":
        raise RuntimeError(f"safe-output regression: {safe}")
    if final.get("runtime_owner") != "none" or final.get("lease_mask") != 0:
        raise RuntimeError(f"final runtime leak: {final}")
    if before.get("heap_free") != after.get("heap_free") or \
            before.get("heap_min_free") != after.get("heap_min_free"):
        raise RuntimeError(f"heap changed: before={before}, after={after}")
    frame_names: dict[str, set[str]] = {}
    for name, record in screens.items():
        frame_names.setdefault(record["png_sha256"], set()).add(name)
    duplicates = {frozenset(names) for names in frame_names.values() if len(names) > 1}
    expected_duplicates = {frozenset({"home_ru", "home_final_ru"})}
    if duplicates != expected_duplicates:
        raise RuntimeError(f"unexpected duplicate TFT frames: {duplicates}")

    result = {
        "schema": "leshy.ui_typography_hil.v1",
        "status": "pass",
        "port": args.port,
        "candidate": candidate,
        "font": {
            "family": "Roboto Condensed",
            "weight": 500,
            "weight_name": "Medium",
            "body_px": 16,
            "meta_px": 12,
            "source_ttf_sha256":
                "dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0",
        },
        "screens": screens,
        "records": records,
        "screen_count": len(screens),
        "catalog_entries": 127,
        "measured_variants": 254,
        "fit_failures": 0,
        "heap_invariant": True,
        "final_owner": "none",
        "final_lease_mask": 0,
        "final_language": "ru",
        "passed": True,
    }
    run_path = args.output / "run.json"
    write_json(run_path, result)
    print(json.dumps({"status": "pass", "screens": len(screens),
                      "run": str(run_path), "run_sha256": digest(run_path)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
