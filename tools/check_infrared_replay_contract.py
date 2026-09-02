#!/usr/bin/env python3
"""Fail closed if product IR replay loses its bounded safety contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_HEADER = ROOT / "firmware/leshy1/src/apps/lab/InfraredReplay.h"
CONTROLLER_SOURCE = ROOT / "firmware/leshy1/src/apps/lab/InfraredReplay.cpp"
ADAPTER_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardInfraredTransmitter.h"
)
ADAPTER_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardInfraredTransmitter.cpp"
)
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
TESTS = ROOT / "tests/native/infrared_replay_tests.cpp"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def compact(value: str) -> str:
    without_comments = re.sub(
        r"/\*.*?\*/|//[^\n]*", "", value, flags=re.DOTALL
    )
    return re.sub(r"\s+", "", without_comments)


def main() -> int:
    failures: list[str] = []
    try:
        controller = (
            CONTROLLER_HEADER.read_text(encoding="utf-8")
            + CONTROLLER_SOURCE.read_text(encoding="utf-8")
        )
        adapter = (
            ADAPTER_HEADER.read_text(encoding="utf-8")
            + ADAPTER_SOURCE.read_text(encoding="utf-8")
        )
        entry = ENTRY.read_text(encoding="utf-8")
        strings = STRINGS.read_text(encoding="utf-8")
        tests = TESTS.read_text(encoding="utf-8")
    except OSError as error:
        print(f"infrared replay contract check failed: {error}", file=sys.stderr)
        return 1

    controller_compact = compact(controller)
    adapter_compact = compact(adapter)
    entry_compact = compact(entry)

    for marker in (
        "kInfraredReplayCarrierHz = 38000U",
        "kInfraredReplayDutyPercent = 33U",
        "kInfraredReplayMaximumEmissionUs = 100000U",
        "kInfraredReplayPulseCount = 67U",
        "InfraredProtocol::Nec",
        "InfraredProtocol::NecExtended",
        "NotPersistent",
        "Simulated",
        "RecoveredFallback",
        "GenerationMissing",
        "Truncated",
        "IntegrityInvalid",
        "CodeInvalid",
        "requestConfirmation",
        "cancelConfirmation",
        "confirmAndStart",
        "deadlineExpired = true",
        "output.stop()",
        "output.inactive()",
    ):
        require(failures, marker in controller,
                f"missing bounded controller contract: {marker}")

    for forbidden in (
        "source.raw",
        "pulseDurationsUs = source",
        "rawDurations",
        "repeatCount",
        "loopCount",
        "while(true)",
    ):
        require(failures, forbidden.replace(" ", "") not in controller_compact,
                f"controller permits unbounded/raw replay: {forbidden}")

    for marker in (
        "BoardProfile::kIrTxPin",
        "BoardProfile::kRfShieldDeclared",
        "BoardProfile::kIrDeclared",
        "trans_queue_depth = 1U",
        "transmit.loop_count = 0",
        "transmit.flags.eot_level = 0U",
        "queue_nonblocking = 1U",
        "BoardSafeOutputs::emergencyQuiesce()",
        "admittedRadioSpi_",
        "admittedSafety_",
        "rmt_tx_wait_all_done",
        "digitalWrite(BoardProfile::kIrTxPin, LOW)",
    ):
        require(failures, marker in adapter,
                f"missing board fail-safe contract: {marker}")
    require(failures, "rmt_transmit(" in adapter,
            "board adapter has no explicit one-shot transmit")
    require(failures, "rmt_write_sample" not in adapter_compact,
            "board adapter gained an unreviewed raw sample path")

    for marker in (
        "kInfraredReplayPage = 18",
        "libraryDetailActionCount()",
        "libraryDetailActionSelection == 1U",
        "openSelectedInfraredReplay()",
        "selected->generation == sessionStoreWorkspace().generation",
        "Resource::RadioSpi",
        "DeviceLockOperation::ProtectedUi",
        "InfraredReplayState::Confirmation",
        "quiesceInfraredReplayOnSafetyStop()",
        "serviceInfraredReplay()",
        "renderInfraredReplayPage(clearContent)",
    ):
        require(failures, marker.replace(" ", "") in entry_compact,
                f"missing product workflow contract: {marker}")
    for marker in (
        "LibraryActionReplay",
        "IrReplayOwnership",
        "IrReplayConfirmHint",
        "IrReplayOutputSafe",
        "NavSend",
    ):
        require(failures, marker in strings,
                f"missing user-facing replay text: {marker}")

    for marker in (
        "buildsCanonicalNecPlans",
        "rejectsInvalidDecodes",
        "refusesUnsafeSources",
        "requiresPreviewAndExplicitConfirmation",
        "stopAndDeadlineAlwaysQuiesceOutput",
        "failsClosedWhenOutputCannotStartOrStop",
    ):
        require(failures, marker in tests,
                f"missing replay regression: {marker}")

    if failures:
        print("infrared replay contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Infrared replay contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
