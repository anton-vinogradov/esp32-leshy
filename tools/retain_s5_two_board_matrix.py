#!/usr/bin/env python3
"""Retain and independently verify a complete S5 two-board matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from run_s5_two_board_hil import (
    BUILD_ARTIFACTS,
    MATRIX,
    ROOT,
    SCENARIOS,
    sha256_file,
    verify_completed_matrix,
)


SUMMARY_SCHEMA = "leshy.hil.s5_two_board_matrix.acceptance.v1"
PROVENANCE_SCHEMA = "leshy.hil.s5_two_board_matrix.provenance.v1"
SOURCE_PATHS = (
    "tools/run_s5_two_board_hil.py",
    "tools/run_hil_scenario.py",
    "tools/retain_s5_two_board_matrix.py",
)
OMITTED_CHILD_FILES = {
    "artifacts.sha256", "firmware.bin", "fixture.bin",
    "fixture-profile.json",
}
HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def git_blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0,
            result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest_records(bundle: Path) -> dict[str, str]:
    manifest = bundle / "artifacts.sha256"
    require(manifest.is_file(), f"artifact manifest missing: {bundle}")
    records: dict[str, str] = {}
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None,
                f"malformed artifact manifest line {number}: {bundle}")
        expected, relative = match.groups()
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts and
                relative not in records,
                f"unsafe or duplicate artifact path: {relative}")
        records[relative] = expected
    return records


def verify_source_manifest(source: Path) -> dict[str, str]:
    records = manifest_records(source)
    actual = {
        str(path.relative_to(source)): path
        for path in source.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(set(records) == set(actual),
            f"source manifest coverage mismatch: {source}")
    for relative, path in actual.items():
        require(sha256_file(path) == records[relative],
                f"source artifact mismatch: {source.name}/{relative}")
    return records


def build_relative(role: str, name: str) -> str:
    return f"build/{role}/{name}"


def is_optional_opaque(relative: str) -> bool:
    for role, paths in BUILD_ARTIFACTS.items():
        for name in paths:
            if relative == build_relative(role, name):
                return Path(name).suffix in {".bin", ".elf", ".map"}
    return False


def write_manifest(destination: Path) -> tuple[int, str]:
    manifest = destination / "artifacts.sha256"
    files = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path != manifest)
    manifest.write_text("".join(
        f"{sha256_file(path)}  {path.relative_to(destination)}\n"
        for path in files), encoding="utf-8")
    return len(files) + 1, sha256_file(manifest)


def verify_retained_manifest(bundle: Path) -> dict[str, str]:
    records = manifest_records(bundle)
    absent: set[str] = set()
    for relative, expected in records.items():
        path = bundle / relative
        if not path.is_file() and is_optional_opaque(relative):
            absent.add(relative)
            continue
        require(path.is_file(), f"retained artifact missing: {relative}")
        require(sha256_file(path) == expected,
                f"retained artifact mismatch: {relative}")
    actual = {
        str(path.relative_to(bundle)) for path in bundle.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(set(records) == actual | absent,
            "retained manifest coverage mismatch")
    return records


def repository_evidence_path(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT)
    require(relative.parts[:3] == ("tests", "hil", "evidence"),
            "retained evidence must stay below tests/hil/evidence")
    return str(relative)


def summary_bundle_path(summary: dict[str, Any], *,
                        require_repository_bundle: bool) -> Path:
    recorded = summary.get("bundle")
    require(isinstance(recorded, str) and recorded,
            "retained bundle path missing")
    path = Path(recorded)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if require_repository_bundle:
        repository_evidence_path(path)
    return path


def copy_child(source: Path, destination: Path) -> None:
    verify_source_manifest(source)
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if (str(relative) in OMITTED_CHILD_FILES or
                path.suffix == ".rgb565"):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def retained_source_files(destination: Path, commit: str
                          ) -> dict[str, str]:
    records: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        payload = git_blob(commit, relative)
        target = destination / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records[relative] = sha256_bytes(payload)
    for scenario_id in MATRIX:
        relative = str(SCENARIOS[scenario_id].relative_to(ROOT))
        payload = git_blob(commit, relative)
        target = destination / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records[relative] = sha256_bytes(payload)
    return records


def copy_build_artifacts(destination: Path,
                         inventory: dict[str, Any]) -> None:
    for role, paths in BUILD_ARTIFACTS.items():
        records = inventory[role]
        for name, source in paths.items():
            record = records[name]
            require(source.is_file(),
                    f"{role} build artifact missing: {name}")
            require(source.stat().st_size == record["bytes"] and
                    sha256_file(source) == record["sha256"],
                    f"{role} build artifact drift: {name}")
            target = destination / build_relative(role, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def retain_matrix(source: Path, destination: Path, summary_path: Path, *,
                  evidence_ids: list[str] | None = None,
                  require_repository_paths: bool = True) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    summary_path = summary_path.resolve()
    require(source.is_dir(), "source S5 matrix is missing")
    require(not destination.exists(), "retained destination already exists")
    require(not summary_path.exists(), "retained summary already exists")
    if require_repository_paths:
        bundle_relative = repository_evidence_path(destination)
        repository_evidence_path(summary_path)
    else:
        bundle_relative = str(destination)

    matrix = verify_completed_matrix(source / "run.json")
    source_commit = matrix["source_commit"]
    require(HEX_40.fullmatch(source_commit) is not None,
            "source commit is invalid")
    inventory = matrix["build_artifacts"]
    for role in BUILD_ARTIFACTS:
        for name in BUILD_ARTIFACTS[role]:
            record = inventory[role][name]
            require(HEX_64.fullmatch(record["sha256"]) is not None,
                    f"invalid {role} build hash: {name}")

    child_manifests: dict[str, str] = {}
    fixture_profiles: set[str] = set()
    for scenario_id in MATRIX:
        child = source / scenario_id
        records = verify_source_manifest(child)
        child_manifests[scenario_id] = sha256_file(
            child / "artifacts.sha256")
        for name, expected in (
                ("firmware.bin", matrix["product_firmware_sha256"]),
                ("fixture.bin", matrix["fixture_firmware_sha256"]),
                ("fixture-profile.json", matrix["fixture_profile_sha256"])):
            require(records.get(name) == expected,
                    f"{scenario_id}: duplicate {name} identity mismatch")
        fixture_profiles.add(records["fixture-profile.json"])
    require(fixture_profiles == {matrix["fixture_profile_sha256"]},
            "fixture profile drift across matrix")

    staging = destination.with_name(destination.name + ".tmp-retain")
    require(not staging.exists(), "retained staging destination exists")
    try:
        staging.mkdir(parents=True)
        shutil.copy2(source / "run.json", staging / "run.json")
        for scenario_id in MATRIX:
            copy_child(source / scenario_id, staging / scenario_id)
        copy_build_artifacts(staging, inventory)
        shutil.copy2(
            source / MATRIX[0] / "fixture-profile.json",
            staging / "fixture-profile.json")
        source_files = retained_source_files(staging, source_commit)
        child_runs = {
            scenario_id: sha256_file(
                staging / scenario_id / "run.json")
            for scenario_id in MATRIX
        }
        provenance = {
            "schema": PROVENANCE_SCHEMA,
            "source_commit": source_commit,
            "matrix": list(MATRIX),
            "parent_run_sha256": sha256_file(staging / "run.json"),
            "child_runs": child_runs,
            "source_files": source_files,
            "source_child_manifests": child_manifests,
            "build_artifacts": inventory,
            "fixture_profile_sha256": sha256_file(
                staging / "fixture-profile.json"),
            "compaction": {
                "duplicate_child_firmware_removed": True,
                "duplicate_child_fixture_firmware_removed": True,
                "duplicate_child_fixture_profile_removed": True,
                "raw_rgb565_removed": True,
                "rendered_png_and_machine_records_retained": True,
            },
        }
        write(staging / "provenance.json", provenance)
        file_count, manifest_sha = write_manifest(staging)
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    acceptance = {
        "schema": SUMMARY_SCHEMA,
        "status": "pass",
        "bundle": bundle_relative,
        "evidence_ids": evidence_ids or [],
        "source_commit": source_commit,
        "matrix": list(MATRIX),
        "candidate": {
            "version": matrix["product_version"],
            "firmware_sha256": matrix["product_firmware_sha256"],
            "app_elf_sha256": matrix["product_app_elf_sha256"],
        },
        "fixture": {
            "version": matrix["fixture_version"],
            "firmware_sha256": matrix["fixture_firmware_sha256"],
            "app_elf_sha256": matrix["fixture_app_elf_sha256"],
            "fixture_id": matrix["fixture_id"],
            "profile_sha256": matrix["fixture_profile_sha256"],
        },
        "evidence": {
            "files": file_count,
            "artifact_index_sha256": manifest_sha,
            "provenance_sha256": sha256_file(
                destination / "provenance.json"),
            "parent_run_sha256": sha256_file(destination / "run.json"),
            "child_runs": child_runs,
        },
        "verified": {
            "expected_cid": matrix["expected_cid"],
            "candidate_port": matrix["candidate_port"],
            "fixture_port": matrix["fixture_port"],
            "four_positive_physical_scenarios": True,
            "later_scenarios_reused_exact_images": True,
            "all_terminal_home_zero_lease": True,
            "fixture_outputs_inactive": True,
        },
    }
    try:
        write(summary_path, acceptance)
        verify_retained_summary(
            summary_path,
            require_repository_bundle=require_repository_paths)
    except Exception:
        if summary_path.exists():
            summary_path.unlink()
        if destination.exists():
            shutil.rmtree(destination)
        raise
    return acceptance


def verify_retained_summary(summary_path: Path, *,
                            require_repository_bundle: bool = True
                            ) -> dict[str, Any]:
    summary = load(summary_path.resolve())
    require(summary.get("schema") == SUMMARY_SCHEMA,
            "retained summary schema mismatch")
    require(summary.get("status") == "pass",
            "retained summary is not passing")
    bundle = summary_bundle_path(
        summary, require_repository_bundle=require_repository_bundle)
    require(bundle.is_dir(), "retained bundle is missing")
    provenance = load(bundle / "provenance.json")
    require(provenance.get("schema") == PROVENANCE_SCHEMA,
            "retained provenance schema mismatch")
    records = verify_retained_manifest(bundle)
    evidence = summary.get("evidence", {})
    require(evidence.get("files") == len(records) + 1,
            "retained file count mismatch")
    require(evidence.get("artifact_index_sha256") ==
            sha256_file(bundle / "artifacts.sha256"),
            "retained manifest hash mismatch")
    require(evidence.get("provenance_sha256") ==
            sha256_file(bundle / "provenance.json"),
            "retained provenance hash mismatch")
    require(evidence.get("parent_run_sha256") ==
            provenance.get("parent_run_sha256") ==
            sha256_file(bundle / "run.json"),
            "retained parent run hash mismatch")

    matrix = verify_completed_matrix(
        bundle / "run.json", allow_relocated_children=True)
    require(summary.get("source_commit") ==
            provenance.get("source_commit") == matrix.get("source_commit"),
            "retained source commit mismatch")
    require(summary.get("matrix") == provenance.get("matrix") ==
            matrix.get("matrix") == list(MATRIX),
            "retained matrix identity mismatch")
    require(summary.get("candidate") == {
        "version": matrix["product_version"],
        "firmware_sha256": matrix["product_firmware_sha256"],
        "app_elf_sha256": matrix["product_app_elf_sha256"],
    }, "retained candidate identity mismatch")
    require(summary.get("fixture") == {
        "version": matrix["fixture_version"],
        "firmware_sha256": matrix["fixture_firmware_sha256"],
        "app_elf_sha256": matrix["fixture_app_elf_sha256"],
        "fixture_id": matrix["fixture_id"],
        "profile_sha256": matrix["fixture_profile_sha256"],
    }, "retained fixture identity mismatch")

    source_commit = matrix["source_commit"]
    expected_sources = set(SOURCE_PATHS) | {
        str(SCENARIOS[scenario_id].relative_to(ROOT))
        for scenario_id in MATRIX
    }
    source_files = provenance.get("source_files")
    require(isinstance(source_files, dict) and
            set(source_files) == expected_sources,
            "retained source file set mismatch")
    for relative, expected in source_files.items():
        blob = git_blob(source_commit, relative)
        retained = bundle / "source" / relative
        require(retained.is_file() and
                sha256_file(retained) == expected == sha256_bytes(blob),
                f"retained source identity mismatch: {relative}")

    inventory = provenance.get("build_artifacts")
    require(inventory == matrix.get("build_artifacts"),
            "retained build inventory mismatch")
    for role, paths in BUILD_ARTIFACTS.items():
        for name in paths:
            relative = build_relative(role, name)
            record = inventory[role][name]
            require(records.get(relative) == record["sha256"],
                    f"retained build manifest mismatch: {role}/{name}")
            path = bundle / relative
            if path.is_file():
                require(path.stat().st_size == record["bytes"] and
                        sha256_file(path) == record["sha256"],
                        f"retained build artifact mismatch: {role}/{name}")

    profile = load(bundle / "fixture-profile.json")
    require(sha256_file(bundle / "fixture-profile.json") ==
            matrix["fixture_profile_sha256"] ==
            provenance.get("fixture_profile_sha256"),
            "retained fixture profile hash mismatch")
    require(profile.get("schema") == "leshy.hil.board_profile.v1" and
            profile.get("accepted_for_fixture_flash") is True and
            profile.get("writes_performed") is False and
            profile.get("chip", {}).get("fixture_id") ==
            matrix["fixture_id"],
            "retained fixture profile admission mismatch")

    child_runs = provenance.get("child_runs")
    require(isinstance(child_runs, dict) and
            set(child_runs) == set(MATRIX) and
            evidence.get("child_runs") == child_runs,
            "retained child run set mismatch")
    for scenario_id in MATRIX:
        require(child_runs[scenario_id] == sha256_file(
            bundle / scenario_id / "run.json"),
            f"retained child run mismatch: {scenario_id}")
        child_files = {
            str(path.relative_to(bundle / scenario_id))
            for path in (bundle / scenario_id).rglob("*") if path.is_file()
        }
        require(not (child_files & OMITTED_CHILD_FILES) and
                not any(Path(relative).suffix == ".rgb565"
                        for relative in child_files),
                f"retained child was not compacted: {scenario_id}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    retain_parser = commands.add_parser("retain")
    retain_parser.add_argument("--source", required=True, type=Path)
    retain_parser.add_argument("--destination", required=True, type=Path)
    retain_parser.add_argument("--summary", required=True, type=Path)
    retain_parser.add_argument("--evidence-id", action="append", default=[])
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "retain":
            result = retain_matrix(
                args.source, args.destination, args.summary,
                evidence_ids=args.evidence_id)
            output = {
                "status": "retained", "summary": str(args.summary),
                "bundle": result["bundle"],
                "files": result["evidence"]["files"],
            }
        else:
            result = verify_retained_summary(args.summary)
            output = {
                "status": "pass", "summary": str(args.summary),
                "bundle": result["bundle"],
                "scenarios": result["matrix"],
            }
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
