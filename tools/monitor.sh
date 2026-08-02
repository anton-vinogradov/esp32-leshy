#!/usr/bin/env bash
# Serial monitor only (see logs; type the serial-remote commands: scan/chan/spectrum/stat/…).
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
exec pio device monitor -b 115200
