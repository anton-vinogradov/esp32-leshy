#!/usr/bin/env bash
# Compile the archived 0.x line. Never used by active 1.x automation.
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec pio run -d "$repo_dir" -e esp32-div
