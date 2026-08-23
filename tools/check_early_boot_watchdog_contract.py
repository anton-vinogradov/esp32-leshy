#!/usr/bin/env python3
"""Fail closed unless the early application boot interval is Task-WDT guarded."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"early boot watchdog contract failed: {message}")


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    setup = text[text.index("void setup() {"):]
    arm = setup.index("armRuntimeSafetyWatchdog()")
    display = setup.index("display.init()")
    input_probe = setup.index("probeInputAtBoot(")
    recovery = setup.index("recoverProductCatalogAtBoot()")
    interactive = setup.index("renderInteractiveScreen()")
    require(arm < display < input_probe < recovery < interactive,
            "runtime WDT must cover display, input, recovery and render")
    require(setup.count("armRuntimeSafetyWatchdog()") == 1,
            "setup must establish one permanent runtime subscription")
    require(setup.count("feedRuntimeSafetyWatchdog();") >= 5,
            "bounded boot stages require explicit progress feeds")
    for token in (
        "RTC_NOINIT_ATTR std::uint32_t earlyBootWatchdogTestRtcState",
        "safety.early-boot-watchdog-test confirm",
        "leshy.safety.early_boot_watchdog_test.v1",
        '\\"stage\\":\\"before_display\\"',
        "earlyBootWatchdogTestRtcState = 0",
        "for (;;) delay(1000)",
        "recordRuntimeSafetyWatchdogTrip()",
        "quiesceEmergencyGpioFromIsr()",
    ):
        require(token in text, f"missing {token!r}")
    print(
        "early boot watchdog contract passed: exact-app Task-WDT is armed "
        "before display/input/SD and has a confirmed pre-display injection"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
