#!/usr/bin/env python3
"""Fail closed if a HIL runner holds stale native-USB descriptors across reset."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
BOOT_HELPER = TOOLS / "capture_1x_boot.py"
SURVEY_RUNNER = TOOLS / "run_1x_product_survey_hil.py"
PRERELEASE_RUNNER = TOOLS / "run_1x_prerelease_hil.py"
CONTRACT = Path(__file__).resolve()


def main() -> int:
    failures: list[str] = []
    boot = BOOT_HELPER.read_text(encoding="utf-8")
    survey = SURVEY_RUNNER.read_text(encoding="utf-8")
    prerelease = PRERELEASE_RUNNER.read_text(encoding="utf-8")

    for path in sorted(TOOLS.glob("*.py")):
        if path in (BOOT_HELPER, CONTRACT):
            continue
        text = path.read_text(encoding="utf-8")
        if "from capture_1x_boot import reset_and_capture\n" in text:
            failures.append(f"{path.name} imports stale-descriptor reset_and_capture")
        if "reset_and_capture(" in text:
            failures.append(f"{path.name} calls stale-descriptor reset_and_capture")

    for label, text in (("shared reset", survey),
                        ("prerelease", prerelease)):
        if "reset_and_capture_reconnecting(" not in text:
            failures.append(f"{label} omits reconnect-aware native USB reset")
        if "with serial.Serial(args.port" in text or \
                "with serial.Serial(port" in text:
            failures.append(f"{label} holds native USB open across reset")

    for marker in (
        "def reset_and_capture_reconnecting(",
        "capture_reconnecting_until_ready(port, seconds)",
        "PassiveSerial(port, 115200, timeout=0.05)",
        "disconnects += 1",
        "open_attempts += 1",
    ):
        if marker not in boot:
            failures.append(f"boot helper omits {marker}")

    main_body = boot.split("def main()", 1)[-1]
    if "reset_and_capture_reconnecting(args.port, args.seconds)" not in main_body:
        failures.append("capture_1x_boot CLI still uses a stale descriptor")

    if failures:
        print("native USB reset contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "native USB reset contract passed: reset handle closes before "
        "ESP32-S3 re-enumeration and all active runners reconnect by exact port"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
