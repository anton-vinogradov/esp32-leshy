#!/usr/bin/env python3
"""Build and run the source-bound two-board infrared HIL scenario."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from profile_hil_board import esptool_python  # noqa: E402


PRODUCT_ENV = "esp32-div-v2-clean"
FIXTURE_ENV = "esp32-div-v2-signal-fixture"
PRODUCT_FIRMWARE = (
    ROOT / "firmware/leshy1/.pio/build" / PRODUCT_ENV / "firmware.bin")
FIXTURE_FIRMWARE = (
    ROOT / "firmware/leshy_fixture/.pio/build" / FIXTURE_ENV /
    "firmware.bin")
SCENARIOS = {
    "infrared-nec-positive": (
        ROOT / "tests/hil/scenarios/infrared-nec-positive.json"),
    "nrf24-carrier-positive": (
        ROOT / "tests/hil/scenarios/nrf24-carrier-positive.json"),
    "nrf24-fixture-regression": (
        ROOT / "tests/hil/scenarios/nrf24-fixture-regression.json"),
    "nrf24-fixture-inventory": (
        ROOT / "tests/hil/scenarios/nrf24-fixture-inventory.json"),
    "subghz-ook-positive": (
        ROOT / "tests/hil/scenarios/subghz-ook-positive.json"),
    "subghz-fsk-positive": (
        ROOT / "tests/hil/scenarios/subghz-fsk-positive.json"),
}
DEADLINE_FLOW = "infrared-store-deadline"
SCENARIO = SCENARIOS["infrared-nec-positive"]
VERSION_VALUE = re.compile(
    r"-D\s+{symbol}=\\\"([^\"\r\n]+)\\\"")


def validate_fixture_profile(profile: dict[str, Any], fixture_id: str,
                             fixture_port: str | None = None) -> None:
    expected = {
        "schema": "leshy.hil.board_profile.v1",
        "status": "accepted",
        "accepted_for_fixture_flash": True,
        "writes_performed": False,
        "flash_erases_performed": 0,
        "flash_bytes_written": 0,
        "ram_stub_uploaded": False,
    }
    chip = profile.get("chip", {})
    assembly = profile.get("assembly", {})
    failures = [
        f"fixture_profile.{key}: {profile.get(key)!r} != {value!r}"
        for key, value in expected.items() if profile.get(key) != value]
    for key, value in {
            "family": "esp32-s3", "fixture_id": fixture_id,
            "flash_size": "16MB"}.items():
        if chip.get(key) != value:
            failures.append(
                f"fixture_profile.chip.{key}: {chip.get(key)!r} != {value!r}")
    for key, value in {
            "profile": "esp32-div-v2-n16", "extension_modules": "none",
            "antennas_attached": True}.items():
        if assembly.get(key) != value:
            failures.append(
                "fixture_profile.assembly."
                f"{key}: {assembly.get(key)!r} != {value!r}")
    operations = profile.get("operations")
    if (not isinstance(operations, list) or len(operations) != 4 or
            any(not isinstance(value, dict) or
                value.get("read_only") is not True or
                value.get("returncode") != 0 for value in operations)):
        failures.append("fixture_profile.operations: read-only proof missing")
    if fixture_port is not None and \
            profile.get("port_at_profile") != fixture_port:
        failures.append(
            "fixture_profile.port_at_profile: fixture port mismatch")
    if failures:
        raise ValueError("; ".join(failures))


def read_version(config: Path, symbol: str) -> str:
    text = config.read_text(encoding="utf-8")
    match = re.search(VERSION_VALUE.pattern.format(symbol=re.escape(symbol)),
                      text)
    if match is None:
        raise ValueError(f"{symbol} is missing from {config}")
    return match.group(1)


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def require_clean_source() -> str:
    status = git_output("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError(
            "source tree is not clean; commit the exact candidate before HIL")
    commit = git_output("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("HEAD is not a full lowercase Git commit ID")
    return commit


def load_profile(path: Path, fixture_port: str) -> tuple[dict[str, Any], str]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    fixture_id = profile.get("chip", {}).get("fixture_id")
    if not isinstance(fixture_id, str):
        raise ValueError("fixture profile has no canonical fixture ID")
    validate_fixture_profile(profile, fixture_id, fixture_port)
    return profile, fixture_id


def profile_command(port: str, output: Path,
                    standard_v2_no_extensions: bool,
                    antennas_attached: bool) -> list[str]:
    command = [
        str(esptool_python()), str(ROOT / "tools/profile_hil_board.py"),
        "--port", port,
        "--output", str(output),
        "--execute-read-only-profile",
    ]
    if standard_v2_no_extensions:
        command.append("--declare-standard-v2-no-extensions")
    if antennas_attached:
        command.append("--declare-antennas-attached")
    return command


def runner_command(*, candidate_port: str, fixture_port: str,
                   profile: Path, fixture_id: str, expected_cid: str,
                   output: Path, source_commit: str,
                   product_version: str, fixture_version: str,
                   reuse_candidate: bool,
                   reuse_fixture: bool,
                   scenario: Path = SCENARIO) -> list[str]:
    command = [
        str(esptool_python()), str(ROOT / "tools/run_hil_scenario.py"),
        "--scenario", str(scenario),
        "--port", f"candidate={candidate_port}",
        "--port", f"fixture={fixture_port}",
        "--firmware", str(PRODUCT_FIRMWARE),
        "--expected-version", product_version,
        "--expected-cid", expected_cid,
        "--source-commit", source_commit,
        "--output", str(output),
        "--fixture-firmware", str(FIXTURE_FIRMWARE),
        "--fixture-profile", str(profile),
        "--expected-fixture-version", fixture_version,
        "--expected-fixture-id", fixture_id,
        "--fixture-source-commit", source_commit,
    ]
    command.append("--reuse-exact-flash" if reuse_candidate else "--flash")
    command.append(
        "--reuse-exact-fixture-flash" if reuse_fixture
        else "--flash-fixture")
    return command


def deadline_runner_command(*, candidate_port: str, fixture_port: str,
                            profile: Path, fixture_id: str,
                            expected_cid: str, output: Path,
                            source_commit: str, product_version: str,
                            fixture_version: str,
                            reuse_candidate: bool,
                            reuse_fixture: bool) -> list[str]:
    command = [
        str(esptool_python()),
        str(ROOT / "tools/run_1x_infrared_store_deadline_hil.py"),
        "--candidate-port", candidate_port,
        "--fixture-port", fixture_port,
        "--firmware", str(PRODUCT_FIRMWARE),
        "--fixture-firmware", str(FIXTURE_FIRMWARE),
        "--fixture-profile", str(profile),
        "--expected-version", product_version,
        "--expected-fixture-version", fixture_version,
        "--expected-fixture-id", fixture_id,
        "--expected-cid", expected_cid,
        "--source-commit", source_commit,
        "--output", str(output),
    ]
    command.append("--reuse-exact-flash" if reuse_candidate else "--flash")
    command.append(
        "--reuse-exact-fixture-flash" if reuse_fixture
        else "--flash-fixture")
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-port", required=True)
    parser.add_argument("--fixture-port", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--scenario", choices=(*SCENARIOS, DEADLINE_FLOW),
        default="infrared-nec-positive")
    profile = parser.add_mutually_exclusive_group(required=True)
    profile.add_argument("--fixture-profile", type=Path)
    profile.add_argument("--profile-fixture-read-only", action="store_true")
    parser.add_argument(
        "--declare-standard-v2-no-extensions", action="store_true")
    parser.add_argument("--declare-antennas-attached", action="store_true")
    parser.add_argument("--reuse-exact-candidate-flash", action="store_true")
    parser.add_argument("--reuse-exact-fixture-flash", action="store_true")
    args = parser.parse_args()

    if args.candidate_port == args.fixture_port:
        parser.error("candidate and fixture ports must be distinct")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.profile_fixture_read_only and not (
            args.declare_standard_v2_no_extensions and
            args.declare_antennas_attached):
        parser.error(
            "automatic profiling requires both explicit assembly declarations")
    if args.fixture_profile is not None and (
            args.declare_standard_v2_no_extensions or
            args.declare_antennas_attached):
        parser.error(
            "assembly declarations apply only to a new read-only profile")
    try:
        source_commit = require_clean_source()
        product_version = read_version(
            ROOT / "firmware/leshy1/platformio.ini", "LESHY1_VERSION")
        fixture_version = read_version(
            ROOT / "firmware/leshy_fixture/platformio.ini",
            "LESHY_FIXTURE_VERSION")
        fixture_profile = args.fixture_profile
        if args.profile_fixture_read_only:
            fixture_profile = args.output.with_name(
                args.output.name + ".fixture-profile.json")
            subprocess.run(
                profile_command(
                    args.fixture_port, fixture_profile,
                    args.declare_standard_v2_no_extensions,
                    args.declare_antennas_attached),
                cwd=ROOT, check=True)
        assert fixture_profile is not None
        if not fixture_profile.is_file():
            raise ValueError(f"fixture profile not found: {fixture_profile}")
        _, fixture_id = load_profile(fixture_profile, args.fixture_port)

        subprocess.run([str(ROOT / "tools/build.sh")], cwd=ROOT, check=True)
        subprocess.run(
            [str(ROOT / "tools/build_ir_fixture.sh")], cwd=ROOT, check=True)
        if args.scenario == DEADLINE_FLOW:
            command = deadline_runner_command(
                candidate_port=args.candidate_port,
                fixture_port=args.fixture_port,
                profile=fixture_profile,
                fixture_id=fixture_id,
                expected_cid=args.expected_cid,
                output=args.output,
                source_commit=source_commit,
                product_version=product_version,
                fixture_version=fixture_version,
                reuse_candidate=args.reuse_exact_candidate_flash,
                reuse_fixture=args.reuse_exact_fixture_flash)
        else:
            command = runner_command(
                candidate_port=args.candidate_port,
                fixture_port=args.fixture_port,
                profile=fixture_profile,
                fixture_id=fixture_id,
                expected_cid=args.expected_cid,
                output=args.output,
                source_commit=source_commit,
                product_version=product_version,
                fixture_version=fixture_version,
                reuse_candidate=args.reuse_exact_candidate_flash,
                reuse_fixture=args.reuse_exact_fixture_flash,
                scenario=SCENARIOS[args.scenario])
        subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
