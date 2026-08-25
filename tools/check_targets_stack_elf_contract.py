#!/usr/bin/env python3
"""Reject exact product ELFs with unsafe Targets loop-task stack frames."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


LIMITS = {
    "TargetsController::reset()": 512,
    "TargetsController::loadBindings(": 1024,
    "TargetsController::loadComparisonSide(": 512,
    "TargetsController::comparisonItemBefore(": 768,
    "TargetsController::rebuildComparisonOrder()": 512,
    "resetTargetComparisonResult(": 128,
    "compareTargetSessionsInto(": 512,
    "buildSide(": 1536,
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
                   if line.endswith(">:") and label in line]
        if len(headers) != 1:
            raise ValueError(
                f"expected one Targets stack symbol {label!r}, found {len(headers)}")
        start = disassembly.index(headers[0])
        body = disassembly[start:start + 600]
        match = re.search(r"\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)", body)
        if match is None:
            raise ValueError(f"stack entry not found for {label}")
        frame = int(match.group(1), 0)
        if frame > limit:
            raise ValueError(f"unsafe Targets stack frame {label}: {frame} > {limit}")
        frames[label] = frame
    return frames


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, required=True)
    args = parser.parse_args()
    try:
        frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps({"schema": "leshy.targets_stack_elf.v1",
                      "status": "pass", "frames": frames}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
