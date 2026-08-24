#!/usr/bin/env python3
"""Verify that the exact linked GDO0 ISR and every call target reside in IRAM."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    fallback = (Path.home() / ".platformio/packages/"
                "toolchain-xtensa-esp-elf/bin" / name)
    if fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(name)


def run(binary: str, *args: str) -> str:
    return subprocess.run(
        [binary, *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def in_iram(address: int) -> bool:
    return 0x40370000 <= address < 0x40400000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, required=True)
    args = parser.parse_args()
    failures: list[str] = []
    nm = run(tool("xtensa-esp32s3-elf-nm"), "-n", "-C", str(args.elf))
    symbols = [
        line for line in nm.splitlines()
        if "captureAsyncEdge(void*)" in line
    ]
    if len(symbols) != 1:
        failures.append(f"expected one captureAsyncEdge symbol, found {len(symbols)}")
        handler_address = 0
    else:
        handler_address = int(symbols[0].split()[0], 16)
        if not in_iram(handler_address):
            failures.append(f"handler is outside IRAM: 0x{handler_address:08x}")

    disassembly = run(
        tool("xtensa-esp32s3-elf-objdump"), "-d", "-C", str(args.elf))
    match = re.search(
        r"^[0-9a-f]+ <[^\n]*captureAsyncEdge\(void\*\)>:\n"
        r"(?P<body>.*?)(?=\n[0-9a-f]+ <|\Z)",
        disassembly, re.MULTILINE | re.DOTALL)
    if match is None:
        failures.append("captureAsyncEdge disassembly not found")
        body = ""
    else:
        body = match.group("body")
    calls = [int(value, 16) for value in re.findall(
        r"\bcall\d+\s+([0-9a-f]+)\s+<", body)]
    if not calls:
        failures.append("captureAsyncEdge has no audited call targets")
    flash_calls = [address for address in calls if not in_iram(address)]
    if flash_calls:
        failures.append("non-IRAM call targets: " + ", ".join(
            f"0x{address:08x}" for address in flash_calls))
    if "__digitalRead" in body:
        failures.append("captureAsyncEdge calls __digitalRead")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "status": "pass",
        "handler_address": f"0x{handler_address:08x}",
        "handler_region": "iram",
        "call_targets": [f"0x{address:08x}" for address in calls],
        "flash_call_targets": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
