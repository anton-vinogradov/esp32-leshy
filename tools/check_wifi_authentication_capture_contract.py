#!/usr/bin/env python3
"""Fail closed if the host-only authentication analyzer gains side effects."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    ROOT
    / "firmware/leshy1/src/services/auth/WifiAuthenticationCapture.h"
)
SOURCE = (
    ROOT
    / "firmware/leshy1/src/services/auth/WifiAuthenticationCapture.cpp"
)
TEST = ROOT / "tests/native/wifi_authentication_capture_tests.cpp"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        tests = TEST.read_text(encoding="utf-8")
    except OSError as error:
        print(
            f"wifi authentication capture contract check failed: {error}",
            file=sys.stderr,
        )
        return 1

    combined = header + source
    for marker in (
        "WifiFrameSource",
        "kSourceFrameInspectionCapacity = 64",
        "kEvidenceCapacity = 16",
        "kPeerCapacity = 4",
        "kPmkidCapacity = 4",
        "WifiEapolKeyMessage::Message1",
        "WifiEapolKeyMessage::Message4",
        "replayCountersConsistent",
        "keyMaterialConsistent",
        "findPmkidKde",
        "0x00U && element[1] == 0x0fU",
        "element[2] == 0xacU && element[3] == 0x04U",
        "WifiAuthenticationUncertaintyCaptureLoss",
        "WifiAuthenticationUncertaintyMalformed",
        "WifiAuthenticationUncertaintyTruncated",
        "WifiAuthenticationUncertaintyCapacity",
        "WifiAuthenticationUncertaintyUnsupported",
        "WifiAuthenticationKeyProfile::Unsupported",
        "kSupportedDescriptorType = 2U",
        "kSupportedDescriptorVersion2 = 2U",
        "kSupportedDescriptorVersion3 = 3U",
        "keyDataLength != bodyLength - kEapolKeyFixedBytes",
        "messageDirectionIsValid",
        "applyAttemptMessage",
        "decoded.replayCounter <= peer->replayCounters[0]",
        "anyNonzero(peer.authenticatorNonce)",
        "anyNonzero(peer.stationNonce)",
        "peer.sequenceConsistent",
        "sequenceRejected",
        "sourceFrameIndex",
        "framesDroppedCapacity",
        "framesDroppedInvalid",
    ):
        require(failures, marker in combined,
                f"missing bounded parser contract: {marker}")

    for marker in (
        "testCompleteHandshakeAndPmkidRetainExactEvidence",
        "testIncompleteHandshakeIsExplicitAndPeersNeverMerge",
        "testReplayMismatchCannotBecomeComplete",
        "testMismatchedAuthenticatorNonceCannotBecomeComplete",
        "testNoAuthenticationEvidenceStaysInconclusive",
        "testTruncatedEapolFailsClosed",
        "testMalformedKeyAndPmkidElementFailClosed",
        "testOnlySupportedRsnProfilesCanComplete",
        "testUnsupportedDescriptorsAreRetainedAndNeverComplete",
        "testUnsupportedKeyInfoIsRetainedAndInconclusive",
        "testAttemptOrderDirectionNonceAndDescriptorConsistencyFailClosed",
        "testCompletedAttemptSurvivesANewerIncompleteAttempt",
        "testExactLengthsQosAndFcs",
        "testConflictingPmkidKdesFailClosed",
        "testCaptureDropsAndUnreadableSourceFailClosed",
        "testInspectionAndReportCapacityAreBounded",
        "testInvalidAccountingAndNullInputFailClosed",
    ):
        require(failures, marker in tests,
                f"missing authentication parser fixture: {marker}")

    forbidden = (
        "#include <Arduino",
        "#include <WiFi",
        "#include \"platform/",
        "#include \"drivers/",
        "esp_wifi_",
        "ResourceBroker",
        "SafetySupervisor",
        "xTaskCreate",
        "digitalWrite",
        "analogWrite",
        "malloc(",
        "calloc(",
        "realloc(",
        "new ",
        "operator new",
        "delete ",
        "std::vector",
        "std::string",
        "std::deque",
        "std::list",
        "std::map",
        "std::unordered_",
        "std::function",
    )
    for marker in forbidden:
        require(failures, marker not in combined,
                f"host-only parser gained forbidden dependency: {marker}")

    if failures:
        print("wifi authentication capture contract check failed:",
              file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("wifi authentication capture contract check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
