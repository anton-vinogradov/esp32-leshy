#!/usr/bin/env python3
"""Retain a compact, source-bound HIL delta without duplicating build binaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)
    require(completed.returncode == 0,
            completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout


def verify_source_manifest(source: Path) -> tuple[int, int]:
    manifest = source / "artifacts.sha256"
    require(manifest.is_file(), "source artifact manifest missing")
    indexed: set[str] = set()
    total_bytes = manifest.stat().st_size
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None,
                f"malformed source artifact manifest line {number}")
        expected, relative = match.groups()
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts and
                relative not in indexed,
                f"unsafe or duplicate source artifact: {relative}")
        artifact = source / path
        require(artifact.is_file() and digest(artifact) == expected,
                f"source artifact mismatch: {relative}")
        indexed.add(relative)
        total_bytes += artifact.stat().st_size
    actual = {
        str(path.relative_to(source)) for path in source.rglob("*")
        if path.is_file() and path != manifest
    }
    require(indexed == actual,
            "source artifact manifest does not exactly cover bundle")
    return len(indexed) + 1, total_bytes


def source_hashes(base: str, commit: str) -> dict[str, str]:
    changed = git("diff", "--name-only", base, commit, "--").decode(
        "utf-8").splitlines()
    require(bool(changed), "candidate has no changed source paths")
    hashes: dict[str, str] = {}
    for relative in changed:
        blob = git("show", f"{commit}:{relative}")
        hashes[relative] = hashlib.sha256(blob).hexdigest()
    return hashes


def write_retained_manifest(destination: Path) -> tuple[int, str]:
    manifest = destination / "artifacts.sha256"
    files = sorted(
        path for path in destination.rglob("*")
        if path.is_file() and path != manifest
    )
    lines = [
        f"{digest(path)}  {path.relative_to(destination)}"
        for path in files
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(files) + 1, digest(manifest)


def capture_png(source: Path, name: str) -> Path:
    candidates = dict.fromkeys([
        source / "frames" / f"{name}.png",
        source / "frames" / f"{name.replace('_', '-')}.png",
    ])
    matches = [path for path in candidates if path.is_file()]
    require(len(matches) == 1,
            f"capture PNG path is missing or ambiguous: {name}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    parser.add_argument("--factory-sha256", required=True)
    parser.add_argument("--map-sha256", required=True)
    parser.add_argument(
        "--runner", type=Path,
        help="executed runner path in the candidate commit when the raw bundle "
             "does not carry its own copy",
    )
    parser.add_argument("--expected-run-schema")
    parser.add_argument("--delta-review", type=Path)
    parser.add_argument("--accepted-delta-ordinal", type=int)
    parser.add_argument("--cadence-anchor")
    parser.add_argument("--full-after-accepted-deltas", type=int, default=15)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    require(source.is_dir(), "source HIL bundle missing")
    require(not destination.exists(), "destination already exists")

    run_path = source / "run.json"
    require(run_path.is_file(), "run.json missing")
    run = load(run_path)
    candidate = run.get("candidate", {})
    if args.expected_run_schema is not None:
        require(run.get("schema") == args.expected_run_schema,
                "source run schema mismatch")
    annotated_scope = run.get("scope")
    annotated_full_matrix = run.get("full_matrix_run")
    require(run.get("passed") is True and run.get("failures") == [] and
            annotated_scope in {None, "delta"} and
            annotated_full_matrix in {None, False} and
            run.get("gate_eligible") is True,
            "source is not an accepted delta HIL run")
    commit = str(candidate.get("source_commit", ""))
    require(bool(commit), "candidate source commit missing")
    git("cat-file", "-e", f"{commit}^{{commit}}")
    git("cat-file", "-e", f"{args.base_commit}^{{commit}}")
    original_files, original_bytes = verify_source_manifest(source)

    runner_bytes: bytes
    runner_relative: str
    if args.runner is not None:
        runner = args.runner
        if not runner.is_absolute():
            runner = ROOT / runner
        runner = runner.resolve()
        try:
            runner_relative = str(runner.relative_to(ROOT))
        except ValueError as error:
            raise ValueError("runner must stay below repository root") from error
        runner_bytes = git("show", f"{commit}:{runner_relative}")
        recorded_runner_sha = run.get("runner_source_sha256")
        require(
            isinstance(recorded_runner_sha, str) and
            hashlib.sha256(runner_bytes).hexdigest() == recorded_runner_sha,
            "candidate runner does not match the executed runner identity",
        )
    else:
        runners = sorted(source.glob("run_1x_*.py"))
        require(len(runners) == 1,
                "source must contain exactly one executed runner")
        runner_bytes = runners[0].read_bytes()
        runner_relative = runners[0].name

    delta_review: dict[str, Any] | None = None
    delta_review_relative: str | None = None
    if args.delta_review is not None:
        review = args.delta_review
        if not review.is_absolute():
            review = ROOT / review
        review = review.resolve()
        try:
            delta_review_relative = str(review.relative_to(ROOT))
        except ValueError as error:
            raise ValueError(
                "delta review must stay below repository root") from error
        delta_review = load(review)
        require(delta_review.get("schema") == "leshy.hil_delta_review.v1",
                "delta review schema mismatch")
        require(git("show", f"{commit}:{delta_review_relative}") ==
                review.read_bytes(),
                "delta review is not bound to the candidate commit")
    if annotated_scope is None or annotated_full_matrix is None:
        require(delta_review is not None,
                "unannotated run requires a source-bound delta review")
    require(args.accepted_delta_ordinal is None or
            args.accepted_delta_ordinal > 0,
            "accepted delta ordinal must be positive")
    require(args.full_after_accepted_deltas > 0,
            "full-HIL cadence must be positive")
    captures = run.get("captures", {})
    require(isinstance(captures, dict) and captures,
            "run has no automatic TFT captures")

    destination.mkdir(parents=True)
    shutil.copy2(run_path, destination / "run.json")
    (destination / "runner.py").write_bytes(runner_bytes)
    frames = destination / "frames"
    frames.mkdir()
    for name, capture in sorted(captures.items()):
        png = capture_png(source, name)
        require(png.is_file() and digest(png) == capture.get("png_sha256"),
                f"PNG identity mismatch: {name}")
        shutil.copy2(png, frames / f"{name}.png")

    provenance = {
        "schema": "leshy.compact_delta_hil.provenance.v1",
        "base_commit": args.base_commit,
        "candidate": candidate,
        "source_sha256": source_hashes(args.base_commit, commit),
        "run_sha256": digest(destination / "run.json"),
        "runner_sha256": digest(destination / "runner.py"),
        "runner_source": runner_relative,
        "delta_review": ({
            "path": delta_review_relative,
            "sha256": digest(ROOT / delta_review_relative),
            "id": delta_review.get("id"),
        } if delta_review is not None and delta_review_relative is not None
         else None),
        "cadence": {
            "scope": "delta",
            "full_matrix_run": False,
            "accepted_delta_ordinal": args.accepted_delta_ordinal,
            "anchor_evidence": args.cadence_anchor,
            "full_after_accepted_deltas": args.full_after_accepted_deltas,
        },
        "build": {
            "static_ram_bytes": args.static_ram_bytes,
            "linked_flash_bytes": args.linked_flash_bytes,
            "factory_sha256": args.factory_sha256,
            "map_sha256": args.map_sha256,
        },
        "original_bundle": {
            "artifact_manifest_sha256": digest(source / "artifacts.sha256"),
            "files": original_files,
            "bytes": original_bytes,
        },
        "retention": {
            "policy": "compact_delta_no_duplicate_build_binaries",
            "png_frames": len(captures),
            "omitted": ["firmware.bin", "firmware.elf", "firmware.map",
                        "rgb565", "per-frame JSON"],
        },
    }
    write(destination / "provenance.json", provenance)
    retained_files, retained_manifest_sha = write_retained_manifest(destination)
    print(json.dumps({
        "destination": str(destination),
        "original_bytes": original_bytes,
        "original_files": original_files,
        "retained_files": retained_files,
        "retained_manifest_sha256": retained_manifest_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
