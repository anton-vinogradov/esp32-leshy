#!/usr/bin/env python3
"""Fail closed when product screens regress to developer-facing telemetry."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"


REQUIRED_OUTCOME_IDS = {
    "NoteWifiReady",
    "NoteBleReady",
    "NoteSpectrum24",
    "NoteSubGhz",
    "NoteCaptureReady",
    "NoteLibraryReady",
    "CaptureWifiPurpose",
    "CapturePacketsFormat",
    "IrAimDevice",
    "IrSignalDetected",
    "SubGhzPressButton",
    "SubGhzSignalRecorded",
    "SurveyFoundFormat",
    "SurveySearchWifi",
    "SurveySearchBle",
    "LibraryWifiScan",
    "LibraryBleScan",
    "LibraryWifiCapture",
    "LibrarySubGhzCapture",
    "LibraryInfraredCapture",
}

# These remain valid in diagnostics/USB evidence, but they must not be rendered
# on product screens. Their catalog entries are retained for historical evidence
# compatibility until a later catalog compaction.
FORBIDDEN_RENDER_IDS = {
    "CaptureSource",
    "CaptureChannels",
    "CaptureLimit",
    "CaptureSnaplen",
    "CaptureBytesFormat",
    "CaptureDropsFormat",
    "CaptureScrubNote",
    "IrReceiver",
    "IrTimeout",
    "IrMode",
    "IrSafety",
    "IrPulsesFormat",
    "IrSamplingFormat",
    "IrCaptureNote",
    "IrNoSignalNote",
    "IrUnreliableNote",
    "SubGhzRawThresholdFormat",
    "SubGhzRawPulsesFormat",
    "SubGhzRawSamplesFormat",
    "SubGhzRawFskLater",
    "FifoNoRf",
    "FifoRxOnly",
    "FifoFormat",
    "PipelineFormat",
    "GenerationFormat",
    "FrequencyFormat",
    "LibraryRowFormat",
    "LibraryCaptureRowFormat",
    "LibraryRawRowFormat",
    "IntegrityFormat",
    "TimelineStoredFormat",
    "TimelineDutyFormat",
    "TransportSerial",
    "CaptureImmutable",
    "BleDeviceSeenFormat",
    "WifiNetworkSamplesFormat",
    "WifiDeviceFramesFormat",
}

REQUIRED_DENSE_DETAIL_IDS = {
    "RadioSignalLabel",
    "RadioSignalExcellent",
    "RadioSignalGood",
    "RadioSignalWeak",
    "RadioSignalVeryWeak",
    "RadioSignalDbmFormat",
    "RadioSignalScaleWeak",
    "RadioSignalScaleStrong",
    "WifiNetworkRadioFormat",
    "WifiNetworkSecurityFormat",
    "WifiNetworkVendorFormat",
}


def main() -> int:
    renderer = RENDERER.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    failures: list[str] = []

    for identifier in sorted(REQUIRED_OUTCOME_IDS):
        if f"LESHY_UI_TEXT({identifier}," not in strings:
            failures.append(f"missing outcome-oriented string: {identifier}")
        if f"UiTextId::{identifier}" not in renderer:
            failures.append(f"outcome-oriented string is not rendered: {identifier}")

    for identifier in sorted(FORBIDDEN_RENDER_IDS):
        if re.search(rf"UiTextId::{re.escape(identifier)}\b", renderer):
            failures.append(f"developer-facing field rendered: {identifier}")

    for identifier in sorted(REQUIRED_DENSE_DETAIL_IDS):
        if f"LESHY_UI_TEXT({identifier}," not in strings:
            failures.append(f"missing dense detail string: {identifier}")
        if f"UiTextId::{identifier}" not in renderer:
            failures.append(f"dense detail string is not rendered: {identifier}")

    if renderer.count("void renderRadioSignalCard(") != 1 or \
            renderer.count("renderRadioSignalCard(") < 3 or \
            renderer.count("void renderRadioSignalCardDelta(") != 1 or \
            renderer.count("renderRadioSignalCardDelta(") < 2:
        failures.append(
            "radio details must share one full signal card and one bounded "
            "delta renderer"
        )

    for internal in (
        "capturePersistStatus",
        "infraredCapturePersistStatus",
        "subGhzCapturePersistStatus",
    ):
        display_path = re.search(
            rf"display\.print\([^;]*{re.escape(internal)}[^;]*\);", renderer,
            re.DOTALL,
        )
        if display_path:
            failures.append(f"internal persistence status rendered: {internal}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(
        "product UI content contract passed: outcomes/actions visible; "
        "developer telemetry kept off product screens; radio details use the "
        "shared user-facing signal card"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
