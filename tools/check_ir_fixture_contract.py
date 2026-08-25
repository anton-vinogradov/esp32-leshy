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
    phase_orchestrator = (ROOT / "tools/run_s5_two_board_hil.py").read_text(
        encoding="utf-8")
    subghz_ook_wrapper = (
        ROOT / "tools/run_subghz_ook_two_board_hil.py").read_text(
            encoding="utf-8")
    subghz_fsk_wrapper = (
        ROOT / "tools/run_subghz_fsk_two_board_hil.py").read_text(
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
    subghz_ook = json.loads((
        ROOT / "tests/hil/scenarios/subghz-ook-positive.json"
    ).read_text(encoding="utf-8"))
    subghz_fsk = json.loads((
        ROOT / "tests/hil/scenarios/subghz-fsk-positive.json"
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
        "LESHY_FIXTURE_VERSION=\\\"0.3.0-subghz-safe\\\"",
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
        'std::strcmp(command, "fixture.cc1101.ook.once")',
        'std::strcmp(command, "fixture.cc1101.fsk.once")',
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
        "kNrfCe3SharedPin = kIrTxPin",
        "configureIrCarrier", "ledcDetach(kIrTxPin)",
        "startFixedNrf24Carrier", "serviceFixtureHardware",
        "nrf_start_error\\\":\\\"%s", "nrf_status_readback\\\":%u",
        "channel_readback_mismatch", "rf_setup_readback_mismatch",
        "config_readback_mismatch",
        "kNrfProbeSpiHz = 2000000", "probeNrfOrientation",
        "ce_high_events\\\":0", "primary_mask\\\":%u",
        "swapped_mask\\\":%u",
        "cc_identity_attempted\\\":true", "kCcReadPartNumber = 0xF0",
        "kCcReadVersion = 0xF1", "readCcIdentityRegister",
        "kCcFrequencyKHz = 433920", "kCcPowerDbm = -15",
        "kCcMinimumPowerTable = 0x1D", "kCcPacketLength = 60",
        "kCcOokPacketCount = 4", "kCcFskPacketCount = 1",
        "kCcRegisterTxBytes = 0x3A",
        "cc_power_cleared", "cc_tx_fifo_cleared",
        "emitFixedCcVector", "cc_hardware_auto_idle\\\":true",
        "maximum_cc1101_emission_us\\\":250000",
        "configuration_readback_mismatch", "transmit_state_timeout",
        "idle_state_timeout",
    ):
        if marker not in entry:
            errors.append(f"fixture entry missing safety marker: {marker}")
    for marker in (
        "kSessionLifetimeMs = 5000", "kMaximumIrEmissionUs = 100000",
        "kNrf24CarrierDurationUs = 2000000",
        "kMaximumNrf24CarrierUs = 2500000",
        "kMaximumCc1101EmissionUs = 250000",
        'kNecVectorId = "nec-10-34"', "app_identity_mismatch",
        'kNrf24VectorId = "nrf24-ch42-min-2s"',
        'kCc1101OokVectorId = "cc1101-ook-433920-min"',
        'kCc1101FskVectorId = "cc1101-fsk-433920-min"',
        "fixture_identity_mismatch", "vector_not_allowed",
        "session_expired", "duration_out_of_bounds",
    ):
        if marker not in header + controller:
            errors.append(f"fixture controller missing bound: {marker}")

    low_before_output = re.compile(
        r"digitalWrite\(pin, LOW\);\s*pinMode\(pin, OUTPUT\);", re.S)
    if not low_before_output.search(entry):
        errors.append("fixture does not preload inactive LOW before OUTPUT")
    if re.search(r"digitalWrite\s*\(\s*kNrfCe3", entry):
        errors.append(
            "fixture drives shared IR/CE3 pin through GPIO after LEDC attach")
    if "ledcWrite(kIrTxPin, 0)" not in entry:
        errors.append("fixture does not quiesce the shared IR/CE3 pin via LEDC")
    if entry.find("establishBootInvariant();") > entry.find("Serial.begin"):
        errors.append("fixture console starts before safe outputs")
    for forbidden in (
        "WiFi.h", "BLEDevice", "SD.h", "Preferences.h",
        "RadioLib", "ELECHOUSE", "user-replay", "sendRaw",
    ):
        if forbidden in entry or forbidden in config:
            errors.append(f"fixture contains forbidden capability: {forbidden}")
    for pattern in (
        r"\bW_TX_PAYLOAD\b",
        r"\bledcWrite\s*\(\s*kBuzzerPin\s*,",
        r"fixture\.cc1101\.(?:frequency|power|payload|duration)",
        r"fixture\.cc1101\.tx",
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
        '"capture.subghz.export.csv"',
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
    for modulation, scenario_value, command, vector in (
            ("ook_envelope", subghz_ook,
             "fixture.cc1101.ook.once ${session_id} "
             "cc1101-ook-433920-min", "cc1101-ook-433920-min"),
            ("fsk_async", subghz_fsk,
             "fixture.cc1101.fsk.once ${session_id} "
             "cc1101-fsk-433920-min", "cc1101-fsk-433920-min")):
        sub_steps = {
            step.get("id"): step for step in scenario_value.get("steps", [])
            if isinstance(step, dict)
        }
        if scenario_value.get("gate_eligible") is not True:
            errors.append(f"Sub-GHz {modulation} scenario is not gate eligible")
        emission_id = "emit_ook" if modulation == "ook_envelope" else "emit_fsk"
        if sub_steps.get(emission_id, {}).get("command") != command:
            errors.append(
                f"Sub-GHz {modulation} scenario lacks exact bounded vector")
        for step_id, operation in (
                ("live_csv", "stream"), ("cold_reopen", "reboot"),
                ("library_metadata", "query"), ("library_csv", "stream")):
            if sub_steps.get(step_id, {}).get("op") != operation:
                errors.append(
                    f"Sub-GHz {modulation} scenario lacks {step_id}/{operation}")
        sub_limits = scenario_value.get("limits", {})
        for field, expected in (
                ("fixed_cc1101_vector", vector),
                ("fixture_source_bound", True),
                ("fixture_single_bounded_emission", True),
                ("fixture_minimum_chip_tx_power_dbm", -15),
                ("fixture_frequency_khz", 433920),
                ("fixture_hardware_auto_idle", True),
                ("fixture_maximum_emission_us", 250000),
                ("product_rx_only", True),
                ("successful_physical_signal_required", True),
                ("physical_persistence_exercised", True),
                ("cold_reopen_exercised", True),
                ("byte_exact_csv_compared", True)):
            if sub_limits.get(field) != expected:
                errors.append(
                    f"Sub-GHz {modulation} limit {field} is not {expected!r}")
        if scenario_value.get("invariants", {}).get(
                "byte_exact_streams") != ["live_csv", "library_csv"]:
            errors.append(
                f"Sub-GHz {modulation} lacks byte-exact persisted CSV proof")
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
            ("cc_identity_attempted", True),
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
        '"subghz-ook-positive"', '"subghz-fsk-positive"',
    ):
        if marker not in orchestrator:
            errors.append(f"two-board orchestrator missing guard: {marker}")
    if '"subghz-ook-positive"' not in subghz_ook_wrapper:
        errors.append("Sub-GHz OOK wrapper is not scenario-pinned")
    if '"subghz-fsk-positive"' not in subghz_fsk_wrapper:
        errors.append("Sub-GHz FSK wrapper is not scenario-pinned")
    for marker in (
        '"infrared-nec-positive"', '"nrf24-carrier-positive"',
        '"subghz-ook-positive"', '"subghz-fsk-positive"',
        '"building_once"', "index > 0", "accepted_child",
        '"candidate image identity drift across matrix"',
        '"fixture image identity drift across matrix"',
        '"status": "failed"', "require_clean_source",
        "--profile-fixture-read-only", "--reuse-exact-candidate-flash",
        "--reuse-exact-fixture-flash",
    ):
        if marker not in phase_orchestrator:
            errors.append(f"S5 matrix orchestrator missing guard: {marker}")
    if "profile.get(\"port_at_profile\") != fixture_port" not in runner:
        errors.append("HIL runner does not bind fixture profile to exact port")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("Bounded signal fixture contract passed: separate image, inactive "
          "boot, exact identity/session, fixed NEC, minimum-power nRF24, and "
          "finite minimum-power CC1101 vectors with bounded timeout and "
          "panic stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
