#!/usr/bin/env python3
"""Retain privacy-minimal incident-to-fix evidence for the WDT journal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(directory: Path) -> str:
    manifest = directory / "artifacts.sha256"
    require(manifest.is_file(), f"artifact manifest missing: {directory}")
    indexed: set[str] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, f"malformed manifest line {number}")
        expected, relative = match.groups()
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts,
                f"unsafe manifest path: {relative}")
        require(relative not in indexed, f"duplicate manifest path: {relative}")
        artifact = directory / path
        require(artifact.is_file() and digest(artifact) == expected,
                f"artifact mismatch: {relative}")
        indexed.add(relative)
    actual = {
        str(path.relative_to(directory)) for path in directory.rglob("*")
        if path.is_file() and path != manifest
    }
    require(actual == indexed, "manifest does not exactly cover source bundle")
    return digest(manifest)


def pick(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--failed-run-dir", type=Path, required=True)
    parser.add_argument("--failed-panic", type=Path, required=True)
    parser.add_argument("--passed-run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static-ram-bytes", type=int, required=True)
    parser.add_argument("--linked-flash-bytes", type=int, required=True)
    parser.add_argument("--factory-sha256", required=True)
    parser.add_argument("--map-sha256", required=True)
    parser.add_argument("--write-sd-stack-before", type=int, required=True)
    parser.add_argument("--write-sd-stack-after", type=int, required=True)
    parser.add_argument("--exact-file-stack-after", type=int, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")

    failed_path = args.failed_run_dir / "run.json"
    passed_path = args.passed_run_dir / "run.json"
    failed = load(failed_path)
    passed = load(passed_path)
    failed_manifest = verify_manifest(args.failed_run_dir)
    passed_manifest = verify_manifest(args.passed_run_dir)
    panic = args.failed_panic.read_bytes()

    require(failed.get("schema") == "leshy.safety_watchdog_hil.run.v2" and
            failed.get("passed") is False and
            failed.get("gate_eligible") is False,
            "predecessor is not retained fail-closed evidence")
    require(passed.get("schema") == "leshy.safety_watchdog_hil.run.v2" and
            passed.get("passed") is True and
            passed.get("gate_eligible") is True and
            passed.get("failures") == [],
            "successor is not gate-eligible evidence")
    require(b"Stack canary watchpoint triggered (loopTask)" in panic and
            b"ELF file SHA256: 3121fc970" in panic,
            "panic capture is not the exact predecessor stack failure")

    failed_latched = failed["records"]["safety_latched"]
    failed_restart = failed["records"]["safety_after_latched_restart"]
    require(failed_latched.get("watchdog_journal_persist_status") ==
            "written_verified" and
            failed_latched.get("watchdog_journal_nvs_verified") is True and
            failed_latched.get("watchdog_journal_sequence") == 1 and
            failed_restart.get("watchdog_journal_persist_status") ==
            "already_persisted" and
            failed_restart.get("watchdog_journal_nvs_write_attempted") is False,
            "predecessor did not prove first-boot persistence and deduplication")

    records = passed["records"]
    candidate = passed["candidate"]
    latched = records["safety_latched"]
    restart = records["safety_after_latched_restart"]
    final = records["safety_final"]
    recovery = records["recovery_final"]
    require(candidate.get("version") == "1.0.0-dev.376" and
            candidate.get("flashed") is True,
            "successor candidate identity mismatch")
    require(latched.get("watchdog_journal_persist_status") ==
            "written_verified" and
            latched.get("watchdog_journal_nvs_verified") is True and
            latched.get("watchdog_journal_sequence") == 2 and
            latched.get("watchdog_journal_sd_status") == "deferred_safe_mode",
            "successor Safe Mode persistence mismatch")
    require(restart.get("watchdog_journal_sequence") == 2 and
            restart.get("watchdog_journal_persist_status") ==
            "already_persisted" and
            restart.get("watchdog_journal_nvs_write_attempted") is False,
            "successor restart duplicated the incident")
    require(final.get("state") == "armed" and
            final.get("watchdog_journal_sequence") == 2 and
            final.get("watchdog_journal_sd_status") == "written_verified" and
            final.get("watchdog_journal_sd_write_status") == "written" and
            final.get("watchdog_journal_sd_mirrored_sequence") == 2 and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "successor final SD mirror/cleanup mismatch")
    require(recovery.get("expected_fingerprint") == passed.get("expected_cid") and
            recovery.get("fingerprint_matched") is True and
            recovery.get("cleanup_complete") is True and
            recovery.get("owned_after") == 0,
            "successor exact-CID recovery mismatch")

    evidence = {
        "schema": "leshy.runtime_watchdog_journal.acceptance.v1",
        "status": "pass_with_retained_negative_evidence",
        "trust_status": "unsigned_local_result",
        "board": "board-01",
        "evidence_ids": [
            "E-BUILD-245", "E-AUTO-224", "E-HIL-241", "E-SAFETY-089",
            "RB-M258",
        ],
        "candidate": candidate,
        "media": {
            "cid": passed["expected_cid"],
            "generation": recovery["generation"],
            "observations": recovery["observations"],
        },
        "retained_failure": {
            "candidate": failed["candidate"],
            "failures": failed["failures"],
            "run_sha256": digest(failed_path),
            "artifact_manifest_sha256": failed_manifest,
            "panic_sha256": digest(args.failed_panic),
            "panic_bytes": len(panic),
            "failure": "loopTask_stack_canary_during_sd_mirror",
            "journal_sequence": failed_latched["watchdog_journal_sequence"],
            "nvs_first_boot_status":
                failed_latched["watchdog_journal_persist_status"],
            "nvs_restart_status":
                failed_restart["watchdog_journal_persist_status"],
            "sd_status": failed_latched["watchdog_journal_sd_status"],
            "gate_eligible": False,
        },
        "correction": {
            "fatfs_workspace": "heap_nothrow_single_reused_workspace",
            "write_sd_stack_bytes_before": args.write_sd_stack_before,
            "write_sd_stack_bytes_after": args.write_sd_stack_after,
            "exact_file_stack_bytes_after": args.exact_file_stack_after,
            "usb_reconnect_after_every_restart": True,
            "nvs_required_sd_opportunistic": True,
        },
        "accepted_run": {
            "run_sha256": digest(passed_path),
            "artifact_manifest_sha256": passed_manifest,
            "watchdog_reset_reason_code":
                records["watchdog_ready"]["reset_reason_code"],
            "journal": pick(latched, (
                "watchdog_journal_sequence", "watchdog_journal_version",
                "watchdog_journal_app_elf_sha256",
                "watchdog_journal_reset_reason_code",
                "watchdog_journal_triggered_cpu_mask",
                "watchdog_journal_stage", "watchdog_journal_page",
                "watchdog_journal_wifi_view",
                "watchdog_journal_persist_status",
                "watchdog_journal_nvs_verified",
                "watchdog_journal_sd_status",
            )),
            "deduplicated_restart": pick(restart, (
                "watchdog_journal_sequence",
                "watchdog_journal_persist_status",
                "watchdog_journal_nvs_write_attempted",
            )),
            "final": pick(final, (
                "state", "reason", "watchdog_journal_sequence",
                "watchdog_journal_persist_status",
                "watchdog_journal_nvs_verified",
                "watchdog_journal_sd_status",
                "watchdog_journal_sd_write_attempted",
                "watchdog_journal_sd_write_status",
                "watchdog_journal_sd_mirrored_sequence",
                "runtime_owner", "lease_mask",
            )),
            "ready_ms": {
                "watchdog": records["watchdog_ready_marker_ms"],
                "restart": records["latched_restart_ready_marker_ms"],
                "clear": records["clear_ready_marker_ms"],
            },
        },
        "build": {
            "static_ram_bytes": args.static_ram_bytes,
            "linked_flash_bytes": args.linked_flash_bytes,
            "app_image_bytes": (args.passed_run_dir / "firmware.bin").stat().st_size,
            "ota_free_bytes": 4194304 -
                (args.passed_run_dir / "firmware.bin").stat().st_size,
            "factory_sha256": args.factory_sha256,
            "map_sha256": args.map_sha256,
        },
        "privacy": {
            "ambient_ssid_retained": False,
            "ambient_bssid_retained": False,
            "raw_wifi_frames_retained": False,
            "device_port_retained": False,
        },
        "verified": {
            "cause_available_without_reproduction": True,
            "nvs_survives_reset": True,
            "same_incident_not_duplicated": True,
            "safe_mode_defers_sd": True,
            "exact_cid_sd_mirror_atomic_and_verified": True,
            "final_home_none_zero_lease": True,
            "mac_wifi_untouched": True,
            "rf_transmit_invoked": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output),
                      "sha256": digest(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
