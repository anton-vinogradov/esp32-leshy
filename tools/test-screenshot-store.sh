#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-screenshot-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/screenshot_store_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ScreenshotStore.cpp" \
    -o "$test_tmp/screenshot_store_tests"

"$test_tmp/screenshot_store_tests"
