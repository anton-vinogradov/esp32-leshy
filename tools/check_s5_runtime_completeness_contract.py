#!/usr/bin/env python3
"""Fail closed unless the S5.5 runtime-completeness source contract is intact."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needles: tuple[str, ...], label: str,
            failures: list[str]) -> None:
    for needle in needles:
        if needle not in text:
            failures.append(f"{label}: missing {needle!r}")


def main() -> int:
    failures: list[str] = []
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text(
        encoding="utf-8")
    board = (ROOT / "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h").read_text(
        encoding="utf-8")
    policy_h = (ROOT / "firmware/leshy1/src/services/power/PowerSafetyPolicy.h").read_text(
        encoding="utf-8")
    store = (ROOT / "firmware/leshy1/src/storage/ProductStorePolicy.cpp").read_text(
        encoding="utf-8")
    inventory = (ROOT / "firmware/leshy1/src/domain/hardware/HardwareInventory.cpp").read_text(
        encoding="utf-8")
    tests = (ROOT / "tests/native/clean_target_tests.cpp").read_text(
        encoding="utf-8")

    require(board, (
        'kAssemblyProfileId =', '"stock-rf-no-gps-no-pn532"',
        'kPowerManagerAddress = 0x75',
    ), "assembly profile", failures)
    require(policy_h, (
        "kLowMillivolts = 3350", "kRecoveryMillivolts = 3550",
        "kConfirmSamples = 3", "ProhibitedLowVoltage",
    ), "power policy", failures)
    require(store, (
        "ProductStoreAccessStatus::PowerUnsafe", "PowerWriteDisposition::ProhibitedLowVoltage",
    ), "store admission", failures)
    require(inventory, ("CapabilityState::NotApplicable", '"not_applicable"'),
            "inventory", failures)
    require(tests, (
        "testPowerSafetyPolicyDebouncesAndBlocksWrites",
        "ProductStoreAccessStatus::PowerUnsafe",
    ), "native coverage", failures)
    require(entry, (
        '"power.manager"', '"power.voltage"', '"power.safe_write"',
        '"power.sleep_resume"', '"assembly.profile"',
        '"assembly.gps"', '"assembly.pn532"',
        'std::strcmp(command, "power.state")',
        '"power.low-voltage-test confirm"',
        '"power.sleep-test confirm"',
        '"power.sleep-test state"', "PowerSleepTestReport",
        "esp_light_sleep_start()", "kLightSleepTimerToleranceUs",
        "kLightSleepTransportRecoveryMs",
        "powerSafetyPolicy.writeDisposition()",
        "productSurveyControl() == ProductSurveyWorkerControl::Idle",
        "!productSurveyScanActive()",
        '"capture.subghz.test-fixture fixed-rx-only"',
        '\\"software_fixture\\":true', '\\"physical_signal\\":false',
        '\\"application_tx_calls\\":0',
    ), "runtime", failures)
    if entry.count("powerSafetyPolicy.writeDisposition()") < 5:
        failures.append("runtime: not every product Store family is power-gated")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("S5.5 runtime-completeness source contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
