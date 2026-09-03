#!/usr/bin/env python3
"""Verify retained one-press Wi-Fi menu-entry and heap evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/board-01-wifi-menu-entry-1.0.0-dev.377.json")
FIRMWARE_SOURCE = "53cc36c4a45fb72cabbf171b8fa828788d776025"
TOOLING_SOURCE = "975fb844a7f0eb5783fddc1c47dd0037b571e70e"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Wi-Fi menu-entry acceptance failed: {message}")


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        require(isinstance(current, dict) and key in current,
                f"missing {'.'.join(keys)}")
        current = current[key]
    return current


def git_blob(commit: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(completed.returncode == 0,
            f"missing source blob {commit}:{relative}")
    return completed.stdout


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(evidence.get("schema") ==
            "leshy.wifi_menu_entry_hil.acceptance.v1", "schema mismatch")
    require(evidence.get("status") ==
            "pass_with_retained_heap_oracle_correction", "status mismatch")
    require(evidence.get("evidence_ids") == [
        "E-BUILD-246", "E-AUTO-225", "E-HIL-242", "E-UX-093",
        "RB-M259",
    ], "evidence IDs mismatch")

    candidate = nested(evidence, "candidate")
    require(candidate == {
        "version": "1.0.0-dev.377",
        "cid": "FE343253440000002000000055019CB7",
        "firmware_source_commit": FIRMWARE_SOURCE,
        "tooling_source_commit": TOOLING_SOURCE,
        "firmware_sha256":
            "ec140e78bac945e6d067dfb2ba2707722f13c86a6f32ce061e3bb4fe5507300a",
        "factory_sha256":
            "2c1223fc2b283e5177863917aebc1e822cc2abaf75ad54b129362a617d3622b7",
        "elf_sha256":
            "555abc7f46c1d7d244a9d45a591274c2eaea04ba068a0afae2649286fcdd27a8",
        "map_sha256":
            "5f37093a792b9550c5f8537fefc12309f16c79ae7875a8eb61817884934455a8",
        "firmware_bytes": 3613216,
        "factory_bytes": 3678752,
        "elf_bytes": 25225012,
        "map_bytes": 18947140,
        "fresh_flashes": 1,
        "exact_image_reuse_runs": 1,
    }, "candidate identity/resources changed")

    tooling = nested(evidence, "host_tooling")
    expected_blobs = {
        "runner_sha256": "tools/run_1x_wifi_networks_hil.py",
        "run_checker_sha256": "tools/check_wifi_networks_run.py",
        "heap_policy_sha256": "tools/wifi_heap_plateau_policy.py",
        "contract_checker_sha256": "tools/check_wifi_networks_contract.py",
    }
    for key, relative in expected_blobs.items():
        actual = hashlib.sha256(git_blob(TOOLING_SOURCE, relative)).hexdigest()
        require(tooling.get(key) == actual,
                f"tooling is not source-bound: {relative}")
    ui_strings = git_blob(FIRMWARE_SOURCE,
                          "firmware/leshy1/src/ui/UiStrings.def")
    require(b'"WI-FI", u8"WI-FI"' in ui_strings and
            "СЕТИ · УСТРОЙСТВА · КАНАЛЫ".encode() in ui_strings,
            "firmware source does not contain the clarified Wi-Fi Home card")

    failure = nested(evidence, "retained_failure")
    require(failure.get("accepted") is False and
            failure.get("reason") ==
                "stale_2048_byte_cold_wifi_heap_oracle" and
            failure.get("cold_initialization_bytes") == 7344 and
            failure.get("corrected_ceiling_bytes") == 8192 and
            failure.get("boot_heap_free_bytes") == 66664 and
            failure.get("first_heap_free_bytes") == 59320 and
            failure.get("final_heap_free_bytes") == 59320 and
            failure.get("post_warm_heap_drift_bytes") == 0 and
            failure.get("cleanup_complete") is True and
            failure.get("final_lease_mask") == 0,
            "retained fail-closed heap precursor mismatch")

    accepted = nested(evidence, "accepted_run")
    require(accepted.get("run_sha256") ==
            "75c0518819816e50a451e852ec94b40cc03130bb14aac26d4fd0cb67886264ca" and
            accepted.get("passed") is True and
            accepted.get("gate_eligible") is True and
            accepted.get("flash_mode") == "reuse_exact" and
            accepted.get("wifi_lifecycles") == 2 and
            accepted.get("navigation_presses") == 8 and
            accepted.get("manual_button_presses") == 0,
            "accepted run mismatch")
    entries = accepted.get("single_press_entries")
    require(isinstance(entries, list) and len(entries) == 2 and
            [entry.get("action") for entry in entries] == ["select", "right"],
            "both one-press entry controls are not retained")
    for entry in entries:
        require(entry.get("changed") is True and
                entry.get("page") == "survey" and
                entry.get("runtime_owner") == "wifi" and
                entry.get("lease_mask") == 15 and
                entry.get("runtime_event") == "wifi_networks_preparing",
                "one-press entry transition mismatch")

    require(nested(evidence, "runtime") == {
        "heap_total_bytes": 142284,
        "first_heap_free_bytes": 59320,
        "final_heap_free_bytes": 59320,
        "minimum_heap_free_bytes": 17940,
        "one_time_initialization_ceiling_bytes": 8192,
        "heap_drift_after_warmup_bytes": 0,
        "input_queue_drops": 0,
        "input_read_errors": 0,
        "ambiguous_presses": 0,
    }, "runtime accounting changed")
    require(nested(evidence, "storage") == {
        "cid": "FE343253440000002000000055019CB7",
        "generation": 13,
        "observations": 0,
        "mounted_read_only": True,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
    }, "storage boundary changed")
    require(nested(evidence, "cleanup") == {
        "complete": True,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
    }, "cleanup changed")
    require(nested(evidence, "resources", "free_ota_bytes") == 581088 and
            nested(evidence, "resources", "free_ota_bytes") >= 524288,
            "OTA headroom changed")
    require(nested(evidence, "policy") == {
        "passive_wifi_only": True,
        "host_network_tools_invoked": False,
        "active_host_wifi_touched": False,
        "cardputer_connected_or_opened": False,
        "raw_radio_tx_commands_invoked_by_runner": 0,
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "scope/policy changed")
    require(nested(evidence, "privacy") == {
        "ambient_identifiers_retained": False,
        "raw_run_retained": False,
        "screenshots_retained": False,
        "exact_device_port_retained": False,
    }, "privacy boundary changed")
    serialized = EVIDENCE.read_text(encoding="utf-8").lower()
    for forbidden in ("/dev/", "usbmodem", '"ssid"', '"bssid"'):
        require(forbidden not in serialized,
                f"privacy-minimal evidence contains {forbidden!r}")
    print(
        "wifi_menu_entry_hil_acceptance: PASS; Home enters the Wi-Fi task "
        "menu in one action, then Select and Right each enter Nearby Networks "
        "from that menu in one action; cold Wi-Fi init is bounded, warm heap "
        "is invariant, storage is read-only and final lease is zero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
