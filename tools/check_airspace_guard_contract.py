#!/usr/bin/env python3
"""Fail closed if the passive Airspace Guard foundation gains side effects."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/services/guard/AirspaceGuard.h"
SOURCE = ROOT / "firmware/leshy1/src/services/guard/AirspaceGuard.cpp"
TEST = ROOT / "tests/native/airspace_guard_tests.cpp"
CONTROLLER_HEADER = (
    ROOT / "firmware/leshy1/src/apps/guard/AirspaceGuardController.h"
)
CONTROLLER_SOURCE = (
    ROOT / "firmware/leshy1/src/apps/guard/AirspaceGuardController.cpp"
)
CONTROLLER_TEST = ROOT / "tests/native/airspace_guard_controller_tests.cpp"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        tests = TEST.read_text(encoding="utf-8")
        controller_header = CONTROLLER_HEADER.read_text(encoding="utf-8")
        controller_source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
        controller_tests = CONTROLLER_TEST.read_text(encoding="utf-8")
    except OSError as error:
        print(f"airspace guard contract check failed: {error}", file=sys.stderr)
        return 1

    combined = header + source
    for marker in (
        "kFrameInspectionCapacity = 64",
        "kEvidenceCapacity = 8",
        "kDetectorVersion = 1",
        "disconnectBurstThreshold = 4",
        "disconnectWindowUs = 2000000ULL",
        "WifiFrameSource& source",
        "frameIndex = event.frameIndex",
        "DisconnectDecode::Malformed",
        "AirspaceGuardStatus::Inconclusive",
        "subtype != 10U && subtype != 12U",
    ):
        require(failures, marker in combined,
                f"missing passive detector contract: {marker}")

    for marker in (
        "testPolicyAndEmptyEvidenceFailClosed",
        "testBenignAndSparseDisconnectFramesStayClear",
        "testDisconnectBurstRetainsExactEvidence",
        "testSourcesAreNeverMergedAndConfidenceIsBounded",
        "testMalformedFailedAndTruncatedEvidenceIsInconclusive",
    ):
        require(failures, marker in tests,
                f"missing Airspace Guard native coverage: {marker}")

    for forbidden in (
        '#include "drivers/',
        '#include "platform/',
        '#include "kernel/',
        "ResourceBroker",
        "esp_wifi",
        "esp_ble",
        "NimBLE",
        "WIFI_MODE",
        "sendPacket",
        "injectFrame",
        "setTxPower",
    ):
        require(failures, forbidden not in combined,
                f"Airspace Guard bypasses receive-evidence boundary: {forbidden}")

    controller = controller_header + controller_source
    for marker in (
        "AirspaceGuardView::Finding",
        "AirspaceGuardView::EvidenceList",
        "AirspaceGuardView::EvidenceDetail",
        "comesBefore",
        "evidenceIncomplete",
        "AirspaceGuardLoadStatus::InvalidReport",
        "findingOrder_",
    ):
        require(failures, marker in controller,
                f"missing Airspace Guard user-flow contract: {marker}")
    for marker in (
        "testStrongestFindingOpensFirstAndOrderIsStable",
        "testEvidenceDrilldownUsesExactSourceReference",
        "testIncompleteEvidenceRemainsVisibleUncertainty",
        "testClearAndInconclusiveStayOutcomeOnly",
        "testMalformedReportsFailClosed",
    ):
        require(failures, marker in controller_tests,
                f"missing Airspace Guard controller coverage: {marker}")
    for forbidden in (
        '#include "drivers/',
        '#include "platform/',
        '#include "kernel/',
        "ResourceBroker",
        "esp_wifi",
        "esp_ble",
        "NimBLE",
        "sendPacket",
        "injectFrame",
        "setTxPower",
    ):
        require(failures, forbidden not in controller,
                f"Airspace Guard UI bypasses passive boundary: {forbidden}")

    if failures:
        print("airspace guard contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Airspace Guard passive contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
