#!/usr/bin/env bash
# Fast host-side tests for the hardware-independent firmware core.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

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
    "$repo_dir/firmware/leshy1/src/apps/capture/RadiotapPcap.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/WifiFrameCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/library/LibraryController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/library/SessionCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/self_test/SelfTestController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/ProductSurveyAdmission.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyPipeline.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveySourceController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyWorkflow.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/apps/AppCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/hardware/HardwareInventory.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/ble/BlePassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/AppRuntime.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/ResourceBroker.cpp" \
    "$repo_dir/firmware/leshy1/src/platform/arduino/RamSessionStoreIo.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/BootReport.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/HilSession.cpp" \
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
    "$repo_dir/firmware/leshy1/src/ui/LanguageController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiController.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiStrings.cpp" \
    -o "$test_tmp/clean_target_tests"

"$test_tmp/clean_target_tests"

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
python3 "$repo_dir/tools/check_product_recovery_acceptance.py"
python3 "$repo_dir/tools/check_product_start_resilience_acceptance.py"
python3 "$repo_dir/tools/check_product_boot_resilience_acceptance.py"
python3 "$repo_dir/tools/check_product_hardware_watchdog_acceptance.py"
python3 "$repo_dir/tools/check_visual_system_acceptance.py"
python3 "$repo_dir/tools/check_self_test_acceptance.py"
python3 "$repo_dir/tools/check_ui_components_acceptance.py"
python3 "$repo_dir/tools/check_ui_language_contract.py"
python3 "$repo_dir/tools/check_ui_language_acceptance.py"
python3 "$repo_dir/tools/check_ui_typography_acceptance.py"
python3 "$repo_dir/tools/check_ui_accessibility_contract.py"
python3 "$repo_dir/tools/check_ui_accessibility_acceptance.py"
python3 "$repo_dir/tools/check_ui_navigation_acceptance.py"
python3 "$repo_dir/tools/check_ui_states_acceptance.py"
python3 "$repo_dir/tools/check_stage_demo_s2_acceptance.py"
python3 "$repo_dir/tools/check_s3_product_progress.py"
python3 "$repo_dir/tools/check_product_survey_worker_acceptance.py"
python3 "$repo_dir/tools/check_product_survey_terminal_ack_acceptance.py"
python3 "$repo_dir/tools/check_product_survey_active_cancel_acceptance.py"
python3 "$repo_dir/tools/check_product_survey_missing_source_acceptance.py"
python3 "$repo_dir/tools/check_littlefs_parity_acceptance.py"
python3 "$repo_dir/tools/check_littlefs_reset_matrix_acceptance.py"
python3 "$repo_dir/tools/check_stage_demo_s3_acceptance.py"
python3 "$repo_dir/tools/check_survey_source_plan_acceptance.py"
python3 "$repo_dir/tools/check_source_timeline_runtime_acceptance.py"
python3 "$repo_dir/tools/check_source_timeline_persistence_acceptance.py"
python3 "$repo_dir/tools/check_passive_ble_acceptance.py"
python3 "$repo_dir/tools/check_runtime_degradation_acceptance.py"
python3 "$repo_dir/tools/check_observation_browser_acceptance.py"
python3 "$repo_dir/tools/check_capture_export_acceptance.py"
python3 "$repo_dir/tools/check_wifi_frame_capture_acceptance.py"
python3 "$repo_dir/tools/check_persistent_wifi_capture_acceptance.py"
python3 "$repo_dir/tools/check_self_test_coverage_acceptance.py"
python3 "$repo_dir/tools/check_release_hil_acceptance.py"
python3 "$repo_dir/tools/test_sd_reset_runner.py"
python3 "$repo_dir/tools/test_prerelease_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_hil_runner.py"
python3 "$repo_dir/tools/test_source_timeline_hil_runner.py"
python3 "$repo_dir/tools/test_passive_ble_hil_runner.py"
python3 "$repo_dir/tools/test_runtime_degradation_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_cancel_hil_runner.py"
python3 "$repo_dir/tools/test_product_survey_missing_source_hil_runner.py"
python3 "$repo_dir/tools/test_littlefs_parity_hil_runner.py"
python3 "$repo_dir/tools/test_littlefs_reset_matrix_hil_runner.py"
python3 "$repo_dir/tools/test_stage_demo_s3_hil_runner.py"
python3 "$repo_dir/tools/test_product_boot_watchdog_hil_runner.py"
python3 "$repo_dir/tools/test_product_endurance_hil_runner.py"
python3 "$repo_dir/tools/test_release_hil_runner.py"
python3 "$repo_dir/tools/test_camera_subset.py"
python3 "$repo_dir/tools/test_prerelease_bundle_verifier.py"
python3 "$repo_dir/tools/test_prerelease_bundle_package.py"
python3 "$repo_dir/tools/test_release_1x.py"
python3 "$repo_dir/tools/read_1x_version.py" >/dev/null
