#!/usr/bin/env python3
"""Fail closed unless the 2.4 GHz signal-finder source contract is present."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    header = (ROOT / "firmware/leshy1/src/apps/spectrum/"
              "Nrf24SignalFinder.h").read_text(encoding="utf-8")
    source = (ROOT / "firmware/leshy1/src/apps/spectrum/"
              "Nrf24SignalFinder.cpp").read_text(encoding="utf-8")
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/"
             "ArduinoEntry.cpp").read_text(encoding="utf-8")
    strings = (ROOT / "firmware/leshy1/src/ui/UiStrings.def").read_text(
        encoding="utf-8")
    tests = (ROOT / "tests/native/clean_target_tests.cpp").read_text(
        encoding="utf-8")

    for token in (
            "kSweepsPerWindow = 48", "kCalibrationWindows = 2",
            "kDetectionRise = 8", "std::array<std::uint8_t, kChannelCount>",
            "bool ingest(", "bool restart(", "nearestWifiChannel"):
        require(token in header, f"finder header contract missing: {token}")
    for token in (
            "accumulated_[index] < baseline_[index]", "totalDelta",
            "- meanDelta", "heldRise_[index] - kHoldDecay"):
        require(token in source, f"ambient/local-rise contract missing: {token}")
    for token in (
            "Nrf24Menu", "Nrf24Finder", "renderNrf24FinderGraph(false)",
            "hardware.nrf24.finder", r"all_available_antennas\":true",
            "tx_payload_commands", r"storage_writes\":0"):
        require(token in entry, f"product/diagnostic contract missing: {token}")
    for token in (
            "Nrf24Overview", "Nrf24FinderWaiting", "Nrf24FinderFound",
            "NavAgain"):
        require(token in strings, f"user string missing: {token}")
    require("testNrf24SignalFinderLearnsFloorAndFindsOnlyLocalRise" in tests,
            "deterministic found-branch test missing")
    for forbidden in ("startListening", "writePayload", "openWritingPipe"):
        require(forbidden not in source,
                f"signal finder contains active/TX token: {forbidden}")
    print("PASS: nRF24 signal finder is passive, bounded and product-routable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
