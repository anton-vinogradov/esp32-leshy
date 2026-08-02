#!/usr/bin/env bash
# Compile the firmware (no flashing).
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
exec pio run
