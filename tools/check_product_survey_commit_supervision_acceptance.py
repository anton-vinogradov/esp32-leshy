#!/usr/bin/env python3
"""Fail closed unless exact dev.301 async Survey commit evidence is intact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT / "tests/hil/evidence" /
    "board-01-product-survey-commit-supervision-1.0.0-dev.301.json"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(
            record.get(key) == value,
            f"{label}.{key}: {record.get(key)!r} != {value!r}",
        )


def main() -> int:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact(value, {
        "schema": "leshy.product_survey_commit_supervision.acceptance.v1",
        "status": "pass_async_worker_commit_repeatability",
        "gate_eligible": True,
        "board": "board-01",
        "evidence_ids": [
            "E-BUILD-204", "E-AUTO-179", "E-HIL-213",
            "E-SAFETY-008", "E-STORAGE-038", "E-SURVEY-019",
            "RB-M215",
        ],
    }, "acceptance")
    exact(value["candidate"], {
        "version": "1.0.0-dev.301",
        "source_commit": "d34a9b0c6f61d43b462b1a638ce1c7781fe77947",
        "runner_sha256":
            "500d0747112f77e8f8b5a33127b64a77fb0082229d3a33062b5897d12281201f",
        "firmware_sha256":
            "d45fcdadb39bc1ea3851c65bb96792abcc5251cbdf9b1677f23914dc6f72255f",
        "factory_sha256":
            "8b611677b0622a0594c926f5d64366ade352ad50e84bc3e29e72cd776729e35f",
        "app_elf_sha256":
            "921e1eff0f5083cdda8533e9d376cc4b08fbffcdba0c4353fe24e66978008fe5",
        "map_sha256":
            "452cb9d01a23132a2f2551649b857939e291c51b00b1a4230a16c8694deaadcd",
        "firmware_bytes": 3533760,
        "factory_bytes": 3599296,
        "linked_flash_bytes": 3533256,
        "static_ram_bytes": 232496,
        "ota_slot_free_bytes": 660544,
    }, "candidate")
    negative = value["negative_lineage"]
    require(len(negative) == 2, "negative_lineage must retain two failures")
    exact(negative[0], {
        "version": "1.0.0-dev.299",
        "runner_status": "failed",
        "observations_before_failure": 57,
        "drops_before_failure": 0,
        "terminal_commit_model": "synchronous_ui_task",
        "failure": "task_watchdog_reset_inside_terminal_sd_commit",
    }, "negative_lineage[0]")
    exact(negative[1], {
        "version": "1.0.0-dev.300",
        "runner_status": "failed",
        "observations_before_failure": 53,
        "drops_before_failure": 0,
        "terminal_commit_model":
            "synchronous_ui_task_with_interstage_task_wdt_feeds",
        "failure": "task_watchdog_reset_inside_one_terminal_sd_primitive",
    }, "negative_lineage[1]")
    exact(value["physical_delta"], {
        "run_sha256":
            "473febaf06a259630c6d4d534c5199be0b7f56afdf0bc906e7380dd5fcbef795",
        "runner_status": "pass",
        "mode": "survey_only",
        "application_flashes": 1,
        "survey_cycles": 2,
        "exact_cid": "FE343253440000002000000055019CB7",
        "generation_before": 6,
        "generations_committed": [7, 8],
        "observations_committed": [54, 54],
        "wifi_observations": [22, 23],
        "ble_observations": [32, 31],
        "wifi_drops": [0, 0],
        "ble_drops": [0, 0],
        "pipeline_drops": [0, 0],
        "timeline_windows_persisted": [6, 6],
        "identity_attempts": [2, 1],
        "identity_transient_retries": [1, 0],
        "filesystem_mount_attempts": [1, 1],
        "filesystem_mount_transient_retries": [0, 0],
        "cleanup_complete": [True, True],
    }, "physical_delta")
    exact(value["worker_supervision_after"], {
        "safety_state": "armed",
        "safety_reason": "none",
        "safety_latched": False,
        "emergency_quiesce_count": 0,
        "worker_active": "none",
        "worker_last_expired": "none",
        "worker_armed": False,
        "worker_deadline_ms": 8000,
        "worker_arm_count": 6,
        "worker_heartbeat_count": 2263,
        "worker_trip_count": 0,
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
    }, "worker_supervision_after")
    exact(value["final_state"], {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_generation": 8, "library_entries": 1,
        "library_persistent": True, "cleanup_complete": True,
        "input_queue_drops": 0, "radio_tx_commands": 0,
    }, "final_state")
    exact(value["scope"], {
        "manual_button_presses": 0, "host_wifi_control_calls": 0,
        "clone_touched": False, "cardputer_touched": False,
        "raw_wifi_identifiers_retained": False,
        "raw_ble_addresses_retained": False,
        "screenshots_retained": False,
        "full_hil_matrix": False, "delta_only": True,
    }, "scope")
    print(
        "Product Survey commit supervision passed: dev.299/dev.300 "
        "fail closed, exact dev.301 generations 6->7->8, worker trip 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
