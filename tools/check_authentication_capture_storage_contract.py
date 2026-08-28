#!/usr/bin/env python3
"""Fail-closed static contract for CAP-049 authentication capture storage."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEC_HEADER = ROOT / "firmware/leshy1/src/storage/SessionCodec.h"
CODEC_SOURCE = ROOT / "firmware/leshy1/src/storage/SessionCodec.cpp"
STORE_HEADER = ROOT / "firmware/leshy1/src/storage/SessionStore.h"
STORE_SOURCE = ROOT / "firmware/leshy1/src/storage/SessionStore.cpp"
HOST_TEST = ROOT / "tests/native/authentication_capture_storage_tests.cpp"


def compact(value: str) -> str:
    without_comments = re.sub(
        r"/\*.*?\*/|//[^\n]*", "", value, flags=re.DOTALL
    )
    return re.sub(r"\s+", "", without_comments)


def braced_block(value: str, marker: str) -> str:
    start = value.find(marker)
    if start < 0:
        return ""
    opening = value.find("{", start + len(marker))
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start:index + 1]
    return ""


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check_sources(
    codec_header: str,
    codec_source: str,
    store_header: str,
    store_source: str,
    host_test: str,
) -> list[str]:
    failures: list[str] = []
    codec_h = compact(codec_header)
    codec = compact(codec_source)
    store_h = compact(store_header)
    store = compact(store_source)
    tests = compact(host_test)

    for marker in (
        "kAuthenticationCaptureSessionSchemaVersion=8",
        "kAuthenticationCaptureSegmentSchemaVersion=8",
        "AuthenticationCapturePurpose",
        "Generic=0",
        "Authentication=1",
        "kBssidBytes=6",
        "kSsidCapacity=32",
        "framesReported",
        "framesAccepted",
        "framesDroppedCapacity",
        "framesDroppedInvalid",
    ):
        require(failures, marker in codec_h,
                f"missing schema-8 provenance contract: {marker}")
    for marker in (
        "kAuthenticationCaptureWireVersion=5",
        "kAuthenticationCaptureRecordBytes=132",
        "output[4]=kAuthenticationCaptureWireVersion",
        "put16(footer+4,kAuthenticationCaptureSegmentSchemaVersion)",
    ):
        require(failures, marker in codec,
                f"missing wire-5 persistence contract: {marker}")

    generic_open = braced_block(
        codec, "SessionCodecStatusopenPersistedWifiFrameCapture(")
    require(failures, bool(generic_open),
            "generic persisted Wi-Fi open API is missing")
    for marker in (
        "kWifiFrameSegmentSchemaVersion",
        "kAuthenticationCaptureSegmentSchemaVersion",
        "kCaptureRecordBytes",
        "kAuthenticationCaptureRecordBytes",
        "decodeWifiFrameBlock(",
    ):
        require(failures, marker in generic_open,
                f"generic raw-frame open lost schema4/8 path: {marker}")
    require(
        failures,
        "(schemaVersion!=kWifiFrameSegmentSchemaVersion&&"
        "schemaVersion!=kAuthenticationCaptureSegmentSchemaVersion)" in
        generic_open,
        "generic raw-frame open lost schema4/8 admission",
    )

    manifest_decode = braced_block(
        codec, "SessionCodecStatusdecodeSessionManifest(")
    reopen = braced_block(codec, "SessionCodecStatusreopenSession(")
    require(failures, "kWifiFrameSessionSchemaVersion" in manifest_decode,
            "schema 4 manifest read path was removed")
    require(failures,
            "kAuthenticationCaptureSessionSchemaVersion" in manifest_decode,
            "schema 8 manifest read path is missing")
    for marker in (
        "kWifiFrameSessionSchemaVersion",
        "kAuthenticationCaptureSessionSchemaVersion",
        "authenticationProvenance.framesAccepted!=decodedCaptureCount",
    ):
        require(failures, marker in reopen,
                f"reopen validation lost schema4/8 invariant: {marker}")

    provenance_validation = braced_block(
        codec, "boolvalidAuthenticationCaptureProvenance(")
    for marker in (
        "provenance.ssidLength>provenance.ssid.size()",
        "provenance.ssidKnown&&provenance.ssidLength==0",
        "!provenance.ssidKnown&&provenance.ssidLength!=0",
        "allZero(provenance.ssid.data()+provenance.ssidLength",
        "provenance.framesAccepted",
        "provenance.framesDroppedCapacity",
        "provenance.framesDroppedInvalid",
        "accounted!=provenance.framesReported",
    ):
        require(failures, marker in provenance_validation,
                f"bounded provenance validation is missing: {marker}")
    authentication_open = braced_block(
        codec, "SessionCodecStatusopenPersistedAuthenticationCapture(")
    require(
        failures,
        "decodedProvenance.framesAccepted!=output->frameCount()" in
        authentication_open,
        "authentication open does not bind accounting to retained frames",
    )

    commit = braced_block(
        store, "SessionStoreCommitResultcommitAuthenticationCapture(")
    commit_next = braced_block(
        store, "SessionStoreCommitResultcommitNextAuthenticationCapture(")
    for marker in (
        "encodeAuthenticationCaptureSegment(",
        "encodeSessionManifest(",
        "StoreCommitBackendbackend(",
        "commitGeneration(backend,head)",
    ):
        require(failures, marker in commit,
                f"authentication capture bypasses atomic SessionStore: {marker}")
    require(failures, "recoverSession(" in commit_next,
            "next authentication generation bypasses atomic recovery")
    require(failures, store.count("classStoreCommitBackend") == 1,
            "a parallel authentication storage backend was introduced")
    for marker in (
        "commitAuthenticationCapture(",
        "commitNextAuthenticationCapture(",
    ):
        require(failures, marker in store_h,
                f"missing public immutable-store API: {marker}")

    production = codec_header + codec_source + store_header + store_source
    include_lines = "\n".join(re.findall(
        r"^\s*#include[^\n]*$", production, flags=re.MULTILINE))
    for marker in (
        "platform/", "drivers/", "Arduino", "WiFi.h", "esp_wifi",
        "radio/", "transmit", "TxController",
    ):
        require(failures, marker not in include_lines,
                f"storage gained forbidden radio/platform dependency: {marker}")
    production_compact = compact(production)
    for marker in (
        "malloc(", "calloc(", "realloc(", "operatornew", "new(",
        "std::vector", "std::deque", "std::list", "std::map",
        "std::unordered_", "std::string",
    ):
        require(failures, marker not in production_compact,
                f"storage gained dynamic allocation: {marker}")
    production_without_comments = re.sub(
        r"/\*.*?\*/|//[^\n]*", "", production, flags=re.DOTALL
    )
    for keyword in ("new", "delete"):
        require(
            failures,
            re.search(rf"\b{keyword}\b", production_without_comments) is None,
            f"storage gained dynamic allocation keyword: {keyword}",
        )

    for marker in (
        "testSchemaEightRoundTripAndGenericOpen",
        "testSchemaFourRemainsReadable",
        "testSchemaEightGenericPurpose",
        "testInvalidProvenanceAndCorruptionFailClosed",
        "invalidKnownEmpty",
        "unknownAuthentication",
        "testAtomicBoundaryRecoveryFallsBackToSchemaFour",
    ):
        require(failures, marker in tests,
                f"missing storage regression fixture: {marker}")
    return failures


def main() -> int:
    try:
        sources = [path.read_text(encoding="utf-8") for path in (
            CODEC_HEADER, CODEC_SOURCE, STORE_HEADER, STORE_SOURCE, HOST_TEST
        )]
    except OSError as error:
        print(f"authentication capture storage contract failed: {error}",
              file=sys.stderr)
        return 1
    failures = check_sources(*sources)
    if failures:
        print("authentication capture storage contract failed:",
              file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("authentication capture storage contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
