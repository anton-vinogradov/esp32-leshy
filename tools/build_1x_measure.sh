#!/usr/bin/env bash
# Compile the independent 1.x S1 measurement target. Does not flash.
set -euo pipefail

export PATH="$HOME/.platformio/penv/bin:$PATH"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec pio run -d "$repo_dir/firmware/leshy1"
