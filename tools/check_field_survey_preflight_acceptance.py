#!/usr/bin/env python3
"""Fail closed on the retained CAP-050 BLE-start regression checkpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-field-survey-preflight-1.0.0-dev.261.json"
)


def failures(record: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def exact(path: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            result.append(f"{path}: {actual!r} != {expected!r}")

    exact("schema", record.get("schema"),
          "leshy.field_survey_preflight.acceptance.v1")
    exact("status", record.get("status"),
          "pass_regression_not_capability_gate")
    exact("board", record.get("board"), "board-01")
    exact("cid", record.get("cid"),
          "FE343253440000002000000055019CB7")

    scope = record.get("scope", {})
    exact("scope.mode", scope.get("mode"), "preflight")
    exact("scope.receive_only", scope.get("receive_only"), True)
    exact("scope.first_visit_committed",
          scope.get("first_visit_committed"), False)
    exact("scope.revisit_committed", scope.get("revisit_committed"), False)
    exact("scope.capability_gate_eligible",
          scope.get("capability_gate_eligible"), False)

    negative = record.get("negative", {})
    exact("negative.version", negative.get("version"), "1.0.0-dev.260")
    exact("negative.ble_begin_stage", negative.get("ble_begin_stage"),
          "host_sync")
    exact("negative.ble_begin_error", negative.get("ble_begin_error"), 263)
    exact("negative.scan_cycles", negative.get("scan_cycles"), 11)
    exact("negative.wifi_scan_cycles", negative.get("wifi_scan_cycles"), 11)
    exact("negative.ble_scan_cycles", negative.get("ble_scan_cycles"), 0)
    exact("negative.active_source_mask",
          negative.get("active_source_mask"), 1)
    exact("negative.unavailable_source_mask",
          negative.get("unavailable_source_mask"), 2)
    exact("negative.wifi_read", negative.get("wifi_read"), 81)
    exact("negative.wifi_accepted", negative.get("wifi_accepted"), 81)
    exact("negative.pipeline_received",
          negative.get("pipeline_received"), 81)
    exact("negative.pipeline_forwarded",
          negative.get("pipeline_forwarded"), 64)
    exact("negative.pipeline_dropped", negative.get("pipeline_dropped"), 17)
    exact("negative.writes_committed", negative.get("writes_committed"), 0)
    exact("negative.cleanup_complete", negative.get("cleanup_complete"), True)
    exact("negative.final_page", negative.get("final_page"), "home")
    exact("negative.final_owner", negative.get("final_owner"), "none")
    exact("negative.final_lease_mask", negative.get("final_lease_mask"), 0)

    positive = record.get("positive", {})
    exact("positive.version", positive.get("version"), "1.0.0-dev.261")
    exact("positive.source_commit", positive.get("source_commit"),
          "b38464f93cdb7807734a24b1e1a08f03d4bbae24")
    exact("positive.static_ram_bytes", positive.get("static_ram_bytes"),
          231624)
    exact("positive.static_ram_reclaimed_bytes",
          positive.get("static_ram_reclaimed_bytes"), 4560)
    if (negative.get("static_ram_bytes", 0) -
            positive.get("static_ram_bytes", 0) != 4560):
        result.append("static RAM delta does not equal reclaimed HIL capture")
    exact("positive.ble_begin_stage", positive.get("ble_begin_stage"),
          "ready")
    exact("positive.ble_begin_error", positive.get("ble_begin_error"), 0)
    exact("positive.scan_cycles", positive.get("scan_cycles"), 1)
    exact("positive.wifi_scan_cycles", positive.get("wifi_scan_cycles"), 1)
    exact("positive.ble_scan_cycles", positive.get("ble_scan_cycles"), 1)
    exact("positive.selected_source_mask",
          positive.get("selected_source_mask"), 3)
    exact("positive.active_source_mask",
          positive.get("active_source_mask"), 3)
    exact("positive.unavailable_source_mask",
          positive.get("unavailable_source_mask"), 0)
    if positive.get("ble_heap_free_before", 0) < 73000:
        result.append("positive BLE pre-start heap is below regression floor")
    if positive.get("ble_heap_largest_before", 0) < 28000:
        result.append("positive BLE pre-start largest block is below floor")
    for source in ("wifi", "ble"):
        reported = positive.get(f"{source}_reported")
        exact(f"positive.{source}_read", positive.get(f"{source}_read"),
              reported)
        exact(f"positive.{source}_accepted",
              positive.get(f"{source}_accepted"), reported)
        exact(f"positive.{source}_dropped",
              positive.get(f"{source}_dropped"), 0)
    exact("positive.pipeline_received", positive.get("pipeline_received"), 45)
    exact("positive.pipeline_forwarded", positive.get("pipeline_forwarded"),
          positive.get("pipeline_received"))
    exact("positive.pipeline_dropped", positive.get("pipeline_dropped"), 0)
    exact("positive.generation_after", positive.get("generation_after"),
          positive.get("generation_before"))
    exact("positive.writes_committed", positive.get("writes_committed"), 0)
    exact("positive.cleanup_complete", positive.get("cleanup_complete"), True)
    exact("positive.final_page", positive.get("final_page"), "home")
    exact("positive.final_owner", positive.get("final_owner"), "none")
    exact("positive.final_lease_mask", positive.get("final_lease_mask"), 0)
    exact("positive.final_safety_state",
          positive.get("final_safety_state"), "armed")
    exact("positive.hil_active_after", positive.get("hil_active_after"), False)

    for field in ("run_sha256", "firmware_sha256", "app_elf_sha256",
                  "map_sha256"):
        value = positive.get(field, "")
        if not isinstance(value, str) or len(value) != 64:
            result.append(f"positive.{field}: invalid SHA-256")
    if len(record.get("open_gates", [])) < 5:
        result.append("open CAP-050 gates are not retained")
    return result


def main() -> int:
    record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems = failures(record)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(
        "Field Survey preflight acceptance passed: dev.260 repeated-cycle failure "
        "retained, dev.261 BLE ready after one "
        "Wi-Fi+BLE pass with zero drops/writes and final Home/none/lease 0; "
        "full CAP-050 visit gate remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
