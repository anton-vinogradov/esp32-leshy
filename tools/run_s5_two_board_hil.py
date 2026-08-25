#!/usr/bin/env python3
"""Run the complete source-bound S5 two-board matrix with one build/flash."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
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
BUILD_ARTIFACTS = {
    "product": {
        name: PRODUCT_FIRMWARE.parent / name
        for name in (
            "firmware.bin", "firmware.factory.bin", "firmware.elf",
            "firmware.map")
    },
    "fixture": {
        name: FIXTURE_FIRMWARE.parent / name
        for name in (
            "firmware.bin", "firmware.factory.bin", "firmware.elf",
            "firmware.map")
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha256(commit: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return hashlib.sha256(result.stdout).hexdigest()


def save_summary(path: Path, summary: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    temporary.replace(path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_artifact_inventory() -> dict[str, dict[str, dict[str, Any]]]:
    inventory: dict[str, dict[str, dict[str, Any]]] = {}
    for role, paths in BUILD_ARTIFACTS.items():
        inventory[role] = {}
        for name, path in paths.items():
            require(path.is_file(), f"{role} build artifact missing: {name}")
            inventory[role][name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    return inventory


def require_build_artifacts(summary: dict[str, Any]) -> None:
    artifacts = summary.get("build_artifacts")
    require(isinstance(artifacts, dict) and
            set(artifacts) == set(BUILD_ARTIFACTS),
            "matrix build artifact roles mismatch")
    for role, paths in BUILD_ARTIFACTS.items():
        records = artifacts.get(role)
        require(isinstance(records, dict) and
                set(records) == set(paths),
                f"matrix {role} build artifact set mismatch")
        for name in paths:
            record = records.get(name)
            require(isinstance(record, dict) and
                    isinstance(record.get("bytes"), int) and
                    record["bytes"] > 0 and
                    isinstance(record.get("sha256"), str) and
                    re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                    is not None,
                    f"matrix {role} build artifact identity invalid: {name}")


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
                   fixture_reused: bool | None = None,
                   expected_scenario_sha256: str | None = None,
                   expected_runner_sha256: str | None = None) -> dict[str, Any]:
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
    scenario_sha256 = expected_scenario_sha256
    if scenario_sha256 is None:
        scenario_sha256 = sha256_file(SCENARIOS[scenario_id])
    if scenario.get("sha256") != scenario_sha256:
        failures.append("scenario source hash mismatch")
    child_runner_sha256 = run.get("runner_source_sha256")
    if expected_runner_sha256 is not None and \
            child_runner_sha256 != expected_runner_sha256:
        failures.append("child runner source hash mismatch")
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
        "runner_source_sha256": child_runner_sha256,
        "candidate_firmware_sha256": candidate.get("firmware_sha256"),
        "fixture_firmware_sha256": fixture.get("firmware_sha256"),
        "candidate_app_elf_sha256": candidate_app,
        "fixture_app_elf_sha256": fixture_app,
        "fixture_profile_sha256": profile_sha,
        "fixture_id": fixture.get("fixture_id"),
        "candidate_exact_flash_reused": candidate.get("exact_flash_reused"),
        "fixture_exact_flash_reused": fixture.get("exact_flash_reused"),
    }


def verify_completed_matrix(summary_path: Path, *,
                            allow_relocated_children: bool = False
                            ) -> dict[str, Any]:
    """Re-read a completed matrix and independently verify every child."""
    summary_path = summary_path.resolve()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    require(isinstance(summary, dict), "matrix summary must be an object")
    require(summary.get("schema") == SCHEMA, "matrix schema mismatch")
    require(summary.get("status") == "pass" and
            summary.get("passed") is True, "matrix is not passing")
    require(summary.get("matrix") == list(MATRIX), "matrix order mismatch")
    require(isinstance(summary.get("completed_at"), str) and
            bool(summary["completed_at"]), "matrix completion is missing")
    require(summary.get("failure") is None, "matrix retains a failure")

    source_commit = summary.get("source_commit")
    product_version = summary.get("product_version")
    fixture_version = summary.get("fixture_version")
    expected_cid = summary.get("expected_cid")
    candidate_port = summary.get("candidate_port")
    fixture_port = summary.get("fixture_port")
    fixture_id = summary.get("fixture_id")
    candidate_hash = summary.get("product_firmware_sha256")
    fixture_hash = summary.get("fixture_firmware_sha256")
    require(isinstance(source_commit, str) and
            re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None,
            "matrix source commit is invalid")
    require(isinstance(product_version, str) and bool(product_version),
            "matrix product version is invalid")
    require(isinstance(fixture_version, str) and bool(fixture_version),
            "matrix fixture version is invalid")
    require(isinstance(expected_cid, str) and
            re.fullmatch(r"[0-9A-F]{32}", expected_cid) is not None,
            "matrix CID is invalid")
    require(isinstance(candidate_port, str) and candidate_port and
            isinstance(fixture_port, str) and fixture_port and
            candidate_port != fixture_port, "matrix role ports are invalid")
    require(isinstance(fixture_id, str) and
            re.fullmatch(r"[0-9A-F]{16}", fixture_id) is not None,
            "matrix fixture ID is invalid")
    require(isinstance(candidate_hash, str) and
            re.fullmatch(r"[0-9a-f]{64}", candidate_hash) is not None and
            isinstance(fixture_hash, str) and
            re.fullmatch(r"[0-9a-f]{64}", fixture_hash) is not None,
            "matrix firmware hashes are invalid")
    require(summary.get("runner_source_sha256") ==
            git_blob_sha256(source_commit, "tools/run_s5_two_board_hil.py"),
            "matrix runner source identity mismatch")
    require_build_artifacts(summary)
    require(summary["build_artifacts"]["product"]["firmware.bin"]
            ["sha256"] == candidate_hash,
            "matrix product firmware/build identity mismatch")
    require(summary["build_artifacts"]["fixture"]["firmware.bin"]
            ["sha256"] == fixture_hash,
            "matrix fixture firmware/build identity mismatch")
    child_runner_sha256 = git_blob_sha256(
        source_commit, "tools/run_hil_scenario.py")

    entries = summary.get("runs")
    require(isinstance(entries, list) and len(entries) == len(MATRIX),
            "matrix child count mismatch")
    accepted: list[dict[str, Any]] = []
    for index, scenario_id in enumerate(MATRIX):
        entry = entries[index]
        require(isinstance(entry, dict) and
                entry.get("scenario_id") == scenario_id,
                f"{scenario_id}: parent child identity mismatch")
        expected_path = (summary_path.parent / scenario_id / "run.json").resolve()
        recorded_path = Path(str(entry.get("run", "")))
        if not recorded_path.is_absolute():
            recorded_path = ROOT / recorded_path
        recorded_path = recorded_path.resolve()
        require(expected_path.is_file(), f"{scenario_id}: child is missing")
        if not allow_relocated_children:
            require(recorded_path == expected_path,
                    f"{scenario_id}: child path mismatch")
        require(entry.get("run_sha256") == sha256_file(expected_path),
                f"{scenario_id}: child run hash mismatch")
        candidate_reused = entry.get("candidate_exact_flash_reused")
        fixture_reused = entry.get("fixture_exact_flash_reused")
        require(isinstance(candidate_reused, bool) and
                isinstance(fixture_reused, bool),
                f"{scenario_id}: flash/reuse state is invalid")
        if index > 0:
            require(candidate_reused and fixture_reused,
                    f"{scenario_id}: later child did not reuse exact images")
        checked = accepted_child(
            expected_path, scenario_id, source_commit,
            product_version=product_version,
            fixture_version=fixture_version,
            expected_cid=expected_cid,
            candidate_port=candidate_port,
            fixture_port=fixture_port,
            fixture_id=fixture_id,
            candidate_firmware_sha256=candidate_hash,
            fixture_firmware_sha256=fixture_hash,
            candidate_reused=candidate_reused,
            fixture_reused=fixture_reused,
            expected_scenario_sha256=git_blob_sha256(
                source_commit,
                str(SCENARIOS[scenario_id].relative_to(ROOT))),
            expected_runner_sha256=child_runner_sha256)
        for key, value in checked.items():
            if key != "run":
                require(entry.get(key) == value,
                        f"{scenario_id}: parent child {key} mismatch")
        accepted.append(checked)

    candidate_apps = {value["candidate_app_elf_sha256"] for value in accepted}
    fixture_apps = {value["fixture_app_elf_sha256"] for value in accepted}
    profiles = {value["fixture_profile_sha256"] for value in accepted}
    fixture_ids = {value["fixture_id"] for value in accepted}
    require(candidate_apps == {summary.get("product_app_elf_sha256")},
            "matrix candidate app identity mismatch")
    require(fixture_apps == {summary.get("fixture_app_elf_sha256")},
            "matrix fixture app identity mismatch")
    require(profiles == {summary.get("fixture_profile_sha256")},
            "matrix fixture profile identity mismatch")
    require(fixture_ids == {fixture_id}, "matrix fixture identity drift")
    return summary


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
    parser.add_argument("--retain-destination", type=Path)
    parser.add_argument("--retain-summary", type=Path)
    parser.add_argument("--retain-evidence-id", action="append", default=[])
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
    if (args.retain_destination is None) != (args.retain_summary is None):
        parser.error(
            "retain destination and summary must be supplied together")
    if args.retain_destination is not None and (
            args.retain_destination.exists() or args.retain_summary.exists()):
        parser.error("retain destination and summary must not already exist")

    summary_path = args.output / "run.json"
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
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
        summary["build_artifacts"] = build_artifact_inventory()
        summary["product_firmware_sha256"] = summary[
            "build_artifacts"]["product"]["firmware.bin"]["sha256"]
        summary["fixture_firmware_sha256"] = summary[
            "build_artifacts"]["fixture"]["firmware.bin"]["sha256"]
        child_runner_sha256 = sha256_file(
            ROOT / "tools/run_hil_scenario.py")

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
                fixture_reused=reuse_fixture,
                expected_runner_sha256=child_runner_sha256))
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
        verify_completed_matrix(summary_path)
        if args.retain_destination is not None:
            retention_command = [
                sys.executable,
                str(ROOT / "tools/retain_s5_two_board_matrix.py"),
                "retain", "--source", str(args.output),
                "--destination", str(args.retain_destination),
                "--summary", str(args.retain_summary),
            ]
            for evidence_id in args.retain_evidence_id:
                retention_command.extend(["--evidence-id", evidence_id])
            subprocess.run(retention_command, cwd=ROOT, check=True)
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
