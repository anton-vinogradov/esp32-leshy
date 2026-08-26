#!/usr/bin/env python3
"""Fail closed unless compact exact 0.160 Targets load evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-load-memory-0.160.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    try:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        bundle = ROOT / summary["bundle"]
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if digest(manifest_path) != summary["manifest_sha256"]:
            failures.append("manifest hash mismatch")
        expected = {"run.json", "provenance.json",
                    "frames/targets-list.json", "frames/targets-list.png",
                    "frames/targets-compare.json", "frames/targets-compare.png",
                    "frames/targets-detail.json", "frames/targets-detail.png"}
        if set(manifest) != expected:
            failures.append("unexpected retained artifact set")
        for relative, expected_hash in manifest.items():
            path = bundle / relative
            if not path.is_file() or digest(path) != expected_hash:
                failures.append(f"retained artifact mismatch: {relative}")
        candidate = summary["candidate"]
        if not (summary["schema"] ==
                "leshy.targets_load_memory_hil.summary.v1" and
                summary["status"] == "pass" and
                summary["evidence_ids"] == ["E-AUTO-115", "E-HIL-175"] and
                summary["source_commit"] ==
                "3846afbcae14dda8d2f5656da3a08c8a46c1c94d" and
                candidate["version"] == "0.160.0-targets-load-memory" and
                candidate["firmware_sha256"] ==
                "a54d1509c01b1e6d77afed25e5cac74eb8d290221942391b45f65b44a50633cd" and
                candidate["app_elf_sha256"] ==
                "af75ba520082f1491bee06dd741e77d2d17613e8edb1324d5ad58ff7c98d87d9"):
            failures.append("summary/candidate identity mismatch")
        targets = summary["targets"]
        if not (summary["exact_cid"] == "FE343253440000002000000055019CB7" and
                summary["session_generations"] == [160, 161] and
                summary["flash_count"] == 0 and
                summary["survey_cycles_executed"] == 0 and
                targets["visible"] == 7 and targets["catalog"] == 16 and
                targets["classification"] ==
                {"added": 2, "removed": 1, "changed": 0, "unchanged": 4} and
                targets["heap_free_before"] == 67436 and
                targets["heap_free_loaded"] >= 40000 and
                targets["heap_free_after_release"] >=
                targets["heap_free_before"] - 512 and
                targets["blocked_write_attempts"] == 0):
            failures.append("Targets load/release invariant mismatch")
        if summary["safe_outputs"] != {
                "buzzer_inactive": True, "nrf_ce_inactive": True,
                "software_quiesce_complete": True}:
            failures.append("safe outputs mismatch")
        if summary["input"] != {
                "status": "ready", "read_errors": 0, "queue_drops": 0,
                "ambiguous_presses": 0}:
            failures.append("input integrity mismatch")
        if summary["final"] != {
                "page": "home", "runtime_owner": "none", "lease_mask": 0,
                "library_generation": 161}:
            failures.append("terminal cleanup mismatch")
        if summary["radio_tx_commands"] != 0:
            failures.append("radio TX observed")
        for record in summary["screens"].values():
            path = bundle / record["png"]
            if not path.is_file() or digest(path) != record["png_sha256"]:
                failures.append(f"screenshot mismatch: {record['png']}")
        if digest(bundle / "run.json") != summary["raw_run_sha256"]:
            failures.append("raw run hash mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets load-memory HIL acceptance passed: generations 160/161, "
          "zero flash/scans/TX/drops/leases, full heap release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
