#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-wifi-security.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/wifi_security_advisor_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/wifi/WifiSecurityAdvisor.cpp" \
    -o "$test_tmp/wifi_security_advisor_tests"

"$test_tmp/wifi_security_advisor_tests"

python3 "$repo_dir/tools/check_wifi_security_advisor_contract.py"
