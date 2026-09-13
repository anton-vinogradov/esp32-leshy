#!/usr/bin/env python3
"""Update the Wi-Fi mockup inside its checked-in standalone export, offline.

The existing wrapper supplies the sandbox, styles and small runtime. Only its
marked fragment is replaced; no plugin, browser, network or firmware is needed.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs/v1/wifi-screen-flow.source.html"
EXPORT = ROOT / "docs/v1/wifi-screen-flow.html"
START = "<!-- leshy-wifi-source:start -->"
END = "<!-- leshy-wifi-source:end -->"
SRCDOC = re.compile(r'\bsrcdoc="([^"]*)"')


def marked_region(text: str) -> tuple[int, int]:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("expected exactly one source start/end marker")
    start, end = text.index(START), text.index(END) + len(END)
    if end <= start:
        raise ValueError("source markers are reversed")
    return start, end


def updated_export(source: str, exported: str) -> str:
    source = source.strip()
    start, end = marked_region(source)
    if start != 0 or end != len(source):
        raise ValueError("source must be entirely inside its markers")
    if len(source.encode("utf-8")) >= 1_000_000:
        raise ValueError("source exceeds the fragment budget")
    matches = list(SRCDOC.finditer(exported))
    if len(matches) != 1:
        raise ValueError("expected one sandboxed srcdoc export")
    match = matches[0]
    inner = html.unescape(match[1])
    start, end = marked_region(inner)
    inner = inner[:start] + source + inner[end:]
    return exported[:match.start(1)] + html.escape(inner, quote=True) + exported[match.end(1):]


def drift_errors() -> list[str]:
    try:
        source = SOURCE.read_text(encoding="utf-8")
        exported = EXPORT.read_text(encoding="utf-8")
        if updated_export(source, exported) != exported:
            return ["Wi-Fi map export drift: run python3 tools/export_wifi_map.py"]
    except (OSError, ValueError) as error:
        return [f"Wi-Fi map export invalid: {error}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        errors = drift_errors()
        print("\n".join(errors) if errors else "Wi-Fi source/export match")
        return bool(errors)
    try:
        existing = EXPORT.read_text(encoding="utf-8")
        result = updated_export(SOURCE.read_text(encoding="utf-8"), existing)
        if result != existing:
            EXPORT.write_text(result, encoding="utf-8")
        print("Wi-Fi standalone export is up to date")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
