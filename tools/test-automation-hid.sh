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
    "$repo_dir/firmware/leshy1/src/apps/automation/AutomationTrustBundle.cpp" \
    "$repo_dir/firmware/leshy1/src/apps/automation/AutomationTrustStore.cpp" \
    -o "$test_tmp/automation_package_tests"

"$test_tmp/automation_package_tests"
PYTHONPATH="$repo_dir/tools" python3 "$repo_dir/tools/test_automation_trust_bundle.py"
PYTHONPATH="$repo_dir/tools" python3 "$repo_dir/tools/test_automation_trust_positive_hil_runner.py"
python3 "$repo_dir/tools/check_automation_hid_foundation.py"
python3 "$repo_dir/tools/check_automation_inspector_hil_acceptance.py"
python3 "$repo_dir/tools/check_automation_trust_ui_hil_acceptance.py"
if [[ -f "$repo_dir/tests/hil/evidence/board-01-automation-trust-positive-1.0.0-dev.308.json" ]]; then
    python3 "$repo_dir/tools/check_automation_trust_positive_hil_acceptance.py"
fi
