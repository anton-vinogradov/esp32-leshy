#!/usr/bin/env bash
# Build + flash to the connected ESP32-DIV over USB. Upload only, on purpose:
# the port is released the moment flashing finishes, so the next upload — or the
# web installer, or anything else that needs the serial port — just works. Watch
# logs with the separate "Monitor (serial)" button (it holds the port until you
# stop it with the red square).
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
pio run -t upload
echo "-- flashed; port released. Click 'Monitor (serial)' to watch logs. --"
