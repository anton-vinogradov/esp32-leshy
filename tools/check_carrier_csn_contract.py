#!/usr/bin/env python3
"""Static and oracle checks for the read-only RF-carrier CSN diagnostic."""

from __future__ import annotations

from pathlib import Path

from run_1x_shield_receiver_probe_crosscheck import (
    carrier_csn_outcome,
    probe_contract_failures,
)


ROOT = Path(__file__).resolve().parents[1]


def carrier_report(
    nrf: tuple[int, int, int] = (32, 32, 32),
    cc: int = 32,
    miso: tuple[int, int] = (0, 0),
) -> dict:
    return {
        "schema_version": 1,
        "status": "failed",
        "read_only": True,
        "profile_declared": True,
        "gps_excluded_by_profile": True,
        "pn532_excluded_by_profile": True,
        "nrf_slot3_gated": True,
        "gpio21_stable_high": nrf[2] == 32,
        "resource_acquired": True,
        "resource_released": True,
        "cleanup_complete": nrf[2] == 32,
        "detected_receivers": 0,
        "bus_line": {
            "complete": False,
            "samples_per_pull": 32,
            "idle_pull_down_high_samples": miso[0],
            "idle_pull_up_high_samples": miso[1],
            "nrf_nop": [
                {"slot": 1, "pull_down_status": 0xFF,
                 "pull_up_status": 0xFF},
                {"slot": 2, "pull_down_status": 0xFF,
                 "pull_up_status": 0xFF},
            ],
            "nrf_nop_reads": 0,
            "bitbang_spi_bytes_clocked": 0,
        },
        "chip_selects": {
            "complete": True,
            "samples_per_pin": 32,
            "nrf": [
                {"slot": 1, "gpio": 4,
                 "pull_up_high_samples": nrf[0]},
                {"slot": 2, "gpio": 48,
                 "pull_up_high_samples": nrf[1]},
                {"slot": 3, "gpio": 21,
                 "pull_up_high_samples": nrf[2]},
            ],
            "cc1101": {"gpio": 5, "pull_up_high_samples": cc},
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
    header = (ROOT / "firmware/leshy1/src/drivers/radio/"
              "ShieldReceiverIdentity.h").read_text(encoding="utf-8")
    profile = (ROOT / "firmware/leshy1/src/boards/esp32_div_v2/"
               "BoardProfile.h").read_text(encoding="utf-8")
    platform = (ROOT / "firmware/leshy1/platformio.ini").read_text(
        encoding="utf-8")

    assert "kRfCarrierChipSelectCharacterizationOnly = true" in profile
    assert 'LESHY1_VERSION=\\"0.132.0-carrier-csn-characterization\\"' in (
        platform)
    assert "chipSelectCharacterizationComplete" in header
    assert "std::array<std::uint8_t, 3> nrfCsnPullUpHighSamples" in header

    characterize = source.split(
        "void BoardShieldReceiverProbe::characterizeChipSelectLines()", 1
    )[1].split(
        "std::uint8_t BoardShieldReceiverProbe::readNrfNopBitBang", 1)[0]
    assert "digitalWrite(pin, LOW)" not in characterize
    assert "digitalWrite(BoardProfile::kNrfCePins" not in characterize
    assert "samplePinHigh(pin, INPUT_PULLUP)" in characterize
    assert "GPIO21 is also the IR receiver output" in characterize

    bus = source.split(
        "void BoardShieldReceiverProbe::characterizeBusLine()", 1
    )[1].split(
        "std::uint8_t BoardShieldReceiverProbe::transfer", 1)[0]
    miso_at = bus.index("sampleMisoHigh(INPUT_PULLUP)")
    gate_at = bus.index("kRfCarrierChipSelectCharacterizationOnly")
    nop_at = bus.index("readNrfNopBitBang")
    assert miso_at < gate_at < nop_at

    run = source.split("bool BoardShieldReceiverProbe::run", 1)[1]
    csn_at = run.index("characterizeChipSelectLines();")
    bus_at = run.index("characterizeBusLine();")
    exit_at = run.index("kRfCarrierChipSelectCharacterizationOnly")
    spi_at = run.index("SPI.begin(")
    assert csn_at < bus_at < exit_at < spi_at

    healthy = carrier_report()
    assert not probe_contract_failures(
        healthy, require_carrier_csn_characterization=True)
    assert carrier_csn_outcome(healthy) == "carrier_csn_high_miso_low"
    assert carrier_csn_outcome(carrier_report(miso=(32, 32))) == (
        "carrier_csn_high_miso_high")
    assert carrier_csn_outcome(carrier_report(miso=(0, 32))) == (
        "carrier_csn_high_miso_follows_pulls")
    assert carrier_csn_outcome(carrier_report(nrf=(32, 0, 32))) == (
        "carrier_csn_stuck_low")
    assert carrier_csn_outcome(carrier_report(cc=17)) == (
        "carrier_csn_unstable")
    assert probe_contract_failures(
        carrier_report(cc=17),
        require_carrier_csn_characterization=True)

    unsafe = carrier_report()
    unsafe["wire"]["spi_bytes_clocked"] = 1
    assert probe_contract_failures(
        unsafe, require_carrier_csn_characterization=True)
    unsafe = carrier_report()
    unsafe["side_effects"]["radio_tx_commands"] = 1
    assert probe_contract_failures(
        unsafe, require_carrier_csn_characterization=True)

    print("carrier CSN contract passed: four pull-up lines, zero SPI/TX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
