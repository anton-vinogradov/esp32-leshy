#!/usr/bin/env bash
# Explicitly flash the archived 0.x line. Active 1.x automation never calls it.
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
pio run -d "$repo_dir" -e esp32-div -t upload
echo "-- archived 0.x flashed explicitly; port released. --"
