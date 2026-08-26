#!/usr/bin/env python3
"""Choose the smallest honest HIL scope for the current change.

The planner is deliberately read-only.  It prevents routine fixes from silently
turning into a full physical regression and makes every full-run trigger visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tests/hil/hil-cadence.v1.json"


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return completed.stdout


def changed_paths(base: str) -> list[str]:
    tracked = git("diff", "--name-only", base, "--").splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({path for path in [*tracked, *untracked] if path})


def begins_with_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def anchor_commit(anchor_evidence: str) -> str | None:
    commits = git(
        "log", "--diff-filter=A", "--format=%H", "--", anchor_evidence,
    ).splitlines()
    return commits[-1] if commits else None


def is_accepted_evidence(path: Path) -> bool:
    """Count only explicit passing summaries, never fail-closed precursors."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    status = value.get("status") if isinstance(value, dict) else None
    return isinstance(status, str) and (
        status == "pass" or status.startswith("pass_")
    )


def accepted_evidence_since(anchor_evidence: str) -> list[str]:
    anchor = anchor_commit(anchor_evidence)
    if anchor is None:
        return []
    names = git(
        "log", f"{anchor}..HEAD", "--diff-filter=A", "--name-only",
        "--format=", "--", ":(glob)tests/hil/evidence/*.json",
    ).splitlines()
    candidates = {
        name for name in names
        if name.startswith("tests/hil/evidence/")
        and name.count("/") == 3
        and name.endswith(".json")
        and name != anchor_evidence
    }
    return sorted(
        name for name in candidates if is_accepted_evidence(ROOT / name)
    )


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema") != "leshy.hil_cadence.v1":
        raise ValueError(f"unsupported policy schema in {path}")
    return policy


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / path).open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_delta_review(path: Path) -> dict:
    review = json.loads(path.read_text(encoding="utf-8"))
    if review.get("schema") != "leshy.hil_delta_review.v1":
        raise ValueError(f"unsupported delta review schema in {path}")
    required = (
        "id", "rationale", "reviewed_cross_cutting_sha256",
        "required_host_checks", "required_hil_scenarios",
    )
    for field in required:
        if not review.get(field):
            raise ValueError(f"delta review {path} has empty {field}")
    hashes = review["reviewed_cross_cutting_sha256"]
    if not isinstance(hashes, dict):
        raise ValueError(f"delta review {path} hashes must be an object")
    for reviewed_path, expected_hash in hashes.items():
        actual_hash = file_sha256(reviewed_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"delta review {path} is stale for {reviewed_path}: "
                f"{actual_hash} != {expected_hash}"
            )
    return review


def plan(policy: dict, paths: list[str], *, stage_end: bool,
         release_candidate: bool, delta_review: dict | None = None) -> dict:
    accepted = accepted_evidence_since(policy["anchor_evidence"])
    interval = int(policy["full_after_accepted_deltas"])
    host_only = [
        path for path in paths
        if begins_with_any(path, policy["host_only_prefixes"])
    ]
    runtime_paths = [path for path in paths if path not in host_only]
    firmware = [
        path for path in runtime_paths
        if begins_with_any(path, policy["firmware_prefixes"])
    ]
    hil = [
        path for path in runtime_paths
        if begins_with_any(path, policy["hil_prefixes"])
    ]
    cross_cutting = [
        path for path in runtime_paths
        if begins_with_any(path, policy["cross_cutting_prefixes"])
    ]
    reviewed_cross_cutting = sorted(
        (delta_review or {}).get("reviewed_cross_cutting_sha256", {}).keys()
    )
    review_matches = bool(delta_review) and reviewed_cross_cutting == cross_cutting

    reasons: list[str] = []
    if stage_end:
        reasons.append("stage_end")
    if release_candidate:
        reasons.append("release_candidate")
    if len(accepted) >= interval:
        reasons.append("accepted_delta_interval")
    if cross_cutting and not review_matches:
        reasons.append("cross_cutting_runtime_change")

    if reasons:
        scope = "full"
    elif firmware or hil:
        scope = "delta"
        reasons.append(
            "reviewed_additive_cross_cutting_delta"
            if review_matches else "affected_runtime_or_hil_surface"
        )
    else:
        scope = "none"
        reasons.append("host_only_change")

    return {
        "schema": "leshy.hil_scope_plan.v1",
        "scope": scope,
        "reasons": reasons,
        "changed_paths": paths,
        "host_only_paths": host_only,
        "firmware_paths": firmware,
        "hil_paths": hil,
        "cross_cutting_paths": cross_cutting,
        "delta_review": None if delta_review is None else {
            "id": delta_review["id"],
            "rationale": delta_review["rationale"],
            "reviewed_cross_cutting_paths": reviewed_cross_cutting,
            "required_host_checks": delta_review["required_host_checks"],
            "required_hil_scenarios": delta_review["required_hil_scenarios"],
        },
        "accepted_deltas_since_anchor": len(accepted),
        "accepted_delta_evidence": accepted,
        "full_after_accepted_deltas": interval,
        "anchor_evidence": policy["anchor_evidence"],
        "flash_policy": (
            "one_exact_candidate_flash_for_entire_matrix"
            if scope == "full"
            else "flash_once_only_if_candidate_image_changed"
            if scope == "delta"
            else "no_flash"
        ),
        "execution_rule": policy["execution_rules"][scope],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--stage-end", action="store_true")
    parser.add_argument("--release-candidate", action="store_true")
    parser.add_argument("--delta-review", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        policy = load_policy(args.policy)
        result = plan(
            policy, changed_paths(args.base), stage_end=args.stage_end,
            release_candidate=args.release_candidate,
            delta_review=(
                load_delta_review(args.delta_review)
                if args.delta_review is not None else None
            ),
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"HIL scope planning failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(
        result, ensure_ascii=False, sort_keys=True,
        separators=(",", ":") if args.compact else None,
        indent=None if args.compact else 2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
