#!/usr/bin/env python3
"""Prove authenticated product storage on one exact ESP32-DIV/SD pair."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    artifact_manifest,
    best_effort_cleanup,
    boot_ready_failures,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.protected_storage_hil.run.v1"
RESULT_SCHEMA = "leshy.storage.product_bootstrap.v2"


def positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def cleanup_summary(cleanup: dict[str, Any]) -> dict[str, Any]:
    final = cleanup.get("final_state", {})
    return {
        "attempted": cleanup.get("attempted") is True,
        "complete": cleanup.get("complete") is True,
        "action_count": len(cleanup.get("actions", [])),
        "errors": cleanup.get("errors", []),
        "final_state": {
            key: final.get(key)
            for key in ("page", "runtime_owner", "lease_mask",
                        "safety_state", "safety_reason")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one flash mode")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing application image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    retained_runner = args.output / Path(__file__).name
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.firmware.parent / "firmware.elf", retained_elf)
    shutil.copyfile(args.firmware.parent / "firmware.map", retained_map)
    shutil.copyfile(Path(__file__), retained_runner)
    app_sha = app_elf_sha256(candidate)
    firmware_sha = sha256_file(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    records: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    hil_begun = False

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.6)
        with PassiveSerial(args.port, 115200, timeout=0.05) as device:
            synchronize_console(device, 45.0)
            records["boot"] = query(
                device, b"metrics", "leshy.boot.v1", "ready")
            failures.extend(boot_ready_failures(
                records["boot"], args.expected_version, app_sha))
            records["recovery_before"] = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            recovery = records["recovery_before"]
            failures.extend(expect(recovery, {
                "expected_fingerprint": args.expected_cid,
                "observed_fingerprint": args.expected_cid,
                "fingerprint_matched": True,
                "mounted_read_only": True,
                "read_only_guaranteed": True,
                "blocked_write_attempts": 0,
                "cleanup_complete": True,
                "physical_write_calls": 0,
            }, "recovery_before"))
            if recovery.get("status") not in {"empty", "admitted"}:
                failures.append(
                    "recovery_before.status: expected empty or admitted")
            cleanup = best_effort_cleanup(device)
            records["cleanup_before"] = cleanup_summary(cleanup)
            if not cleanup.get("complete"):
                failures.append("initial Home/zero-lease cleanup failed")
            if failures:
                raise RuntimeError("preflight failed")

            records["hil_begin"] = query(
                device, f"hil.begin {run_id} {app_sha}".encode("ascii"),
                "leshy.hil.session.v1", "begun")
            hil_begun = records["hil_begin"].get("active") is True
            failures.extend(expect(records["hil_begin"], {
                "status": "begun", "session_id": run_id, "active": True,
                "app_elf_sha256": app_sha,
                "firmware_version": args.expected_version,
            }, "hil_begin"))

            command = (
                "storage.product.bootstrap disposable-write " +
                args.expected_cid).encode("ascii")
            records["protected_store"] = query(
                device, command, RESULT_SCHEMA, "result", timeout=60.0)
            stored = records["protected_store"]
            failures.extend(expect(stored, {
                "status": "valid",
                "expected_fingerprint": args.expected_cid,
                "cid_hex": args.expected_cid,
                "fingerprint_matched": True,
                "mounted_writable": True,
                "explicitly_selected": True,
                "format_allowed": False,
                "product_root": "/leshy/sessions/v1",
                "permit_status": "permitted",
                "opened": True,
                "wifi_scan_status": "valid",
                "queue_drops": 0,
                "append_drops": 0,
                "commit_status": "valid",
                "catalog_status": "admitted",
                "catalog_admitted": True,
                "encrypted_namespace": True,
                "envelope_header_valid": True,
                "physical_size_exact": True,
                "ciphertext_differs": True,
                "io_failure": "none",
                "io_result": "FR_OK",
                "enrollment_saved": True,
                "owned_after": 0,
                "identity_cleanup": True,
                "scanner_cleanup": True,
                "filesystem_cleanup": True,
                "radio_connect_calls": 0,
                "application_raw_tx_calls": 0,
            }, "protected_store"))
            for key in ("wifi_records", "observations", "generation",
                        "protected_plaintext_bytes",
                        "protected_physical_bytes", "bytes_written",
                        "file_syncs", "directory_syncs", "owned_during"):
                if not positive_integer(stored.get(key)):
                    failures.append(f"protected_store.{key}: expected > 0")
            if (positive_integer(stored.get("protected_plaintext_bytes")) and
                    positive_integer(stored.get("protected_physical_bytes")) and
                    stored["protected_physical_bytes"] <=
                    stored["protected_plaintext_bytes"] + 32):
                failures.append("protected envelope has no authentication overhead")

            cleanup = best_effort_cleanup(device)
            records["cleanup_after"] = cleanup_summary(cleanup)
            if not cleanup.get("complete"):
                failures.append("final Home/zero-lease cleanup failed")
            records["hil_end"] = query(
                device, f"hil.end {run_id}".encode("ascii"),
                "leshy.hil.session.v1", "ended")
            hil_begun = False
            failures.extend(expect(records["hil_end"], {
                "status": "ended", "session_id": run_id, "active": False,
                "app_elf_sha256": app_sha,
            }, "hil_end"))
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
        try:
            with PassiveSerial(args.port, 115200, timeout=0.05) as device:
                synchronize_console(device, 10.0)
                cleanup = best_effort_cleanup(device)
                records["failure_cleanup"] = cleanup_summary(cleanup)
                if hil_begun:
                    records["failure_hil_end"] = query(
                        device, f"hil.end {run_id}".encode("ascii"),
                        "leshy.hil.session.v1", "ended")
        except Exception as cleanup_error:
            failures.append(
                f"cleanup {type(cleanup_error).__name__}: {cleanup_error}")

    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "gate_eligible": args.flash and not failures,
        "failures": failures,
        "board": "board-01",
        "run_id": run_id,
        "expected_cid": args.expected_cid,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_sha,
            "elf_sha256": sha256_file(retained_elf),
            "map_sha256": sha256_file(retained_map),
            "runner_sha256": sha256_file(retained_runner),
            "flashed": args.flash,
            "flash_mode": "fresh" if args.flash else "exact_reuse",
        },
        "records": records,
        "scope": {
            "single_application_flash": args.flash,
            "manual_button_presses": 0,
            "screenshots": 0,
            "normal_product_commit": True,
            "factory_reset": False,
            "sd_format": False,
            "radio_connect_calls": 0,
            "application_raw_tx_calls": 0,
            "host_wifi_control_calls": 0,
            "clone_touched": False,
            "cardputer_touched": False,
            "terminal_zero_lease": cleanup.get("complete") is True,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "generation": records.get("protected_store", {}).get("generation"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
