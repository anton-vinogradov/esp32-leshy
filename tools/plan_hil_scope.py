#!/usr/bin/env python3
"""Choose the smallest honest HIL scope for the current change.

The planner is deliberately read-only.  It prevents routine fixes from silently
turning into a full physical regression and makes every full-run trigger visible.
"""

from __future__ import annotations

import argparse
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
    return sorted(candidates)


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema") != "leshy.hil_cadence.v1":
        raise ValueError(f"unsupported policy schema in {path}")
    return policy


def plan(policy: dict, paths: list[str], *, stage_end: bool,
         release_candidate: bool) -> dict:
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

    reasons: list[str] = []
    if stage_end:
        reasons.append("stage_end")
    if release_candidate:
        reasons.append("release_candidate")
    if len(accepted) >= interval:
        reasons.append("accepted_delta_interval")
    if cross_cutting:
        reasons.append("cross_cutting_runtime_change")

    if reasons:
        scope = "full"
    elif firmware or hil:
        scope = "delta"
        reasons.append("affected_runtime_or_hil_surface")
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
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        policy = load_policy(args.policy)
        result = plan(
            policy, changed_paths(args.base), stage_end=args.stage_end,
            release_candidate=args.release_candidate,
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
