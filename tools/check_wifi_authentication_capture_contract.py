#!/usr/bin/env python3
"""Fail closed if the host-only authentication analyzer gains side effects."""

from __future__ import annotations

import re
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
DECODER_HEADER = (
    ROOT
    / "firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.h"
)
DECODER_SOURCE = (
    ROOT
    / "firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp"
)
TEST = ROOT / "tests/native/wifi_authentication_capture_tests.cpp"
BOARD_HEADER = (
    ROOT
    / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.h"
)
BOARD_SOURCE = (
    ROOT
    / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp"
)
TEARDOWN_POLICY = (
    ROOT / "firmware/leshy1/src/platform/arduino/"
    "WifiPassiveCaptureTeardownPolicy.h"
)
TEARDOWN_TEST = (
    ROOT / "tests/native/wifi_passive_capture_teardown_policy_tests.cpp"
)
ARDUINO_ENTRY = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
)


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def compact_cpp(value: str) -> str:
    """Normalize formatting without weakening token/order checks."""
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", "", value,
                              flags=re.DOTALL)
    return re.sub(r"\s+", "", without_comments)


def section(value: str, start: str, end: str) -> str:
    start_index = value.find(start)
    if start_index < 0:
        return ""
    end_index = value.find(end, start_index + len(start))
    return value[start_index:] if end_index < 0 else value[start_index:end_index]


def braced_block(value: str, marker: str) -> str:
    """Return the balanced C++ block beginning after a unique control marker."""
    marker_index = value.find(marker)
    if marker_index < 0:
        return ""
    opening = value.find("{", marker_index + len(marker))
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[marker_index:index + 1]
    return ""


def require_ordered(
    failures: list[str], value: str, markers: tuple[str, ...], message: str
) -> None:
    cursor = 0
    for marker in markers:
        position = value.find(marker, cursor)
        if position < 0:
            failures.append(f"{message}: missing/out-of-order {marker}")
            return
        cursor = position + len(marker)


def main() -> int:
    failures: list[str] = []
    try:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        decoder_header = DECODER_HEADER.read_text(encoding="utf-8")
        decoder_source = DECODER_SOURCE.read_text(encoding="utf-8")
        tests = TEST.read_text(encoding="utf-8")
        board_header = BOARD_HEADER.read_text(encoding="utf-8")
        board_source = BOARD_SOURCE.read_text(encoding="utf-8")
        teardown_policy = TEARDOWN_POLICY.read_text(encoding="utf-8")
        teardown_tests = TEARDOWN_TEST.read_text(encoding="utf-8")
        arduino_entry = ARDUINO_ENTRY.read_text(encoding="utf-8")
    except OSError as error:
        print(
            f"wifi authentication capture contract check failed: {error}",
            file=sys.stderr,
        )
        return 1

    combined = header + source + decoder_header + decoder_source
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
        "WifiAuthenticationIngressDisposition",
        "classifyWifiAuthenticationIngress",
        "kEapolLlcSnap",
        "bytesMatchPrefix",
        "frameAccessPoint",
        "Disposition::Retain",
        "kWifiAuthenticationSupportedDescriptorType = 2U",
        "kWifiAuthenticationSupportedDescriptorVersion2 = 2U",
        "kWifiAuthenticationSupportedDescriptorVersion3 = 3U",
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
        "testIngressRetainsTargetNonQosQosAndFcs",
        "testIngressIgnoresWrongBssidAndNonEapol",
        "testIngressRetainsProvableTargetFailuresFailClosed",
        "testIngressRejectsUnidentifiableMalformedFrames",
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

    board = board_header + board_source
    teardown_contract = teardown_policy + teardown_tests
    for marker in (
        "AuthenticationCaptureStats",
        "beginAuthenticationCapture",
        "authenticationCaptureStats",
        "authenticationTarget_",
        "authenticationCapture_",
        "WIFI_PROMIS_FILTER_MASK_DATA",
        "classifyWifiAuthenticationIngress",
        "authenticationStats_.framesObserved",
        "authenticationStats_.framesIgnored",
        "authenticationStats_.framesInvalid",
        "authenticationStats_.candidatesAccepted",
        "authenticationStats_.candidatesDropped",
        "capture_.append",
    ):
        require(failures, marker in board,
                f"missing live authentication adapter contract: {marker}")
    require(failures, board_header.count("WifiFrameCapture capture_") == 1,
            "live authentication adapter must reuse one WifiFrameCapture")
    for marker in (
        "WifiPassiveTeardownStep::RetryRequired",
        "wifiPassiveCleanupProven",
        "wifiPassiveCaptureCompletionPermitted",
        "wifiPassiveCallbackOwnerReleasePermitted",
        "wifiPassiveRfLeaseReleasePermitted",
        "wifiAuthenticationSurveyBackendClosePermitted",
        "testTimeoutAndEveryIdfFailureRetainOwnershipUntilRetry",
        "testCleanPathAllowsCompletionOnlyAfterAllStages",
        "testSurveyBackendCloseRequiresProducerQuiescence",
    ):
        require(failures, marker in teardown_contract,
                f"missing executable teardown policy contract: {marker}")

    compact_header = compact_cpp(board_header)
    compact_source = compact_cpp(board_source)
    begin_authentication = section(
        compact_source,
        "boolBoardWifiPassiveCapture::beginAuthenticationCapture(",
        "boolBoardWifiPassiveCapture::beginCapture(",
    )
    begin_capture = section(
        compact_source,
        "boolBoardWifiPassiveCapture::beginCapture(",
        "boolBoardWifiPassiveCapture::beginDeviceMonitor(",
    )
    wait_for_callbacks = section(
        compact_source,
        "boolBoardWifiPassiveCapture::waitForCallbackQuiescence(",
        "voidBoardWifiPassiveCapture::releaseFailedBegin(",
    )
    release_failed_begin = section(
        compact_source,
        "voidBoardWifiPassiveCapture::releaseFailedBegin(",
        "boolBoardWifiPassiveCapture::begin(",
    )
    stop_capture = section(
        compact_source,
        "boolBoardWifiPassiveCapture::stop(",
        "voidBoardWifiPassiveCapture::reset(",
    )
    end_wifi = section(
        compact_source,
        "boolBoardWifiPassiveCapture::endWifi(",
        "}namespace",
    )
    receive_callback = section(
        compact_source,
        "voidBoardWifiPassiveCapture::receive(",
        "voidBoardWifiPassiveCapture::accept(",
    )
    accept_callback = section(
        compact_source,
        "voidBoardWifiPassiveCapture::accept(",
        "boolBoardWifiPassiveCapture::changeChannel(",
    )
    authentication_ingress = section(
        accept_callback,
        "if(authenticationCapture_){",
        "if(channelMonitor_){",
    )

    for name, value in (
        ("beginAuthenticationCapture", begin_authentication),
        ("beginCapture", begin_capture),
        ("waitForCallbackQuiescence", wait_for_callbacks),
        ("releaseFailedBegin", release_failed_begin),
        ("stop", stop_capture),
        ("endWifi", end_wifi),
        ("receive", receive_callback),
        ("accept", accept_callback),
        ("authentication ingress", authentication_ingress),
    ):
        require(failures, bool(value),
                f"missing live authentication lifecycle section: {name}")

    # A rejected/re-entrant begin must be observationally inert. The public
    # authentication entry point only validates and delegates; the target is
    # committed after idle-owner reservation in beginCapture.
    require(
        failures,
        "authenticationTarget_=" not in begin_authentication and
        "authenticationCapture_=false" not in begin_authentication,
        "re-entrant authentication begin may mutate the active session",
    )
    require_ordered(
        failures,
        begin_capture,
        (
            "initialized_",
            "started_",
            "promiscuous_",
            "reserveCallbackOwner()",
            "authenticationTarget_=*authenticationTarget",
            "esp_wifi_set_promiscuous(true)",
            "authenticationStats_.active=true",
            "openCallbackAdmission()",
        ),
        "authentication admission must remain closed until successful start",
    )

    # One global owner and in-flight count protect the borrowed callback pointer;
    # generation closure makes already-admitted but not-yet-running work stale.
    for marker in (
        "staticportMUX_TYPEcallbackMux_",
        "staticstd::uint32_tcallbacksInFlight_",
        "std::uint32_tcallbackGeneration_=0",
        "boolcallbackAdmissionOpen_=false",
    ):
        require(failures, marker in compact_header,
                f"missing callback barrier state: {marker}")
    require_ordered(
        failures,
        receive_callback,
        (
            "callbackAdmissionOpen_",
            "generation=instance->callbackGeneration_",
            "++callbacksInFlight_",
            "instance->accept(buffer,type,generation)",
            "--callbacksInFlight_",
        ),
        "callback in-flight accounting must bracket accept",
    )
    require_ordered(
        failures,
        accept_callback,
        (
            "callbackGeneration_==generation",
            "if(!currentGeneration)return",
            "if(buffer==nullptr)return",
        ),
        "stale callback generations must be rejected before payload access",
    )

    # Quiescence is bounded and a timeout leaves both capture and ownership
    # unfinalized so a later stop can safely retry. Capture completion is a
    # postcondition of the complete physical ESP-IDF teardown, never a promise
    # made before stop/deinit/event-loop-delete can still fail.
    require_ordered(
        failures,
        wait_for_callbacks,
        (
            "kCallbackQuiescenceTimeoutMs",
            "while(!callbacksQuiescent())",
            ">=deadlineUs",
            "returnfalse",
            "vTaskDelay(1U)",
        ),
        "callback quiescence wait must remain bounded",
    )
    require_ordered(
        failures,
        stop_capture,
        (
            "closeCallbackAdmission()",
            "esp_wifi_set_promiscuous(false)",
            "waitForCallbackQuiescence()",
            "WifiPassiveTeardownStep::AwaitCallbacks,ESP_ERR_TIMEOUT",
            "applyTeardownState(teardown)",
            "returnfalse",
            "endWifi(&teardown)",
            "if(!wifiCleanup)",
            "capture_.fail(lastError_,endedUs)",
            "returnfalse",
            "wifiPassiveCallbackOwnerReleasePermitted(teardown)",
            "capture_.complete(endedUs)",
            "releaseCallbackOwner()",
        ),
        "stop must close, quiesce, physically clean up, finalize, then release owner",
    )
    require(
        failures,
        stop_capture.count("releaseCallbackOwner()") == 1,
        "stop may release callback ownership before terminal quiescence",
    )
    require_ordered(
        failures,
        release_failed_begin,
        (
            "closeCallbackAdmission()",
            "wifiPassiveCallbackOwnerReleasePermitted(teardown)",
            "return",
            "deviceMonitor_=false",
            "authenticationCapture_=false",
            "releaseCallbackOwner()",
        ),
        "failed begin must retain admission owner until exact cleanup",
    )
    require_ordered(
        failures,
        stop_capture,
        (
            "!eventLoopOwned_",
            "!ownsCallbackLifecycle",
            "!authenticationCapture_",
            "returncleanupComplete_&&terminalCapture",
            "closeCallbackAdmission()",
            "if(!wifiCleanup)",
            "returnfalse",
            "authenticationCapture_=false",
            "releaseCallbackOwner()",
            "returntrue",
        ),
        "stop fast/retry path may publish clean or release owner early",
    )
    failed_wifi_cleanup = braced_block(stop_capture, "if(!wifiCleanup)")
    require(
        failures,
        bool(failed_wifi_cleanup) and
        "if(capture_.stats().state==WifiFrameCaptureState::Running)" in
        failed_wifi_cleanup and
        "capture_.fail(lastError_,endedUs)" in failed_wifi_cleanup and
        "capture_.complete(endedUs)" not in failed_wifi_cleanup and
        "releaseCallbackOwner()" not in failed_wifi_cleanup and
        "deviceMonitor_=false" not in failed_wifi_cleanup and
        "channelMonitor_=false" not in failed_wifi_cleanup and
        "airspaceGuardMonitor_=false" not in failed_wifi_cleanup and
        "authenticationCapture_=false" not in failed_wifi_cleanup and
        "returnfalse" in failed_wifi_cleanup,
        "failed ESP-IDF cleanup must retain mode and callback ownership",
    )
    require(
        failures,
        stop_capture.find("endWifi(&teardown)") <
        stop_capture.find("capture_.complete(endedUs)") and
        stop_capture.count("capture_.complete(endedUs)") == 1,
        "capture may become Complete before exact physical teardown",
    )
    promiscuous_teardown = braced_block(stop_capture, "if(promiscuous_)")
    promiscuous_failure = braced_block(
        promiscuous_teardown, "if(error!=ESP_OK)")
    require_ordered(
        failures,
        promiscuous_teardown,
        (
            "esp_wifi_set_promiscuous(false)",
            "if(error!=ESP_OK)",
            "applyWifiPassiveTeardownFailure(",
            "WifiPassiveTeardownStep::DisablePromiscuous,error",
            "applyTeardownState(teardown)",
            "returnfalse",
            "}else{",
            "applyWifiPassiveTeardownSuccess(",
        ),
        "promiscuous ownership flag must clear only after successful disable",
    )
    require(
        failures,
        bool(promiscuous_failure) and
        "applyWifiPassiveTeardownSuccess(" not in promiscuous_failure and
        "waitForCallbackQuiescence()" not in promiscuous_failure and
        "endWifi(" not in promiscuous_failure,
        "stop forgets promiscuous state after a failed disable",
    )

    # ESP-IDF teardown is a retryable state machine. A failed stage must retain
    # its ownership flag and must not attempt later dependent stages. Only an
    # exact all-clear may publish cleanupComplete.
    require_ordered(
        failures,
        end_wifi,
        (
            "if(started_)",
            "esp_wifi_stop()",
            "if(error!=ESP_OK)",
            "WifiPassiveTeardownStep::StopWifi,error",
            "applyTeardownState(local)",
            "returnfalse",
            "WifiPassiveTeardownStep::StopWifi)",
            "if(initialized_)",
            "esp_wifi_deinit()",
            "if(error!=ESP_OK)",
            "WifiPassiveTeardownStep::DeinitWifi,error",
            "applyTeardownState(local)",
            "returnfalse",
            "WifiPassiveTeardownStep::DeinitWifi)",
            "if(eventLoopOwned_)",
            "esp_event_loop_delete_default()",
            "if(error!=ESP_OK)",
            "WifiPassiveTeardownStep::DeleteEventLoop,error",
            "applyTeardownState(local)",
            "returnfalse",
            "WifiPassiveTeardownStep::DeleteEventLoop)",
            "cleanupComplete_=wifiPassiveCleanupProven(local)",
            "returncleanupComplete_",
        ),
        "ESP-IDF teardown stages must retain flags and fail closed",
    )
    for flag in ("started_=false", "initialized_=false",
                 "eventLoopOwned_=false", "promiscuous_=false"):
        require(
            failures,
            flag not in end_wifi,
            f"Board bypasses host-tested teardown transition: {flag}",
        )

    # ESP-IDF reports FCS in sig_len, but a prefix snap does not retain the tail.
    # The stored flag must therefore describe retained bytes, not raw metadata.
    require(
        failures,
        "packet->rx_ctrl.sig_len<=capture_.plan().snapLength" in
        authentication_ingress,
        "authentication snap truncation may falsely retain FCS metadata",
    )
    require_ordered(
        failures,
        authentication_ingress,
        (
            "constboolretainedFrameIncludesFcs=",
            "packet->rx_ctrl.sig_len<=capture_.plan().snapLength",
            "capture_.append(",
            "WifiFrameKind::Data,retainedFrameIncludesFcs",
        ),
        "authentication retention must derive FCS from retained length",
    )
    for marker in (
        "esp_wifi_80211_tx",
        "esp_wifi_connect",
        "esp_wifi_set_config",
        "WIFI_MODE_AP",
        "WIFI_MODE_APSTA",
    ):
        require(failures, marker not in board,
                f"live authentication adapter gained TX/connect path: {marker}")

    # The survey worker owns the RF backend while authentication is waiting.
    # It may publish Idle/reset only after the exact terminal timeline/backend/
    # scanner/deadline predicate proves quiescence. A failed proof must remain a
    # visible, non-Idle ResultBeforeCleanup state for a later Back retry.
    compact_entry = compact_cpp(arduino_entry)
    safety_authentication = section(
        compact_entry,
        "voidquiesceWifiAuthenticationOnSafetyStop()",
        "boolstopWifiChannelsProduct()",
    )
    main_loop = section(compact_entry, "voidloop()", "voidsetup()")
    worker_deadline = section(
        compact_entry,
        "voidserviceWorkerDeadlineSupervisor()",
        "boolarmRuntimeSafetyWatchdog()",
    )
    survey_terminal_release = section(
        compact_entry,
        "voidreleaseProductSurveyAfterTerminal(",
        "voidserviceProductSurveyWorker()",
    )
    authentication_target = section(
        compact_entry, "structWifiAuthenticationTargetfinal{",
        "WifiAuthenticationProductStatewifiAuthenticationProductState=",
    )
    authentication_renderer = section(
        compact_entry, "voidrenderWifiAuthenticationHeaderRegions(",
        "voidrenderInventoryPage(",
    )
    authentication_diagnostic = section(
        compact_entry, "voidemitWifiAuthenticationCaptureState(",
        "voidemitBleDeviceDetailState(",
    )
    require(
        failures,
        bool(authentication_target) and ".label" not in authentication_target,
        "authentication target must not retain an SSID/label copy",
    )
    require_ordered(
        failures,
        safety_authentication,
        (
            "WifiAuthenticationProductState::WaitingForSurveyStop",
            "WifiAuthenticationProductState::Running",
            "authenticationCaptureStats()",
            "constboolboardDirty=",
            "WifiAuthenticationProductState::Failed",
            "if(!waitingForSurvey&&!running&&!failedCleanup)return",
            "serviceProductSurveyWorker()",
            "constboolterminalOrAlreadyReleased=",
            "WifiAuthenticationSurveyTeardownStatesurveyTeardown{",
            "terminalOrAlreadyReleased",
            "productSurveyRuntime.timelineHealthy",
            "productSurveyRuntime.identityCleanupComplete",
            "productSurveyRuntime.scannerCleanupComplete",
            "productSurveyRuntime.sourceActive",
            "productSurveyScanActive()",
            "worker.armed",
            "constboolbackendClosePermitted=",
            "wifiAuthenticationSurveyBackendClosePermitted(",
            "constboolbackendCleanup=backendClosePermitted&&",
            "closeProductSurveyBackend()",
            "surveyCleanup=backendClosePermitted&&backendCleanup&&",
            "productSurveyRuntime.cleanupComplete",
            "wifiFrameCapture.cleanupComplete()",
            "!ingress.active",
            "wifiFrameCapture.stop(endedUs)",
            "wifiFrameCapture.cleanupComplete()",
            "if(cleanup&&appRuntime.running())appRuntime.stop()",
            "constboolruntimeReleased=cleanup&&!appRuntime.running()&&"
            "appRuntime.activeResources()==0U",
            "wifiAuthenticationProductState="
            "WifiAuthenticationProductState::Failed",
            "WifiAuthenticationCaptureUiFailure::RuntimeFailed",
            "WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup",
            "authentication_safety_stop",
            "authentication_safety_cleanup_failed",
        ),
        "safety latch must boundedly stop auth capture and retain cleanup failure",
    )
    require_ordered(
        failures,
        safety_authentication,
        (
            "wifiAuthenticationSafetyCleanupActive=true",
            "serviceProductSurveyWorker()",
            "wifiAuthenticationSafetyCleanupActive=false",
        ),
        "safety survey drain must suppress generic early app release",
    )
    require(
        failures,
        "!wifiAuthenticationSafetyCleanupActive" in survey_terminal_release,
        "survey terminal path may release auth lease during safety cleanup",
    )
    require_ordered(
        failures,
        worker_deadline,
        (
            "constboolauthenticationBoardDirty=",
            "!wifiFrameCapture.cleanupComplete()",
            "constboolauthenticationSurveyDirty=",
            "productSurveyControl()!=ProductSurveyWorkerControl::Idle",
            "!productSurveyRuntime.identityCleanupComplete",
            "!productSurveyRuntime.scannerCleanupComplete",
            "!productSurveyRuntime.cleanupComplete",
            "productSurveyRuntime.sourceActive",
            "productSurveyScanActive()",
            "constboolauthenticationCleanupDeferred=",
            "WifiAuthenticationProductState::WaitingForSurveyStop",
            "WifiAuthenticationProductState::Running",
            "WifiAuthenticationProductState::Failed",
            "authenticationBoardDirty||authenticationSurveyDirty",
            "if(!authenticationCleanupDeferred&&appRuntime.running())",
            "appRuntime.stop()",
            "latchSafetyStopInTask(SafetyReason::WorkerDeadline)",
        ),
        "worker deadline may release auth RF lease before Board teardown",
    )
    require(
        failures,
        "productSurveyRuntime.sourceActive=false" not in worker_deadline,
        "worker deadline fabricates source inactivity before worker teardown",
    )
    for marker in (
        "constboolsurveyDirty=",
        "!productSurveyRuntime.identityCleanupComplete",
        "!productSurveyRuntime.scannerCleanupComplete",
        "!productSurveyRuntime.cleanupComplete",
        "productSurveyRuntime.sourceActive",
        "productSurveyScanActive()",
        "initialWorker.armed",
        "boardDirty||surveyDirty",
    ):
        require(
            failures,
            marker in safety_authentication,
            "safety cleanup omits factual dirty ownership marker: " + marker,
        )
    require(
        failures,
        "wifi_passive_capture_teardown_policy_tests.cpp" in
        (ROOT / "tools/test.sh").read_text(encoding="utf-8"),
        "teardown policy native test is not wired into host checks",
    )
    require(
        failures,
        safety_authentication.count("appRuntime.stop()") == 1 and
        safety_authentication.find("wifiFrameCapture.cleanupComplete()") <
        safety_authentication.find("appRuntime.stop()"),
        "safety latch may release foreground lease before exact auth cleanup",
    )
    require(
        failures,
        "wifiFrameCapture.reset()" not in safety_authentication and
        "resetWifiAuthenticationCaptureProduct()" not in safety_authentication,
        "safety latch must not erase failed authentication evidence/state",
    )
    require_ordered(
        failures,
        main_loop,
        (
            "if(safetySupervisor.latched())",
            "quiesceAirspaceGuardOnSafetyStop()",
            "quiesceWifiAuthenticationOnSafetyStop()",
            "if(!safetySupervisor.latched())",
            "serviceWifiAuthenticationCapture()",
        ),
        "safety latch must quiesce auth before suppressing normal services",
    )
    for forbidden_private in (
        "target_bssid", "target_identity_hash", "identity_hash",
        "%02X:%02X:%02X:%02X:%02X:%02X",
    ):
        require(
            failures,
            forbidden_private not in authentication_renderer and
            forbidden_private not in authentication_diagnostic,
            f"authentication product UI/diagnostic leaks {forbidden_private}",
        )
    require_ordered(
        failures,
        authentication_renderer,
        (
            "renderWifiAuthenticationHeaderRegions(",
            "tr(model.title)",
            "renderHeaderStatus()",
            "WifiAuthSelectedTargetFormat",
            "kWifiAuthenticationTitleRegion",
            "renderWifiAuthenticationHeaderRegions(model)",
            "++wifiAuthenticationChromeRepaints",
        ),
        "authentication lifecycle title/RX header must repaint incrementally",
    )
    require(
        failures,
        "renderHeader(\"\",clearContent)" in authentication_renderer and
        "renderWifiAuthenticationTarget()" in authentication_renderer,
        "authentication screen must render a generic selected target",
    )
    survey_authentication = section(
        compact_entry,
        "render=false;}else{if(surveyWorkflow.state()==",
        "}else{constboolwindowClosed=closeProductSurveyScanWindow(",
    )
    return_after_survey = braced_block(
        survey_authentication,
        "if(wifiAuthenticationReturnAfterSurveyStop)",
    )
    quiescent_survey_reset = braced_block(
        survey_authentication,
        "if(surveyQuiescent)",
    )
    quiescent_back_release = braced_block(
        return_after_survey,
        "if(surveyQuiescent)",
    )
    for name, value in (
        ("survey authentication terminal", survey_authentication),
        ("Back-after-survey branch", return_after_survey),
        ("quiescent survey reset", quiescent_survey_reset),
        ("quiescent Back release", quiescent_back_release),
    ):
        require(failures, bool(value),
                f"missing authentication cleanup lifecycle section: {name}")
    exact_quiescence_markers = (
        "timelineCancelled",
        "backendCleanup",
        "productSurveyRuntime.scannerCleanupComplete",
        "productSurveyRuntime.cleanupComplete",
        "sourceInactive",
        "!worker.armed",
    )
    require_ordered(
        failures,
        survey_authentication,
        (
            "constboolsurveyQuiescent=",
            *exact_quiescence_markers,
            "if(surveyQuiescent)",
            "setProductSurveyControl(ProductSurveyWorkerControl::Idle)",
            "surveyPipeline.resetToSetup()",
            "productSurveyTimeline.reset()",
            "if(wifiAuthenticationReturnAfterSurveyStop)",
        ),
        "survey Idle/reset must follow exact quiescence",
    )
    for marker in (
        "setProductSurveyControl(ProductSurveyWorkerControl::Idle)",
        "surveyPipeline.resetToSetup()",
        "productSurveyTimeline.reset()",
    ):
        require(
            failures,
            survey_authentication.count(marker) == 1 and
            marker in quiescent_survey_reset,
            f"survey terminal operation escaped quiescent branch: {marker}",
        )
    require(
        failures,
        survey_authentication.count(
            "wifiAuthenticationProductState=WifiAuthenticationProductState::Idle"
        ) == 1 and
        "wifiAuthenticationProductState=WifiAuthenticationProductState::Idle"
        in quiescent_back_release,
        "Back-during-survey may publish authentication Idle before quiescence",
    )
    require_ordered(
        failures,
        return_after_survey,
        (
            "if(surveyQuiescent)",
            "wifiAuthenticationProductState="
            "WifiAuthenticationProductState::Idle",
            "wifiProductView=WifiProductView::Menu",
            "}else{",
            "wifiAuthenticationProductState="
            "WifiAuthenticationProductState::Failed",
            "wifiAuthenticationFailure="
            "WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup",
            "authentication_survey_cleanup_failed",
        ),
        "failed survey teardown must remain non-Idle and visible",
    )

    # Back from ResultBeforeCleanup is the recovery path. It must re-prove the
    # same strong quiescence predicate and return before releasing/resetting on
    # any failed predicate; only then may it clear worker ownership and UI state.
    leave_authentication = section(
        compact_entry,
        "boolleaveWifiAuthenticationCapture()",
        "voidserviceWifiAuthenticationCapture()",
    )
    cleanup_retry = braced_block(
        leave_authentication,
        "if(wifiAuthenticationProductState=="
        "WifiAuthenticationProductState::Failed&&"
        "wifiAuthenticationFailure=="
        "WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup&&"
        "productSurveyControl()!=ProductSurveyWorkerControl::Idle)",
    )
    failed_quiescence = braced_block(
        cleanup_retry, "if(!surveyQuiescent)")
    for name, value in (
        ("leave authentication", leave_authentication),
        ("ResultBeforeCleanup retry", cleanup_retry),
        ("failed quiescence guard", failed_quiescence),
    ):
        require(failures, bool(value),
                f"missing authentication Back cleanup section: {name}")
    require_ordered(
        failures,
        cleanup_retry,
        (
            "constWorkerDeadlineSnapshotworker=workerDeadlineSnapshot()",
            "constbooltimelineTerminal=",
            "productSurveyTimeline.state()==SourceTimelineState::Cancelled",
            "WifiAuthenticationSurveyTeardownStatesurveyTeardown{",
            "timelineTerminal",
            "productSurveyRuntime.timelineHealthy",
            "productSurveyRuntime.identityCleanupComplete",
            "productSurveyRuntime.scannerCleanupComplete",
            "productSurveyRuntime.sourceActive",
            "productSurveyScanActive()",
            "worker.armed",
            "constboolbackendClosePermitted=",
            "wifiAuthenticationSurveyBackendClosePermitted(",
            "surveyTeardown",
            "constboolbackendCleanup=backendClosePermitted&&",
            "closeProductSurveyBackend()",
            "constboolsurveyQuiescent=",
            "backendClosePermitted",
            "backendCleanup",
            "productSurveyRuntime.cleanupComplete",
            "if(!surveyQuiescent)",
            "returntrue",
            "setProductSurveyControl(ProductSurveyWorkerControl::Idle)",
            "surveyPipeline.resetToSetup()",
            "productSurveyTimeline.reset()",
        ),
        "ResultBeforeCleanup Back may release before exact quiescence",
    )
    require(
        failures,
        cleanup_retry.count("closeProductSurveyBackend()") == 1 and
        "constboolbackendCleanup=backendClosePermitted&&"
        "closeProductSurveyBackend()" in cleanup_retry and
        cleanup_retry.find("wifiAuthenticationSurveyBackendClosePermitted(") <
        cleanup_retry.find("closeProductSurveyBackend()"),
        "ResultBeforeCleanup Back may close survey backend without policy proof",
    )
    require(
        failures,
        "wifiAuthenticationProductState="
        "WifiAuthenticationProductState::Idle" not in cleanup_retry and
        "resetWifiAuthenticationCaptureProduct()" not in cleanup_retry and
        "wifiProductView=WifiProductView::Menu" not in cleanup_retry,
        "ResultBeforeCleanup retry directly clears authentication state",
    )
    require(
        failures,
        "returntrue" in failed_quiescence and
        "setProductSurveyControl(ProductSurveyWorkerControl::Idle)" not in
        failed_quiescence and
        "resetWifiAuthenticationCaptureProduct()" not in failed_quiescence,
        "failed quiescence does not preserve the non-Idle failure state",
    )
    require_ordered(
        failures,
        leave_authentication,
        (
            "WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup",
            "if(!surveyQuiescent)",
            "returntrue",
            "setProductSurveyControl(ProductSurveyWorkerControl::Idle)",
            "if(capture.state==WifiFrameCaptureState::Running",
            "wifiAuthenticationProductState="
            "WifiAuthenticationProductState::Failed",
            "wifiAuthenticationFailure="
            "WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup",
            "returntrue",
            "wifiFrameCapture.reset()",
            "resetWifiAuthenticationCaptureProduct()",
            "wifiProductView=WifiProductView::Menu",
        ),
        "Back must preserve cleanup failure until receiver and survey quiesce",
    )

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
