#!/usr/bin/env python3
"""Retain and verify source-bound HIL runs without feature-specific packers."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCHEMA = "leshy.hil.acceptance.v1"
PROVENANCE_SCHEMA = "leshy.hil.provenance.v1"
INDEX_SCHEMA = "leshy.hil.evidence_index.v1"
OPTIONAL_OPAQUE_BUILD_ARTIFACTS = {
    "firmware.bin", "firmware.factory.bin",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def relative_to_root(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def retain(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    destination = args.destination.resolve()
    summary_path = args.summary.resolve()
    runner = (ROOT / args.runner).resolve()
    scenario = (ROOT / args.scenario).resolve() if args.scenario else None
    factory = args.factory.resolve()
    map_file = args.map.resolve()
    required = (source / "run.json", source / "firmware.bin", runner,
                factory, map_file)
    require(source.is_dir(), "source run is missing")
    require(not destination.exists(), "destination already exists")
    require(not summary_path.exists(), "summary already exists")
    require(all(path.is_file() for path in required),
            "one or more required artifacts are missing")
    require(len(args.source_commit) == 40 and len(args.runner_commit) == 40,
            "source and runner commits must be full IDs")

    run = load(source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == args.run_schema, "run schema mismatch")
    require(run.get("passed") is True and run.get("failures") == [],
            "only a passing fail-closed run can be retained")
    require(run.get("checkpoint") == args.checkpoint, "checkpoint mismatch")
    require(run.get("expected_cid") == args.expected_cid, "CID mismatch")
    require(candidate.get("version") == args.version, "version mismatch")
    require(candidate.get("source_commit") == args.source_commit,
            "source commit mismatch")
    require(candidate.get("firmware_sha256") == digest(source / "firmware.bin"),
            "firmware hash mismatch")
    require(candidate.get("app_elf_sha256") ==
            app_elf_sha256(source / "firmware.bin"),
            "app identity mismatch")
    require(run.get("runner_source_sha256") == digest(runner),
            "executed runner hash mismatch")
    runner_relative = relative_to_root(runner)
    require(hashlib.sha256(git_blob(
        args.runner_commit, runner_relative)).hexdigest() == digest(runner),
        "runner commit does not bind the executed runner")
    scenario_relative: str | None = None
    if scenario is not None:
        require(scenario.is_file(), "scenario source is missing")
        scenario_relative = relative_to_root(scenario)
        run_scenario = run.get("scenario", {})
        require(run_scenario.get("sha256") == digest(scenario) and
                run_scenario.get("id") == args.scenario_id,
                "executed scenario identity mismatch")
        require(hashlib.sha256(git_blob(
            args.runner_commit, scenario_relative)).hexdigest() ==
            digest(scenario),
            "runner commit does not bind the executed scenario")

    final = run.get("reports", {}).get("final", {})
    cleanup = run.get("cleanup", {})
    require(final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0, "final lease is not zero")
    require(cleanup.get("complete") is True, "cleanup is incomplete")

    shutil.copytree(source, destination)
    copied_manifest = destination / "artifacts.sha256"
    if copied_manifest.exists():
        copied_manifest.unlink()
    shutil.copy2(runner, destination / "runner.py")
    if scenario is not None:
        shutil.copy2(scenario, destination / "scenario.json")
    shutil.copy2(factory, destination / "firmware.factory.bin")

    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "scenario_id": args.scenario_id,
        "run_schema": args.run_schema,
        "checkpoint": args.checkpoint,
        "version": args.version,
        "source_commit": args.source_commit,
        "runner_commit": args.runner_commit,
        "runner_path": runner_relative,
        "scenario_path": scenario_relative,
        "scenario_sha256": digest(destination / "scenario.json")
            if scenario is not None else None,
        "firmware_sha256": digest(destination / "firmware.bin"),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        # Linker maps are large opaque build products. Bind their digest and
        # resource facts without bloating every retained HIL bundle.
        "map_sha256": digest(map_file),
        "app_elf_sha256": app_elf_sha256(destination / "firmware.bin"),
        "runner_sha256": digest(destination / "runner.py"),
        "run_sha256": digest(destination / "run.json"),
        "firmware_bytes": (destination / "firmware.bin").stat().st_size,
        "factory_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    copied_manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    recovery = run.get("recovery_before", {})
    terminal_states = {
        key: value.get("state") for key, value in run.get("reports", {}).items()
        if isinstance(value, dict) and isinstance(value.get("state"), str)
    }
    summary = {
        "schema": SUMMARY_SCHEMA,
        "status": args.status,
        "scenario_id": args.scenario_id,
        "board": args.board,
        "bundle": relative_to_root(destination),
        "evidence_ids": args.evidence_id,
        "candidate": provenance,
        "evidence": {
            "files": len(indexed) + 1,
            "tft_states": len(run.get("captures", {})),
            "artifact_index_sha256": digest(copied_manifest),
            "provenance_sha256": digest(destination / "provenance.json"),
            "run_sha256": digest(destination / "run.json"),
        },
        "verified": {
            "expected_cid": args.expected_cid,
            "storage_generation": recovery.get("generation"),
            "storage_observations": recovery.get("observations"),
            "storage_physical_write_calls": recovery.get(
                "physical_write_calls"),
            "heap": [run.get("boot", {}).get("heap_total"),
                     run.get("boot", {}).get("heap_free"),
                     run.get("boot", {}).get("heap_min_free")],
            "input_read_errors": run.get("input", {}).get("read_errors"),
            "input_queue_drops": run.get("input", {}).get("queue_drops"),
            "buzzer_inactive": run.get("safe_outputs", {}).get(
                "buzzer_inactive"),
            "nrf_ce_inactive": run.get("safe_outputs", {}).get(
                "nrf_ce_inactive"),
            "terminal_states": terminal_states,
            "automatic_screenshots": True,
            "manual_button_presses": 0,
            "final_owner": final.get("runtime_owner"),
            "final_lease_mask": final.get("lease_mask"),
        },
        "limits": run.get("limits", {}),
    }
    write(summary_path, summary)
    print(json.dumps({
        "status": "retained", "summary": relative_to_root(summary_path),
        "destination": relative_to_root(destination),
        **summary["evidence"],
    }, sort_keys=True))
    return 0


def verify_manifest(bundle: Path) -> set[str]:
    manifest = bundle / "artifacts.sha256"
    require(manifest.is_file(), "artifact index missing")
    indexed: set[str] = set()
    absent_opaque: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        require(len(parts) == 2, "malformed artifact index")
        expected, relative = parts
        indexed.add(relative)
        path = bundle / relative
        if not path.is_file() and relative in OPTIONAL_OPAQUE_BUILD_ARTIFACTS:
            absent_opaque.add(relative)
            continue
        require(path.is_file(), f"retained artifact missing: {relative}")
        require(digest(path) == expected,
                f"retained artifact mismatch: {relative}")
    actual = {
        str(path.relative_to(bundle)) for path in bundle.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed == actual | absent_opaque,
            "artifact index coverage mismatch")
    return indexed


def verify_optional_build_artifact(path: Path, expected_hash: object,
                                   expected_bytes: object,
                                   label: str) -> None:
    require(isinstance(expected_hash, str) and len(expected_hash) == 64,
            f"{label} hash is invalid")
    require(isinstance(expected_bytes, int) and expected_bytes > 0,
            f"{label} byte count is invalid")
    if path.is_file():
        require(path.stat().st_size == expected_bytes,
                f"{label} byte count mismatch")
        require(digest(path) == expected_hash, f"{label} hash mismatch")


def verify_summary(summary_path: Path) -> dict[str, Any]:
    summary = load(summary_path)
    require(summary.get("schema") == SUMMARY_SCHEMA, "summary schema mismatch")
    require(str(summary.get("status", "")).startswith("pass"),
            "summary is not passing")
    bundle = (ROOT / str(summary.get("bundle", ""))).resolve()
    require(bundle.is_dir() and bundle.is_relative_to(ROOT),
            "retained bundle path is invalid")
    provenance = load(bundle / "provenance.json")
    run = load(bundle / "run.json")
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(provenance == candidate, "summary/provenance mismatch")
    require(provenance.get("schema") == PROVENANCE_SCHEMA,
            "provenance schema mismatch")
    indexed = verify_manifest(bundle)
    require(evidence.get("files") == len(indexed) + 1,
            "retained file count mismatch")
    require(evidence.get("artifact_index_sha256") ==
            digest(bundle / "artifacts.sha256"), "manifest hash mismatch")
    require(evidence.get("provenance_sha256") ==
            digest(bundle / "provenance.json"), "provenance hash mismatch")
    require(evidence.get("run_sha256") == digest(bundle / "run.json") ==
            provenance.get("run_sha256"), "run hash mismatch")
    firmware = bundle / "firmware.bin"
    factory = bundle / "firmware.factory.bin"
    verify_optional_build_artifact(
        firmware, provenance.get("firmware_sha256"),
        provenance.get("firmware_bytes"), "firmware")
    verify_optional_build_artifact(
        factory, provenance.get("factory_sha256"),
        provenance.get("factory_bytes"), "factory")
    require(isinstance(provenance.get("app_elf_sha256"), str) and
            len(provenance["app_elf_sha256"]) == 64,
            "app identity is invalid")
    if firmware.is_file():
        require(app_elf_sha256(firmware) == provenance.get("app_elf_sha256"),
                "app identity mismatch")
    require(isinstance(provenance.get("map_sha256"), str) and
            len(provenance["map_sha256"]) == 64, "map hash is invalid")
    if (bundle / "firmware.map").is_file():
        require(digest(bundle / "firmware.map") ==
                provenance.get("map_sha256"), "map hash mismatch")
    require(digest(bundle / "runner.py") == provenance.get("runner_sha256"),
            "runner hash mismatch")
    runner_blob = git_blob(provenance["runner_commit"],
                           provenance["runner_path"])
    require(hashlib.sha256(runner_blob).hexdigest() ==
            provenance.get("runner_sha256"), "runner commit mismatch")
    if provenance.get("scenario_path") is not None:
        require(digest(bundle / "scenario.json") ==
                provenance.get("scenario_sha256"), "scenario hash mismatch")
        scenario_blob = git_blob(provenance["runner_commit"],
                                 provenance["scenario_path"])
        require(hashlib.sha256(scenario_blob).hexdigest() ==
                provenance.get("scenario_sha256"),
                "scenario commit mismatch")
        require(run.get("scenario", {}).get("sha256") ==
                provenance.get("scenario_sha256"), "run/scenario mismatch")
    run_candidate = run.get("candidate", {})
    require(run.get("schema") == provenance.get("run_schema") and
            run.get("checkpoint") == provenance.get("checkpoint") and
            run.get("passed") is True and run.get("failures") == [],
            "run identity/result mismatch")
    require(run.get("runner_source_sha256") ==
            provenance.get("runner_sha256"), "run/runner mismatch")
    require(run_candidate.get("version") == provenance.get("version") and
            run_candidate.get("source_commit") ==
            provenance.get("source_commit") and
            run_candidate.get("firmware_sha256") ==
            provenance.get("firmware_sha256") and
            run_candidate.get("app_elf_sha256") ==
            provenance.get("app_elf_sha256"), "candidate mismatch")
    require(run.get("expected_cid") == verified.get("expected_cid"),
            "expected CID mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(before.get("generation") == after.get("generation") ==
            verified.get("storage_generation") and
            before.get("observations") == after.get("observations") ==
            verified.get("storage_observations") and
            before.get("physical_write_calls") ==
            after.get("physical_write_calls") ==
            verified.get("storage_physical_write_calls"),
            "storage continuity mismatch")
    final = run.get("reports", {}).get("final", {})
    require(final.get("runtime_owner") == verified.get("final_owner") ==
            "none" and final.get("lease_mask") ==
            verified.get("final_lease_mask") == 0 and
            run.get("cleanup", {}).get("complete") is True,
            "final cleanup/lease mismatch")
    require(run.get("boot", {}).get("heap_free") ==
            run.get("metrics_after", {}).get("heap_free") and
            verified.get("input_read_errors") == 0 and
            verified.get("input_queue_drops") == 0 and
            verified.get("buzzer_inactive") is True and
            verified.get("nrf_ce_inactive") is True,
            "heap/input/safe-output invariant mismatch")
    require(summary.get("limits") == run.get("limits"),
            "limitation disclosure mismatch")
    return summary


def verify(args: argparse.Namespace) -> int:
    index = load(args.index.resolve())
    require(index.get("schema") == INDEX_SCHEMA, "evidence index schema mismatch")
    entries = index.get("summaries")
    require(isinstance(entries, list) and entries,
            "evidence index must contain summaries")
    checked = []
    for relative in entries:
        require(isinstance(relative, str), "summary path must be a string")
        path = (ROOT / relative).resolve()
        require(path.is_file() and path.is_relative_to(ROOT),
                f"summary path is invalid: {relative}")
        checked.append(verify_summary(path))
    print(json.dumps({
        "status": "pass", "summaries": len(checked),
        "scenarios": [value["scenario_id"] for value in checked],
    }, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("retain")
    pack.add_argument("--source", required=True, type=Path)
    pack.add_argument("--destination", required=True, type=Path)
    pack.add_argument("--summary", required=True, type=Path)
    pack.add_argument("--runner", required=True)
    pack.add_argument("--scenario")
    pack.add_argument("--source-commit", required=True)
    pack.add_argument("--runner-commit", required=True)
    pack.add_argument("--factory", required=True, type=Path)
    pack.add_argument("--map", required=True, type=Path)
    pack.add_argument("--static-ram-bytes", required=True, type=int)
    pack.add_argument("--linked-flash-bytes", required=True, type=int)
    pack.add_argument("--scenario-id", required=True)
    pack.add_argument("--run-schema", required=True)
    pack.add_argument("--checkpoint", required=True)
    pack.add_argument("--version", required=True)
    pack.add_argument("--expected-cid", required=True)
    pack.add_argument("--status", required=True)
    pack.add_argument("--board", default="board-01")
    pack.add_argument("--evidence-id", action="append", default=[])
    pack.set_defaults(function=retain)
    check = commands.add_parser("verify")
    check.add_argument("--index", required=True, type=Path)
    check.set_defaults(function=verify)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.function(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
