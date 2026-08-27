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
MUTATION_HEADER = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionMutationAdapter.h"
)
MUTATION_SOURCE = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionMutationAdapter.cpp"
)
MUTATION_TEST = ROOT / "tests/native/companion_mutation_adapter_tests.cpp"
WEB_HEADER = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.h"
)
WEB_SOURCE = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp"
)
WEB_TEST = ROOT / "tests/native/companion_web_adapter_tests.cpp"
CONNECTIVITY_HEADER = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionConnectivity.h"
)
CONNECTIVITY_SOURCE = (
    ROOT / "firmware/leshy1/src/services/companion/CompanionConnectivity.cpp"
)
CONNECTIVITY_TEST = ROOT / "tests/native/companion_connectivity_tests.cpp"
ARDUINO_WEB_HEADER = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoCompanionWebService.h"
)
ARDUINO_WEB_SOURCE = (
    ROOT / "firmware/leshy1/src/platform/arduino/ArduinoCompanionWebService.cpp"
)
MUTATION_HIL = ROOT / "tools/run_1x_companion_mutation_delta_hil.py"
WEB_HIL = ROOT / "tools/run_1x_companion_web_delta_hil.py"
WEB_HTTP_HIL = ROOT / "tools/companion_web_http_hil.py"
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
        mutation_header = MUTATION_HEADER.read_text(encoding="utf-8")
        mutation_source = MUTATION_SOURCE.read_text(encoding="utf-8")
        mutation_tests = MUTATION_TEST.read_text(encoding="utf-8")
        web_header = WEB_HEADER.read_text(encoding="utf-8")
        web_source = WEB_SOURCE.read_text(encoding="utf-8")
        web_tests = WEB_TEST.read_text(encoding="utf-8")
        connectivity_header = CONNECTIVITY_HEADER.read_text(encoding="utf-8")
        connectivity_source = CONNECTIVITY_SOURCE.read_text(encoding="utf-8")
        connectivity_tests = CONNECTIVITY_TEST.read_text(encoding="utf-8")
        arduino_web_header = ARDUINO_WEB_HEADER.read_text(encoding="utf-8")
        arduino_web_source = ARDUINO_WEB_SOURCE.read_text(encoding="utf-8")
        mutation_hil = MUTATION_HIL.read_text(encoding="utf-8")
        web_hil = WEB_HIL.read_text(encoding="utf-8")
        web_http_hil = WEB_HTTP_HIL.read_text(encoding="utf-8")
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
        "target.favorite.set",
        "target.name.set",
        "target.notes.set",
        "target.tag.add",
        "target.tag.remove",
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

    mutation_combined = mutation_header + mutation_source
    for forbidden in (
        '#include "drivers/',
        '#include "storage/',
        '#include "platform/',
        "Serial.",
        "SPI.",
        "SD.",
        "WiFi.",
    ):
        require(failures, forbidden not in mutation_combined,
                f"companion mutation adapter bypasses its boundary: {forbidden}")
    for marker in (
        "target.mutation.preview",
        "target.mutation.confirm",
        "target.mutation.status",
        "expectedRevision",
        "previewTargetAction",
        "kCompanionS65MutationScopes",
        "kCompanionTargetMutationCapabilities",
        "CompanionMutationId",
        "AlreadyConfirmed",
        "RevisionConflict",
        "decodeBase64",
        "kCompanionMaxFrameBytes + 1U",
    ):
        require(failures, marker in mutation_combined,
                f"missing mutation adapter contract: {marker}")
    for marker in (
        "testAllFiveTypedActionsAndFullNotesFitOneFrame",
        "testStrictParserRejectsMalformedAndNeverPublishesPartialOutput",
        "testPreviewUsesExactRevisionAndExplicitGrant",
        "testDeterministicBoundedResponses",
        "kCompanionMaxFrameBytes + 1U",
        "RevisionConflict",
        "CapabilityDenied",
    ):
        require(failures, marker in mutation_tests,
                f"missing mutation adapter native coverage: {marker}")

    web_combined = web_header + web_source
    for forbidden in (
        '#include "drivers/',
        '#include "storage/',
        '#include "platform/',
        "Serial.",
        "SPI.",
        "SD.",
        "WiFi.",
        "WebServer",
        "http://",
        "https://",
    ):
        require(failures, forbidden not in web_combined,
                f"companion Web presentation bypasses its boundary: {forbidden}")
    for marker in (
        'kCompanionWebApiPath = "/api/v1/companion"',
        "validateCompanionWebRequest",
        "kCompanionMaxFrameBytes",
        "deviceSessionAuthorized",
        "ChunkedUnsupported",
        "encodeCompanionWebError",
        "companionWebIndexHtml",
        "leshy.companion.request.v1",
        "target.mutation.preview",
        "target.mutation.confirm",
        "target.mutation.status",
    ):
        require(failures, marker in web_combined,
                f"missing local Web contract: {marker}")
    for marker in (
        "testExactIndexAndApiRoutes",
        "testBoundaryFailsClosedWithoutPublishingPartialRequest",
        "testExact512ByteBodyLimit",
        "testBoundedErrorsAndHttpMapping",
        "testOfflinePageUsesOnlyTheSharedContract",
        "parseCompanionConnectRequest",
    ):
        require(failures, marker in web_tests,
                f"missing local Web native coverage: {marker}")

    connectivity_combined = connectivity_header + connectivity_source
    for marker in (
        "kCompanionLocalIdleTimeoutUs",
        "10ULL * 60ULL * 1000000ULL",
        "kCompanionLocalMaximumLifetimeUs",
        "30ULL * 60ULL * 1000000ULL",
        "CompanionLocalCredentials",
        "makeCompanionLocalCredentials",
        "parseCompanionHilEntropyHex",
        "secureClear",
        "CompanionConnectivity::authorize",
        "CompanionConnectivity::recordActivity",
        "CompanionConnectivity::service",
        "CompanionConnectivity::revoke",
        "generation != generation_",
        "nowUs < startedUs_",
    ):
        require(failures, marker in connectivity_combined,
                f"missing local connectivity lifecycle: {marker}")
    for forbidden in (
        "Preferences",
        "nvs_open",
        "nvs_set_",
        "nvs_commit",
        "LittleFS",
        "SPIFFS",
        "SD.",
        "Serial.",
        "WiFi.",
    ):
        require(failures, forbidden not in connectivity_combined,
                f"ephemeral connectivity persists or bypasses its boundary: {forbidden}")
    for marker in (
        "testEphemeralCredentialsAreBoundedAndClearable",
        "testAuthorizationIsExplicitAndGenerationBound",
        "testIdleAndAbsoluteTimeoutsFailClosed",
        "testClockRollbackRevokesInsteadOfExtending",
        "testHilEntropyParsingIsExactAndFailClosed",
    ):
        require(failures, marker in connectivity_tests,
                f"missing connectivity native coverage: {marker}")

    arduino_web = arduino_web_header + arduino_web_source
    for marker in (
        "kMaximumHeaderBytes = 768",
        "kClientDeadlineUs = 3000000ULL",
        "server_(80, 1)",
        "kStaticRxBuffers = 2",
        "kDynamicRxBuffers = 1",
        "kStaticTxBuffers = 2",
        "kDynamicTxBuffers = 0",
        "init.tx_buf_type = 0",
        "init.static_tx_buf_num = kStaticTxBuffers",
        "kRxManagementBuffers = 1",
        "kCacheTxBuffers = 1",
        "kManagementShortBuffers = 6",
        "kApReadyTimeoutMs = 2000",
        "kApReadyPollMs = 10",
        "esp_netif_attach_wifi_ap",
        "esp_wifi_set_default_wifi_ap_handlers",
        "esp_wifi_set_storage(WIFI_STORAGE_RAM)",
        "esp_wifi_set_mode(WIFI_MODE_AP)",
        "config.ap.max_connection = 1",
        "config.ap.authmode = WIFI_AUTH_WPA2_PSK",
        "esp_wifi_start()",
        "millis() - readyStartedMs",
        "delay(kApReadyPollMs)",
        "ESP_ERR_TIMEOUT",
        "esp_wifi_stop()",
        "esp_wifi_deinit()",
        "esp_wifi_clear_default_wifi_driver_and_handlers",
        "esp_netif_destroy(apNetif_)",
        "Cache-Control: no-store",
        "Connection: close",
        "X-Content-Type-Options: nosniff",
        "validateCompanionWebRequest",
        "kCompanionMaxFrameBytes",
        "client_.stop()",
    ):
        require(failures, marker in arduino_web,
                f"missing bounded Arduino Web runtime: {marker}")
    for forbidden in (
        "Preferences",
        "nvs_open",
        "nvs_set_",
        "nvs_commit",
        "LittleFS",
        "SPIFFS",
        "WiFi.begin(",
        "WiFi.persistent(",
        "WiFi.softAP(",
        "WIFI_STA",
        "WIFI_AP_STA",
    ):
        require(failures, forbidden not in arduino_web,
                f"Arduino Web runtime contains ambient/persistent path: {forbidden}")

    for marker in (
        'parser.add_argument("--port", required=True)',
        '"serial_port_discovery_calls": 0',
        '"cardputer_ports_opened": 0',
        '"flash_count": 0',
        'record["flash_count"] = 1',
        'parser.add_argument("--reuse-installed-from", type=Path)',
        'precursor_candidate != record["candidate"]',
        'def leave_targets(',
        'for presses in range(1, 6)',
        'reset_and_capture_reconnecting(',
        '"open_attempts": reset_open_attempts',
        'home_denied.get("reason") == "scope_unavailable"',
        'no_op.get("reason") == "unchanged"',
        'stale.get("reason") == "revision_conflict"',
        'replay_confirm.get("reason") == "already_confirmed"',
        'state.get("mutation_write_calls") == 3',
        'state.get("mutation_file_syncs") == 3',
        'state.get("mutation_directory_syncs") == 3',
        'cold_target.get("revision") == revision_before + 2',
        '"radio_tx_commands": 0',
    ):
        require(failures, marker in mutation_hil,
                f"missing mutation delta HIL contract: {marker}")

    for marker in (
        'parser.add_argument("--port", required=True)',
        'parser.add_argument("--partitions", required=True, type=Path)',
        '"serial_port_discovery_calls": 0',
        '"cardputer_ports_opened": 0',
        '"flash_count": 0',
        'record["flash_count"] = 1',
        '"partition_flash_count": 0',
        '"performed_before_application_flash": True',
        'read_flash_with_retry(',
        '"installed partition table does not match the candidate',
        'parser.add_argument("--reuse-installed-from", type=Path)',
        'precursor_candidate_matches(',
        'parser.add_argument(\n        "--clear-proven-preexisting-safety-latch"',
        'proven_clearable_runtime_watchdog(',
        'b"safety.clear confirm"',
        '"clear_action_replays": 0',
        'safety_after.get("state") == "armed"',
        'precursor.get("checkpoint") == "console_sync"',
        'def open_console_reconnecting(',
        'write_timeout=0.5',
        '"flush_calls_during_reconnect": 0',
        '"http_exchange_tested": False',
        '"host_wifi_state_not_modified"',
        'b"companion.web.state"',
        'staged.get("authorized") is False',
        'active.get("authorized") is True',
        'active.get("targets_suspended") is True',
        'active.get("survey_worker_suspended") is True',
        'active.get("lease_mask") == 15',
        'stopped.get("credential_present") is False',
        'stopped.get("survey_worker_suspended") is True',
        'released.get("survey_worker_suspended") is False',
        'released.get("lease_mask") == 0',
        '"raw_radio_tx_commands": 0',
        'best_effort_cleanup(device)',
        '"--allow-host-wifi-change"',
        '"leshy.companion.web.seed.v1", "armed"',
        'b"companion.web.hil-proof"',
        'safe_credential_proof(',
        'active.get("dhcp_server_started") is True',
        'joined_proof.get("associated_stations") == 1',
        'normalized_pages(web_session_pages)',
        'normalized_pages(web_target_pages)',
        'normalized_pages(web_compare_pages)',
        '"target.mutation.preview", "web-first-preview"',
        '"target.mutation.confirm", "web-restore-confirm"',
        'assert_atomic_mutation_state(',
        'host_wifi["dhcp_requests"] = wifi_guard.dhcp_requests',
        'host_wifi["restored"] is True',
    ):
        require(failures, marker in web_hil,
                f"missing local Web delta HIL contract: {marker}")

    for marker in (
        'NETWORKSETUP = "/usr/sbin/networksetup"',
        'IPCONFIG = "/usr/sbin/ipconfig"',
        'derive_local_credentials',
        '"-getairportpower"',
        '"-getairportnetwork"',
        '"-setairportnetwork"',
        '"-setairportpower"',
        '"-listpreferredwirelessnetworks"',
        '"-removepreferredwirelessnetwork"',
        'temporary HIL SSID already exists as a preferred network',
        'self.association_attempts += 1',
        'self._request_dhcp_lease()',
        '["-setdhcp", self.service, client_id]',
        'explicit Wi-Fi service is not in DHCP mode',
        'self._is_hil_fingerprint(observed)',
        'self._wait_for_disconnected()',
        'urllib.request.ProxyHandler({})',
    ):
        require(failures, marker in web_http_hil,
                f"missing guarded host Web HIL boundary: {marker}")

    for marker in (
        "handleUsbCompanionFrame",
        "companionReadContext",
        "suspendProductSurveyWorkerForWebCompanion",
        "restoreProductSurveyWorkerAfterWebCompanion",
        "survey_worker_suspended",
        'uiController.page() != 7',
        'std::strcmp(targetsProductStatus, "ready") != 0',
        "policy.availableCapabilities = capabilities",
        "usbCompanionConnection = {}",
        "kUsbCommandCapacity",
        "Serial.setRxBufferSize(kUsbRxBufferCapacity)",
        "usbCommandOverflow",
        "response_encoding_failed",
        "targetsIdentityTransientRetries",
        "handleCompanionMutation",
        "requestTargetsMutationExact",
        "targetsMutationExpectedRevision",
        "companionMutationCapabilities(context.targets)",
        "CompanionMutationState::Previewed",
        "CompanionMutationState::Saving",
        "CompanionMutationStatus::AlreadyConfirmed",
        "poll(Serial, usbCommand",
        "poll(Serial0, uartCommand",
        "startWebCompanion",
        "stopWebCompanion",
        "serviceWebCompanion",
        "computeCompanionWebHilProof",
        "emitCompanionWebHilProof",
        "dhcpServerStarted",
        "associatedStations",
        "CompanionLocalStopReason::LeftForeground",
        "CompanionLocalStopReason::SafetyStop",
        "resourceBroker.acquire(AppRuntime::kForegroundOwner, espRf)",
        "resourceBroker.release(",
        "arduinoCompanionWebService.poll(",
        "CompanionTransport::LocalWeb",
        "emitCompanionWebState",
        "savingAuthorizedWebMutation",
        "targetsMutationCompanionWeb",
        '"credential_persisted\\\":false',
        '"credential_exposed_over_diagnostic\\\":false',
        "clearWebCompanionHilEntropy",
        "armCompanionWebHilEntropy",
        "computeCompanionWebHilProof",
        "emitCompanionWebHilProof",
        '"credential_material_exposed\\\":false',
        '"proof_persisted\\\":false',
        '"hil_seed_armed\\\":%s',
        "leshy.companion.web.seed.v1",
    ):
        require(failures, marker in arduino,
                f"missing native USB wiring contract: {marker}")
    require(failures,
            "sizeof(usbCommand), true" in arduino and
            "sizeof(uartCommand), false" in arduino,
            "companion JSON must be enabled only on native USB, not Serial0")
    require(failures, "handleUsbCompanionFrame(Serial0" not in arduino,
            "Serial0 must never enter the companion transport")
    require(failures, arduino.count("webCompanionCredentials.passphrase") == 2,
            "local Web passphrase must only reach the display and the "
            "active-HIL non-retained SHA-256 proof")

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
            "target.mutation.preview",
            "target.mutation.confirm",
            "target.mutation.status",
            "expected_revision",
            "mutation_id",
            "already_confirmed",
            "revision",
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
        "confirmed shared Actions and zero direct driver/storage path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
