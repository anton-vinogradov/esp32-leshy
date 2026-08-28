#!/usr/bin/env python3
"""Reject exact product ELFs with unsafe Airspace Guard stack frames."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


# Arduino's loop task has an 8-KiB stack. serviceAirspaceGuardProduct() is
# called below loop(), while render/inspect/merge are its deepest relevant
# callees. Keep every concrete frame bounded and, most importantly, prevent the
# dev.223 7,280-byte service frame from returning unnoticed.
LIMITS = {
    "serviceAirspaceGuardProduct()": 1024,
    "runProductSurveyWorker(void*)": 6144,
    "finalizeAirspaceGuardWifiEvidence(": 3072,
    "renderAirspaceGuardPage(": 1280,
    "AirspaceGuard::inspectWifi(": 2816,
    "mergeAirspaceGuardReports(": 2560,
    "BoardWifiPassiveCapture::accept(": 512,
}


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    fallback = (Path.home() / ".platformio/packages/"
                "toolchain-xtensa-esp-elf/bin" / name)
    if fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(name)


def stack_frames(elf: Path) -> dict[str, int]:
    disassembly = subprocess.run(
        [tool("xtensa-esp32s3-elf-objdump"), "-d", "-C", str(elf)],
        check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    frames: dict[str, int] = {}
    for label, limit in LIMITS.items():
        headers = [line for line in disassembly.splitlines()
                   if line.endswith(">:") and label in line and
                   "::{lambda" not in line]
        if len(headers) != 1:
            raise ValueError(
                f"expected one Airspace Guard stack symbol {label!r}, "
                f"found {len(headers)}")
        start = disassembly.index(headers[0])
        body = disassembly[start:start + 600]
        match = re.search(r"\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)", body)
        if match is None:
            raise ValueError(f"stack entry not found for {label}")
        frame = int(match.group(1), 0)
        if frame > limit:
            raise ValueError(
                f"unsafe Airspace Guard stack frame {label}: "
                f"{frame} > {limit}")
        frames[label] = frame
    return frames


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, required=True)
    args = parser.parse_args()
    try:
        frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError,
            ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps({
        "schema": "leshy.airspace_guard_stack_elf.v1",
        "status": "pass",
        "frames": frames,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
