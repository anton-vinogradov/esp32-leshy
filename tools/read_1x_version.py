#!/usr/bin/env python3
"""Print the version embedded by the independent ESP32-Leshy 1.x target."""

from __future__ import annotations

import re
from pathlib import Path


CONFIG = Path(__file__).parents[1] / "firmware" / "leshy1" / "platformio.ini"
PATTERN = re.compile(r'^\s*-D\s+LESHY1_VERSION=\\"([^\"]+)\\"\s*$', re.MULTILINE)


def main() -> int:
    match = PATTERN.search(CONFIG.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"LESHY1_VERSION not found in {CONFIG}")
    print(match.group(1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
