#!/usr/bin/env python3
"""Fail closed if the first S6.5 companion boundary drifts."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/services/companion/CompanionProtocol.h"
SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionProtocol.cpp"
TEST = ROOT / "tests/native/companion_protocol_tests.cpp"
READ_HEADER = ROOT / "firmware/leshy1/src/services/companion/CompanionReadAdapter.h"
READ_SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionReadAdapter.cpp"
READ_TEST = ROOT / "tests/native/companion_read_adapter_tests.cpp"
ARDUINO = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
ACTION = ROOT / "firmware/leshy1/src/services/targets/TargetComparisonService.cpp"
DOCS = (
    ROOT / "docs/v1/COMPANION_PROTOCOL.md",
    ROOT / "docs/v1/COMPANION_PROTOCOL.ru.md",
)


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        tests = TEST.read_text(encoding="utf-8")
        read_header = READ_HEADER.read_text(encoding="utf-8")
        read_source = READ_SOURCE.read_text(encoding="utf-8")
        read_tests = READ_TEST.read_text(encoding="utf-8")
        arduino = ARDUINO.read_text(encoding="utf-8")
        action = ACTION.read_text(encoding="utf-8")
        docs = [path.read_text(encoding="utf-8") for path in DOCS]
    except OSError as error:
        print(f"companion contract check failed: {error}", file=sys.stderr)
        return 1

    for marker in (
        "kCompanionProtocolVersion = 1",
        "kCompanionMaxFrameBytes = 512",
        '"leshy.companion.request.v1"',
        '"leshy.companion.response.v1"',
        "kCompanionS65ReadScopes",
        "parseCompanionConnectRequest",
        "negotiateCompanionConnection",
        "encodeCompanionConnectResponse",
    ):
        require(failures, marker in header, f"missing header contract: {marker}")

    for scope in (
        "session.read",
        "target.read",
        "target.compare",
        "target.mutate",
        "library.export",
        "connectivity.manage",
    ):
        require(failures, f'"{scope}"' in source,
                f"missing stable scope: {scope}")
        for path, text in zip(DOCS, docs):
            require(failures, f"`{scope}`" in text,
                    f"{path.name} omits scope {scope}")

    for capability in (
        "session.list",
        "session.detail",
        "target.list",
        "target.detail",
        "target.compare",
    ):
        require(failures, f'"{capability}"' in source,
                f"missing truthful capability: {capability}")

    require(failures, '"target.compare", 1, 1' in action,
            "companion target.compare must match the existing typed Action")
    require(failures,
            '"target.compare", CompanionCapability::TargetCompare' in source and
            '"target.compare", 1, 1, true' in source,
            "companion capability does not bind target.compare schemas v1")
    require(failures,
            "request.requestedScopes & ~policy.deviceSessionScopes" in source and
            "request.requestedScopes & ~policy.availableScopes" in source,
            "scope negotiation must intersect explicit device and availability masks")
    require(failures, "connection.grantedScopes = request.requestedScopes" in source,
            "successful negotiation must grant exactly the requested mask")
    require(failures,
            "policy.availableCapabilities & kCompanionKnownCapabilities" in source,
            "scope grant must not invent an unwired capability")
    require(failures, "std::array<char, kCompanionMaxFrameBytes + 1U> encoded" in source,
            "response must stage into a bounded buffer before publication")

    combined = header + source
    for forbidden in (
        '#include "drivers/',
        '#include "storage/',
        '#include "platform/',
        "Serial.",
        "SPI.",
        "SD.",
        "WiFi.",
    ):
        require(failures, forbidden not in combined,
                f"companion envelope bypasses its boundary: {forbidden}")

    read_combined = read_header + read_source
    for forbidden in (
        '#include "drivers/',
        '#include "storage/',
        '#include "platform/',
        "Serial.",
        "SPI.",
        "SD.",
        "WiFi.",
    ):
        require(failures, forbidden not in read_combined,
                f"companion read adapter bypasses its boundary: {forbidden}")
    for marker in (
        "CompanionReadContext",
        "TargetCatalog* targets",
        "TargetComparisonResult* comparison",
        "parseCompanionReadRequest",
        "encodeCompanionReadResponse",
        "session.list",
        "session.detail",
        "target.list",
        "target.detail",
        "target.compare",
        "next_offset",
        "OffsetOutOfRange",
    ):
        require(failures, marker in read_combined,
                f"missing read adapter contract: {marker}")
    for marker in (
        "testEveryTruncatedFrameIsRejected",
        "testAllReadOnlyProjectionsStayBounded",
        "testAuthorizationAndExactCoordinatesFailClosed",
        "testAllOrNothingEncodingAndParseErrors",
        "offset_out_of_range",
    ):
        require(failures, marker in read_tests,
                f"missing read adapter native coverage: {marker}")

    for marker in (
        "handleUsbCompanionFrame",
        "companionReadContext",
        'uiController.page() != 7',
        'std::strcmp(targetsProductStatus, "ready") != 0',
        "policy.availableCapabilities = capabilities",
        "usbCompanionConnection = {}",
        "kUsbCommandCapacity",
        "Serial.setRxBufferSize(kUsbRxBufferCapacity)",
        "usbCommandOverflow",
        "response_encoding_failed",
        "targetsIdentityTransientRetries",
        "poll(Serial, usbCommand",
        "poll(Serial0, uartCommand",
    ):
        require(failures, marker in arduino,
                f"missing native USB wiring contract: {marker}")
    require(failures,
            "sizeof(usbCommand), true" in arduino and
            "sizeof(uartCommand), false" in arduino,
            "companion JSON must be enabled only on native USB, not Serial0")
    require(failures, "handleUsbCompanionFrame(Serial0" not in arduino,
            "Serial0 must never enter the companion transport")

    for marker in (
        "testEveryTruncatedFrameIsRejected",
        "testParserFailsClosedWithoutPublishingPartialOutput",
        "testScopesNeverExceedTheBoundDeviceSession",
        "testDeniedResponseDisclosesNoCapabilities",
        "testScopesDoNotInventUnwiredCapabilities",
        "CompanionTransport::UsbSerial",
        "CompanionTransport::LocalWeb",
        "DuplicateField",
        "UnknownScope",
        "TooLarge",
    ):
        require(failures, marker in tests, f"missing native coverage: {marker}")

    for path, text in zip(DOCS, docs):
        for marker in (
            "leshy.companion.request.v1",
            "leshy.companion.response.v1",
            "512",
            "scope_denied",
            "scope_unavailable",
            "scope_dependency_missing",
            "target.compare",
            "target.detail",
            "next_offset",
            "offset_out_of_range",
            "Serial0",
        ):
            require(failures, marker in text,
                    f"{path.name} omits protocol marker {marker}")

    if failures:
        print("companion protocol contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "companion protocol contract passed: bounded v1 parser, exact scopes, "
        "shared Action and zero direct driver/storage path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
