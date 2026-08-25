#!/usr/bin/env python3
"""Run the complete source-bound S5 two-board matrix with one build/flash."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from run_ir_two_board_hil import (
    FIXTURE_FIRMWARE,
    PRODUCT_FIRMWARE,
    ROOT,
    SCENARIOS,
    load_profile,
    profile_command,
    read_version,
    require_clean_source,
    runner_command,
)


MATRIX = (
    "infrared-nec-positive",
    "nrf24-carrier-positive",
    "subghz-ook-positive",
    "subghz-fsk-positive",
)
SCHEMA = "leshy.hil.s5_two_board_matrix.run.v1"
CHILD_SCHEMA = "leshy.hil.scenario_run.v1"
CHECKPOINTS = {
    "infrared-nec-positive": "physical_ir_nec_decode_save",
    "nrf24-carrier-positive": "physical_nrf24_known_signal_finder",
    "subghz-ook-positive": "physical_subghz_ook_capture_save",
    "subghz-fsk-positive": "physical_subghz_fsk_capture_save",
}
FINAL_REPORTS = {
    "infrared-nec-positive": "final_home",
    "nrf24-carrier-positive": "final_home",
    "subghz-ook-positive": "final",
    "subghz-fsk-positive": "final",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_summary(path: Path, summary: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    temporary.replace(path)


def accepted_child(run_path: Path, scenario_id: str, source_commit: str, *,
                   product_version: str | None = None,
                   fixture_version: str | None = None,
                   expected_cid: str | None = None,
                   candidate_port: str | None = None,
                   fixture_port: str | None = None,
                   fixture_id: str | None = None,
                   candidate_firmware_sha256: str | None = None,
                   fixture_firmware_sha256: str | None = None,
                   candidate_reused: bool | None = None,
                   fixture_reused: bool | None = None) -> dict[str, Any]:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    candidate = run.get("candidate", {})
    fixture = run.get("fixture", {})
    scenario = run.get("scenario", {})
    ports = run.get("ports", {})
    cleanup = run.get("cleanup", {})
    fixture_cleanup = fixture.get("cleanup", {})
    final = run.get("reports", {}).get(FINAL_REPORTS[scenario_id], {})
    failures: list[str] = []
    if run.get("schema") != CHILD_SCHEMA:
        failures.append("child schema mismatch")
    if run.get("passed") is not True:
        failures.append("passed is not true")
    if run.get("failures") != []:
        failures.append("failures are not empty")
    if run.get("gate_eligible") is not True:
        failures.append("child is not gate eligible")
    if run.get("checkpoint") != CHECKPOINTS[scenario_id]:
        failures.append("checkpoint mismatch")
    if scenario.get("id") != scenario_id:
        failures.append("scenario identity mismatch")
    scenario_path = SCENARIOS[scenario_id]
    if scenario.get("sha256") != sha256_file(scenario_path):
        failures.append("scenario source hash mismatch")
    if candidate.get("source_commit") != source_commit or \
            fixture.get("source_commit") != source_commit:
        failures.append("source commit mismatch")
    if product_version is not None and \
            candidate.get("version") != product_version:
        failures.append("candidate version mismatch")
    if fixture_version is not None and \
            fixture.get("version") != fixture_version:
        failures.append("fixture version mismatch")
    if expected_cid is not None and run.get("expected_cid") != expected_cid:
        failures.append("CID mismatch")
    if candidate_port is not None and ports.get("candidate") != candidate_port:
        failures.append("candidate port mismatch")
    if fixture_port is not None and ports.get("fixture") != fixture_port:
        failures.append("fixture port mismatch")
    if fixture_id is not None and fixture.get("fixture_id") != fixture_id:
        failures.append("fixture identity mismatch")
    if candidate_firmware_sha256 is not None and \
            candidate.get("firmware_sha256") != candidate_firmware_sha256:
        failures.append("candidate firmware mismatch")
    if fixture_firmware_sha256 is not None and \
            fixture.get("firmware_sha256") != fixture_firmware_sha256:
        failures.append("fixture firmware mismatch")
    if candidate_reused is not None and (
            candidate.get("exact_flash_reused") is not candidate_reused or
            candidate.get("flashed") is candidate_reused):
        failures.append("candidate flash/reuse contract mismatch")
    if fixture_reused is not None and (
            fixture.get("exact_flash_reused") is not fixture_reused or
            fixture.get("flashed") is fixture_reused):
        failures.append("fixture flash/reuse contract mismatch")
    if cleanup.get("complete") is not True or \
            final.get("page") != "home" or \
            final.get("runtime_owner") != "none" or \
            final.get("lease_mask") != 0:
        failures.append("candidate terminal cleanup mismatch")
    if (fixture_cleanup.get("state") != "stopped" or
            fixture_cleanup.get("output_inactive") is not True or
            fixture_cleanup.get("ir_tx_inactive") is not True or
            fixture_cleanup.get("nrf_ce_inactive") is not True or
            fixture_cleanup.get("nrf_powered_down") is not True or
            fixture_cleanup.get("cc_transmit_active") is not False or
            fixture_cleanup.get("cc_idle") is not True or
            fixture_cleanup.get("cc_power_cleared") is not True or
            fixture_cleanup.get("cc_tx_fifo_cleared") is not True):
        failures.append("fixture terminal cleanup mismatch")
    candidate_app = candidate.get("app_elf_sha256")
    fixture_app = fixture.get("app_elf_sha256")
    profile_sha = fixture.get("profile_sha256")
    if not isinstance(candidate_app, str) or len(candidate_app) != 64:
        failures.append("candidate app identity invalid")
    if not isinstance(fixture_app, str) or len(fixture_app) != 64:
        failures.append("fixture app identity invalid")
    if not isinstance(profile_sha, str) or len(profile_sha) != 64:
        failures.append("fixture profile identity invalid")
    if failures:
        raise ValueError(f"{scenario_id}: " + "; ".join(failures))
    return {
        "scenario_id": scenario_id,
        "passed": True,
        "run": str(run_path),
        "run_sha256": sha256_file(run_path),
        "candidate_firmware_sha256": candidate.get("firmware_sha256"),
        "fixture_firmware_sha256": fixture.get("firmware_sha256"),
        "candidate_app_elf_sha256": candidate_app,
        "fixture_app_elf_sha256": fixture_app,
        "fixture_profile_sha256": profile_sha,
        "fixture_id": fixture.get("fixture_id"),
        "candidate_exact_flash_reused": candidate.get("exact_flash_reused"),
        "fixture_exact_flash_reused": fixture.get("exact_flash_reused"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-port", required=True)
    parser.add_argument("--fixture-port", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
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

    summary_path = args.output / "run.json"
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "initializing",
        "passed": False,
        "started_at": utc_now(),
        "completed_at": None,
        "source_commit": None,
        "product_version": None,
        "fixture_version": None,
        "candidate_port": args.candidate_port,
        "fixture_port": args.fixture_port,
        "expected_cid": args.expected_cid,
        "matrix": list(MATRIX),
        "runs": [],
        "failure": None,
    }
    args.output.mkdir(parents=True)
    save_summary(summary_path, summary)

    try:
        source_commit = require_clean_source()
        product_version = read_version(
            ROOT / "firmware/leshy1/platformio.ini", "LESHY1_VERSION")
        fixture_version = read_version(
            ROOT / "firmware/leshy_fixture/platformio.ini",
            "LESHY_FIXTURE_VERSION")
        summary.update({
            "source_commit": source_commit,
            "product_version": product_version,
            "fixture_version": fixture_version,
        })

        fixture_profile = args.fixture_profile
        if args.profile_fixture_read_only:
            fixture_profile = args.output.with_name(
                args.output.name + ".fixture-profile.json")
            summary["status"] = "profiling_fixture"
            save_summary(summary_path, summary)
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
        summary["fixture_profile"] = str(fixture_profile)
        summary["fixture_id"] = fixture_id

        summary["status"] = "building_once"
        save_summary(summary_path, summary)
        subprocess.run([str(ROOT / "tools/build.sh")], cwd=ROOT, check=True)
        subprocess.run(
            [str(ROOT / "tools/build_ir_fixture.sh")], cwd=ROOT, check=True)
        summary["product_firmware_sha256"] = sha256_file(PRODUCT_FIRMWARE)
        summary["fixture_firmware_sha256"] = sha256_file(FIXTURE_FIRMWARE)

        for index, scenario_id in enumerate(MATRIX):
            output = args.output / scenario_id
            summary["status"] = f"running:{scenario_id}"
            save_summary(summary_path, summary)
            command = runner_command(
                candidate_port=args.candidate_port,
                fixture_port=args.fixture_port,
                profile=fixture_profile,
                fixture_id=fixture_id,
                expected_cid=args.expected_cid,
                output=output,
                source_commit=source_commit,
                product_version=product_version,
                fixture_version=fixture_version,
                reuse_candidate=(
                    index > 0 or args.reuse_exact_candidate_flash),
                reuse_fixture=(
                    index > 0 or args.reuse_exact_fixture_flash),
                scenario=SCENARIOS[scenario_id])
            subprocess.run(command, cwd=ROOT, check=True)
            reuse_candidate = index > 0 or args.reuse_exact_candidate_flash
            reuse_fixture = index > 0 or args.reuse_exact_fixture_flash
            summary["runs"].append(accepted_child(
                output / "run.json", scenario_id, source_commit,
                product_version=product_version,
                fixture_version=fixture_version,
                expected_cid=args.expected_cid,
                candidate_port=args.candidate_port,
                fixture_port=args.fixture_port,
                fixture_id=fixture_id,
                candidate_firmware_sha256=(
                    summary["product_firmware_sha256"]),
                fixture_firmware_sha256=(
                    summary["fixture_firmware_sha256"]),
                candidate_reused=reuse_candidate,
                fixture_reused=reuse_fixture))
            save_summary(summary_path, summary)

        if len(summary["runs"]) != len(MATRIX):
            raise ValueError("matrix ended without all required scenarios")
        candidate_hashes = {
            run["candidate_firmware_sha256"] for run in summary["runs"]}
        fixture_hashes = {
            run["fixture_firmware_sha256"] for run in summary["runs"]}
        candidate_app_hashes = {
            run["candidate_app_elf_sha256"] for run in summary["runs"]}
        fixture_app_hashes = {
            run["fixture_app_elf_sha256"] for run in summary["runs"]}
        fixture_profile_hashes = {
            run["fixture_profile_sha256"] for run in summary["runs"]}
        fixture_ids = {run["fixture_id"] for run in summary["runs"]}
        if candidate_hashes != {summary["product_firmware_sha256"]}:
            raise ValueError("candidate image identity drift across matrix")
        if fixture_hashes != {summary["fixture_firmware_sha256"]}:
            raise ValueError("fixture image identity drift across matrix")
        if len(candidate_app_hashes) != 1 or len(fixture_app_hashes) != 1:
            raise ValueError("app identity drift across matrix")
        if len(fixture_profile_hashes) != 1 or fixture_ids != {fixture_id}:
            raise ValueError("fixture admission identity drift across matrix")
        summary.update({
            "status": "pass",
            "passed": True,
            "completed_at": utc_now(),
            "product_app_elf_sha256": next(iter(candidate_app_hashes)),
            "fixture_app_elf_sha256": next(iter(fixture_app_hashes)),
            "fixture_profile_sha256": next(iter(fixture_profile_hashes)),
        })
        save_summary(summary_path, summary)
    except (OSError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError) as error:
        summary.update({
            "status": "failed",
            "passed": False,
            "completed_at": utc_now(),
            "failure": str(error),
        })
        save_summary(summary_path, summary)
        print(f"S5 two-board matrix failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "schema": SCHEMA,
        "passed": True,
        "runs": len(summary["runs"]),
        "output": str(summary_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
