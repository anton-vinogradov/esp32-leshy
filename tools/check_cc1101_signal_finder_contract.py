#!/usr/bin/env python3
"""Fail closed if the Sub-GHz frequency-finder product contract drifts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.cpp"
HEADER = ROOT / "firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.h"
BOARD = ROOT / "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
TESTS = ROOT / "tests/native/clean_target_tests.cpp"
PLATFORM = ROOT / "firmware/leshy1/platformio.ini"


def require(blob: bytes, tokens: tuple[bytes, ...], label: str) -> None:
    missing = [token.decode("utf-8", "replace") for token in tokens
               if token not in blob]
    if missing:
        raise SystemExit(f"{label}: missing {missing}")


def main() -> int:
    app = APP.read_bytes()
    header = HEADER.read_bytes()
    board = BOARD.read_bytes()
    entry = ENTRY.read_bytes()
    strings = STRINGS.read_bytes()
    tests = TESTS.read_bytes()
    platform = PLATFORM.read_bytes()

    require(header, (
        b"kStepKHz = 250", b"kBinCount = 1099",
        b"kCalibrationPasses = 2", b"kDetectionRiseDb = 18",
        b"std::array<std::int8_t, kBinCount> baseline_",
        b"std::array<std::uint8_t, kBinCount> heldRise_",
    ), "bounded finder")
    require(app, (
        b"{300000U, 348000U}", b"{387000U, 464000U}",
        b"{779000U, 928000U}", b"sample < baseline_[nextBin_]",
        b"meanDelta", b"kHoldDecayDb", b"433 ISM", b"915 ISM",
    ), "finder algorithm")
    require(board, (
        b"BoardCc1101PassiveSpectrum::sampleFrequency",
        b"sampleAtFrequency(receivePlan, frequencyKHz",
        b"validateCc1101PassiveSpectrumReport",
    ), "RX adapter")
    require(entry, (
        b"RfSpectrumView::CcFinder", b"startCc1101Finder()",
        b"serviceCc1101Finder()", b"stopCc1101Finder()",
        b"renderCcFinderPage", b"renderCcFinderGraph",
        b"hardware.cc1101.finder",
        b"leshy.cc1101.signal-finder.v1",
        b"minimum_of_two_ambient_sweeps",
        b"local_rssi_rise_after_common_drift",
        b"storage_writes\\\":0",
    ), "product route and diagnostics")
    require(strings, (
        b"LESHY_UI_TEXT(CcFinder,", b"FIND FREQUENCY",
        "НАЙТИ ЧАСТОТУ".encode(), b"LESHY_UI_TEXT(CcFinderResponse,",
    ), "EN/RU UI")
    require(tests, (
        b"testCc1101SignalFinderCoversWindowsAndRejectsAmbientDrift",
        b"targetFrequencyKHz = 433250U",
        b"uniform one-dB ambient shift is common drift",
    ), "native proof")
    require(platform, (
        b'LESHY1_VERSION=\\"0.124.0-cc1101-frequency-finder\\"',
    ), "exact version")

    sample = board.split(
        b"BoardCc1101PassiveSpectrum::sampleFrequency", 1)[1].split(
        b"BoardCc1101PassiveSpectrum::lockReceive", 1)[0]
    forbidden = (b"kCommandTransmit", b"paTable", b"fifo", b"STX")
    present = [token.decode() for token in forbidden if token in sample]
    if present:
        raise SystemExit(f"RX finder exposes transmit semantics: {present}")

    render = entry.split(b"void renderCcFinderResult", 1)[1].split(
        b"void formatCcFrequency", 1)[0]
    telemetry = (b"samples", b"sweeps", b"registerReads",
                 b"commandStrobes", b"heap")
    leaked = [token.decode() for token in telemetry if token in render]
    if leaked:
        raise SystemExit(f"product screen leaks implementation telemetry: {leaked}")

    print("PASS: CC1101 frequency finder is full-window, bounded, RX-only and product-routable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
