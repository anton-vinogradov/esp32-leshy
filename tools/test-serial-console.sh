#!/usr/bin/env bash
# Focused CAP-053 host delta: shared Action policy, strict CLI and serial preflight.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-serial-console-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/serial_console_action_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/kernel/runtime/ResourceBroker.cpp" \
    "$repo_dir/firmware/leshy1/src/services/actions/ActionDispatcher.cpp" \
    "$repo_dir/firmware/leshy1/src/services/actions/ActionsCli.cpp" \
    "$repo_dir/firmware/leshy1/src/services/serial/SerialConsoleBuffer.cpp" \
    "$repo_dir/firmware/leshy1/src/services/serial/SerialConsoleContract.cpp" \
    -o "$test_tmp/serial_console_action_tests"

"$test_tmp/serial_console_action_tests"
python3 "$repo_dir/tools/check_serial_console_product_acceptance.py"
python3 "$repo_dir/tools/check_serial_console_hil_acceptance.py"
