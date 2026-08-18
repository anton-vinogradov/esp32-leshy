#!/usr/bin/env python3
"""Canonicalize a passing touch HIL run into a repository evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rewrite_paths(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: rewrite_paths(item, old, new)
                for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_paths(item, old, new) for item in value]
    if isinstance(value, str) and value.startswith(old):
        return new + value[len(old):]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if not source.is_dir() or destination.exists():
        parser.error("source must exist and destination must not exist")
    try:
        old_relative = str(source.relative_to(ROOT))
        new_relative = str(destination.relative_to(ROOT))
    except ValueError as error:
        parser.error(f"source/destination must be below repository root: {error}")

    original = load(source / "run.json")
    candidate = original.get("candidate", {})
    artifacts = {
        "firmware.bin": (args.firmware.resolve(), "firmware_sha256"),
        "firmware.factory.bin": (args.factory.resolve(), "factory_sha256"),
        "firmware.elf": (args.elf.resolve(), "elf_file_sha256"),
        "runner.py": (Path(__file__).with_name("run_1x_touch_hil.py"),
                      "runner_sha256"),
    }
    if original.get("status") != "pass" or \
            original.get("physical_touch_observed") is not True:
        parser.error("only a passing physical touch run can be retained")
    for name, (path, key) in artifacts.items():
        if not path.is_file() or digest(path) != candidate.get(key):
            parser.error(f"candidate binding mismatch for {name}")

    shutil.copytree(source, destination)
    shutil.copy2(source / "run.json", destination / "run.original.json")
    for name, (path, _) in artifacts.items():
        shutil.copy2(path, destination / name)

    for path in sorted(destination.glob("*.json")):
        if path.name == "run.original.json":
            continue
        write(path, rewrite_paths(load(path), old_relative, new_relative))

    run = load(destination / "run.json")
    for record in run.get("screens", {}).values():
        trace = ROOT / record["trace_path"]
        record["trace_sha256"] = digest(trace)
    write(destination / "run.json", run)

    indexed = sorted(
        path for path in destination.iterdir()
        if path.is_file() and path.name != "artifacts.sha256")
    index = "".join(
        f"{digest(path)}  {path.name}\n" for path in indexed)
    (destination / "artifacts.sha256").write_text(index, encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": new_relative,
        "files": len(indexed) + 1,
        "original_run_sha256": digest(destination / "run.original.json"),
        "canonical_run_sha256": digest(destination / "run.json"),
        "artifact_index_sha256": digest(destination / "artifacts.sha256"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
