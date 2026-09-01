#!/usr/bin/env bash
# Focused WF-15 gate: live-PCAP protocol plus Wireshark extcap host adapter.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-live-companion.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_protocol_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    -o "$test_tmp/companion_protocol_tests"
"$test_tmp/companion_protocol_tests"

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/companion_read_adapter_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionProtocol.cpp" \
    "$repo_dir/firmware/leshy1/src/services/companion/CompanionReadAdapter.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/RadiotapPcap.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/capture/WifiFrameCapture.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SourceTimeline.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetCatalog.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/TargetComparison.cpp" \
    -o "$test_tmp/companion_read_adapter_tests"
"$test_tmp/companion_read_adapter_tests"

python3 "$repo_dir/tools/test_leshy_extcap.py"
python3 -m py_compile \
    "$repo_dir/tools/leshy_extcap.py" \
    "$repo_dir/tools/test_leshy_extcap.py" \
    "$repo_dir/tools/run_1x_live_companion_wifi_hil.py"

grep -Fq '"leshy.hardware.safe-outputs.v1"' \
    "$repo_dir/tools/run_1x_live_companion_wifi_hil.py"
grep -Fq '"leshy.input.frontend.v1"' \
    "$repo_dir/tools/run_1x_live_companion_wifi_hil.py"
if grep -Fq '"leshy.hardware.safe_outputs.v1"' \
        "$repo_dir/tools/run_1x_live_companion_wifi_hil.py"; then
    echo "live companion runner uses a non-existent safe-output schema" >&2
    exit 1
fi
if grep -Fq '"leshy.input.v1"' \
        "$repo_dir/tools/run_1x_live_companion_wifi_hil.py"; then
    echo "live companion runner uses a non-existent input schema" >&2
    exit 1
fi
