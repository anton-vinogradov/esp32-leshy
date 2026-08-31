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

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/protected_file_envelope_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProtectedFileEnvelope.cpp" \
    -o "$test_tmp/protected_file_envelope_tests"

"$test_tmp/protected_file_envelope_tests"
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
PYTHONPATH="$repo_dir/tools" python3 \
    "$repo_dir/tools/test_device_lock_persistence_hil_runner.py"
PYTHONPATH="$repo_dir/tools" python3 \
    "$repo_dir/tools/test_device_lock_recovery_admission_hil_runner.py"
python3 "$repo_dir/tools/check_device_lock_hil_acceptance.py"
python3 "$repo_dir/tools/check_device_lock_persistence_hil_acceptance.py"
python3 \
    "$repo_dir/tools/check_device_lock_recovery_admission_hil_acceptance.py"
python3 "$repo_dir/tools/check_protected_storage_hil_evidence.py"
python3 "$repo_dir/tools/check_device_lock_disable_hil_acceptance.py"
