#!/usr/bin/env python3
"""Validate and atomically retain exact CAP049 board-01 HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import check_wifi_authentication_capture_hil_acceptance as acceptance


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence"
CURRENT_RUNNER = ROOT / "tools/run_1x_wifi_authentication_capture_hil.py"
DEFAULT_DESTINATION = (
    EVIDENCE / "board-01-wifi-authentication-capture-1.0.0-dev.243"
)
DEFAULT_EXPECTATIONS = EVIDENCE / (
    "board-01-wifi-authentication-capture-1.0.0-dev.243-acceptance.json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
SESSION_ID = re.compile(r"[0-9a-f]{32}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_input_tree(path: Path) -> Path:
    require(path.is_dir() and not path.is_symlink(),
            "positive: regular source directory required")
    for item in path.rglob("*"):
        require(not item.is_symlink(),
                f"positive: symlink rejected: {item}")
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
    source = safe_input_tree(args.positive)
    expected = {
        "version": args.expected_version,
        "cid": args.expected_cid,
        "source": args.expected_source_commit,
        "firmware": args.expected_firmware_sha256,
        "app": args.expected_app_elf_sha256,
        "runner": args.expected_runner_sha256,
    }
    require(COMMIT.fullmatch(expected["source"]) is not None,
            "expected source must be a full lowercase commit")
    for field in ("firmware", "app", "runner"):
        require(SHA256.fullmatch(expected[field]) is not None,
                f"expected {field} must be lowercase SHA-256")
    require(CURRENT_RUNNER.is_file() and
            digest(CURRENT_RUNNER) == expected["runner"],
            "expected runner SHA-256 does not match current HIL runner")

    destination = args.destination.resolve()
    expectations = args.expectations.resolve()
    require(destination != expectations,
            "bundle and expectations destinations must differ")
    require(destination.parent == expectations.parent,
            "bundle and expectations must share one output parent")
    parent = destination.parent
    require(parent.is_dir() and not parent.is_symlink(),
            "output parent must be an existing regular directory")
    for output in (destination, expectations):
        require(not output.exists(), f"destination already exists: {output}")
        require(output != source and source not in output.parents,
                "outputs must not be inside source evidence")

    structural_failures: list[str] = []
    entries = acceptance.verify_manifest(source, structural_failures)
    require(not structural_failures,
            "source manifest rejected: " + "; ".join(structural_failures))
    run = load(source / "run.json")
    privacy_failures: list[str] = []
    acceptance.verify_indexed_json_privacy(
        source, entries, privacy_failures)
    require(not privacy_failures,
            "private target evidence rejected: " +
            "; ".join(privacy_failures))
    candidate = run.get("candidate")
    require(isinstance(candidate, dict), "positive.candidate missing")
    require(run.get("schema") == acceptance.RUN_SCHEMA and
            run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "positive run is not a clean CAP049 pass")
    require(run.get("expected_cid") == expected["cid"],
            "positive expected CID mismatch")
    require(run.get("runner_source_sha256") == expected["runner"],
            "positive runner SHA-256 mismatch")
    require(isinstance(run.get("run_id"), str) and
            SESSION_ID.fullmatch(run["run_id"]) is not None,
            "positive run ID must be lowercase 32-hex")
    exact_candidate = {
        "version": expected["version"],
        "source_commit": expected["source"],
        "firmware_sha256": expected["firmware"],
        "app_elf_sha256": expected["app"],
    }
    for field, value in exact_candidate.items():
        require(candidate.get(field) == value,
                f"positive.candidate.{field} mismatch")
    require(candidate.get("flashed") is True and
            candidate.get("exact_boot_verified") is True and
            candidate.get("flash_mode") in ("fresh", "reuse_exact"),
            "positive candidate lacks exact verified flash proof")

    staging = Path(tempfile.mkdtemp(
        prefix=".wifi-auth-capture-retain-", dir=parent))
    staged_bundle = staging / "positive"
    staged_expectations = staging / "acceptance.json"
    try:
        shutil.copytree(source, staged_bundle, copy_function=shutil.copy2)
        marker = {
            "schema": acceptance.EXPECTATIONS_SCHEMA,
            "version": expected["version"],
            "expected_cid": expected["cid"],
            "run_id": run["run_id"],
            "source_commit": expected["source"],
            "firmware_sha256": expected["firmware"],
            "app_elf_sha256": expected["app"],
            "runner_source_sha256": expected["runner"],
            "positive_run_sha256": digest(staged_bundle / "run.json"),
            "positive_artifact_index_sha256": digest(
                staged_bundle / "artifacts.sha256"),
        }
        write(staged_expectations, marker)
        check_args = acceptance.parse_args([
            "--expectations", str(staged_expectations),
            "--positive", str(staged_bundle),
            "--expected-version", expected["version"],
            "--expected-cid", expected["cid"],
            "--expected-source-commit", expected["source"],
            "--expected-firmware-sha256", expected["firmware"],
            "--expected-app-elf-sha256", expected["app"],
            "--expected-runner-sha256", expected["runner"],
        ])
        failures = acceptance.check(check_args)
        require(not failures,
                "staged acceptance failed: " + "; ".join(failures))
        promote([
            (staged_bundle, destination),
            (staged_expectations, expectations),
        ], staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "schema": "leshy.wifi.authentication_capture_hil.retention.v1",
        "status": "retained",
        "positive": str(destination),
        "expectations": str(expectations),
        "positive_run_sha256": digest(destination / "run.json"),
        "positive_artifact_index_sha256": digest(
            destination / "artifacts.sha256"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", required=True, type=Path)
    parser.add_argument("--expected-version", default=acceptance.VERSION)
    parser.add_argument("--expected-cid", default=acceptance.CID)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-firmware-sha256", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--destination", type=Path,
                        default=DEFAULT_DESTINATION)
    parser.add_argument("--expectations", type=Path,
                        default=DEFAULT_EXPECTATIONS)
    return parser.parse_args(argv)


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
