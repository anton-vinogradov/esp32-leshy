#!/usr/bin/env bash
# Compile the independent 1.x S1 measurement target. Does not flash.
set -euo pipefail

export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
export PLATFORMIO_CORE_DIR="${LESHY_PLATFORMIO_CORE_DIR:-$repo_dir/work/platformio-core/leshy1}"
exec pio run -d "$repo_dir/firmware/leshy1"
