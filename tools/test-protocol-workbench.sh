#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/leshy-protocol-workbench.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT

"${CXX:-c++}" \
    -std=c++17 \
    -Wall -Wextra -Werror -pedantic \
    -Wconversion -Wsign-conversion -Wshadow \
    -I"$repo_dir/firmware/leshy1/src" \
    "$repo_dir/tests/native/protocol_workbench_tests.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolCaptureSnapshot.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolWorkbenchTaskController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolAnnotationController.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolAnnotations.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolComparison.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolDerivedDecode.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/protocol/ProtocolWorkbench.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProtocolAnnotationCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProtocolAnnotationStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProtocolDerivedDecodeCodec.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/ProtocolDerivedDecodeStore.cpp" \
    "$repo_dir/firmware/leshy1/src/storage/AtomicHead.cpp" \
    -o "$test_tmp/protocol_workbench_tests"

"$test_tmp/protocol_workbench_tests"
python3 "$repo_dir/tools/check_protocol_workbench_contract.py"
