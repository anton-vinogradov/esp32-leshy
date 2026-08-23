#!/usr/bin/env python3
"""Fail closed if the bounded signal fixture drifts outside its safety contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "firmware/leshy_fixture"
PRODUCT = ROOT / "firmware/leshy1"


def main() -> int:
    errors: list[str] = []
    config = (FIXTURE / "platformio.ini").read_text(encoding="utf-8")
    entry = (FIXTURE / "src/main.cpp").read_text(encoding="utf-8")
    controller = (FIXTURE / "src/FixtureSession.cpp").read_text(
        encoding="utf-8")
    header = (FIXTURE / "src/FixtureSession.h").read_text(encoding="utf-8")
    build = (ROOT / "tools/build_ir_fixture.sh").read_text(encoding="utf-8")
    runner = (ROOT / "tools/run_hil_scenario.py").read_text(encoding="utf-8")
    orchestrator = (ROOT / "tools/run_ir_two_board_hil.py").read_text(
        encoding="utf-8")
    profiler = (ROOT / "tools/profile_hil_board.py").read_text(
        encoding="utf-8")
    scenario = json.loads((
        ROOT / "tests/hil/scenarios/infrared-nec-positive.json"
    ).read_text(encoding="utf-8"))
    nrf_scenario = json.loads((
        ROOT / "tests/hil/scenarios/nrf24-carrier-positive.json"
    ).read_text(encoding="utf-8"))
    nrf_regression = json.loads((
        ROOT / "tests/hil/scenarios/nrf24-fixture-regression.json"
    ).read_text(encoding="utf-8"))
    nrf_inventory = json.loads((
        ROOT / "tests/hil/scenarios/nrf24-fixture-inventory.json"
    ).read_text(encoding="utf-8"))
    product_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (PRODUCT / "src").rglob("*") if path.is_file())

    required_config = (
        "55.03.39/platform-espressif32.zip",
        "esp32-div-v2-signal-fixture",
        "board_build.flash_size = 16MB",
        "-std=gnu++17",
        "ARDUINO_USB_CDC_ON_BOOT=1",
        "LESHY_FIXTURE_VERSION=\\\"0.2.3-bounded-signals\\\"",
    )
    for marker in required_config:
        if marker not in config:
            errors.append(f"fixture config missing: {marker}")
    for marker in (
        "kBuzzerPin = 2", "kIrTxPin = 14", "kNrfCe1Pin = 15",
        "kNrfCe2Pin = 47", "kIrRxPin = 21", "kCarrierHz = 38000",
        "kNecCode = 0xCB34EF10U", "quiesceFromIsr",
        "esp_efuse_mac_get_default", "0000%02X%02X%02X%02X%02X%02X",
        "identity_ready\\\":%s",
        'std::strcmp(command, "fixture.begin")',
        'std::strcmp(command, "fixture.ir.nec.once")',
        'std::strcmp(command, "fixture.nrf24.carrier.start")',
        'std::strcmp(command, "fixture.nrf24.inventory")',
        'std::strcmp(command, "fixture.stop")',
        'std::strcmp(command, "fixture.panic")',
        "esp_task_wdt_isr_user_handler", "fixed_vector_only\\\":true",
        "auto_arm\\\":false", "maximum_duration_us\\\":",
        "nrf_powered_down\\\":%s", "nrf_carrier_active\\\":%s",
        "kNrfChannel = 42", "kNrfFrequencyMhz = 2400U + kNrfChannel",
        "kNrfPowerDbm = -18", "kNrfMinimumPowerCarrierSetup = 0x90",
        "kFixtureNrfCePin = kNrfCe2Pin",
        "kFixtureNrfCsnPin = kNrfCsn2Pin",
        "startFixedNrf24Carrier", "serviceFixtureHardware",
        "nrf_start_error\\\":\\\"%s", "nrf_status_readback\\\":%u",
        "channel_readback_mismatch", "rf_setup_readback_mismatch",
        "config_readback_mismatch",
        "kNrfProbeSpiHz = 2000000", "probeNrfOrientation",
        "ce_high_events\\\":0", "primary_mask\\\":%u",
        "swapped_mask\\\":%u",
    ):
        if marker not in entry:
            errors.append(f"fixture entry missing safety marker: {marker}")
    for marker in (
        "kSessionLifetimeMs = 5000", "kMaximumIrEmissionUs = 100000",
        "kNrf24CarrierDurationUs = 2000000",
        "kMaximumNrf24CarrierUs = 2500000",
        'kNecVectorId = "nec-10-34"', "app_identity_mismatch",
        'kNrf24VectorId = "nrf24-ch42-min-2s"',
        "fixture_identity_mismatch", "vector_not_allowed",
        "session_expired", "duration_out_of_bounds",
    ):
        if marker not in header + controller:
            errors.append(f"fixture controller missing bound: {marker}")

    low_before_output = re.compile(
        r"digitalWrite\(pin, LOW\);\s*pinMode\(pin, OUTPUT\);", re.S)
    if not low_before_output.search(entry):
        errors.append("fixture does not preload inactive LOW before OUTPUT")
    if entry.find("establishBootInvariant();") > entry.find("Serial.begin"):
        errors.append("fixture console starts before safe outputs")
    for forbidden in (
        "WiFi.h", "BLEDevice", "SD.h", "Preferences.h",
        "RadioLib", "ELECHOUSE", "user-replay", "sendRaw",
    ):
        if forbidden in entry or forbidden in config:
            errors.append(f"fixture contains forbidden capability: {forbidden}")
    for pattern in (
        r"\b0x35\b", r"\bSTX\b", r"\bW_TX_PAYLOAD\b",
        r"\bledcWrite\s*\(\s*kBuzzerPin\s*,",
    ):
        if re.search(pattern, entry):
            errors.append(f"fixture contains RF/buzzer TX path: {pattern}")
    if "leshy_fixture" in product_sources or "FixtureSession" in product_sources:
        errors.append("test-only fixture leaked into product sources")
    if any(value in build for value in ("upload", "esptool", "--port", "write_flash")):
        errors.append("fixture build helper can flash a device")
    for marker in ("firmware/leshy_fixture", "esp32-div-v2-signal-fixture"):
        if marker not in build:
            errors.append(f"fixture build helper is not pinned: {marker}")
    for marker in (
        "--fixture-profile", "validate_fixture_profile",
        "--expected-fixture-version", "--expected-fixture-id",
        "--fixture-source-commit", "--reuse-exact-fixture-flash",
        "fixture.begin {run_id}", "fixture.stop {run_id}",
        'else "fixture.panic"', "fixture_admission_failures",
        "fixture_inactive_failures", "byte_exact_streams",
    ):
        if marker not in runner:
            errors.append(f"HIL runner missing fixture guard: {marker}")
    devices = scenario.get("devices", {})
    fixture_policy = devices.get("fixture", {})
    steps = scenario.get("steps", [])
    step_by_id = {
        step.get("id"): step for step in steps if isinstance(step, dict)
    }
    if fixture_policy != {"required": True, "kind": "bounded_signal_fixture"}:
        errors.append("positive scenario does not require the exact fixture kind")
    emission = step_by_id.get("emit_nec", {})
    if emission.get("command") != \
            "fixture.ir.nec.once ${session_id} nec-10-34":
        errors.append("positive scenario does not use the fixed session vector")
    for step_id, operation in (
        ("live_csv", "stream"), ("cold_reopen", "reboot"),
        ("library_metadata", "query"), ("library_csv", "stream"),
    ):
        if step_by_id.get(step_id, {}).get("op") != operation:
            errors.append(
                f"positive scenario missing {step_id}/{operation}")
    invariants = scenario.get("invariants", {})
    if invariants.get("byte_exact_streams") != ["live_csv", "library_csv"]:
        errors.append("positive scenario lacks byte-exact live/Library CSV")
    if scenario.get("gate_eligible") is not True:
        errors.append("complete positive scenario is not gate eligible")
    nrf_devices = nrf_scenario.get("devices", {})
    nrf_fixture_policy = nrf_devices.get("fixture", {})
    nrf_steps = nrf_scenario.get("steps", [])
    nrf_step_by_id = {
        step.get("id"): step for step in nrf_steps if isinstance(step, dict)
    }
    if nrf_fixture_policy != {
            "required": True, "kind": "bounded_signal_fixture"}:
        errors.append("nRF scenario does not require the bounded fixture")
    carrier = nrf_step_by_id.get("start_known_signal", {})
    if carrier.get("command") != (
            "fixture.nrf24.carrier.start ${session_id} "
            "nrf24-ch42-min-2s"):
        errors.append("nRF scenario does not use the fixed session vector")
    limits = nrf_scenario.get("limits", {})
    for required_limit, expected in (
            ("calibrated_power_or_distance", False),
            ("physical_rf_silence_instrumented", False),
            ("product_rx_only", True),
            ("product_all_available_antennas", True)):
        if limits.get(required_limit) is not expected:
            errors.append(
                f"nRF scenario limit {required_limit} is not {expected}")
    if nrf_scenario.get("gate_eligible") is not True:
        errors.append("complete nRF scenario is not gate eligible")
    regression_steps = {
        step.get("id"): step for step in nrf_regression.get("steps", [])
        if isinstance(step, dict)
    }
    if nrf_regression.get("gate_eligible") is not False:
        errors.append("short nRF fixture regression is incorrectly gate eligible")
    if regression_steps.get("start_known_signal", {}).get("command") != (
            "fixture.nrf24.carrier.start ${session_id} "
            "nrf24-ch42-min-2s"):
        errors.append("short nRF fixture regression lacks the fixed vector")
    if regression_steps.get("fixture_complete", {}).get("op") != "poll_query":
        errors.append("short nRF fixture regression lacks terminal read-back")
    inventory_steps = {
        step.get("id"): step for step in nrf_inventory.get("steps", [])
        if isinstance(step, dict)
    }
    inventory = inventory_steps.get("fixture_inventory", {})
    inventory_expect = inventory.get("expect", {})
    if nrf_inventory.get("gate_eligible") is not False:
        errors.append("nRF fixture inventory is incorrectly gate eligible")
    if inventory.get("command") != "fixture.nrf24.inventory":
        errors.append("nRF fixture inventory lacks the diagnostic command")
    for field, expected in (
            ("read_only", True), ("ce_high_events", 0),
            ("nrf_ce_inactive", True), ("nrf_carrier_active", False),
            ("output_inactive", True)):
        if inventory_expect.get(field) != expected:
            errors.append(
                f"nRF fixture inventory does not enforce {field}={expected}")
    if '\\"source\\":\\"infrared\\"' not in product_sources or \
            '\\"captured_infrared_raw\\"' not in product_sources:
        errors.append("product Library lacks explicit IR capture metadata")
    for marker in (
        'READ_ONLY_COMMANDS = ("chip-id", "read-mac", "flash-id", '
        '"get-security-info")',
        '"--no-stub"', '"accepted_for_fixture_flash": accepted',
        '"writes_performed": False', '"ram_stub_uploaded": False',
        '"fixture_id": fixture_id',
    ):
        if marker not in profiler:
            errors.append(f"board profiler missing read-only guard: {marker}")
    for forbidden in ("write-flash", "erase-flash", "load-ram", "write-mem"):
        if forbidden in profiler:
            errors.append(f"board profiler exposes mutation command: {forbidden}")
    for marker in (
        "require_clean_source", "--profile-fixture-read-only",
        "--declare-standard-v2-no-extensions",
        "--declare-antennas-attached",
        "tools/build.sh", "tools/build_ir_fixture.sh",
        "--fixture-source-commit", "--flash-fixture",
    ):
        if marker not in orchestrator:
            errors.append(f"two-board orchestrator missing guard: {marker}")
    if "profile.get(\"port_at_profile\") != fixture_port" not in runner:
        errors.append("HIL runner does not bind fixture profile to exact port")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("Bounded signal fixture contract passed: separate image, inactive "
          "boot, exact identity/session, fixed NEC and minimum-power nRF24 "
          "vectors, bounded timeout and panic stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
