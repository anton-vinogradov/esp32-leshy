#!/usr/bin/env python3
"""Fail-closed acceptance check for retained CAP049 board-01 HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from read_1x_version import read_version


ROOT = Path(__file__).resolve().parents[1]
CURRENT_RUNNER = ROOT / "tools/run_1x_wifi_authentication_capture_hil.py"
HIL_CHECKER = ROOT / "tools/check_wifi_authentication_capture_hil_run.py"
CID = "FE343253440000002000000055019CB7"
BOARD = "board-01"
PORT = "/dev/cu.usbmodem2101"
RUN_SCHEMA = "leshy.wifi.authentication_capture_hil.run.v1"
EXPECTATIONS_SCHEMA = (
    "leshy.wifi.authentication_capture_hil.acceptance_expectations.v1"
)
EVIDENCE = ROOT / "tests/hil/evidence"


def evidence_paths(version: str) -> tuple[Path, Path]:
    stem = f"board-01-wifi-authentication-capture-{version}"
    return EVIDENCE / stem, EVIDENCE / f"{stem}-acceptance.json"


VERSION = read_version()
DEFAULT_POSITIVE, DEFAULT_EXPECTATIONS = evidence_paths(VERSION)
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
SESSION_ID = re.compile(r"[0-9a-f]{32}")
PRIVATE_TARGET_KEYS = frozenset({
    "target_bssid", "target_identity_hash", "identity_hash",
    "wifi_network_selected_identity_hash", "ssid", "bssid", "target_label",
    "wifi_network_order_hash", "wifi_device_order_hash",
})
MAC_ADDRESS = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def verify_private_target_absent(failures: list[str], value: Any,
                                 path: str = "run") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            private_key = (isinstance(key, str) and
                           key.lower() in PRIVATE_TARGET_KEYS)
            require(failures, not private_key,
                    f"{path}.{key}: private target key retained")
            verify_private_target_absent(failures, item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            verify_private_target_absent(failures, item,
                                         f"{path}[{index}]")
    elif isinstance(value, str):
        require(failures, MAC_ADDRESS.search(value) is None,
                f"{path}: MAC-like private identifier retained")


def load_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{label}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{label}: JSON object expected")
        return {}
    return value


def safe_bundle(path: Path, failures: list[str]) -> Path:
    resolved = path.resolve()
    require(failures, path.is_dir() and not path.is_symlink(),
            "positive: regular bundle directory required")
    if path.is_dir():
        for item in path.rglob("*"):
            require(failures, not item.is_symlink(),
                    f"positive: symlink rejected: {item}")
    return resolved


def verify_manifest(bundle: Path, failures: list[str]) -> dict[str, str]:
    index = bundle / "artifacts.sha256"
    if not index.is_file() or index.is_symlink():
        failures.append("positive.artifacts.sha256: missing regular file")
        return {}
    entries: dict[str, str] = {}
    try:
        lines = index.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        failures.append(f"positive.artifacts.sha256: {error}")
        return {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"positive.artifacts.sha256:{number}: malformed")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or
                name in entries or name == "artifacts.sha256"):
            failures.append(
                f"positive.artifacts.sha256:{number}: unsafe/duplicate {name!r}")
            continue
        target = bundle / relative
        if not target.is_file() or target.is_symlink():
            failures.append(f"positive: indexed artifact missing: {name}")
        else:
            try:
                actual = digest(target)
            except OSError as error:
                failures.append(f"positive.{name}: {error}")
            else:
                require(failures, actual == expected,
                        f"positive.{name}: artifact hash mismatch")
        entries[name] = expected
    try:
        actual_files = {
            item.relative_to(bundle).as_posix()
            for item in bundle.rglob("*")
            if item.is_file() and item != index
        }
    except OSError as error:
        failures.append(f"positive: inventory failed: {error}")
        actual_files = set()
    require(failures, set(entries) == actual_files,
            "positive.artifacts.sha256: exact inventory mismatch")
    require(failures, "run.json" in entries and "firmware.bin" in entries,
            "positive.artifacts.sha256: run/firmware must be indexed")
    return entries


def verify_indexed_json_privacy(bundle: Path, entries: dict[str, str],
                                failures: list[str]) -> None:
    """Fail closed if any manifest-indexed JSON retains a private target."""
    for name in sorted(entries):
        if Path(name).suffix.lower() != ".json":
            continue
        value = load_json(bundle / name, failures, f"positive.{name}")
        verify_private_target_absent(failures, value, f"positive.{name}")


def verify_expectations(marker: dict[str, Any], failures: list[str],
                        args: argparse.Namespace) -> None:
    fields = {
        "schema", "version", "expected_cid", "run_id", "source_commit",
        "firmware_sha256", "app_elf_sha256", "runner_source_sha256",
        "positive_run_sha256", "positive_artifact_index_sha256",
    }
    require(failures, set(marker) == fields,
            "expectations: exact field inventory required")
    expected = {
        "schema": EXPECTATIONS_SCHEMA,
        "version": args.expected_version,
        "expected_cid": args.expected_cid,
        "source_commit": args.expected_source_commit,
        "firmware_sha256": args.expected_firmware_sha256,
        "app_elf_sha256": args.expected_app_elf_sha256,
        "runner_source_sha256": args.expected_runner_sha256,
    }
    for field, value in expected.items():
        require(failures, marker.get(field) == value,
                f"expectations.{field}: exact pin mismatch")
    require(failures, isinstance(marker.get("run_id"), str) and
            SESSION_ID.fullmatch(marker["run_id"]) is not None,
            "expectations.run_id: lowercase 32-hex required")
    require(failures, COMMIT.fullmatch(args.expected_source_commit) is not None,
            "expected source commit must be full lowercase hexadecimal")
    for field in (
            "expected_firmware_sha256", "expected_app_elf_sha256",
            "expected_runner_sha256"):
        require(failures, SHA256.fullmatch(getattr(args, field)) is not None,
                f"{field}: lowercase SHA-256 required")
    for field in ("positive_run_sha256",
                  "positive_artifact_index_sha256"):
        require(failures, isinstance(marker.get(field), str) and
                SHA256.fullmatch(marker[field]) is not None,
                f"expectations.{field}: lowercase SHA-256 required")


def run_semantic_checker(bundle: Path, marker: dict[str, Any]) -> list[str]:
    command = [
        sys.executable, str(HIL_CHECKER), "--run", str(bundle),
        "--expected-version", str(marker.get("version", "")),
        "--expected-cid", str(marker.get("expected_cid", "")),
        "--source-commit", str(marker.get("source_commit", "")),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return []
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return [f"positive semantic HIL checker rejected bundle: {output}"]


def check(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    bundle = safe_bundle(args.positive, failures)
    if (not args.expectations.is_file() or
            args.expectations.is_symlink()):
        failures.append("expectations: regular JSON file required")
        marker: dict[str, Any] = {}
    else:
        marker = load_json(args.expectations, failures, "expectations")
    verify_expectations(marker, failures, args)
    require(failures, CURRENT_RUNNER.is_file(), "current CAP049 runner missing")
    require(failures, HIL_CHECKER.is_file(), "current CAP049 checker missing")
    if CURRENT_RUNNER.is_file():
        require(failures, digest(CURRENT_RUNNER) == args.expected_runner_sha256,
                "expected runner SHA-256 does not match current runner")
    if failures:
        return failures

    entries = verify_manifest(bundle, failures)
    verify_indexed_json_privacy(bundle, entries, failures)
    run_path = bundle / "run.json"
    index_path = bundle / "artifacts.sha256"
    run = load_json(run_path, failures, "positive.run")
    require(failures, digest(run_path) == marker.get("positive_run_sha256"),
            "positive.run.json: acceptance pin mismatch")
    require(failures,
            digest(index_path) == marker.get("positive_artifact_index_sha256"),
            "positive.artifacts.sha256: acceptance pin mismatch")
    require(failures, run.get("schema") == RUN_SCHEMA and
            run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "positive.run: clean pass required")
    require(failures, run.get("run_id") == marker.get("run_id"),
            "positive.run_id: acceptance pin mismatch")
    require(failures,
            run.get("expected_cid") == marker.get("expected_cid"),
            "positive.expected_cid: acceptance pin mismatch")
    require(failures,
            run.get("runner_source_sha256") ==
                marker.get("runner_source_sha256"),
            "positive.runner_source_sha256: acceptance pin mismatch")
    candidate = run.get("candidate")
    require(failures, isinstance(candidate, dict),
            "positive.candidate: object required")
    if isinstance(candidate, dict):
        for field in ("version", "source_commit", "firmware_sha256",
                      "app_elf_sha256"):
            require(failures, candidate.get(field) == marker.get(field),
                    f"positive.candidate.{field}: acceptance pin mismatch")
        require(failures, candidate.get("flashed") is True and
                candidate.get("exact_boot_verified") is True and
                candidate.get("flash_mode") in ("fresh", "reuse_exact"),
                "positive.candidate: exact verified flash required")
    firmware = bundle / "firmware.bin"
    require(failures,
            entries.get("firmware.bin") == marker.get("firmware_sha256"),
            "positive.firmware.bin: manifest/candidate binding mismatch")
    if firmware.is_file():
        try:
            embedded = app_elf_sha256(firmware)
        except (OSError, ValueError, struct.error) as error:
            failures.append(f"positive.firmware.bin: invalid ESP image: {error}")
        else:
            require(failures, embedded == marker.get("app_elf_sha256"),
                    "positive.firmware.bin: embedded app identity mismatch")
    if not failures:
        failures.extend(run_semantic_checker(bundle, marker))
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expectations", type=Path)
    parser.add_argument("--positive", type=Path)
    parser.add_argument("--expected-version", default=VERSION)
    parser.add_argument("--expected-cid", default=CID)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-firmware-sha256", required=True)
    parser.add_argument("--expected-app-elf-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    args = parser.parse_args(argv)
    default_positive, default_expectations = evidence_paths(
        args.expected_version)
    if args.positive is None:
        args.positive = default_positive
    if args.expectations is None:
        args.expectations = default_expectations
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = check(args)
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "schema": EXPECTATIONS_SCHEMA,
        "status": "pass",
        "version": args.expected_version,
        "board": BOARD,
        "port": PORT,
        "positive": str(args.positive.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
