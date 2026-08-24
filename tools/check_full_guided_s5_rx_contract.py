#!/usr/bin/env python3
"""Fail closed unless Full/Guided actively exercises the S5 RX adapters."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
CONTROLLER = ROOT / "firmware/leshy1/src/apps/self_test/SelfTestController.cpp"
HEADER = ROOT / "firmware/leshy1/src/apps/self_test/SelfTestController.h"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    entry = ENTRY.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    start = entry.index("void startFullGuidedRfChecks()")
    end = entry.index("void releaseWifiFrameCaptureRfLease()", start)
    active = entry[start:end]
    failures: list[str] = []

    require("kPlanVersion = 9" in header, "Self-Test plan is not v9", failures)
    require("kCapacity = 32" in header, "Self-Test report capacity drifted", failures)
    for check_id in (
        "full.shield.ir",
        "full.s5.capture.subghz.ook.receive",
        "full.s5.capture.subghz.fsk.receive",
    ):
        require(check_id in controller, f"missing check {check_id}", failures)

    for step in ("SubGhzOokReceive", "SubGhzFskReceive", "InfraredReceive"):
        require(step in entry, f"missing active step {step}", failures)
    require("kFullGuidedReceiveSamples = 32" in entry,
            "Sub-GHz sample ceiling drifted", failures)
    require("kFullGuidedInfraredSamples = 64" in entry,
            "IR sample ceiling drifted", failures)
    require("SubGhzRawModulation::OokEnvelope" in active and
            "SubGhzRawModulation::FskAsync" in active,
            "both CC1101 receive modes are not exercised", failures)
    for call in (
        "boardCc1101Spectrum.lockReceive(",
        "boardCc1101Spectrum.sampleRssi(",
        "boardCc1101Spectrum.startAsyncEdgeCapture(",
        "boardCc1101Spectrum.popAsyncEdge(",
        "boardCc1101Spectrum.takeAsyncEdgeOverflow(",
        "boardCc1101Spectrum.stopAsyncEdgeCapture(",
        "boardInfraredReceiver.begin(",
        "boardInfraredReceiver.sample(",
        "boardInfraredReceiver.end(",
    ):
        require(call in active, f"missing active adapter call {call}", failures)
    for fact in (
        "facts.subGhzOokExerciseComplete",
        "facts.subGhzFskExerciseComplete",
        "facts.infraredReceiverExerciseComplete",
    ):
        require(fact in entry, f"missing report fact {fact}", failures)
    for forbidden in ("STX", "kCommandTransmit", "writeTx", "flushTx"):
        require(forbidden not in active,
                f"transmit surface leaked into Full/Guided: {forbidden}",
                failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Full/Guided S5 RX contract passed: bounded OOK/FSK/IR adapters, "
          "FSK ISR drain, mandatory cleanup and no TX surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
