#!/usr/bin/env python3
"""Canonicalize a passing product-menu HIL run into retained evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


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
    parser.add_argument("--failed-source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    failed_source = args.failed_source.resolve()
    destination = args.destination.resolve()
    firmware = args.firmware.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    runner = Path(__file__).with_name("run_1x_product_menu_hil.py")
    if not source.is_dir() or not failed_source.is_dir() or destination.exists():
        parser.error("sources must exist and destination must not exist")
    if not all(path.is_file() for path in (firmware, factory, elf, runner)):
        parser.error("candidate artifacts are incomplete")
    try:
        old_relative = str(source.relative_to(ROOT))
        new_relative = str(destination.relative_to(ROOT))
    except ValueError as error:
        parser.error(f"source/destination must be below repository root: {error}")

    original = load(source / "run.json")
    failed = load(failed_source / "run.json")
    candidate = original.get("candidate", {})
    failed_candidate = failed.get("candidate", {})
    if original.get("status") != "pass" or original.get("passed") is not True:
        parser.error("only a passing menu run can be retained")
    if failed.get("status") != "failed" or failed_candidate.get("flashed") is not True:
        parser.error("the initial flashed runner failure must be retained")
    if candidate.get("version") != "0.90.0-product-menu" or \
            candidate.get("firmware_sha256") != digest(firmware) or \
            candidate.get("app_elf_sha256") != app_elf_sha256(firmware) or \
            candidate.get("runner_sha256") != digest(runner):
        parser.error("passing candidate binding mismatch")
    for key in ("version", "firmware_sha256", "app_elf_sha256"):
        if failed_candidate.get(key) != candidate.get(key):
            parser.error(f"failed/pass candidate mismatch: {key}")

    shutil.copytree(source, destination)
    shutil.copy2(source / "run.json", destination / "run.original.json")
    shutil.copy2(failed_source / "run.json", destination / "runner-failure.json")
    for path, name in (
        (firmware, "firmware.bin"),
        (factory, "firmware.factory.bin"),
        (elf, "firmware.elf"),
        (runner, "runner.py"),
    ):
        shutil.copy2(path, destination / name)

    for path in sorted(destination.glob("*.json")):
        if path.name in {"run.original.json", "runner-failure.json"}:
            continue
        write(path, rewrite_paths(load(path), old_relative, new_relative))

    run = load(destination / "run.json")
    for record in run.get("screens", {}).values():
        png = Path(record["png_path"])
        trace = destination / (png.stem + ".json")
        record["trace_path"] = str(trace.relative_to(ROOT))
        record["trace_sha256"] = digest(trace)
    write(destination / "run.json", run)

    provenance = {
        "schema": "leshy.product_menu_hil.provenance.v1",
        "source_commit": args.source_commit,
        "runner_commit": args.runner_commit,
        "version": candidate["version"],
        "firmware_sha256": digest(destination / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "app_elf_sha256": app_elf_sha256(destination / "firmware.bin"),
        "runner_sha256": digest(destination / "runner.py"),
        "firmware_bytes": (destination / "firmware.bin").stat().st_size,
        "factory_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "elf_bytes": (destination / "firmware.elf").stat().st_size,
    }
    write(destination / "provenance.json", provenance)

    indexed = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256")
    index = "".join(
        f"{digest(path)}  {path.relative_to(destination)}\n" for path in indexed)
    (destination / "artifacts.sha256").write_text(index, encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": new_relative,
        "files": len(indexed) + 1,
        "original_run_sha256": digest(destination / "run.original.json"),
        "canonical_run_sha256": digest(destination / "run.json"),
        "failed_run_sha256": digest(destination / "runner-failure.json"),
        "provenance_sha256": digest(destination / "provenance.json"),
        "artifact_index_sha256": digest(destination / "artifacts.sha256"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
