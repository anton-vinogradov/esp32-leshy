#!/usr/bin/env python3
"""Verify the Git-carried portion of one retained HIL bundle.

Large historical firmware/map/ELF files are intentionally ignored by repository
policy.  The connected-board gate verifies those bytes before retention and records
their hashes in each artifact index.  CI must neither pretend those opaque files are
present nor discard verification of the tracked run, provenance, frame and source
artifacts around them.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-product-home-0.93"
HASH_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
OPAQUE_SUFFIXES = (".bin", ".elf", ".map")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE,
    )
    return {
        item.decode("utf-8")
        for item in result.stdout.split(b"\0") if item
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle", type=Path, default=DEFAULT_BUNDLE,
        help="retained bundle containing artifacts.sha256",
    )
    args = parser.parse_args()
    requested_bundle = args.bundle
    if not requested_bundle.is_absolute():
        requested_bundle = ROOT / requested_bundle
    requested_bundle = requested_bundle.resolve()
    try:
        requested_bundle.relative_to((ROOT / "tests/hil/evidence").resolve())
    except ValueError:
        print("FAIL: bundle must stay below tests/hil/evidence")
        return 1

    tracked = git_paths()
    failures: list[str] = []
    indexes = 0
    indexed_tracked = 0
    declared_opaque = 0
    locally_rehashed_opaque = 0

    for index in [requested_bundle / "artifacts.sha256"]:
        index_rel = str(index.relative_to(ROOT))
        if index_rel not in tracked:
            continue
        indexes += 1
        bundle = index.parent.resolve()
        indexed_here: set[str] = set()
        for line_number, line in enumerate(
                index.read_text(encoding="utf-8").splitlines(), start=1):
            match = HASH_LINE.fullmatch(line)
            if match is None:
                failures.append(f"{index_rel}:{line_number}: malformed hash line")
                continue
            expected, relative = match.groups()
            target = (bundle / relative).resolve()
            try:
                target.relative_to(bundle)
            except ValueError:
                failures.append(f"{index_rel}: artifact escapes bundle: {relative}")
                continue
            root_relative = str(target.relative_to(ROOT))
            indexed_here.add(root_relative)
            if root_relative in tracked:
                indexed_tracked += 1
                if not target.is_file():
                    failures.append(f"{index_rel}: tracked artifact missing: {relative}")
                elif digest(target) != expected:
                    failures.append(f"{index_rel}: tracked hash mismatch: {relative}")
                continue

            if not relative.endswith(OPAQUE_SUFFIXES):
                failures.append(
                    f"{index_rel}: non-opaque indexed artifact is not tracked: {relative}"
                )
                continue
            declared_opaque += 1
            if target.is_file():
                locally_rehashed_opaque += 1
                if digest(target) != expected:
                    failures.append(f"{index_rel}: local opaque hash mismatch: {relative}")

        tracked_below = {
            path for path in tracked
            if path.startswith(str(index.parent.relative_to(ROOT)) + "/")
            and path != index_rel
        }
        # Independently indexed child bundles own their own artifacts.
        nested_roots = {
            str(other.parent.relative_to(ROOT)) + "/"
            for other in index.parent.rglob("artifacts.sha256")
            if other != index and str(other.relative_to(ROOT)) in tracked
        }
        owned_tracked = {
            path for path in tracked_below
            if not any(path.startswith(prefix) for prefix in nested_roots)
        }
        missing_from_index = sorted(owned_tracked - indexed_here)
        for path in missing_from_index:
            failures.append(f"{index_rel}: tracked artifact absent from index: {path}")

    if indexes == 0:
        failures.append("no tracked retained artifact indexes found")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(
        "tracked HIL evidence passed: "
        f"{indexes} index, {indexed_tracked} tracked artifacts rehashed, "
        f"{declared_opaque} opaque build artifacts declared, "
        f"{locally_rehashed_opaque} locally present opaque artifacts rehashed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
