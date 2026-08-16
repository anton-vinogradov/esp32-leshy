#!/usr/bin/env bash
# Build and run the destructive-only-to-mkdtemp host storage fixture.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <evidence.json>" >&2
    exit 2
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-storage-build.XXXXXX")"
trap 'rm -rf "$build_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/storage_filesystem_fixture.cpp" \
    "$repo_dir/firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp" \
    "$repo_dir/firmware/leshy1/src/services/survey/SurveySession.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/SessionStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/StorageGuard.cpp" \
    -o "$build_tmp/storage_filesystem_fixture"

"$build_tmp/storage_filesystem_fixture" --output "$1"
