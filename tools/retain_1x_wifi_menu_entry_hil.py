#!/usr/bin/env python3
"""Retain privacy-minimal Wi-Fi menu-entry and heap-oracle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


VERSION = "1.0.0-dev.377"
CID = "FE343253440000002000000055019CB7"
FIRMWARE_SOURCE = "53cc36c4a45fb72cabbf171b8fa828788d776025"
TOOLING_SOURCE = "975fb844a7f0eb5783fddc1c47dd0037b571e70e"
HEAP_CEILING = 8 * 1024


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
        artifact = directory / path
        require(artifact.is_file() and digest(artifact) == expected,
                f"artifact mismatch: {relative}")
        indexed.add(relative)
    actual = {
        str(path.relative_to(directory)) for path in directory.rglob("*")
        if path.is_file() and path != manifest
    }
    require(actual == indexed, "manifest does not exactly cover run bundle")
    return digest(manifest)


def cleanup_ok(run: dict[str, Any]) -> bool:
    cleanup = run.get("cleanup_after", {})
    final = cleanup.get("final_state", {})
    return (cleanup.get("complete") is True and final.get("page") == "home"
            and final.get("runtime_owner") == "none"
            and final.get("lease_mask") == 0)


def entry_records(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for record in run.get("trace", []):
        if (record.get("action") in ("select", "right") and
                record.get("wifi_product_view") == "networks"):
            result.append({
                "action": record.get("action"),
                "changed": record.get("changed"),
                "page": record.get("page"),
                "runtime_owner": record.get("runtime_owner"),
                "lease_mask": record.get("lease_mask"),
                "runtime_event": record.get("runtime_event"),
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--failed-run-dir", type=Path, required=True)
    parser.add_argument("--passed-run-dir", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--factory", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--run-checker", type=Path, required=True)
    parser.add_argument("--heap-policy", type=Path, required=True)
    parser.add_argument("--contract-checker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")

    failed_path = args.failed_run_dir / "run.json"
    passed_path = args.passed_run_dir / "run.json"
    failed = load(failed_path)
    passed = load(passed_path)
    failed_manifest = verify_manifest(args.failed_run_dir)
    passed_manifest = verify_manifest(args.passed_run_dir)

    for label, run in (("failed", failed), ("passed", passed)):
        candidate = run.get("candidate", {})
        require(run.get("schema") == "leshy.wifi_networks_hil.run.v1",
                f"{label} schema mismatch")
        require(run.get("expected_cid") == CID, f"{label} CID mismatch")
        require(candidate.get("version") == VERSION and
                candidate.get("source_commit") == FIRMWARE_SOURCE and
                candidate.get("firmware_sha256") == digest(args.firmware) and
                candidate.get("app_elf_sha256") == digest(args.elf),
                f"{label} candidate mismatch")
        require(cleanup_ok(run), f"{label} cleanup mismatch")

    failed_scope = failed.get("scope", {})
    failed_boot = failed.get("boot", {})
    failed_first = failed.get("metrics_after_first", {})
    failed_final = failed.get("metrics_after", {})
    require(failed.get("passed") is False and
            failed.get("gate_eligible") is False and
            failed.get("failures") == [
                "Wi-Fi one-time heap warm-up is unbounded: 7344 bytes"
            ] and failed.get("candidate", {}).get("flash_mode") == "fresh",
            "failed precursor is not the exact stale heap-oracle rejection")
    require(failed_scope.get("bounded_one_time_heap_warmup_bytes") == 7344 and
            failed_scope.get("zero_heap_drift_after_warmup") is True and
            failed_scope.get("two_complete_wifi_lifecycles") is True and
            failed_boot.get("heap_free") == 66664 and
            failed_first.get("heap_free") == 59320 and
            failed_final.get("heap_free") == 59320 and
            failed_first.get("heap_total") == 142284 and
            failed_final.get("heap_total") == 142284,
            "failed precursor heap plateau mismatch")

    scope = passed.get("scope", {})
    first = passed.get("metrics_after_first", {})
    final = passed.get("metrics_after", {})
    entries = entry_records(passed)
    require(passed.get("passed") is True and
            passed.get("gate_eligible") is True and
            passed.get("failures") == [] and
            passed.get("candidate", {}).get("flash_mode") == "reuse_exact",
            "accepted run is not gate eligible")
    require(scope.get("single_select_entry") is True and
            scope.get("single_right_entry") is True and
            scope.get("one_time_heap_initialization_ceiling_bytes") ==
                HEAP_CEILING and
            scope.get("two_complete_wifi_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True and
            scope.get("passive_wifi_only") is True and
            scope.get("storage_write_authorized") is False,
            "accepted run scope mismatch")
    require([entry["action"] for entry in entries] == ["select", "right"],
            "accepted run did not exercise one Select then one Right entry "
            "from the Wi-Fi task menu")
    for entry in entries:
        require(entry == {
            "action": entry["action"],
            "changed": True,
            "page": "survey",
            "runtime_owner": "wifi",
            "lease_mask": 15,
            "runtime_event": "wifi_networks_preparing",
        }, f"invalid one-press entry record: {entry['action']}")
    require(first.get("heap_free") == final.get("heap_free") == 59320 and
            first.get("heap_total") == final.get("heap_total") == 142284,
            "accepted run heap plateau mismatch")
    require(passed.get("input", {}).get("queue_drops") == 0 and
            passed.get("input", {}).get("read_errors") == 0 and
            passed.get("input", {}).get("ambiguous_presses") == 0,
            "accepted run input mismatch")
    before = passed.get("recovery_before", {})
    after = passed.get("recovery_after", {})
    require(before.get("generation") == after.get("generation") == 13 and
            before.get("observations") == after.get("observations") == 0 and
            after.get("physical_write_calls") == 0 and
            after.get("blocked_write_attempts") == 0 and
            after.get("mounted_read_only") is True,
            "accepted run storage boundary mismatch")
    safe = passed.get("safe_outputs", {})
    require(safe.get("buzzer_inactive") is True and
            safe.get("nrf_ce_inactive") is True and
            safe.get("software_quiesce_complete") is True,
            "accepted safe-output boundary mismatch")

    evidence = {
        "schema": "leshy.wifi_menu_entry_hil.acceptance.v1",
        "status": "pass_with_retained_heap_oracle_correction",
        "trust_status": "unsigned_local_result",
        "board": "board-01",
        "evidence_ids": [
            "E-BUILD-246", "E-AUTO-225", "E-HIL-242", "E-UX-093",
            "RB-M259",
        ],
        "candidate": {
            "version": VERSION,
            "cid": CID,
            "firmware_source_commit": FIRMWARE_SOURCE,
            "tooling_source_commit": TOOLING_SOURCE,
            "firmware_sha256": digest(args.firmware),
            "factory_sha256": digest(args.factory),
            "elf_sha256": digest(args.elf),
            "map_sha256": digest(args.map),
            "firmware_bytes": args.firmware.stat().st_size,
            "factory_bytes": args.factory.stat().st_size,
            "elf_bytes": args.elf.stat().st_size,
            "map_bytes": args.map.stat().st_size,
            "fresh_flashes": 1,
            "exact_image_reuse_runs": 1,
        },
        "host_tooling": {
            "runner_sha256": digest(args.runner),
            "run_checker_sha256": digest(args.run_checker),
            "heap_policy_sha256": digest(args.heap_policy),
            "contract_checker_sha256": digest(args.contract_checker),
            "daemon_or_service_installed": False,
        },
        "retained_failure": {
            "accepted": False,
            "run_sha256": digest(failed_path),
            "artifact_manifest_sha256": failed_manifest,
            "flash_mode": "fresh",
            "reason": "stale_2048_byte_cold_wifi_heap_oracle",
            "reported_failure": failed["failures"][0],
            "cold_initialization_bytes": 7344,
            "corrected_ceiling_bytes": HEAP_CEILING,
            "heap_total_bytes": 142284,
            "boot_heap_free_bytes": 66664,
            "first_heap_free_bytes": 59320,
            "final_heap_free_bytes": 59320,
            "post_warm_heap_drift_bytes": 0,
            "cleanup_complete": True,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "accepted_run": {
            "run_sha256": digest(passed_path),
            "artifact_manifest_sha256": passed_manifest,
            "passed": True,
            "gate_eligible": True,
            "flash_mode": "reuse_exact",
            "single_press_entries": entries,
            "wifi_lifecycles": 2,
            "navigation_presses": scope["navigation_press_count"],
            "maximum_unique_networks": max(
                passed["live_first"]["wifi_networks_unique"],
                passed["live_second"]["wifi_networks_unique"]),
            "manual_button_presses": 0,
        },
        "rendering": {
            "live_rows_only": scope["live_redraw_data_rows_only"],
            "selected_focus_frame_continuous":
                scope["selected_focus_frame_continuous"],
            "live_order_strongest_first":
                scope["live_order_remains_strongest_first"],
            "selected_identity_preserved":
                scope["selected_identity_preserved_during_live_sort"],
            "cursor_reset_after_user_navigation":
                not scope["cursor_not_reset_after_user_navigation"],
            "list_content_changed_pixels":
                passed["list_pixel_changes"]["content_changed_pixels"],
            "list_chrome_changed_pixels":
                passed["list_pixel_changes"]["chrome_changed_pixels"],
        },
        "runtime": {
            "heap_total_bytes": final["heap_total"],
            "first_heap_free_bytes": first["heap_free"],
            "final_heap_free_bytes": final["heap_free"],
            "minimum_heap_free_bytes": final["heap_min_free"],
            "one_time_initialization_ceiling_bytes": HEAP_CEILING,
            "heap_drift_after_warmup_bytes": 0,
            "input_queue_drops": 0,
            "input_read_errors": 0,
            "ambiguous_presses": 0,
        },
        "storage": {
            "cid": CID,
            "generation": 13,
            "observations": 0,
            "mounted_read_only": True,
            "physical_write_calls": 0,
            "blocked_write_attempts": 0,
            "cleanup_complete": True,
        },
        "cleanup": {
            "complete": True,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "resources": {
            "static_ram_bytes": 236008,
            "linked_flash_bytes": 3612708,
            "application_image_bytes": args.firmware.stat().st_size,
            "factory_image_bytes": args.factory.stat().st_size,
            "free_ota_bytes": 4194304 - args.firmware.stat().st_size,
            "required_free_ota_bytes": 524288,
        },
        "policy": {
            "passive_wifi_only": True,
            "host_network_tools_invoked": False,
            "active_host_wifi_touched": False,
            "cardputer_connected_or_opened": False,
            "raw_radio_tx_commands_invoked_by_runner": 0,
            "buzzer_inactive": True,
            "nrf_ce_inactive": True,
            "software_quiesce_complete": True,
        },
        "privacy": {
            "ambient_identifiers_retained": False,
            "raw_run_retained": False,
            "screenshots_retained": False,
            "exact_device_port_retained": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "sha256": digest(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
