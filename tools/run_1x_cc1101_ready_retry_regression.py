#!/usr/bin/env python3
"""Flash once and regress the bounded CC1101 RX-ready retry on 868 MHz."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import (
    CC_SCHEMA,
    WATERFALL_ROWS,
    home_selection,
    require_cc_retry_accounting,
    wait_report,
)
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.cc1101_ready_retry_regression.run.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    report: dict[str, Any] = {}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot = query(device, b"metrics", "leshy.boot.v1", "ready")
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                if not best_effort_cleanup(device).get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                home_selection(device, 3)
                trace.append(action(device, "right"))
                trace.append(action(device, "down"))
                started = action(device, "right")
                trace.append(started)
                if started.get("runtime_event") != "cc1101_spectrum_running":
                    raise RuntimeError(f"CC868 did not start: {started}")
                report = wait_report(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA,
                    WATERFALL_ROWS, timeout=12.0)
                if not (
                    report.get("band") == "868" and
                    report.get("state") == "running" and
                    report.get("status") == "ready" and
                    report.get("history_rows") == WATERFALL_ROWS and
                    report.get("waterfall_full") is True and
                    report.get("adapter_samples", 0) >= 64 and
                    report.get("side_effects") == {
                        "rejected_strobes": 0,
                        "tx_strobes": 0,
                        "pa_table_writes": 0,
                        "fifo_writes": 0,
                        "storage_writes": 0,
                    }
                ):
                    raise RuntimeError(f"CC868 regression mismatch: {report}")
                require_cc_retry_accounting(report, "cc_868_regression")
                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                recovery_after = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                if (
                    recovery_after.get("generation") !=
                        recovery_before.get("generation") or
                    recovery_after.get("observations") !=
                        recovery_before.get("observations") or
                    recovery_after.get("physical_write_calls") != 0
                ):
                    raise RuntimeError("CC868 regression changed persistent data")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "boot": boot,
        "recovery_before": recovery_before,
        "cc868": report,
        "recovery_after": recovery_after,
        "trace": trace,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "receive_only": True,
            "band": "868",
            "minimum_history_rows": WATERFALL_ROWS,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "timeouts": report.get("wire", {}).get("receive_ready_timeouts"),
        "retries": report.get("wire", {}).get("transient_retries"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
