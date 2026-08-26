#!/usr/bin/env python3
"""Keep local Leshy 1.x builds isolated from unrelated PlatformIO projects."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = (
    ROOT / "tools/build.sh",
    ROOT / "tools/deploy.sh",
    ROOT / "tools/build_1x_measure.sh",
    ROOT / "tools/verify_connected_candidate.sh",
)
MARKER = (
    'PLATFORMIO_CORE_DIR="${LESHY_PLATFORMIO_CORE_DIR:-'
    '$repo_dir/work/platformio-core/leshy1}"'
)


def main() -> int:
    failures: list[str] = []
    for path in SCRIPTS:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"{path}: {error}")
            continue
        if MARKER not in source:
            failures.append(
                f"{path.relative_to(ROOT)} does not select the Leshy 1.x "
                "workspace-local PlatformIO core"
            )
        if "rm -" in source or "~/.platformio/packages" in source:
            failures.append(
                f"{path.relative_to(ROOT)} mutates the shared PlatformIO package cache"
            )
    if failures:
        for failure in failures:
            print(f"platformio isolation check failed: {failure}", file=sys.stderr)
        return 1
    print(
        "PlatformIO isolation passed: build, deploy and candidate gate share "
        "one workspace-local Leshy 1.x core"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
