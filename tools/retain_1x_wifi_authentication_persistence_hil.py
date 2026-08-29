#!/usr/bin/env python3
"""Atomically retain exact, sanitized CAP049 persistence HIL evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import check_wifi_authentication_persistence_hil_run as checker


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def safe_source(path: Path) -> Path:
    require(path.is_dir() and not path.is_symlink(),
            "regular source evidence directory required")
    for item in path.rglob("*"):
        require(not item.is_symlink(), f"source symlink rejected: {item}")
    return path.resolve()


def promote(staged: list[tuple[Path, Path]], staging: Path) -> None:
    completed: list[tuple[Path, Path]] = []
    try:
        for source, destination in staged:
            source.replace(destination)
            completed.append((source, destination))
    except OSError:
        for source, destination in reversed(completed):
            if destination.exists() and not source.exists():
                destination.replace(source)
        raise
    shutil.rmtree(staging)


def retain(args: argparse.Namespace) -> dict[str, Any]:
    source = safe_source(args.positive)
    run = load(source / "run.json")
    expected = {
        "version": args.expected_version,
        "expected_cid": args.expected_cid,
        "source_commit": args.expected_source_commit,
        "firmware_sha256": args.expected_firmware_sha256,
        "app_elf_sha256": args.expected_app_elf_sha256,
        "runner_source_sha256": args.expected_runner_sha256,
    }
    require(checker.COMMIT.fullmatch(expected["source_commit"]) is not None,
            "expected source commit must be full lowercase hexadecimal")
    for field in ("firmware_sha256", "app_elf_sha256",
                  "runner_source_sha256"):
        require(checker.SHA256.fullmatch(expected[field]) is not None,
                f"expected {field} must be lowercase SHA-256")
    require(expected["expected_cid"] == checker.CID,
            "retention is bound to board-01 CID")
    require(checker.RUNNER.is_file() and
            checker.digest(checker.RUNNER) == expected["runner_source_sha256"],
            "current persistence runner hash does not match expected runner")
    candidate = run.get("candidate", {})
    require(run.get("schema") == checker.RUN_SCHEMA and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], "source is not a clean CAP049 pass")
    require(run.get("board") == {
        "id": checker.BOARD, "expected_cid": expected["expected_cid"]},
        "source board/CID mismatch")
    require(run.get("runner_source_sha256") ==
            expected["runner_source_sha256"], "source runner hash mismatch")
    for field in ("version", "source_commit", "firmware_sha256",
                  "app_elf_sha256"):
        require(candidate.get(field) == expected[field],
                f"source candidate.{field} mismatch")
    require(isinstance(run.get("run_id"), str) and
            checker.SESSION.fullmatch(run["run_id"]) is not None,
            "source run_id must be lowercase 32-hex")

    structural: list[str] = []
    checker.verify_manifest(source, structural)
    checker.verify_private_absent(structural, run)
    require(not structural, "source evidence rejected: " +
            "; ".join(structural))

    destination = args.destination.resolve()
    expectations = args.expectations.resolve()
    require(destination != expectations and
            destination.parent == expectations.parent,
            "bundle and expectations must be distinct siblings")
    parent = destination.parent
    require(parent.is_dir() and not parent.is_symlink(),
            "output parent must be an existing regular directory")
    require(not destination.exists() and not expectations.exists(),
            "retained destination already exists")

    staging = Path(tempfile.mkdtemp(
        prefix=".wifi-auth-persistence-retain-", dir=parent))
    staged_bundle = staging / "positive"
    staged_expectations = staging / "acceptance.json"
    try:
        shutil.copytree(source, staged_bundle, copy_function=shutil.copy2)
        marker = {
            "schema": checker.EXPECTATIONS_SCHEMA,
            **expected,
            "checker_source_sha256": checker.digest(checker.CHECKER),
            "run_id": run["run_id"],
            "positive_run_sha256": checker.digest(
                staged_bundle / "run.json"),
            "positive_artifact_index_sha256": checker.digest(
                staged_bundle / "artifacts.sha256"),
        }
        write(staged_expectations, marker)
        failures = checker.check(staged_expectations, staged_bundle)
        require(not failures, "staged evidence rejected: " +
                "; ".join(failures))
        promote([
            (staged_bundle, destination),
            (staged_expectations, expectations),
        ], staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "schema": "leshy.wifi.authentication_persistence_hil.retention.v1",
        "status": "retained",
        "positive": str(destination),
        "expectations": str(expectations),
        "positive_run_sha256": checker.digest(destination / "run.json"),
        "positive_artifact_index_sha256": checker.digest(
            destination / "artifacts.sha256"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", default=checker.CID)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-firmware-sha256", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--expectations", type=Path)
    args = parser.parse_args(argv)
    default_destination, default_expectations = checker.evidence_paths(
        args.expected_version)
    args.destination = args.destination or default_destination
    args.expectations = args.expectations or default_expectations
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = retain(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
