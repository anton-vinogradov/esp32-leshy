#!/usr/bin/env python3
"""Fail closed unless the bounded receive-only CC1101 FSK path is intact."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h"
ADAPTER_H = ROOT / "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.h"
ADAPTER_CPP = ROOT / "firmware/leshy1/src/platform/arduino/BoardCc1101PassiveSpectrum.cpp"
CAPTURE_H = ROOT / "firmware/leshy1/src/apps/capture/SubGhzRawCapture.h"
CAPTURE_CPP = ROOT / "firmware/leshy1/src/apps/capture/SubGhzRawCapture.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
CODEC = ROOT / "firmware/leshy1/src/storage/SessionCodec.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
RUNNER = ROOT / "tools/run_1x_subghz_fsk_delta_hil.py"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    profile = PROFILE.read_text(encoding="utf-8")
    header = ADAPTER_H.read_text(encoding="utf-8")
    adapter = ADAPTER_CPP.read_text(encoding="utf-8")
    capture_h = CAPTURE_H.read_text(encoding="utf-8")
    capture = CAPTURE_CPP.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    codec = CODEC.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    require(failures, "kCc1101Gdo0Pin = 6" in profile,
            "CC1101 GDO0 must stay on the photographed board GPIO6 route")
    require(failures, "kGpsDeclared = false" in profile,
            "GPIO6 route is unsafe unless the absent GPS remains excluded")

    for token in (
        "kAsyncEdgeCapacity = 512", "IRAM_ATTR captureAsyncEdge",
        "esp_timer_get_time()", "GPIO.in &", "kAsyncEdgeMask",
        "asyncEdgeOverflow = true", "asyncEdgeActive = false",
        "attachInterruptArg", "detachInterrupt", "CHANGE",
    ):
        require(failures, token in adapter,
                f"bounded ISR transport token missing: {token}")
    handler = re.search(
        r"void IRAM_ATTR captureAsyncEdge\(void\*\) \{(?P<body>.*?)\n\}",
        adapter, re.DOTALL)
    require(failures, handler is not None, "GDO0 ISR body not found")
    if handler is not None:
        body = handler.group("body")
        for forbidden in ("digitalRead", "delay", "SPI.", "Serial", "new ",
                          "malloc", "printf"):
            require(failures, forbidden not in body,
                    f"flash/blocking operation entered GDO0 ISR: {forbidden}")

    for token in (
        "{0x02, 0x0D}", "{0x08, 0x32}", "{0x12, 0x00}",
        "{0x15, 0x47}", "kCommandReset", "kCommandReceive",
        "kCommandIdle", "value != kCommandReset",
        "report_->txStrobes == 0U", "report_->paTableWrites == 0U",
        "report_->fifoWrites == 0U",
    ):
        require(failures, token in adapter,
                f"receive-only FSK adapter token missing: {token}")
    for forbidden in ("kCommandTransmit", "writeFifo", "writePaTable",
                      "transmit(", "replay("):
        require(failures, forbidden not in adapter and forbidden not in header,
                f"transmit capability is representable in FSK adapter: {forbidden}")

    for token in (
        "armFskEdges", "ingestFskEdge", "finishFskTransport",
        "minimumFskPulseUs", "kPulseCapacity = 512",
    ):
        require(failures, token in capture_h or token in capture,
                f"bounded FSK state-machine token missing: {token}")
    require(failures,
            "size_ >= plan_.maximumPulses || size_ >= pulses_.size()" in capture,
            "FSK capture lacks the common 512-event termination bound")

    for token in (
        "SubGhzCaptureModeMenu", "SubGhzRawFsk",
        "startAsyncEdgeCapture", "drainSubGhzFskEdgeTransport",
        "subGhzRawModulationName(",
    ):
        require(failures, token in entry or token in strings,
                f"product FSK workflow token missing: {token}")
    require(failures, "SubGhzActivateSensor" in strings and
            "SubGhzWaitTransmission" in strings,
            "FSK waiting/capturing copy is incomplete")
    require(failures, "SubGhzRawModulation::FskAsync" in codec and
            "subGhzRawModulationName" in codec,
            "FSK artifact persistence/summary support is incomplete")
    for token in (
        '"fsk_async"', '"ook_envelope"', '"scope": "delta"',
        '"full_matrix_run": False', "hil.begin", "hil.end",
        '"physical_fsk_edge_capture_proven": False',
        '"tx_or_replay_in_scope": False',
    ):
        require(failures, token in runner,
                f"one-flash delta runner contract missing: {token}")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "status": "pass",
        "mode": "fsk_async",
        "gdo0_gpio": 6,
        "edge_capacity": 512,
        "tx_api_surface": 0,
        "isr_flash_calls_by_source": 0,
        "persistence": "backward_compatible_additive",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
