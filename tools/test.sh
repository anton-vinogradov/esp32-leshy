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
    "$repo_dir/firmware/leshy1/src/apps/library/LibraryController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/library/SessionCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/ProductSurveyAdmission.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyPipeline.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/survey/SurveyWorkflow.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/apps/AppCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/hardware/HardwareInventory.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/AppRuntime.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/ResourceBroker.cpp" \
    "$repo_dir/firmware/leshy1/src/platform/arduino/RamSessionStoreIo.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/BootReport.cpp" \
    "$repo_dir/firmware/leshy1/src/services/diagnostics/HilSession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/IngressTiming.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/ObservationQueue.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SessionBatchPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/MediaDiscovery.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/MountPolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProductStorePolicy.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdIdentification.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdIdentificationTransport.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdReadOnlyProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdSectorInspection.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SdSpiWireCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStoreBoundary.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageGuard.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageTiming.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/Pcf8574ButtonInput.cpp" \
    "$repo_dir/firmware/leshy1/src/ui/UiController.cpp" \
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
python3 "$repo_dir/tools/test_sd_reset_runner.py"
python3 "$repo_dir/tools/test_prerelease_hil_runner.py"
python3 "$repo_dir/tools/test_prerelease_bundle_verifier.py"
python3 "$repo_dir/tools/test_prerelease_bundle_package.py"
python3 "$repo_dir/tools/test_release_1x.py"
python3 "$repo_dir/tools/read_1x_version.py" >/dev/null
