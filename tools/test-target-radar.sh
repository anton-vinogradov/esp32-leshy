#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-target-radar.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/target_radar_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/targets/TargetRadar.cpp" \
    "$repo_dir/firmware/leshy1/src/domain/targets/Target.cpp" \
    -o "$test_tmp/target_radar_tests"

"$test_tmp/target_radar_tests"
