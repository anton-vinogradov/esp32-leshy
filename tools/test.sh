#!/usr/bin/env bash
# Fast host-side tests for the hardware-independent firmware core.
set -euo pipefail

# HIL runner unit tests import pyserial even though they never open a device.
# Prefer the already provisioned PlatformIO environment so this one-command
# host suite behaves the same from an interactive shell and from automation.
if [[ -x "$HOME/.platformio/penv/bin/python3" ]]; then
    export PATH="$HOME/.platformio/penv/bin:$PATH"
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

retained_evidence_mode="${LESHY_RETAINED_EVIDENCE_MODE:-full}"
case "$retained_evidence_mode" in
    full|tracked) ;;
    *)
        echo "invalid LESHY_RETAINED_EVIDENCE_MODE: $retained_evidence_mode" >&2
        exit 2
        ;;
esac

run_opaque_evidence_check() {
    if [[ "$retained_evidence_mode" == "full" ]]; then
        python3 "$repo_dir/$1"
    fi
}

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/src" \
    "$repo_dir/tests/native/runtime_tests.cpp" \
    "$repo_dir/src/core/navigation/Navigator.cpp" \
    "$repo_dir/src/core/runtime/ResourceBroker.cpp" \
    "$repo_dir/src/core/runtime/Application.cpp" \
    -o "$test_tmp/runtime_tests"

"$test_tmp/runtime_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/clean_target_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/InfraredCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/InfraredCsv.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/RadiotapPcap.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/SubGhzRawCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/SubGhzRawCsv.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/WifiFrameCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/library/LibraryController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/library/SessionCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/self_test/SelfTestController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/spectrum/Cc1101SpectrumController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/spectrum/Cc1101SignalFinder.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/spectrum/Nrf24SignalFinder.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/spectrum/Nrf24SpectrumController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/spectrum/SpectrumViewport.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/ProductSurveyAdmission.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyPipeline.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveySourceController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyWorkflow.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/ble/BleCompanyDatabase.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/ble/BleDeviceCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/ble/BleDeviceIntelligence.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/wifi/WifiNetworkCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/wifi/WifiDeviceCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/wifi/WifiOuiDatabase.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/wifi/WifiChannelLoad.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/apps/AppCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/hardware/HardwareInventory.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/ble/BlePassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/radio/Cc1101PassiveSpectrum.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/radio/ShieldReceiverIdentity.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/radio/Nrf24PassiveSpectrum.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/AppRuntime.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/ResourceBroker.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/safety/SafetySupervisor.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/safety/WorkerDeadlineSupervisor.cpp" \
    "$repo_dir/firmware/leshy1/src/platform/arduino/RamSessionStoreIo.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/BootReport.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/HilSession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/power/PowerSafetyPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/IngressTiming.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/ObservationQueue.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SessionBatchPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceDegradation.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/MediaDiscovery.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/MountPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProductStorePolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProductBootRetry.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProductStartRetry.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdIdentification.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdIdentificationTransport.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdReadOnlyProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdSectorInspection.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdSpiWireCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStoreBoundary.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStoreIoRouter.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageGuard.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageTiming.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/Pcf8574ButtonInput.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/TouchInput.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/TouchTargets.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/InterfaceSettingsController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/AntennaStatusController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/LanguageController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiStrings.cpp" \
    -o "$test_tmp/clean_target_tests"

"$test_tmp/clean_target_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/ble_inspector_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/ResourceBroker.cpp" \
    "$repo_dir/firmware/leshy1/src/services/ble/BleInspector.cpp" \
    -o "$test_tmp/ble_inspector_tests"

"$test_tmp/ble_inspector_tests"
python3 "$repo_dir/tools/check_ble_inspector_contract.py"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/field_survey_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/FieldSurveyCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/FieldSurveyNativeCsv.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/FieldSurveyStation.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/FieldSurveyTracker.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/FieldSurveyWigleCsv.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    -o "$test_tmp/field_survey_tests"

"$test_tmp/field_survey_tests"
python3 "$repo_dir/tools/check_field_survey_product_contract.py"
python3 "$repo_dir/tools/check_field_survey_preflight_acceptance.py"
python3 "$repo_dir/tools/check_field_survey_visits_acceptance.py"
python3 "$repo_dir/tools/check_field_survey_export_acceptance.py"
python3 "$repo_dir/tools/check_field_survey_station_acceptance.py"
python3 "$repo_dir/tools/check_field_survey_trusted_context_acceptance.py"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/airspace_guard_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/guard/AirspaceGuard.cpp" \
    -o "$test_tmp/airspace_guard_tests"

"$test_tmp/airspace_guard_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_capture_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationCapture.cpp" \
    -o "$test_tmp/wifi_authentication_capture_tests"

"$test_tmp/wifi_authentication_capture_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_artifact_policy_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationArtifactPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp" \
    -o "$test_tmp/wifi_authentication_artifact_policy_tests"

"$test_tmp/wifi_authentication_artifact_policy_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_hc22000_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationHc22000.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationArtifactPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationCapture.cpp" \
    -o "$test_tmp/wifi_authentication_hc22000_tests"

"$test_tmp/wifi_authentication_hc22000_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_passive_capture_teardown_policy_tests.cpp" \
    -o "$test_tmp/wifi_passive_capture_teardown_policy_tests"

"$test_tmp/wifi_passive_capture_teardown_policy_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_capture_presenter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationCaptureController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.cpp" \
    -o "$test_tmp/wifi_authentication_capture_presenter_tests"

"$test_tmp/wifi_authentication_capture_presenter_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_capture_controller_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationCaptureController.cpp" \
    -o "$test_tmp/wifi_authentication_capture_controller_tests"

"$test_tmp/wifi_authentication_capture_controller_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_synthetic_hil_fixture_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationSyntheticHilFixture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationArtifactPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationCaptureController.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp" \
    -o "$test_tmp/wifi_authentication_synthetic_hil_fixture_tests"

"$test_tmp/wifi_authentication_synthetic_hil_fixture_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_authentication_persistence_hil_fixture_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationPersistenceHilFixture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationHc22000.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationArtifactPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/auth/WifiAuthenticationCaptureController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/WifiFrameCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationFrameDecoder.cpp" \
    "$repo_dir/firmware/leshy1/src/services/auth/WifiAuthenticationCapture.cpp" \
    -o "$test_tmp/wifi_authentication_persistence_hil_fixture_tests"

"$test_tmp/wifi_authentication_persistence_hil_fixture_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/airspace_guard_controller_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/guard/AirspaceGuardController.cpp" \
    -o "$test_tmp/airspace_guard_controller_tests"

"$test_tmp/airspace_guard_controller_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/airspace_guard_presenter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/guard/AirspaceGuardController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/AirspaceGuardPresenter.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiStrings.cpp" \
    -o "$test_tmp/airspace_guard_presenter_tests"

"$test_tmp/airspace_guard_presenter_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_foundation_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetMerge.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/ObservationTargetAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetService.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStoreBoundary.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/TargetCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/TargetStore.cpp" \
    -o "$test_tmp/target_foundation_tests"

"$test_tmp/target_foundation_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_correlation_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetService.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/CorrelationService.cpp" \
    -o "$test_tmp/target_correlation_tests"

"$test_tmp/target_correlation_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/session_correlation_review_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetComparison.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/ObservationTargetAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SurveySessionTargetEvidenceLookup.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/CorrelationService.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SessionCorrelationReview.cpp" \
    -o "$test_tmp/session_correlation_review_tests"

"$test_tmp/session_correlation_review_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_merge_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetMerge.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetMergeService.cpp" \
    -o "$test_tmp/target_merge_tests"

"$test_tmp/target_merge_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_comparison_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetComparison.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SurveySessionTargetEvidenceLookup.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetComparisonService.cpp" \
    -o "$test_tmp/target_comparison_tests"

"$test_tmp/target_comparison_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_protocol_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    -o "$test_tmp/companion_protocol_tests"

"$test_tmp/companion_protocol_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_web_adapter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp" \
    -o "$test_tmp/companion_web_adapter_tests"

"$test_tmp/companion_web_adapter_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_connectivity_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionConnectivity.cpp" \
    -o "$test_tmp/companion_connectivity_tests"

"$test_tmp/companion_connectivity_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_read_adapter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionReadAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetComparison.cpp" \
    -o "$test_tmp/companion_read_adapter_tests"

"$test_tmp/companion_read_adapter_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_mutation_adapter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionMutationAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetService.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    -o "$test_tmp/companion_mutation_adapter_tests"

"$test_tmp/companion_mutation_adapter_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/session_target_admission_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/ObservationTargetAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SessionTargetAdmission.cpp" \
    -o "$test_tmp/session_target_admission_tests"

"$test_tmp/session_target_admission_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/session_pair_recovery_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/platform/arduino/RamSessionStoreIo.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    -o "$test_tmp/session_pair_recovery_tests"

"$test_tmp/session_pair_recovery_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/authentication_capture_storage_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    -o "$test_tmp/authentication_capture_storage_tests"

"$test_tmp/authentication_capture_storage_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/targets_controller_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/targets/TargetsController.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetComparison.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/ObservationTargetAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/CorrelationService.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SessionCorrelationReview.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SessionTargetAdmission.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/SurveySessionTargetEvidenceLookup.cpp" \
    "$repo_dir/firmware/leshy1/src/services/targets/TargetComparisonService.cpp" \
    -o "$test_tmp/targets_controller_tests"

"$test_tmp/targets_controller_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_state_persistence_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Correlation.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetMerge.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStoreBoundary.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/TargetCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/TargetStateStore.cpp" \
    -o "$test_tmp/target_state_persistence_tests"

"$test_tmp/target_state_persistence_tests"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy_fixture/src" \
    "$repo_dir/tests/native/ir_fixture_tests.cpp" \
    "$repo_dir/firmware/leshy_fixture/src/FixtureSession.cpp" \
    -o "$test_tmp/ir_fixture_tests"

"$test_tmp/ir_fixture_tests"
python3 "$repo_dir/tools/check_ir_fixture_contract.py"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/storage_filesystem_fixture.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageGuard.cpp" \
    -o "$test_tmp/storage_filesystem_fixture"

"$test_tmp/storage_filesystem_fixture" --output "$test_tmp/storage-filesystem-fixture.json"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/diagnostics/hil_probe/include" \
    "$repo_dir/diagnostics/hil_probe/test/probe_logic_tests.cpp" \
    -o "$test_tmp/hil_probe_logic_tests"

"$test_tmp/hil_probe_logic_tests"
python3 "$repo_dir/tools/check_hil_probe.py"
python3 "$repo_dir/tools/check_clean_target.py"
python3 "$repo_dir/tools/check_keypad_acceptance.py"
python3 "$repo_dir/tools/check_product_boot_acceptance.py"
python3 "$repo_dir/tools/check_product_survey_acceptance.py"
python3 "$repo_dir/tools/check_product_repeatability_acceptance.py"
python3 "$repo_dir/tools/check_product_endurance_acceptance.py"
python3 "$repo_dir/tools/check_product_endurance_release_acceptance.py"
python3 "$repo_dir/tools/check_product_recovery_acceptance.py"
python3 "$repo_dir/tools/check_product_start_resilience_acceptance.py"
python3 "$repo_dir/tools/check_product_boot_resilience_acceptance.py"
python3 "$repo_dir/tools/check_product_hardware_watchdog_acceptance.py"
python3 "$repo_dir/tools/check_worker_deadline_supervision.py"
python3 "$repo_dir/tools/check_worker_deadline_acceptance.py"
python3 "$repo_dir/tools/check_worker_deadline_ble_acceptance.py"
python3 "$repo_dir/tools/check_visual_system_acceptance.py"
python3 "$repo_dir/tools/check_self_test_acceptance.py"
python3 "$repo_dir/tools/check_targets_product_contract.py"
python3 "$repo_dir/tools/check_companion_protocol_contract.py"
python3 "$repo_dir/tools/check_airspace_guard_contract.py"
python3 "$repo_dir/tools/check_wifi_authentication_capture_contract.py"
python3 "$repo_dir/tools/check_wifi_authentication_capture_presenter_contract.py"
python3 "$repo_dir/tools/check_wifi_authentication_transition_contract.py"
python3 "$repo_dir/tools/check_wifi_authentication_synthetic_hil_contract.py"
python3 "$repo_dir/tools/check_wifi_authentication_persistence_hil_contract.py"
wifi_auth_capture_version="$(python3 "$repo_dir/tools/read_1x_version.py")"
wifi_auth_capture_positive="$repo_dir/tests/hil/evidence/board-01-wifi-authentication-capture-$wifi_auth_capture_version"
wifi_auth_capture_expectations="$repo_dir/tests/hil/evidence/board-01-wifi-authentication-capture-$wifi_auth_capture_version-acceptance.json"
if [[ -e "$wifi_auth_capture_positive" || -L "$wifi_auth_capture_positive" || \
      -e "$wifi_auth_capture_expectations" || -L "$wifi_auth_capture_expectations" ]]; then
    if [[ -L "$wifi_auth_capture_positive" || \
          -L "$wifi_auth_capture_expectations" || \
          ! -d "$wifi_auth_capture_positive" || \
          ! -f "$wifi_auth_capture_expectations" ]]; then
        echo "FAIL: CAP049 retained evidence is partial, symlinked, or has the wrong type; a regular bundle directory and acceptance JSON are required" >&2
        exit 1
    fi
    python3 "$repo_dir/tools/check_wifi_authentication_capture_hil_acceptance.py" \
        --expectations "$wifi_auth_capture_expectations" \
        --positive "$wifi_auth_capture_positive" \
        --expected-version "$wifi_auth_capture_version" \
        --expected-source-commit "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' "$wifi_auth_capture_expectations")" \
        --expected-firmware-sha256 "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["firmware_sha256"])' "$wifi_auth_capture_expectations")" \
        --expected-app-elf-sha256 "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["app_elf_sha256"])' "$wifi_auth_capture_expectations")" \
        --expected-runner-sha256 "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["runner_source_sha256"])' "$wifi_auth_capture_expectations")"
else
    echo "INFO: no same-version legacy CAP049 capture-navigation bundle for $wifi_auth_capture_version; the authoritative persistence gate is checked below"
fi
wifi_auth_persistence_positive="$repo_dir/tests/hil/evidence/board-01-wifi-authentication-persistence-$wifi_auth_capture_version"
wifi_auth_persistence_expectations="$repo_dir/tests/hil/evidence/board-01-wifi-authentication-persistence-$wifi_auth_capture_version-acceptance.json"
if [[ -e "$wifi_auth_persistence_positive" || -L "$wifi_auth_persistence_positive" || \
      -e "$wifi_auth_persistence_expectations" || -L "$wifi_auth_persistence_expectations" ]]; then
    if [[ -L "$wifi_auth_persistence_positive" || \
          -L "$wifi_auth_persistence_expectations" || \
          ! -d "$wifi_auth_persistence_positive" || \
          ! -f "$wifi_auth_persistence_expectations" ]]; then
        echo "FAIL: CAP049 persistence evidence is partial, symlinked, or has the wrong type; a regular bundle directory and acceptance JSON are required" >&2
        exit 1
    fi
    PYTHONPATH="$repo_dir/tools" python3 \
        "$repo_dir/tools/check_wifi_authentication_persistence_hil_run.py" \
        --version "$wifi_auth_capture_version" \
        --positive "$wifi_auth_persistence_positive" \
        --expectations "$wifi_auth_persistence_expectations"
else
    echo "PENDING: no retained CAP049 persistence evidence for $wifi_auth_capture_version; persistence acceptance is skipped and remains open"
fi
airspace_guard_positive="$repo_dir/tests/hil/evidence/board-01-airspace-guard-1.0.0-dev.242"
airspace_guard_negative_dev239="$repo_dir/tests/hil/evidence/board-01-airspace-guard-1.0.0-dev.239-failed.json"
airspace_guard_negative_dev241="$repo_dir/tests/hil/evidence/board-01-airspace-guard-1.0.0-dev.241-failed.json"
airspace_guard_expectations="$repo_dir/tests/hil/evidence/board-01-airspace-guard-1.0.0-dev.242-acceptance.json"
python3 "$repo_dir/tools/check_airspace_guard_hil_acceptance.py" \
    --expectations "$airspace_guard_expectations" \
    --positive "$airspace_guard_positive" \
    --negative-dev239 "$airspace_guard_negative_dev239" \
    --negative-dev241 "$airspace_guard_negative_dev241"
python3 "$repo_dir/tools/check_companion_post_web_memory_contract.py"
python3 "$repo_dir/tools/check_companion_post_web_acceptance.py"
python3 "$repo_dir/tools/check_stage_demo_s6_contract.py"
if [[ -f "$repo_dir/tests/hil/evidence/board-01-stage-demo-s6-1.0.0-dev.209.json" ]]; then
    python3 "$repo_dir/tools/check_stage_demo_s6_acceptance.py"
fi
python3 "$repo_dir/tools/generate_companion_web_asset.py" --check
python3 "$repo_dir/tools/check_native_usb_reset_contract.py"
python3 "$repo_dir/tools/check_platformio_workspace_isolation.py"
python3 "$repo_dir/tools/check_targets_stack_failure_evidence.py"
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-0.149.json" ]]; then
    python3 "$repo_dir/tools/check_targets_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-load-memory-0.160.json" ]]; then
    python3 "$repo_dir/tools/check_targets_load_memory_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-merge-split-0.165.json" ]]; then
    python3 "$repo_dir/tools/check_targets_merge_split_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-companion-usb-read-0.170.json" ]]; then
    python3 "$repo_dir/tools/check_companion_usb_delta_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-companion-target-mutate-0.172.json" ]]; then
    python3 "$repo_dir/tools/check_companion_mutation_delta_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-companion-web-lifecycle-0.181.json" ]]; then
    python3 "$repo_dir/tools/check_companion_web_lifecycle_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-companion-offline-0.195.json" ]]; then
    python3 "$repo_dir/tools/check_companion_offline_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-evidence-0.150.json" ]]; then
    python3 "$repo_dir/tools/check_targets_evidence_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-favorite-0.151.json" ]]; then
    python3 "$repo_dir/tools/check_targets_favorite_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-name-0.152.json" ]]; then
    python3 "$repo_dir/tools/check_targets_name_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-tags-0.153.json" ]]; then
    python3 "$repo_dir/tools/check_targets_tags_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-notes-0.154.json" ]]; then
    python3 "$repo_dir/tools/check_targets_notes_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-correlation-0.155.json" ]]; then
    python3 "$repo_dir/tools/check_targets_correlation_hil_acceptance.py"
fi
if [[ -f "$repo_dir/tests/hil/evidence/board-01-targets-correlation-reject-0.156.json" ]]; then
    python3 "$repo_dir/tools/check_targets_correlation_reject_hil_acceptance.py"
fi
if [[ -f "$repo_dir/firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.elf" ]]; then
    python3 "$repo_dir/tools/check_targets_stack_elf_contract.py" \
        --elf "$repo_dir/firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.elf"
    python3 "$repo_dir/tools/check_airspace_guard_stack_elf_contract.py" \
        --elf "$repo_dir/firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.elf"
fi
python3 "$repo_dir/tools/check_full_guided_s5_rx_contract.py"
python3 "$repo_dir/tools/check_full_guided_s5_rx_delta_acceptance.py"
python3 "$repo_dir/tools/check_ui_components_acceptance.py"
python3 "$repo_dir/tools/check_ui_language_contract.py"
python3 "$repo_dir/tools/check_interface_settings_contract.py"
python3 "$repo_dir/tools/check_antenna_status_leds_contract.py"
python3 "$repo_dir/tools/check_antenna_status_leds_acceptance.py"
python3 "$repo_dir/tools/check_cadence_full_acceptance.py"
python3 "$repo_dir/tools/check_interface_settings_hil_acceptance.py"
python3 "$repo_dir/tools/check_product_ui_content.py"
python3 "$repo_dir/tools/check_wifi_networks_contract.py"
python3 "$repo_dir/tools/check_wifi_network_hil_selector_contract.py"
python3 "$repo_dir/tools/check_wifi_networks_acceptance.py"
python3 "$repo_dir/tools/check_wifi_network_live_radar_acceptance.py"
python3 "$repo_dir/tools/check_stable_network_nav_acceptance.py"
python3 "$repo_dir/tools/check_wifi_devices_contract.py"
python3 "$repo_dir/tools/check_wifi_devices_acceptance.py"
python3 "$repo_dir/tools/check_wifi_device_intelligence_acceptance.py"
python3 "$repo_dir/tools/check_wifi_device_live_detail_acceptance.py"
python3 "$repo_dir/tools/check_wifi_channels_contract.py"
python3 "$repo_dir/tools/check_wifi_channels_acceptance.py"
python3 "$repo_dir/tools/check_wifi_channel_average_acceptance.py"
python3 "$repo_dir/tools/check_wifi_channel_choice_acceptance.py"
python3 "$repo_dir/tools/check_wifi_channel_neutral_bars_acceptance.py"
python3 "$repo_dir/tools/check_wifi_capture_product_contract.py"
python3 "$repo_dir/tools/check_wifi_capture_product_acceptance.py"
python3 "$repo_dir/tools/check_ble_nearby_contract.py"
python3 "$repo_dir/tools/check_ble_nearby_acceptance.py"
python3 "$repo_dir/tools/check_ble_device_intelligence_acceptance.py"
python3 "$repo_dir/tools/check_signal_order_acceptance.py"
python3 "$repo_dir/tools/check_dense_details_acceptance.py"
python3 "$repo_dir/tools/check_product_content_acceptance.py"
python3 "$repo_dir/tools/check_ui_language_acceptance.py"
python3 "$repo_dir/tools/check_ui_typography_acceptance.py"
python3 "$repo_dir/tools/check_ui_accessibility_contract.py"
python3 "$repo_dir/tools/check_ui_accessibility_acceptance.py"
python3 "$repo_dir/tools/check_ui_navigation_acceptance.py"
python3 "$repo_dir/tools/check_ui_states_acceptance.py"
python3 "$repo_dir/tools/check_stage_demo_s2_acceptance.py"
python3 "$repo_dir/tools/check_s3_product_progress.py"
run_opaque_evidence_check tools/check_product_survey_worker_acceptance.py
run_opaque_evidence_check tools/check_product_survey_terminal_ack_acceptance.py
run_opaque_evidence_check tools/check_product_survey_active_cancel_acceptance.py
python3 "$repo_dir/tools/check_product_survey_missing_source_acceptance.py"
python3 "$repo_dir/tools/check_littlefs_parity_acceptance.py"
python3 "$repo_dir/tools/check_littlefs_reset_matrix_acceptance.py"
run_opaque_evidence_check tools/check_stage_demo_s3_acceptance.py
python3 "$repo_dir/tools/check_survey_source_plan_acceptance.py"
run_opaque_evidence_check tools/check_source_timeline_runtime_acceptance.py
run_opaque_evidence_check tools/check_source_timeline_persistence_acceptance.py
python3 "$repo_dir/tools/check_passive_ble_acceptance.py"
run_opaque_evidence_check tools/check_runtime_degradation_acceptance.py
python3 "$repo_dir/tools/check_observation_browser_acceptance.py"
python3 "$repo_dir/tools/check_capture_export_acceptance.py"
run_opaque_evidence_check tools/check_wifi_frame_capture_acceptance.py
python3 "$repo_dir/tools/check_persistent_wifi_capture_acceptance.py"
python3 "$repo_dir/tools/check_authentication_capture_storage_contract.py"
python3 -m unittest "$repo_dir/tools/test_authentication_capture_storage_contract.py"
python3 "$repo_dir/tools/check_self_test_coverage_acceptance.py"
python3 "$repo_dir/tools/check_shield_receiver_self_test_acceptance.py"
python3 "$repo_dir/tools/check_isolated_main_miso_contract.py"
python3 "$repo_dir/tools/check_carrier_csn_contract.py"
python3 "$repo_dir/tools/check_infrared_station_ab_evidence.py"
run_opaque_evidence_check tools/check_nrf24_spectrum_acceptance.py
python3 "$repo_dir/tools/check_nrf24_signal_finder_contract.py"
run_opaque_evidence_check tools/check_nrf24_signal_finder_acceptance.py
run_opaque_evidence_check tools/check_cc1101_spectrum_acceptance.py
python3 "$repo_dir/tools/check_cc1101_signal_finder_contract.py"
run_opaque_evidence_check tools/check_cc1101_signal_finder_acceptance.py
python3 "$repo_dir/tools/check_full_guided_rf_acceptance.py"
run_opaque_evidence_check tools/check_full_guided_artifact_acceptance.py
run_opaque_evidence_check tools/check_full_guided_disposable_acceptance.py
run_opaque_evidence_check tools/check_full_guided_heap_budget_acceptance.py
run_opaque_evidence_check tools/check_touch_input_acceptance.py
python3 "$repo_dir/tools/check_product_menu_acceptance.py"
run_opaque_evidence_check tools/check_clean_status_acceptance.py
run_opaque_evidence_check tools/check_spectrum_views_acceptance.py
run_opaque_evidence_check tools/check_product_home_acceptance.py
run_opaque_evidence_check tools/check_home_identity_acceptance.py
run_opaque_evidence_check tools/check_inline_key_hints_acceptance.py
run_opaque_evidence_check tools/check_compact_ui_waterfall_acceptance.py
run_opaque_evidence_check tools/check_receiver_paced_waterfall_acceptance.py
run_opaque_evidence_check tools/check_source_history_waterfall_acceptance.py
python3 "$repo_dir/tools/check_live_render_contract.py"
python3 "$repo_dir/tools/check_spectrum_workspace_contract.py"
PYTHONPATH="$repo_dir/tools" python3 -m unittest \
    "$repo_dir/tools/test_spectrum_workspace_contract.py"
run_opaque_evidence_check tools/check_subghz_raw_acceptance.py
python3 "$repo_dir/tools/check_subghz_fsk_contract.py"
python3 "$repo_dir/tools/check_subghz_fsk_delta_acceptance.py"
python3 "$repo_dir/tools/check_early_boot_watchdog_contract.py"
run_opaque_evidence_check tools/check_safety_watchdog_acceptance.py
python3 "$repo_dir/tools/check_worker_preparation_deadline_acceptance.py"
python3 "$repo_dir/tools/check_capture_store_deadline_acceptance.py"
python3 "$repo_dir/tools/check_infrared_store_deadline_acceptance.py"
python3 "$repo_dir/tools/check_s5_runtime_completeness_contract.py"
run_opaque_evidence_check tools/check_s5_runtime_completeness_acceptance.py
python3 "$repo_dir/tools/check_sd_power_cut_acceptance.py"
python3 "$repo_dir/tools/check_release_hil_acceptance.py"
if [[ "$retained_evidence_mode" == "tracked" ]]; then
    python3 "$repo_dir/tools/check_tracked_hil_evidence.py"
    python3 "$repo_dir/tools/hil_evidence.py" verify \
        --index "$repo_dir/tests/hil/evidence/declarative-hil-index.json"
    python3 "$repo_dir/tools/check_product_home_acceptance.py" --tracked-only
    python3 "$repo_dir/tools/check_home_identity_acceptance.py" --tracked-only
    python3 "$repo_dir/tools/check_inline_key_hints_acceptance.py" --tracked-only
    python3 "$repo_dir/tools/check_compact_ui_waterfall_acceptance.py" --tracked-only
    python3 "$repo_dir/tools/check_receiver_paced_waterfall_acceptance.py" --tracked-only
    python3 "$repo_dir/tools/check_source_history_waterfall_acceptance.py" --tracked-only
fi
python3 "$repo_dir/tools/test_sd_reset_runner.py"
python3 "$repo_dir/tools/test_build_budget.py"
python3 "$repo_dir/tools/test_hil_scenario_runner.py"
python3 "$repo_dir/tools/test_hil_board_profile.py"
python3 "$repo_dir/tools/test_ir_two_board_hil.py"
python3 "$repo_dir/tools/test_s5_two_board_retention.py"
python3 "$repo_dir/tools/check_s5_two_board_matrix.py" --help >/dev/null
python3 "$repo_dir/tools/retain_s5_two_board_matrix.py" --help >/dev/null
python3 "$repo_dir/tools/test_sd_power_cut_runner.py"
python3 "$repo_dir/tools/test_prerelease_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_hil_runner.py"
python3 "$repo_dir/tools/test_field_survey_hil_runner.py"
PYTHONPATH="$repo_dir/tools" python3 -m unittest \
    "$repo_dir/tools/test_field_survey_preflight_acceptance.py"
python3 "$repo_dir/tools/test_product_home_hil_runner.py"
python3 "$repo_dir/tools/test_airspace_guard_hil_runner.py"
python3 "$repo_dir/tools/test_airspace_guard_hil_acceptance.py"
python3 "$repo_dir/tools/test_retain_1x_airspace_guard_hil.py"
python3 "$repo_dir/tools/test_wifi_authentication_capture_hil.py"
python3 "$repo_dir/tools/test_wifi_authentication_synthetic_hil_contract.py"
python3 "$repo_dir/tools/test_wifi_authentication_persistence_hil_contract.py"
python3 "$repo_dir/tools/test_wifi_authentication_persistence_hil_runner.py"
PYTHONPATH="$repo_dir/tools" python3 -m unittest \
    "$repo_dir/tools/test_wifi_authentication_persistence_hil_evidence.py"
python3 "$repo_dir/tools/test_wifi_authentication_transition_contract.py"
python3 "$repo_dir/tools/test_retain_1x_wifi_authentication_capture_hil.py"
python3 "$repo_dir/tools/test_targets_merge_split_hil_runner.py"
python3 "$repo_dir/tools/test_companion_offline.py"
python3 "$repo_dir/tools/test_companion_usb_delta_runner.py"
python3 "$repo_dir/tools/test_companion_web_delta_runner.py"
python3 "$repo_dir/tools/test_companion_web_http_hil.py"
python3 "$repo_dir/tools/test_source_timeline_hil_runner.py"
python3 "$repo_dir/tools/test_passive_ble_hil_runner.py"
python3 "$repo_dir/tools/test_ble_nearby_entry_gate.py"
python3 "$repo_dir/tools/test_ble_nearby_run_policy.py"
python3 "$repo_dir/tools/test_top_level_menu_smoke_hil.py"
python3 "$repo_dir/tools/test_runtime_degradation_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_cancel_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_missing_source_hil_runner.py"
python3 "$repo_dir/tools/test_littlefs_parity_hil_runner.py"
python3 "$repo_dir/tools/test_littlefs_reset_matrix_hil_runner.py"
python3 "$repo_dir/tools/test_stage_demo_s3_hil_runner.py"
python3 "$repo_dir/tools/test_stage_demo_s6_hil_runner.py"
python3 "$repo_dir/tools/test_product_boot_watchdog_hil_runner.py"
python3 "$repo_dir/tools/test_capture_1x_boot.py"
python3 "$repo_dir/tools/test_early_boot_watchdog_hil_runner.py"
python3 "$repo_dir/tools/test_product_endurance_hil_runner.py"
python3 "$repo_dir/tools/test_release_hil_runner.py"
python3 "$repo_dir/tools/test_camera_subset.py"
python3 "$repo_dir/tools/test_prerelease_bundle_verifier.py"
python3 "$repo_dir/tools/test_prerelease_bundle_package.py"
python3 "$repo_dir/tools/test_release_1x.py"
python3 "$repo_dir/tools/test_hil_scope_planner.py"
python3 "$repo_dir/tools/run_1x_targets_hil.py" --help >/dev/null
python3 "$repo_dir/tools/read_1x_version.py" >/dev/null
