#!/usr/bin/env python3
"""Flash and verify the product-first Home and nested Device service menu."""

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
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "leshy.product_menu_hil.run.v1"
HOME_X = 120
HOME_ROW_Y = (105, 156, 207)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def request(device: PassiveSerial, command: str, schema: str, kind: str,
            timeout: float = 8.0) -> dict[str, Any]:
    device.write((command + "\n").encode("ascii"))
    device.flush()
    return read_json(device, schema, kind, timeout=timeout)


def state(device: PassiveSerial) -> dict[str, Any]:
    return request(device, "ui.state", "leshy.ui.v1", "state")


def action(device: PassiveSerial, name: str) -> dict[str, Any]:
    return request(device, f"ui.key {name}", "leshy.ui.v1", "state")


def touch(device: PassiveSerial, x: int, y: int) -> dict[str, Any]:
    return request(
        device, f"ui.touch {x} {y}", "leshy.touch.frontend.v1", "state"
    )


def require(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    failures = [
        f"{key}={record.get(key)!r}, expected {wanted!r}"
        for key, wanted in expected.items() if record.get(key) != wanted
    ]
    if failures:
        raise RuntimeError(f"{label}: " + "; ".join(failures))


def normalize_home(device: PassiveSerial) -> dict[str, Any]:
    current = state(device)
    for _ in range(12):
        if current.get("page") == "home":
            break
        current = action(device, "left")
    if current.get("page") != "home":
        raise RuntimeError(f"cannot return Home: {current}")
    for _ in range(8):
        if current.get("selection") == 0:
            break
        current = action(device, "up")
    require(current, {
        "page": "home", "selection": 0, "selected_id": "survey",
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, "normalized Home")
    return current


def capture(device: PassiveSerial, output: Path, name: str) -> dict[str, Any]:
    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    frame = read_exact(device, int(begin["bytes"]), timeout=30.0)
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    current = state(device)
    if (begin.get("width"), begin.get("height"), len(frame)) != (240, 320, 153600):
        raise RuntimeError(f"{name}: invalid TFT frame")
    if begin.get("revision") != end.get("revision") or \
            begin.get("revision") != current.get("revision"):
        raise RuntimeError(f"{name}: UI changed during TFT capture")
    png = rgb565be_to_png(frame, 240, 320)
    raw_path = output / f"{name}.rgb565"
    png_path = output / f"{name}.png"
    record_path = output / f"{name}.json"
    raw_path.write_bytes(frame)
    png_path.write_bytes(png)
    record = {
        "frame_begin": begin,
        "frame_end": end,
        "state": current,
        "rgb565_sha256": hashlib.sha256(frame).hexdigest(),
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "rgb565_path": str(raw_path.relative_to(ROOT)),
        "png_path": str(png_path.relative_to(ROOT)),
    }
    write_json(record_path, record)
    return record


def build_index(output: Path) -> str:
    paths = sorted(
        path for path in output.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    )
    body = "".join(
        f"{digest(path)}  {path.relative_to(output)}\n" for path in paths
    )
    index = output / "artifacts.sha256"
    index.write_text(body, encoding="utf-8")
    return digest(index)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--baud", type=int, default=921600)
    args = parser.parse_args()
    firmware = args.firmware.resolve()
    output = args.output.resolve()
    if not firmware.is_file() or output.exists():
        parser.error("firmware must exist and output must not exist")
    if app_elf_sha256(firmware) != args.expected_app_elf_sha256:
        parser.error("firmware app identity does not match expected ELF SHA-256")
    output.mkdir(parents=True)

    run: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "passed": False,
        "failures": [],
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": digest(firmware),
            "app_elf_sha256": args.expected_app_elf_sha256,
            "runner_sha256": digest(Path(__file__).resolve()),
            "flashed": args.flash,
        },
        "screens": {},
        "states": {},
    }
    write_json(output / "run.json", run)

    try:
        if args.flash:
            flash_candidate(args.port, firmware, 0x10000, args.baud)
            time.sleep(2.0)

        device = PassiveSerial()
        device.port = args.port
        device.baudrate = 115200
        device.timeout = 0.25
        device.open()
        with device:
            synchronize_console(device, timeout=12.0)
            metrics = request(device, "metrics", "leshy.boot.v1", "ready")
            require(metrics, {
                "version": args.expected_version,
                "app_elf_sha256": args.expected_app_elf_sha256,
                "buzzer_inactive": True,
                "input_detected": True,
            }, "candidate")
            run["states"]["metrics"] = metrics

            normalize_home(device)
            request(device, "ui.language ru", "leshy.ui.v1", "state")
            home = normalize_home(device)
            run["states"]["home"] = home
            run["screens"]["home_product_top"] = capture(
                device, output, "home-product-top"
            )

            expected_home = (
                ("capture", True), ("library", True),
                ("targets", False), ("lab", False), ("device", True),
            )
            for selected_id, enabled in expected_home:
                current = action(device, "down")
                require(current, {
                    "page": "home", "selected_id": selected_id,
                    "selected_enabled": enabled,
                }, f"Home item {selected_id}")
                if not enabled:
                    revision = current.get("revision")
                    rejected = action(device, "right")
                    require(rejected, {
                        "page": "home", "selected_id": selected_id,
                        "selected_enabled": False, "changed": False,
                        "revision": revision, "runtime_owner": "none",
                        "lease_mask": 0,
                    }, f"disabled Home item {selected_id}")
            run["screens"]["home_product_bottom"] = capture(
                device, output, "home-product-bottom"
            )

            device_page = action(device, "right")
            require(device_page, {
                "page": "device", "parent_page": "home",
                "device_selection": 0, "selected_id": "device",
                "runtime_owner": "device", "lease_mask": 1,
            }, "Device entry")
            run["screens"]["device_top"] = capture(
                device, output, "device-top"
            )

            before_miss = state(device)
            touch(device, HOME_X, 20)
            after_header = state(device)
            touch(device, HOME_X, 307)
            after_footer = state(device)
            for current in (after_header, after_footer):
                require(current, {
                    "page": "device",
                    "device_selection": before_miss.get("device_selection"),
                    "revision": before_miss.get("revision"),
                }, "non-interactive chrome")

            touch(device, HOME_X, HOME_ROW_Y[1])
            self_test = state(device)
            require(self_test, {
                "page": "self_test", "parent_page": "device",
                "device_selection": 1, "runtime_owner": "device",
                "lease_mask": 1, "self_test_view": "mode_menu",
            }, "touch Self-Test entry")
            run["screens"]["self_test_nested"] = capture(
                device, output, "self-test-nested"
            )
            returned = action(device, "left")
            require(returned, {
                "page": "device", "parent_page": "home",
                "device_selection": 1, "runtime_owner": "device",
                "lease_mask": 1,
            }, "Self-Test back")

            diagnostics_focus = action(device, "down")
            require(diagnostics_focus, {
                "page": "device", "device_selection": 2,
            }, "Diagnostics focus")
            diagnostics = action(device, "right")
            require(diagnostics, {
                "page": "diagnostics", "parent_page": "device",
                "device_selection": 2, "runtime_owner": "device",
                "lease_mask": 1,
            }, "Diagnostics entry")
            run["screens"]["diagnostics_nested"] = capture(
                device, output, "diagnostics-nested"
            )
            action(device, "left")
            about_focus = action(device, "down")
            require(about_focus, {
                "page": "device", "device_selection": 3,
            }, "About focus")
            run["screens"]["device_bottom"] = capture(
                device, output, "device-bottom"
            )
            about = action(device, "right")
            require(about, {
                "page": "about", "parent_page": "device",
                "device_selection": 3, "runtime_owner": "device",
                "lease_mask": 1,
            }, "About entry")
            run["screens"]["about"] = capture(device, output, "about")
            action(device, "left")
            home_bottom = action(device, "left")
            require(home_bottom, {
                "page": "home", "parent_page": "home",
                "selection": 5, "selected_id": "device",
                "runtime_owner": "none", "lease_mask": 0,
            }, "Device back")
            final = normalize_home(device)
            run["screens"]["home_final"] = capture(
                device, output, "home-final"
            )
            touch_metrics = request(
                device, "touch.state", "leshy.touch.frontend.v1", "state"
            )
            require(touch_metrics, {
                "footer_interactive": False, "touch_back_enabled": False,
            }, "touch policy")
            run["states"]["touch"] = touch_metrics
            run["final_state"] = final

        run["status"] = "pass"
        run["passed"] = True
    except Exception as error:
        run["status"] = "failed"
        run["failures"].append(f"{type(error).__name__}: {error}")
    finally:
        write_json(output / "run.json", run)
        build_index(output)

    print(json.dumps({
        "status": run["status"],
        "passed": run["passed"],
        "failures": run["failures"],
        "output": str(output),
        "screens": sorted(run["screens"]),
    }, sort_keys=True))
    return 0 if run["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
