#!/usr/bin/env bash
# Cut a legacy 0.x release: tag HEAD and push it. CI then bakes the version, builds, publishes
# the GitHub release (firmware.bin + firmware.factory.bin) and refreshes the web
# installer; devices pick it up via OTA. No arg → bump the patch (v0.4.2 -> v0.4.3).
# Pass a 0.x version for minor: tools/release.sh v0.10.0. Version 1.x must use
# tools/release_1x.py so the exact bytes pass the physical release gate first.
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
git fetch --tags -q origin
if [ "${1:-}" != "" ]; then
  VER="$1"
else
  LAST="$(git tag -l 'v0.*' --sort=-v:refname | head -1)"; LAST="${LAST:-v0.0.0}"
  IFS=. read -r MA MI PA <<< "${LAST#v}"
  VER="v${MA}.${MI}.$((PA + 1))"
fi
if [[ ! "$VER" =~ ^v0\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: tools/release.sh owns v0.x only; use tools/release_1x.py for 1.x" >&2
  exit 2
fi
echo "About to release ${VER}  (previous: ${LAST:-none},  HEAD $(git rev-parse --short HEAD))"
echo "Ctrl-C within 5s to abort…"; sleep 5
git tag "$VER"
git push origin "$VER"
echo "✅ ${VER} pushed → watch CI: gh run watch, or the Actions tab. Devices update via Settings → Update."
