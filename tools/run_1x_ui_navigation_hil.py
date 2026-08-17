#!/usr/bin/env python3
"""Exercise the spatial five-key navigation contract on the real TFT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
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
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if len(args.expected_app_elf_sha256) != 64:
        parser.error("expected app ELF SHA-256 must contain 64 hex characters")
    args.output.mkdir(parents=True)

    runner = Path(__file__).resolve()
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
        "runner_path": str(runner.relative_to(ROOT)),
        "runner_sha256": digest(runner),
    }
    screens: dict[str, dict[str, Any]] = {}
    transitions: dict[str, dict[str, Any]] = {}
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
                before.get("app_elf_sha256") !=
                args.expected_app_elf_sha256):
            raise RuntimeError(f"running candidate identity mismatch: {before}")
        records["metrics_before"] = retain_record(
            args.output, "metrics-before", before
        )

        normalize_home(device)
        set_language(device, "ru")
        screens["home_ru"] = capture(
            device, args.output, "home-ru", page="home", language="ru"
        )

        # Right and OK/Select are deliberately proven as equivalent inward
        # actions, while Left and diagnostic Back are equivalent return paths.
        transitions["right_enters"] = perform(
            device, "right", page="diagnostics", selection=0, changed=True
        )
        screens["diagnostics_ru"] = capture(
            device, args.output, "diagnostics-ru",
            page="diagnostics", language="ru"
        )
        transitions["left_returns"] = perform(
            device, "left", page="home", selection=0, changed=True
        )
        transitions["select_enters"] = perform(
            device, "select", page="diagnostics", selection=0, changed=True
        )
        transitions["back_returns"] = perform(
            device, "back", page="home", selection=0, changed=True
        )
        transitions["up_at_first_is_bounded"] = perform(
            device, "up", page="home", selection=0, changed=False
        )

        transitions["down_selects_survey"] = perform(
            device, "down", page="home", selection=1, changed=True
        )
        transitions["right_enters_survey"] = perform(
            device, "right", page="survey", selection=1, changed=True
        )
        screens["survey_setup_ru"] = capture(
            device, args.output, "survey-setup-ru",
            page="survey", language="ru"
        )
        transitions["left_returns_from_survey"] = perform(
            device, "left", page="home", selection=1, changed=True
        )

        transitions["down_selects_library"] = perform(
            device, "down", page="home", selection=2, changed=True
        )
        transitions["right_enters_library"] = perform(
            device, "right", page="library", selection=2, changed=True
        )
        screens["library_list_ru"] = capture(
            device, args.output, "library-list-ru",
            page="library", language="ru", library_view="list"
        )
        library_state = transitions["right_enters_library"]
        if int(library_state.get("library_entries", 0)) > 0:
            transitions["right_enters_library_detail"] = perform(
                device, "right", page="library", selection=2, changed=True
            )
            require(transitions["right_enters_library_detail"],
                    library_view="detail")
            screens["library_detail_ru"] = capture(
                device, args.output, "library-detail-ru",
                page="library", language="ru", library_view="detail"
            )
            transitions["left_returns_library_list"] = perform(
                device, "left", page="library", selection=2, changed=True
            )
            require(transitions["left_returns_library_list"],
                    library_view="list")
            transitions["select_enters_library_detail"] = perform(
                device, "select", page="library", selection=2, changed=True
            )
            require(transitions["select_enters_library_detail"],
                    library_view="detail")
            perform(device, "left", page="library", selection=2, changed=True)
        perform(device, "left", page="home", selection=2, changed=True)

        perform(device, "down", page="home", selection=3, changed=True)
        transitions["right_enters_language"] = perform(
            device, "right", page="language", selection=3, changed=True
        )
        screens["language_ru"] = capture(
            device, args.output, "language-ru", page="language", language="ru"
        )
        perform(device, "left", page="home", selection=3, changed=True)

        perform(device, "down", page="home", selection=4, changed=True)
        transitions["right_enters_self_test"] = perform(
            device, "right", page="self_test", selection=4, changed=True
        )
        screens["self_test_modes_ru"] = capture(
            device, args.output, "self-test-modes-ru",
            page="self_test", language="ru", self_test_view="mode_menu"
        )
        perform(device, "left", page="home", selection=4, changed=True)

        set_language(device, "en")
        normalize_home(device)
        screens["home_en"] = capture(
            device, args.output, "home-en", page="home", language="en"
        )
        set_language(device, "ru")
        screens["home_final_ru"] = capture(
            device, args.output, "home-final-ru", page="home", language="ru"
        )

        input_state = request(
            device, "input.state", "leshy.input.frontend.v1", "state"
        )
        safe = request(
            device, "hardware.safe-outputs",
            "leshy.hardware.safe-outputs.v1", "state"
        )
        after = request(device, "metrics", "leshy.boot.v1", "ready")
        records["input"] = retain_record(args.output, "input", input_state)
        records["safe_outputs"] = retain_record(
            args.output, "safe-outputs", safe
        )
        records["metrics_after"] = retain_record(
            args.output, "metrics-after", after
        )

    final = screens["home_final_ru"]["post_capture_state"]
    if (input_state.get("status") != "ready" or
            input_state.get("read_errors") != 0 or
            input_state.get("queue_drops") != 0):
        raise RuntimeError(f"input regression: {input_state}")
    if (safe.get("buzzer_inactive") is not True or
            safe.get("buzzer_level") != "low"):
        raise RuntimeError(f"safe-output regression: {safe}")
    if final.get("runtime_owner") != "none" or final.get("lease_mask") != 0:
        raise RuntimeError(f"final runtime leak: {final}")
    if (before.get("heap_free") != after.get("heap_free") or
            before.get("heap_min_free") != after.get("heap_min_free")):
        raise RuntimeError(f"heap changed: before={before}, after={after}")

    result = {
        "schema": "leshy.ui_navigation_hil.v1",
        "status": "pass",
        "port": args.port,
        "candidate": candidate,
        "contract": {
            "left": "back",
            "right_or_ok": "enter",
            "up_down": "select",
            "context_actions_live_inside_destination": True,
            "technical_status_removed_from_footer": True,
        },
        "screens": screens,
        "screen_count": len(screens),
        "transitions": transitions,
        "transition_count": len(transitions),
        "records": records,
        "heap_invariant": True,
        "final_owner": "none",
        "final_lease_mask": 0,
        "final_language": "ru",
        "passed": True,
    }
    run_path = args.output / "run.json"
    write_json(run_path, result)
    print(json.dumps({
        "status": "pass",
        "screens": len(screens),
        "transitions": len(transitions),
        "run": str(run_path),
        "run_sha256": digest(run_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
