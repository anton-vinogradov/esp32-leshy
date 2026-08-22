#!/usr/bin/env bash
# Build + flash the active clean 1.x firmware over USB. Upload only, on purpose:
# the port is released the moment flashing finishes, so the next upload — or the
# web installer, or anything else that needs the serial port — just works. Watch
# logs with the separate "Monitor (serial)" button (it holds the port until you
# stop it with the red square).
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
pio run -d "$repo_dir/firmware/leshy1" -e esp32-div-v2-clean -t upload
echo "-- clean 1.x flashed; port released. --"
