#!/usr/bin/env bash
# Cut a release: tag HEAD and push it. CI then bakes the version, builds, publishes
# the GitHub release (firmware.bin + firmware.factory.bin) and refreshes the web
# installer; devices pick it up via OTA. No arg → bump the patch (v0.4.2 -> v0.4.3).
# Pass a version for minor/major:  tools/release.sh v0.5.0
set -euo pipefail
export PATH="$HOME/.platformio/penv/bin:$PATH"
cd "$(dirname "$0")/.."
git fetch --tags -q origin
if [ "${1:-}" != "" ]; then
  VER="$1"
else
  LAST="$(git tag -l 'v*' --sort=-v:refname | head -1)"; LAST="${LAST:-v0.0.0}"
  IFS=. read -r MA MI PA <<< "${LAST#v}"
  VER="v${MA}.${MI}.$((PA + 1))"
fi
echo "About to release ${VER}  (previous: ${LAST:-none},  HEAD $(git rev-parse --short HEAD))"
echo "Ctrl-C within 5s to abort…"; sleep 5
git tag "$VER"
git push origin "$VER"
echo "✅ ${VER} pushed → watch CI: gh run watch, or the Actions tab. Devices update via Settings → Update."
