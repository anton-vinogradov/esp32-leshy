#!/usr/bin/env python3
"""Machine-check the retained exact Device Lock PIN-disable delta."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-device-lock-disable-1.0.0-dev.331.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    run = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact(run, {
        "schema": "leshy.device_lock_disable_hil.acceptance.v1",
        "passed": True,
        "failures": [],
    }, "run")
    exact(run["candidate"], {
        "version": "1.0.0-dev.331",
        "source_commit": "43aa366ea57bfbdb7126c2587712b943236eb233",
        "firmware_sha256":
            "e25b7684598308470219a1c4be24a1dbd220d0b087ebecd970e26e44d25c0427",
        "factory_sha256":
            "b9708dc1c3d4898f9dd3edd068e93c6af77ea994104259979ac8d3fcc9354bbd",
        "app_identity_sha256":
            "3bcc061112036624cee3d417889f6b436c07c7dc7431231301746e099a252f03",
        "elf_sha256":
            "be18d3989c3521bf30ffbe1b3ed011e0a13d0690fd6b81a2100b3604f0a99317",
        "map_sha256":
            "542aee5b8ade84a31fb0cc30b3e9f7cd8face6cb52c3fc88c7b3627b97784a51",
        "app_bytes": 3596032,
        "factory_bytes": 3661568,
        "static_ram_bytes": 234784,
        "linked_flash_bytes": 3595528,
        "ota_headroom_bytes": 598272,
    }, "candidate")
    exact(run["owner_action"], {
        "credential_entered_only_on_device": True,
        "raw_pin_retained": False,
        "credential_or_digest_exported": False,
        "separate_confirmation": True,
    }, "owner_action")
    exact(run["live_transition"], {
        "runtime_event": "device_lock_disabled",
        "status": "disabled",
        "failure": "none",
        "failed_attempts": 0,
        "credential_generation": 0,
        "protected_access": True,
        "worker_active": False,
        "radio_touched": False,
        "input_read_errors": 0,
        "input_queue_drops": 0,
    }, "live_transition")
    exact(run["cold_restore"], {
        "status_before_safety_clear": "disabled",
        "protected_access_before_safety_clear": True,
        "transport_reset_latch": "runtime_watchdog",
        "latch_outputs_inactive": True,
        "latch_runtime_owner": "none",
        "latch_lease_mask": 0,
        "explicit_safety_clear": True,
        "status_after_safety_clear": "disabled",
        "protected_access_after_safety_clear": True,
        "failure_after_safety_clear": "none",
    }, "cold_restore")
    exact(run["protected_reopen"], {
        "status": "admitted",
        "expected_cid": "FE343253440000002000000055019CB7",
        "observed_cid": "FE343253440000002000000055019CB7",
        "fingerprint_matched": True,
        "mounted_read_only": True,
        "write_enabled": False,
        "blocked_write_attempts": 0,
        "generation": 8,
        "observations": 54,
        "integrity": "valid",
        "library_entries": 1,
        "library_generation": 8,
        "physical_write_calls": 0,
        "cleanup_complete": True,
    }, "protected_reopen")
    screen = run["screen"]
    image = EVIDENCE.parent / screen["path"]
    require(image.is_file(), "retained TFT frame missing")
    require(hashlib.sha256(image.read_bytes()).hexdigest() ==
            screen["png_sha256"], "retained TFT frame hash mismatch")
    exact(screen, {
        "width": 240,
        "height": 320,
        "png_sha256":
            "c0f95503bc343ffba1c62b15b49366039426f5f0d9522739e587fc55d3d74367",
        "rgb565_sha256":
            "a1a2732545fe773547160752188bafbd5dd21d5c31a8327ed465969ad8eecb71",
        "contains_identifiers": False,
    }, "screen")
    exact(run["runtime_heap"], {
        "total_bytes": 144020,
        "free_bytes": 69664,
        "minimum_free_bytes": 69516,
    }, "runtime_heap")
    exact(run["final"], {
        "page": "home",
        "safety_state": "armed",
        "safety_reason": "none",
        "buzzer_inactive": True,
        "runtime_owner": "none",
        "lease_mask": 0,
        "input_read_errors": 0,
        "input_queue_drops": 0,
        "clone_touched": False,
        "cardputer_touched": False,
        "mac_wifi_control_calls": 0,
        "rf_tx_calls": 0,
    }, "final")
    print(
        "Device Lock PIN-disable HIL acceptance passed: separate owner "
        "confirmation, cold disabled restore, exact-CID protected reopen, "
        "real TFT state, zero TX and zero leaked leases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
