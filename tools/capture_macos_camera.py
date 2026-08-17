#!/usr/bin/env python3
"""Compile and run the one-shot macOS AVFoundation camera provider.

This wrapper exists because partial Command Line Tools upgrades can leave the
unversioned macOS SDK newer than Swift.  It selects an installed real SDK,
builds into a temporary directory, forwards one command, and exits.  Nothing
is installed and no resident process is created.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def sdk_candidates(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    root = Path("/Library/Developer/CommandLineTools/SDKs")
    real = sorted(
        (path for path in root.glob("MacOSX*.sdk") if not path.is_symlink()),
        key=lambda path: path.name,
    )
    # The oldest installed SDK has the broadest chance of matching a compiler
    # after an interrupted CLT update, and AVFoundation needs no new API here.
    return real


def build(source: Path, sdk: Path, binary: Path, log: Path) -> bool:
    cache = Path(os.environ.get("TMPDIR", "/tmp")) / "leshy-swift-module-cache"
    cache.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        "swiftc", "-module-cache-path", str(cache), "-sdk", str(sdk),
        str(source), "-o", str(binary),
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(result.stdout, encoding="utf-8")
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "capture"))
    parser.add_argument("--device-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--warmup-ms", type=int, default=1200)
    parser.add_argument("--sdk", type=Path, help="override macOS SDK path")
    args = parser.parse_args()
    if args.command == "capture" and (not args.device_id or args.output is None):
        parser.error("capture requires --device-id and --output")
    if not 0 <= args.warmup_ms <= 10_000:
        parser.error("--warmup-ms must be between 0 and 10000")
    if platform.system() != "Darwin":
        parser.error("the built-in camera provider requires macOS")

    source = Path(__file__).with_name("capture_macos_camera.swift")
    candidates = sdk_candidates(args.sdk)
    if not candidates:
        parser.error("no macOS SDK found; install Apple Command Line Tools")
    with tempfile.TemporaryDirectory(prefix="leshy-camera-") as temporary:
        temporary_path = Path(temporary)
        binary = temporary_path / "capture-macos-camera"
        selected: Path | None = None
        logs: list[Path] = []
        for index, sdk in enumerate(candidates):
            log = temporary_path / f"swiftc-{index}.log"
            logs.append(log)
            if sdk.is_dir() and build(source, sdk, binary, log):
                selected = sdk
                break
        if selected is None:
            for sdk, log in zip(candidates, logs):
                print(f"camera provider: compiler failed with {sdk}", file=sys.stderr)
                print(log.read_text(encoding="utf-8"), file=sys.stderr)
            return 2
        command = [str(binary), args.command]
        if args.command == "capture":
            command.extend([
                "--device-id", args.device_id,
                "--output", str(args.output.resolve()),
                "--warmup-ms", str(args.warmup_ms),
            ])
        return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
