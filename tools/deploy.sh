#!/usr/bin/env bash
# Build + flash to the connected ESP32-DIV over USB, then open the serial monitor.
# This is the everyday "run on device" button.
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
pio run -t upload
echo "-- flashed; opening serial monitor (Ctrl-C to exit) --"
exec pio device monitor -b 115200
