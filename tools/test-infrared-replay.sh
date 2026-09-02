#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-ir-replay.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

python3 "$repo_dir/tools/check_infrared_replay_contract.py"

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/infrared_replay_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/lab/InfraredReplay.cpp" \
    -o "$test_tmp/infrared_replay_tests"

"$test_tmp/infrared_replay_tests"
