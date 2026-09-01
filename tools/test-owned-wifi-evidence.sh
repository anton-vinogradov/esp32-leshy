#!/usr/bin/env bash
# Focused host delta for capture -> canonical hc22000 -> bounded owned verification.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-owned-wifi.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

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
python3 "$repo_dir/tools/test_owned_wifi_evidence_verifier.py"
python3 "$repo_dir/tools/test_check_my_wifi_password.py"
python3 "$repo_dir/tools/check_owned_wifi_evidence_verifier_contract.py"
