#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-live-list-tests.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/live_list_render_cache_tests.cpp" \
    -o "$test_tmp/live_list_render_cache_tests"

"$test_tmp/live_list_render_cache_tests"
python3 "$repo_dir/tools/check_live_list_rendering_contract.py"
