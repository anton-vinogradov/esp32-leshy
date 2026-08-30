#!/usr/bin/env python3
"""Machine-check one exact authenticated product-storage HIL run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    run_path = args.run / "run.json" if args.run.is_dir() else args.run
    run = json.loads(run_path.read_text(encoding="utf-8"))
    exact(run, {
        "schema": "leshy.protected_storage_hil.run.v1",
        "passed": True, "gate_eligible": True, "failures": [],
        "board": "board-01", "expected_cid": args.expected_cid,
    }, "run")
    exact(run["candidate"], {
        "version": args.expected_version,
        "source_commit": args.source_commit,
        "flashed": True, "flash_mode": "fresh",
    }, "candidate")
    require(len(run["candidate"]["firmware_sha256"]) == 64,
            "candidate firmware hash missing")
    require(len(run["candidate"]["app_elf_sha256"]) == 64,
            "candidate app identity missing")
    stored = run["records"]["protected_store"]
    exact(stored, {
        "schema": "leshy.storage.product_bootstrap.v2",
        "status": "valid",
        "expected_fingerprint": args.expected_cid,
        "cid_hex": args.expected_cid,
        "fingerprint_matched": True,
        "mounted_writable": True,
        "format_allowed": False,
        "permit_status": "permitted",
        "commit_status": "valid",
        "catalog_admitted": True,
        "encrypted_namespace": True,
        "envelope_header_valid": True,
        "physical_size_exact": True,
        "ciphertext_differs": True,
        "io_failure": "none",
        "io_result": "ok",
        "queue_drops": 0,
        "append_drops": 0,
        "owned_after": 0,
        "identity_cleanup": True,
        "scanner_cleanup": True,
        "filesystem_cleanup": True,
        "radio_connect_calls": 0,
        "application_raw_tx_calls": 0,
    }, "protected_store")
    require(stored["protected_plaintext_bytes"] > 0,
            "protected plaintext size missing")
    require(stored["protected_physical_bytes"] >
            stored["protected_plaintext_bytes"] + 32,
            "protected envelope authentication overhead missing")
    exact(run["scope"], {
        "single_application_flash": True,
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
        "terminal_zero_lease": True,
    }, "scope")
    print(
        "Protected storage HIL acceptance passed: exact SD/CID, "
        "AES-GCM envelope, ciphertext separation, authenticated reopen, "
        "zero TX and zero leaked leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
