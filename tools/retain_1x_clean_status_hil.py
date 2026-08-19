#!/usr/bin/env python3
"""Retain the exact 0.91 compact-status menu and active-RF HIL proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.91.0-clean-status"


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


def canonicalize_json_tree(directory: Path, old: str, new: str) -> None:
    for path in sorted(directory.rglob("*.json")):
        write(path, rewrite_paths(load(path), old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--menu-source", required=True, type=Path)
    parser.add_argument("--radio-source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--menu-runner-commit", required=True)
    parser.add_argument("--radio-runner-commit", required=True)
    args = parser.parse_args()

    menu_source = args.menu_source.resolve()
    radio_source = args.radio_source.resolve()
    destination = args.destination.resolve()
    firmware = args.firmware.resolve()
    factory = args.factory.resolve()
    elf = args.elf.resolve()
    menu_runner = ROOT / "tools/run_1x_product_menu_hil.py"
    radio_runner = ROOT / "tools/run_1x_nrf24_spectrum_hil.py"
    required = (firmware, factory, elf, menu_runner, radio_runner)
    if not menu_source.is_dir() or not radio_source.is_dir() or \
            destination.exists() or not all(path.is_file() for path in required):
        parser.error("sources/artifacts must exist and destination must not exist")
    if any(len(commit) != 40 for commit in (
            args.source_commit, args.menu_runner_commit,
            args.radio_runner_commit)):
        parser.error("all commits must be full 40-character IDs")

    menu_run = load(menu_source / "run.json")
    radio_run = load(radio_source / "run.json")
    menu_candidate = menu_run.get("candidate", {})
    radio_candidate = radio_run.get("candidate", {})
    firmware_hash = digest(firmware)
    app_identity = app_elf_sha256(firmware)
    if not (menu_run.get("status") == "pass" and
            menu_run.get("passed") is True and
            menu_run.get("failures") == []):
        parser.error("menu source is not a passing run")
    if not (radio_run.get("passed") is True and
            radio_run.get("failures") == [] and
            radio_run.get("cleanup_after", {}).get("complete") is True):
        parser.error("radio source is not a passing, cleaned-up run")
    for candidate in (menu_candidate, radio_candidate):
        if candidate.get("version") != VERSION or \
                candidate.get("firmware_sha256") != firmware_hash or \
                candidate.get("app_elf_sha256") != app_identity or \
                candidate.get("flashed") is not True:
            parser.error("candidate identity mismatch")
    if radio_candidate.get("source_commit") != args.source_commit or \
            menu_candidate.get("runner_sha256") != digest(menu_runner) or \
            radio_run.get("runner_source_sha256") != digest(radio_runner):
        parser.error("source/runner binding mismatch")

    destination.mkdir(parents=True)
    menu_destination = destination / "menu"
    radio_destination = destination / "radio"
    shutil.copytree(menu_source, menu_destination)
    shutil.copytree(radio_source, radio_destination)
    canonicalize_json_tree(
        menu_destination, str(menu_source.relative_to(ROOT)),
        str(menu_destination.relative_to(ROOT)))
    canonicalize_json_tree(
        radio_destination, str(radio_source.relative_to(ROOT)),
        str(radio_destination.relative_to(ROOT)))

    for source, name in (
        (firmware, "firmware.bin"),
        (factory, "firmware.factory.bin"),
        (elf, "firmware.elf"),
        (menu_runner, "product-menu-runner.py"),
        (radio_runner, "nrf24-spectrum-runner.py"),
    ):
        shutil.copy2(source, destination / name)

    provenance = {
        "schema": "leshy.clean_status_hil.provenance.v1",
        "version": VERSION,
        "source_commit": args.source_commit,
        "menu_runner_commit": args.menu_runner_commit,
        "radio_runner_commit": args.radio_runner_commit,
        "firmware_sha256": firmware_hash,
        "factory_sha256": digest(factory),
        "elf_file_sha256": digest(elf),
        "app_elf_sha256": app_identity,
        "menu_runner_sha256": digest(menu_runner),
        "radio_runner_sha256": digest(radio_runner),
        "firmware_bytes": firmware.stat().st_size,
        "factory_bytes": factory.stat().st_size,
        "elf_bytes": elf.stat().st_size,
        "menu_run_sha256": digest(menu_destination / "run.json"),
        "radio_run_sha256": digest(radio_destination / "run.json"),
    }
    write(destination / "provenance.json", provenance)

    indexed = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path != destination / "artifacts.sha256")
    index = "".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed)
    (destination / "artifacts.sha256").write_text(index, encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": str(destination.relative_to(ROOT)),
        "files": len(indexed) + 1,
        "provenance_sha256": digest(destination / "provenance.json"),
        "artifact_index_sha256": digest(destination / "artifacts.sha256"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
