#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-wifi-ui.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Wconversion -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_network_ui_tests.cpp" \
    -o "$test_tmp/wifi_network_ui_tests"
"$test_tmp/wifi_network_ui_tests"
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Wconversion -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_network_name_evidence_tests.cpp" \
    -o "$test_tmp/wifi_network_name_evidence_tests"
"$test_tmp/wifi_network_name_evidence_tests"
python3 "$repo_dir/tools/check_wifi_ui_contract.py"
python3 "$repo_dir/tools/test_wifi_ui_delta_hil.py"
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Wconversion -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_test_network_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/self_test/SelfTestController.cpp" \
    -o "$test_tmp/wifi_test_network_tests"
"$test_tmp/wifi_test_network_tests"
python3 "$repo_dir/tools/test_wifi_product_network.py"
