#!/usr/bin/env bash
# Build the separate bounded IR-only HIL fixture image. Never flashes a board.
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec pio run -d "$repo_dir/firmware/leshy_fixture" -e esp32-div-v2-ir-fixture
