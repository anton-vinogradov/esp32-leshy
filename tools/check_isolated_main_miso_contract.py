#!/usr/bin/env python3
"""Static and oracle checks for the no-carrier GPIO13 diagnostic path."""

from __future__ import annotations

import json
from pathlib import Path

from run_1x_shield_receiver_probe_crosscheck import (
    isolated_main_outcome,
    probe_contract_failures,
)


ROOT = Path(__file__).resolve().parents[1]


def isolated_report(down: int, up: int) -> dict:
    return {
        "schema_version": 1,
        "status": "failed",
        "read_only": True,
        "profile_declared": True,
        "gps_excluded_by_profile": True,
        "pn532_excluded_by_profile": True,
        "nrf_slot3_gated": True,
        "gpio21_stable_high": False,
        "resource_acquired": True,
        "resource_released": True,
        "cleanup_complete": False,
        "detected_receivers": 0,
        "bus_line": {
            "complete": False,
            "samples_per_pull": 32,
            "idle_pull_down_high_samples": down,
            "idle_pull_up_high_samples": up,
            "nrf_nop": [
                {"slot": 1, "pull_down_status": 0xFF,
                 "pull_up_status": 0xFF},
                {"slot": 2, "pull_down_status": 0xFF,
                 "pull_up_status": 0xFF},
            ],
            "nrf_nop_reads": 0,
            "bitbang_spi_bytes_clocked": 0,
        },
        "wire": {
            "nrf_register_reads": 0,
            "cc_status_reads": 0,
            "spi_bytes_clocked": 0,
        },
        "side_effects": {
            "nrf_ce_high_events": 0,
            "cc_command_strobes": 0,
            "radio_tx_commands": 0,
        },
        "current_owner": "device",
        "current_lease_mask": 1,
    }


def main() -> int:
    source = (ROOT / "firmware/leshy1/src/platform/arduino/"
              "BoardShieldReceiverProbe.cpp").read_text(encoding="utf-8")
    platform = (ROOT / "firmware/leshy1/platformio.ini").read_text(
        encoding="utf-8")

    characterize = source.split(
        "void BoardShieldReceiverProbe::characterizeBusLine()", 1)[1].split(
            "std::uint8_t BoardShieldReceiverProbe::transfer", 1)[0]
    down_at = characterize.index("sampleMisoHigh(INPUT_PULLDOWN)")
    up_at = characterize.index("sampleMisoHigh(INPUT_PULLUP)")
    carrier_guard_at = characterize.index("if (!gpio21Safe()) return;")
    nop_at = characterize.index("readNrfNopBitBang")
    assert down_at < up_at < carrier_guard_at < nop_at

    run_body = source.split(
        "bool BoardShieldReceiverProbe::run", 1)[1]
    characterize_at = run_body.index("characterizeBusLine();")
    assembled_guard_at = run_body.index(
        "if (!report_->busLineCharacterizationComplete || !gpio21Safe())")
    assert characterize_at < assembled_guard_at
    assert 'LESHY1_VERSION=\\"0.131.0-isolated-main-miso\\"' in platform

    healthy = isolated_report(0, 32)
    assert not probe_contract_failures(
        healthy, require_isolated_main_characterization=True)
    assert isolated_main_outcome(healthy) == "isolated_main_gpio_follows_pulls"
    assert isolated_main_outcome(isolated_report(0, 0)) == (
        "isolated_main_gpio_stuck_low")
    assert isolated_main_outcome(isolated_report(32, 32)) == (
        "isolated_main_gpio_stuck_high")
    assert isolated_main_outcome(isolated_report(3, 29)) == (
        "isolated_main_gpio_unstable")

    unsafe = isolated_report(0, 32)
    unsafe["wire"]["spi_bytes_clocked"] = 1
    assert probe_contract_failures(
        unsafe, require_isolated_main_characterization=True)
    unsafe = isolated_report(0, 32)
    unsafe["side_effects"]["nrf_ce_high_events"] = 1
    assert probe_contract_failures(
        unsafe, require_isolated_main_characterization=True)

    evidence = json.loads((
        ROOT / "tests/hil/evidence/board-02-isolated-main-miso-0.131.json"
    ).read_text(encoding="utf-8"))
    assert evidence["schema"] == (
        "leshy.hardware.isolated_main_miso_evidence.v1")
    assert evidence["status"] == (
        "retained_fault_localized_to_rf_carrier")
    assert evidence["candidate"]["version"] == (
        "0.131.0-isolated-main-miso")
    assert evidence["exact_run"]["passed"] is True
    assert evidence["exact_run"]["raw_runner_outcome"] == (
        "isolated_main_gpio_stuck_high")
    assert evidence["exact_run"]["idle_miso_high_samples"] == {
        "pulldown": 32,
        "pullup": 32,
        "samples_per_pull": 32,
    }
    assert all(
        value == 0
        for value in evidence["exact_run"]["receiver_operations"].values()
    )
    assert all(
        value == 0
        for value in evidence["exact_run"]["side_effects"].values()
    )
    assert evidence["comparison"][
        "assembled_exact_0_130_miso_high_samples"] == {
            "pulldown": 0,
            "pullup": 0,
            "samples_per_pull": 32,
        }
    assert evidence["comparison"][
        "isolated_exact_0_131_miso_high_samples"] == {
            "pulldown": 32,
            "pullup": 32,
            "samples_per_pull": 32,
        }
    assert evidence["comparison"][
        "state_changes_when_rf_carrier_removed"] is True
    assert evidence["assessment"][
        "rf_carrier_or_its_connector_side_is_low_source_supported"] is True
    assert evidence["assessment"][
        "main_board_only_gpio13_stuck_low_supported"] is False
    assert evidence["assessment"]["rf_emission_allowed"] is False
    assert evidence["assessment"]["shield_cross_swap_allowed"] is False
    assert evidence["limits"]["stage_or_phase_promoted"] is False

    print(
        "isolated-main MISO contract/evidence passed: carrier-side LOW, "
        "pull-only, zero SPI/TX"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
