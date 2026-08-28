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
PRESENTER_HEADER = ROOT / "firmware/leshy1/src/ui/AirspaceGuardPresenter.h"
PRESENTER_SOURCE = ROOT / "firmware/leshy1/src/ui/AirspaceGuardPresenter.cpp"
PRESENTER_TEST = ROOT / "tests/native/airspace_guard_presenter_tests.cpp"
UI_STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
ARDUINO_ENTRY = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
)
BOARD_CAPTURE_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h"
)
BOARD_CAPTURE_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
)
BOARD_BLE_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.h"
)
BOARD_BLE_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp"
)
BLE_CONTRACT_HEADER = (
    ROOT / "firmware/leshy1/src/drivers/ble/BlePassiveContract.h"
)
HIL_RUNNER = ROOT / "tools/run_1x_airspace_guard_hil.py"
HIL_SCOPE = ROOT / "tests/hil/delta-scopes/airspace-guard-1.0.0-dev.223.json"


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
        presenter_header = PRESENTER_HEADER.read_text(encoding="utf-8")
        presenter_source = PRESENTER_SOURCE.read_text(encoding="utf-8")
        presenter_tests = PRESENTER_TEST.read_text(encoding="utf-8")
        ui_strings = UI_STRINGS.read_text(encoding="utf-8")
        arduino_entry = ARDUINO_ENTRY.read_text(encoding="utf-8")
        board_capture = BOARD_CAPTURE_HEADER.read_text(encoding="utf-8") + (
            BOARD_CAPTURE_SOURCE.read_text(encoding="utf-8")
        )
        board_ble = BOARD_BLE_HEADER.read_text(encoding="utf-8") + (
            BOARD_BLE_SOURCE.read_text(encoding="utf-8")
        )
        ble_contract = BLE_CONTRACT_HEADER.read_text(encoding="utf-8")
        hil_runner = HIL_RUNNER.read_text(encoding="utf-8")
        hil_scope = HIL_SCOPE.read_text(encoding="utf-8")
    except OSError as error:
        print(f"airspace guard contract check failed: {error}", file=sys.stderr)
        return 1

    combined = header + source
    for marker in (
        "kFrameInspectionCapacity = 64",
        "kEvidenceCapacity = 8",
        "kWifiDisconnectDetectorVersion = 1",
        "disconnectBurstThreshold = 4",
        "disconnectWindowUs = 2000000ULL",
        "ssidSecurityConflictEnabled = false",
        "ssidSecurityConflictWindowUs = 10000000ULL",
        "WifiSsidSecurityConflict",
        "ssidChurnEnabled = false",
        "ssidChurnThreshold = 4",
        "ssidChurnWindowUs = 10000000ULL",
        "WifiSsidChurn",
        "isWifiIdentityAdvertisementCandidate",
        "WifiIdentityRetentionKey",
        "wifiIdentityRetentionKey",
        "sameWifiIdentityRetentionKey",
        "kWifiDisconnectLiveRetentionCapacity = 8",
        "kWifiIdentityLiveRetentionCapacity = 8",
        "wifiDisconnectRetentionSlotAvailable",
        "wifiIdentityRetentionSlotAvailable",
        "kWifiIdentityDetectorVersion = 1",
        "kWifiSsidChurnDetectorVersion = 1",
        "WifiElevatedNoise",
        "kWifiElevatedNoiseDetectorVersion = 1",
        "elevatedNoiseEnabled = false",
        "elevatedNoiseFloorDbm = -75",
        "elevatedNoiseThreshold = 4",
        "elevatedNoiseWindowUs = 2000000ULL",
        "WifiNoiseFloorSample",
        "isWifiNoiseFloorCandidate",
        "noiseFloorDbm = -127",
        "BleTrackerPresence",
        "AirspaceBleTrackerProtocol",
        "bleAddressType = 0xffU",
        "kBleTrackerPresenceDetectorVersion = 1",
        "bleTrackerPresenceEnabled = false",
        "bleTrackerPresenceThreshold = 3",
        "bleTrackerPresenceWindowUs = 10000000ULL",
        "BleObservationSource",
        "AirspaceGuardBleRetention",
        "kBleTrackerLiveRetentionCapacity = 32",
        "bleTrackerIngressStatus",
        "mergeAirspaceGuardReports",
        "inspectBle(",
        "channel = 0U",
        "AirspaceWifiSecurity::Rsn",
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
        "testIngressClassifiersStayManagementOnly",
        "testExternalCaptureLossMakesClearEvidenceInconclusive",
        "testIdentityConflictIsOptInUntilLiveRetentionIsComplete",
        "testLiveIdentityRetentionKeyIsExactAndFailClosed",
        "testLiveRetentionPartitionKeepsDisconnectCapacity",
        "testIdentityConflictRetainsTwoExactAdvertisements",
        "testIdentityDetectorRejectsLookalikesAndMalformedEvidence",
        "testIdentityParserExcludesCapturedFcsFromInformationElements",
        "testSsidChurnRetainsDistinctNamesFromOneBssid",
        "testSsidChurnRejectsLookalikesAndIncompleteEvidence",
        "testBleTrackerPresenceIsOptInAndRetainsExactEvidence",
        "testBleTrackerPresenceRejectsLookalikesAndStaleEvidence",
        "testBleTrackerProtocolsRemainDistinct",
        "testBleTrackerPresenceFailsClosedOnIncompleteEvidence",
        "testLiveBleRetentionKeepsCoverageThenAllTrackerRepeats",
        "testLiveBleRetentionFailsClosedOnMalformedOrCapacityLoss",
        "testCompletedWifiAndBleReportsMergeWithoutInventingEvidence",
        "testElevatedNoiseIsLowConfidenceExactAndOptIn",
        "testElevatedNoiseRejectsWeakSplitStaleAndMalformedEvidence",
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
        "classifyBleTracker",
    ):
        require(failures, forbidden not in combined,
                f"Airspace Guard bypasses receive-evidence boundary: {forbidden}")

    for marker in (
        "deduplicateAddresses = true",
        "recordsObserved = 0",
        "scanContext.deduplicateAddresses = plan.deduplicateAddresses",
        "parameters.passive = 1U",
        "parameters.filter_duplicates = 0U",
        "takeReportsObserved",
    ):
        require(failures, marker in board_ble + ble_contract,
                f"missing complete BLE live-ingress contract: {marker}")
    for forbidden in (
        "ble_gap_adv_start",
        "ble_gap_connect",
        "ble_gap_ext_connect",
    ):
        require(failures, forbidden not in board_ble,
                f"BLE live retention gained an active path: {forbidden}")

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
        "testOutcomeStatusMismatchFailsClosed",
        "testMalformedReportsFailClosed",
        "testOutOfBoundsEvidenceFailsClosed",
        "testIdentityConflictReportIsKindAwareAndFailClosed",
        "testDifferentDetectorKindsMayReferenceTheSameTransmitter",
        "testSsidChurnReportIsKindAwareAndFailClosed",
        "testIdentityDetectorsMayShareExactSourceEvidence",
        "testBleTrackerReportUsesChannelFreeKindAwareValidation",
        "testElevatedNoiseReportCannotInventSourceOrConfidence",
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

    presenter = presenter_header + presenter_source
    for marker in (
        "kVisibleRowCapacity = 4",
        "AirspaceGuardEvidenceIncomplete",
        "AirspaceGuardPassiveOnly",
        "finding->detectorVersion",
        "finding->threshold",
        "evidence->frameIndex",
        "evidence->channel",
        "evidence->rssiDbm",
        "controller.inspectionTruncated()",
        "controller.sourceFramesDropped()",
        "controller.sourceFramesObserved()",
        "AirspaceGuardIdentityConflict",
        "AirspaceGuardSecurityPairFormat",
        "networkNameFingerprint",
        "AirspaceGuardSsidChurn",
        "AirspaceGuardChurnSpanFormat",
        "AirspaceGuardBleTrackerPresence",
        "AirspaceGuardBlePresenceOnly",
        "AirspaceGuardEvidenceRecordRowFormat",
        "AirspaceGuardRecordFormat",
        "AirspaceGuardProtocolSignalFormat",
        "AirspaceGuardElevatedNoise",
        "AirspaceGuardInterferencePossible",
        "AirspaceGuardNoiseSpanFormat",
        "AirspaceGuardNoiseEvidenceRowFormat",
        "AirspaceGuardNoiseSignalFormat",
    ):
        require(failures, marker in presenter,
                f"missing Airspace Guard presentation contract: {marker}")
    for marker in (
        "testFindingShowsOnlyActionableUserFacts",
        "testEvidenceListUsesFourStableTouchRows",
        "testEvidenceDetailRetainsExactReference",
        "testRussianInconclusiveExplainsIncompleteEvidence",
        "testMalformedReportHasNoInventedEvidence",
        "testDroppedFindingCountReplacesLessImportantMix",
        "testEmptyCaptureIsExplicitlyIncomplete",
        "testCaptureLossIsShownBeforeFindingMix",
        "testClearOutcomeUsesTheOtherwiseEmptyRowsForCoverage",
        "testIdentityConflictExplainsIndicatorWithoutClaimingProof",
        "testInvalidSsidBytesUseStableNonInventedIdentifier",
        "testSsidChurnExplainsIndicatorWithoutClaimingPineap",
        "testBleTrackerPresenceNeverInventsAChannelOrOwner",
        "testElevatedNoiseExplainsUncertainInterferenceWithoutInventingSource",
    ):
        require(failures, marker in presenter_tests,
                f"missing Airspace Guard presenter coverage: {marker}")
    for marker in (
        "AirspaceGuardTitle",
        "AirspaceGuardFinding",
        "AirspaceGuardEvidenceTitle",
        "AirspaceGuardEvidenceIncomplete",
        "AirspaceGuardPassiveOnly",
        "AirspaceGuardCaptureNotStarted",
        "AirspaceGuardListening",
        "AirspaceGuardEvidenceKindsFormat",
        "AirspaceGuardCaptureLossFormat",
        "AirspaceGuardIdentityConflict",
        "AirspaceGuardSecurityPairFormat",
        "AirspaceGuardSsidFingerprintFormat",
        "AirspaceGuardSsidChurn",
        "AirspaceGuardChurnSpanFormat",
        "AirspaceGuardBleTrackerPresence",
        "AirspaceGuardBlePresenceOnly",
        "AirspaceGuardBleIdFormat",
        "AirspaceGuardBleProtocolSpanFormat",
        "AirspaceGuardEvidenceRecordRowFormat",
        "AirspaceGuardRecordFormat",
        "AirspaceGuardProtocolSignalFormat",
        "AirspaceGuardElevatedNoise",
        "AirspaceGuardInterferencePossible",
        "AirspaceGuardNoiseSpanFormat",
        "AirspaceGuardNoiseEvidenceRowFormat",
        "AirspaceGuardRxSampleFormat",
        "AirspaceGuardNoiseSignalFormat",
        "AirspaceGuardNoiseEvidenceLossFormat",
    ):
        require(failures, marker in ui_strings,
                f"missing EN/RU Airspace Guard copy: {marker}")
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
        require(failures, forbidden not in presenter,
                f"Airspace Guard presenter bypasses passive boundary: {forbidden}")

    for marker in (
        "WifiProductView::AirspaceGuard",
        "UiTextId::WifiMenuAirspaceGuard",
        "openAirspaceGuardProduct()",
        "renderAirspaceGuardPage",
        "presentAirspaceGuard",
        "airspaceGuardController.openSelected()",
        "airspaceGuardController.back()",
        "beginAirspaceGuardMonitor",
        "serviceAirspaceGuardProduct",
        "quiesceAirspaceGuardOnSafetyStop",
        "airspaceGuardDetector.inspectWifi",
        "airspaceGuardDetector.inspectBle",
        "mergeAirspaceGuardReports",
        "runAirspaceGuardBleWorker",
        "retainAirspaceGuardBleRecord",
        "requestAirspaceGuardBleWorker(airspaceGuardGeneration)",
        "event.generation == airspaceGuardGeneration",
        "plan.deduplicateAddresses = false",
        "plan.maximumRecords = 128U",
        "event.retention.complete()",
        "scanner.end()",
        "scanner.cleanupComplete()",
        "kAirspaceGuardCaptureDurationMs = 10000U",
        "kAirspaceGuardChannelDwellMs = 120U",
        "UiTextId::AirspaceGuardEvidenceKindsFormat",
        "emitAirspaceGuardState",
        'std::strcmp(command, "airspace.guard.state") == 0',
        "policy.elevatedNoiseEnabled = monitor.noiseRetentionComplete",
        "report.wifiNoiseSamplesDropped == 0U",
        "report.wifiNoiseSamplesMalformed == 0U",
    ):
        require(failures, marker in arduino_entry,
                f"missing Airspace Guard product integration: {marker}")
    open_start = arduino_entry.find("bool openAirspaceGuardProduct()")
    open_end = arduino_entry.find("bool stopWifiChannelsProduct()", open_start)
    open_body = arduino_entry[open_start:open_end]
    require(failures, open_start >= 0 and open_end > open_start,
            "Airspace Guard product entry point is not bounded")
    for forbidden in (
        "ResourceBroker", "beginDeviceMonitor", "beginChannelMonitor",
        "startProductSurvey", "esp_wifi", "setTxPower", "sendPacket",
        "injectFrame",
    ):
        require(failures, forbidden not in open_body,
                f"bounded Airspace Guard flow bypasses passive adapter: {forbidden}")

    ble_worker_start = arduino_entry.find("void runAirspaceGuardBleWorker()")
    ble_worker_end = arduino_entry.find(
        "void runProductSurveyWorker(", ble_worker_start)
    ble_worker = arduino_entry[ble_worker_start:ble_worker_end]
    require(failures,
            ble_worker_start >= 0 and ble_worker_end > ble_worker_start,
            "Airspace Guard BLE worker is not bounded")
    require(failures, "xTaskCreate" not in ble_worker,
            "Airspace Guard BLE created a second worker task")
    require(failures,
            ble_worker.find("scanner.end()") <
            ble_worker.rfind("xQueueOverwrite(airspaceGuardBleWorkerEvents"),
            "Airspace Guard BLE result escaped before scanner cleanup")

    for marker in (
        "AirspaceGuardMonitorStats",
        "WIFI_PROMIS_FILTER_MASK_MGMT",
        "isWifiDisconnectFrameCandidate",
        "disconnectFramesDropped",
        "kDisconnectRetentionCapacity =",
        "kIdentityRetentionCapacity =",
        "wifiDisconnectRetentionSlotAvailable",
        "wifiIdentityRetentionSlotAvailable",
        "identityProfilesDeduplicated",
        "identityProfilesDropped",
        "identityRetentionComplete",
        "kNoiseRetentionCapacity =",
        "packet->rx_ctrl.noise_floor",
        "noiseSamplesDropped",
        "noiseRetentionComplete",
        "wifiIdentityRetentionKey",
        "sameWifiIdentityRetentionKey",
        "packet->rx_ctrl.sig_len > capture_.plan().snapLength",
        "capture_.size() == 0U",
        "airspaceGuardStats_.cleanupComplete",
        "return stop(nowUs)",
    ):
        require(failures, marker in board_capture,
                f"missing bounded passive adapter contract: {marker}")
    for forbidden in (
        "WIFI_MODE_AP", "WIFI_MODE_APSTA", "esp_wifi_connect",
        "esp_wifi_set_config", "esp_wifi_80211_tx", "setTxPower",
        "sendPacket", "injectFrame",
    ):
        require(failures, forbidden not in board_capture,
                f"Airspace Guard adapter gained active behavior: {forbidden}")
    require(
        failures,
        arduino_entry.count("BoardWifiPassiveCapture wifiFrameCapture;") == 1,
        "Airspace Guard must reuse the one existing Wi-Fi adapter",
    )
    require(
        failures,
        "policy.ssidSecurityConflictEnabled =" in arduino_entry and
        "policy.ssidChurnEnabled =" in arduino_entry and
        "monitor.identityRetentionComplete" in arduino_entry and
        "monitor.identityProfilesDropped" in arduino_entry,
        "live identity detector is not gated by complete bounded retention",
    )
    require(
        failures,
        "policy.elevatedNoiseEnabled = monitor.noiseRetentionComplete" in
            arduino_entry and
        "isWifiNoiseFloorCandidate" in board_capture and
        "noiseSamplesDropped" in board_capture and
        "noiseRetentionComplete" in board_capture,
        "live noise detector is not gated by complete bounded RX metadata",
    )

    for marker in (
        'RUN_SCHEMA = "leshy.airspace_guard_hil.run.v1"',
        'STATE_SCHEMA = "leshy.airspace_guard.v1"',
        "wifi_cancelled",
        "ble_cancelled",
        "two_complete_guard_lifecycles",
        "static_pixels_unchanged_during_live_refresh",
        "zero_heap_drift_after_warmup",
        "absence_of_noise_finding_is_not_absence_of_interference",
        "application_wifi_connect_calls",
        "application_raw_tx_calls",
    ):
        require(failures, marker in hil_runner,
                f"missing Airspace Guard HIL contract: {marker}")
    for marker in (
        '"schema": "leshy.hil.delta_scope.v1"',
        '"candidate_version": "1.0.0-dev.223"',
        '"full_matrix_required": false',
        '"cadence_after_acceptance": "6/15"',
    ):
        require(failures, marker in hil_scope,
                f"missing Airspace Guard delta scope: {marker}")

    if failures:
        print("airspace guard contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Airspace Guard passive contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
