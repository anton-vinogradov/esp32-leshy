#!/usr/bin/env python3
"""Fail closed unless retained physical Automation trust UI evidence is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT / "tests/hil/evidence/board-01-automation-trust-ui-1.0.0-dev.306.json")
SOURCE = "41bf103008202e742598dfd3e092b28aeda45d95"
RUNNER_COMMIT = "959ff6a281e930107481f0d247c12f38a2b4ea94"
RUNNER_SHA = "6c37de1c6cc4ddabd2c03d5220b07f65453f1f6b9f679b44e7fabcaa3b829b27"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    bundle = ROOT / summary.get("bundle", "missing")
    manifest_path = bundle / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {})
    require(failures, manifest_path.is_file() and
            digest(manifest_path) == summary.get("manifest_sha256"),
            "manifest missing or hash mismatch")
    expected = {"provenance.json", "run.json"}
    for stem in ("trust-list-en", "trust-list-ru", "trust-import-ru"):
        expected.update({f"frames/{stem}-a.png", f"frames/{stem}-b.png"})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") == "leshy.automation_trust_ui_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
            ["E-BUILD-208", "E-AUTO-183", "E-HIL-216", "E-UX-069", "RB-M219"],
            "summary identity mismatch")
    require(failures, summary.get("firmware_source_commit") == SOURCE and
            summary.get("runner_commit") == RUNNER_COMMIT,
            "source/runner commit mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate == {
                "app_elf_sha256":
                    "d8155e1dd75b6c4b82e5ce08d41fec406eeee63475f1e2653b1f043d6aa892de",
                "elf_sha256":
                    "d8155e1dd75b6c4b82e5ce08d41fec406eeee63475f1e2653b1f043d6aa892de",
                "firmware_bytes": 3552992,
                "firmware_sha256":
                    "fff7ac4b2b6c9ab66370a6b3bd0cd5c2b205d55ad55028debefebde94a969615",
                "map_sha256":
                    "0f1161041f1812c44fdf42c9dfdbd2c579a02a5f107ccca8a9e56251c8c59150",
                "version": "1.0.0-dev.306",
            } and summary.get("factory_sha256") ==
            "069648d2fde7cc6e4f2c4ec44ef23e1a0f1c6a0b88a6127d3ecdf5bc9c185786",
            "candidate identity mismatch")
    require(failures, summary.get("lineage") == {
        "candidate_flashes": 1,
        "accepted_run_flashes": 1,
        "accepted_run_reused_installed_candidate": False,
    }, "single-flash lineage mismatch")
    trust = summary.get("trust", {})
    require(failures,
            trust.get("capacity") == 4 and
            trust.get("count_before") == trust.get("count_after") and
            trust.get("generation_before") == trust.get("generation_after") and
            trust.get("public_keys_only") is True and
            trust.get("all_keys_p256_and_id_bound") is True and
            trust.get("private_key_stored") is False and
            trust.get("execution_connected") is False,
            "trust boundary mismatch")
    imported = summary.get("import", {})
    require(failures, imported == {
        "root": "/leshy/automation/v1",
        "name": "automation-owner.lhak",
        "read_status": "open_failed",
        "result": "bundle_read_failed",
        "button_path_checked": True,
        "touch_path_checked": True,
        "mutation_confirmed": False,
        "sd_mount": "read_only",
        "sd_files_written": 0,
    }, "read-only import path mismatch")
    for name, screen in summary.get("stable_screens", {}).items():
        pair = screen.get("pair", [])
        require(failures, len(pair) == 2 and
                all((bundle / path).is_file() for path in pair) and
                digest(bundle / pair[0]) == digest(bundle / pair[1]) ==
                screen.get("png_sha256"), f"unstable screen pair: {name}")
    require(failures, set(summary.get("stable_screens", {})) ==
            {"list_en", "list_ru", "first_import_ru"},
            "incomplete stable screen set")
    require(failures, summary.get("visual_review") == {
        "en_list_legible": True,
        "ru_list_legible": True,
        "ru_no_execution_status_single_line": True,
        "static_frames_stable": True,
    }, "visual review mismatch")
    require(failures, summary.get("safe") == {
        "action_invocations": 0,
        "hid_reports": 0,
        "rf_transmit_attempts": 0,
        "trust_namespace_written": False,
        "private_key_used_or_stored": False,
        "wifi_host_touched": False,
        "forbidden_ports_touched": [],
    }, "safe-output contract mismatch")
    require(failures, summary.get("cleanup") == {
        "device_lock_product_restored": True,
        "language_restored": True,
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "hil_active": False,
    }, "terminal cleanup mismatch")
    run_path = bundle / "run.json"
    require(failures, run_path.is_file() and
            digest(run_path) == summary.get("raw_run_sha256"),
            "raw accepted run mismatch")
    provenance_path = bundle / "provenance.json"
    provenance = (json.loads(provenance_path.read_text(encoding="utf-8"))
                  if provenance_path.is_file() else {})
    require(failures, provenance.get("firmware_source_commit") == SOURCE and
            provenance.get("runner_commit") == RUNNER_COMMIT and
            provenance.get("runner_sha256") == RUNNER_SHA,
            "provenance identity mismatch")
    try:
        runner = subprocess.check_output(
            ["git", "show", f"{RUNNER_COMMIT}:tools/run_1x_automation_trust_ui_hil.py"],
            cwd=ROOT)
        require(failures, hashlib.sha256(runner).hexdigest() == RUNNER_SHA,
                "runner blob mismatch")
        for path, expected_hash in provenance.get("source_sha256", {}).items():
            blob = subprocess.check_output(
                ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT)
            require(failures, hashlib.sha256(blob).hexdigest() == expected_hash,
                    f"source blob mismatch: {path}")
    except subprocess.CalledProcessError as error:
        failures.append(f"git provenance lookup failed: {error}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Automation trust UI HIL acceptance passed: stable EN/RU, read-only import, unchanged trust, zero output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
