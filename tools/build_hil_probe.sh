#!/usr/bin/env bash
# Compile the isolated, non-transmitting S1 hardware evidence image. Does not flash.
set -euo pipefail

export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec pio run -d "$repo_dir/diagnostics/hil_probe"
