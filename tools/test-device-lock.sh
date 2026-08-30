#!/usr/bin/env bash
# Focused CAP-052 host delta: security core, product controller and contracts.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-device-lock-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/device_lock_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/services/security/DeviceLock.cpp" \
    "$repo_dir/firmware/leshy1/src/services/security/DeviceLockRecord.cpp" \
    -o "$test_tmp/device_lock_tests"

"$test_tmp/device_lock_tests"
python3 "$repo_dir/tools/check_device_lock_contract.py"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/device_lock_controller_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/device/DeviceLockController.cpp" \
    "$repo_dir/firmware/leshy1/src/services/security/DeviceLock.cpp" \
    -o "$test_tmp/device_lock_controller_tests"

"$test_tmp/device_lock_controller_tests"
PYTHONPATH="$repo_dir/tools" python3 \
    "$repo_dir/tools/test_device_lock_hil_runner.py"
