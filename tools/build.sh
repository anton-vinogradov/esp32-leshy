#!/usr/bin/env bash
# Compile the active clean 1.x firmware (no flashing).
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
export PLATFORMIO_CORE_DIR="${LESHY_PLATFORMIO_CORE_DIR:-$repo_dir/work/platformio-core/leshy1}"
pio run -d "$repo_dir/firmware/leshy1" -e esp32-div-v2-clean
python3 "$repo_dir/tools/check_1x_build_budget.py"
