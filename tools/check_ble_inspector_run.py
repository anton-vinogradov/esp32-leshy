#!/usr/bin/env python3
"""Fail closed unless a raw focused BLE Inspector HIL run is complete."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ble_nearby_entry_gate import (
    BLE_ENTRY_STABILITY_MINIMUM_MS,
    ble_entry_failure,
)


RUN_SCHEMA = "leshy.ble_inspector_hil.run.v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(directory: Path) -> None:
    manifest = directory / "artifacts.sha256"
    require(manifest.is_file(), "artifact manifest missing")
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, separator, relative = line.partition("  ")
        require(separator == "  " and len(expected) == 64,
                f"malformed manifest line: {line!r}")
        require(relative not in seen, f"duplicate manifest entry: {relative}")
        seen.add(relative)
        path = directory / relative
        require(path.is_file() and not path.is_symlink(),
                f"missing regular artifact: {relative}")
        require(digest(path) == expected,
                f"artifact digest mismatch: {relative}")
    actual = {
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(seen == actual, "artifact manifest coverage mismatch")


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
    directory = args.run.resolve()
    require(directory.is_dir() and not directory.is_symlink(),
            "regular run directory required")
    verify_manifest(directory)
    run = load(directory / "run.json")
    exact(run, {
        "schema": RUN_SCHEMA,
        "passed": True,
        "gate_eligible": True,
        "failures": [],
        "expected_cid": args.expected_cid,
    }, "run")
    candidate = run.get("candidate", {})
    require(isinstance(candidate, dict), "candidate missing")
    exact(candidate, {
        "version": args.expected_version,
        "source_commit": args.source_commit,
        "flash_mode": "fresh",
    }, "candidate")
    firmware = directory / "firmware.bin"
    require(digest(firmware) == candidate.get("firmware_sha256"),
            "candidate firmware digest mismatch")
    require(len(str(candidate.get("app_elf_sha256", ""))) == 64,
            "candidate app identity missing")

    preflight = run.get("preflight", {})
    exact(preflight, {
        "performed_before_application_flash": True,
        "expected_cid": args.expected_cid,
        "observed_cid": args.expected_cid,
        "fingerprint_matched": True,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
    }, "preflight")
    boot = run.get("boot", {})
    exact(boot, {
        "schema": "leshy.boot.v1",
        "kind": "ready",
        "version": args.expected_version,
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "input_detected": True,
        "buzzer_inactive": True,
        "buzzer_safety_configured": True,
    }, "boot")
    recovery = run.get("recovery", {})
    exact(recovery, {
        "expected_fingerprint": args.expected_cid,
        "observed_fingerprint": args.expected_cid,
        "fingerprint_matched": True,
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "physical_write_calls": 0,
        "cleanup_complete": True,
    }, "recovery")

    stability = run.get("entry_stability", {})
    require(int(stability.get("duration_ms", 0)) >=
            BLE_ENTRY_STABILITY_MINIMUM_MS,
            "complete bounded BLE entry window unproven")
    require(int(stability.get("samples", 0)) >= 2,
            "BLE entry window samples missing")
    stable_state = stability.get("final_state", {})
    require(isinstance(stable_state, dict) and
            ble_entry_failure(stable_state) is None,
            "Bluetooth route bounced during bounded entry window")
    exact(stable_state, {
        "ble_begin_stage": "ready",
        "ble_begin_error": 0,
        "survey_product_cleanup_complete": False,
        "survey_ble_scan_dropped": 0,
    }, "entry_stability.final_state")

    detail = run.get("detail", {})
    exact(detail, {
        "schema": "leshy.ble.device_detail.v1",
        "active": True,
        "passive": True,
        "active_probe_allowed": False,
        "atomic_text_row_allocation_failures": 0,
        "direct_text_row_fallbacks": 0,
    }, "detail")
    identity_hash = detail.get("identity_hash")
    require(isinstance(identity_hash, int) and identity_hash != 0,
            "selected detail identity missing")

    first = run.get("running_first", {})
    second = run.get("running_second", {})
    frozen = run.get("frozen", {})
    for label, state in (("running_first", first),
                         ("running_second", second),
                         ("frozen", frozen)):
        exact(state, {
            "schema": "leshy.ble.inspector.state.v1",
            "view": "inspector_raw",
            "passive": True,
            "receive_only": True,
            "selected_identity_hash": identity_hash,
            "capacity": 32,
            "invalid": 0,
            "dropped": 0,
            "content_clears": 1,
            "atomic_row_allocation_failures": 0,
            "direct_row_fallbacks": 0,
            "gatt_started": False,
        }, label)
    require(first.get("capture_state") in ("running", "frozen") and
            int(first.get("records", 0)) >= 1,
            "first selected record missing")
    require(int(second.get("records", 0)) >= int(first.get("records", 0)) and
            int(second.get("atomic_row_pushes", 0)) > 0,
            "incremental selected-record update missing")
    exact(frozen, {
        "capture_state": "frozen",
        "export_ready": True,
    }, "frozen")
    records = int(frozen.get("records", 0))
    require(1 <= records <= 32 and frozen.get("accepted") == records,
            "frozen capture accounting mismatch")

    export = run.get("export", {})
    exact(export, {
        "schema": "leshy.ble.inspector.capture.v1",
        "records": records,
        "raw_identifiers_retained_by_runner": False,
        "raw_payload_retained_by_runner": False,
    }, "export")
    require(0 < int(export.get("payload_bytes", 0)) <= records * 31,
            "export payload accounting mismatch")
    require(len(str(export.get("stream_sha256", ""))) == 64,
            "in-memory export digest missing")

    screens = run.get("screens", {})
    require(set(screens) == {
        "running_first", "running_second", "frozen", "home_after"},
        "automatic screenshot set mismatch")
    for label, screen in screens.items():
        require(len(str(screen.get("png_sha256", ""))) == 64 and
                len(str(screen.get("rgb565_sha256", ""))) == 64,
                f"{label} screenshot digests missing")

    exact(run.get("input", {}), {
        "status": "ready", "read_errors": 0, "queue_drops": 0,
    }, "input")
    exact(run.get("safe_outputs", {}), {
        "buzzer_inactive": True,
        "buzzer_level": "low",
        "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "safe_outputs")
    cleanup = run.get("cleanup", {})
    exact(cleanup, {"attempted": True, "complete": True, "errors": []},
          "cleanup")
    exact(cleanup.get("final_state", {}), {
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "survey_product_cleanup_complete": True,
        "safety_state": "armed",
        "safety_latched": False,
    }, "cleanup.final_state")
    exact(run.get("scope", {}), {
        "single_flash": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "passive_ble_only": True,
        "selected_target_only": True,
        "incremental_rows_only": True,
        "raw_export_checked_in_memory": True,
        "raw_private_evidence_retained": False,
        "mac_wifi_touched": False,
        "clone_touched": False,
        "cardputer_touched": False,
    }, "scope")
    print(json.dumps({
        "status": "pass",
        "version": args.expected_version,
        "records": records,
        "entry_stability_ms": stability.get("duration_ms"),
        "final_page": "home",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
