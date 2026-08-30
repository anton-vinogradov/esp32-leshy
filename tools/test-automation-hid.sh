#!/usr/bin/env bash
# Focused CAP-054 host delta: passive package inspection and execution admission.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-automation-hid-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/automation_package_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/automation/AutomationInspectorController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/automation/AutomationPackage.cpp" \
    -o "$test_tmp/automation_package_tests"

"$test_tmp/automation_package_tests"
python3 "$repo_dir/tools/check_automation_hid_foundation.py"
