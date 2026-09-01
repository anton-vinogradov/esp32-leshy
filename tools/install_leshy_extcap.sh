#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/leshy_extcap.py"
TSHARK="${LESHY_TSHARK:-/Applications/Wireshark.app/Contents/MacOS/tshark}"

if [[ ! -x "$TSHARK" ]]; then
  echo "Wireshark tshark was not found: $TSHARK" >&2
  exit 1
fi

PERSONAL_DIR="$($TSHARK -G folders | awk -F '\t' '/^Personal Extcap path:/ {print $2; exit}')"
if [[ -z "$PERSONAL_DIR" || "$PERSONAL_DIR" != /* ]]; then
  echo "Wireshark did not report an absolute personal extcap directory" >&2
  exit 1
fi

DESTINATION="$PERSONAL_DIR/leshy_extcap.py"
if [[ "${1:-}" == "--remove" ]]; then
  if [[ -e "$DESTINATION" ]]; then
    rm "$DESTINATION"
  fi
  echo "Removed Leshy extcap: $DESTINATION"
  exit 0
fi

if [[ $# -ne 0 ]]; then
  echo "usage: $0 [--remove]" >&2
  exit 2
fi

mkdir -p "$PERSONAL_DIR"
install -m 0755 "$SOURCE" "$DESTINATION"
"$DESTINATION" --extcap-interfaces >/dev/null
echo "Installed Leshy extcap: $DESTINATION"
echo "Restart Wireshark, start Capture -> Wi-Fi on Leshy, then select the Leshy source."
