#!/usr/bin/env python3
"""Validate the privacy-minimal dev.377 long-idle input observation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/board-01-long-idle-input-1.0.0-dev.377.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"long-idle input observation failed: {message}")


def git_blob(commit: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(completed.returncode == 0,
            f"missing source blob {commit}:{relative}")
    return completed.stdout


def object_at(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    require(isinstance(result, dict), f"missing object {key}")
    return result


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(evidence.get("schema") ==
            "leshy.long_idle_input.observation.v1", "schema mismatch")
    require(evidence.get("status") ==
            "diagnostic_observation_not_acceptance", "status mismatch")

    candidate = object_at(evidence, "candidate")
    require(candidate == {
        "version": "1.0.0-dev.377",
        "firmware_source_commit":
            "53cc36c4a45fb72cabbf171b8fa828788d776025",
        "firmware_sha256":
            "ec140e78bac945e6d067dfb2ba2707722f13c86a6f32ce061e3bb4fe5507300a",
    }, "candidate mismatch")

    capture = object_at(evidence, "capture")
    tooling_commit = capture.get("tooling_commit")
    require(tooling_commit ==
            "0add687352cc38c845f5bfe9915abec3426f19b2",
            "tooling commit mismatch")
    tool_blob = git_blob(str(tooling_commit), "tools/capture_1x_input.py")
    require(hashlib.sha256(tool_blob).hexdigest() ==
            capture.get("capture_tool_sha256"),
            "capture tool is not source-bound")
    for key in ("read_only",):
        require(capture.get(key) is True, f"{key} not retained")
    for key in (
            "device_reset", "device_reflashed", "cardputer_connected_or_opened",
            "active_host_wifi_touched", "ambient_identifiers_retained",
            "raw_capture_retained"):
        require(capture.get(key) is False, f"{key} boundary mismatch")

    report = object_at(evidence, "operator_report")
    require(report.get("route_started_from_home_after_reboot_and_idle") is True and
            report.get("two_select_presses_were_perceived_as_required") is True and
            report.get("idle_duration_machine_measured") is False,
            "operator/machine provenance boundary mismatch")

    physical = object_at(evidence, "physical_input")
    require(physical.get("task_started") is True and
            physical.get("raw_transitions") ==
                physical.get("stable_transitions") == 8 and
            physical.get("press_events") ==
                physical.get("release_events") ==
                physical.get("dispatched_press_events") == 4 and
            physical.get("select_presses") == 2 and
            physical.get("read_errors") == 0 and
            physical.get("ambiguous_presses") == 0 and
            physical.get("queue_drops") == 0 and
            physical.get("queue_high_water") == 1 and
            physical.get("last_dispatched_action") == "select" and
            physical.get("last_dispatched_changed") is True and
            physical.get("hot_path_serial_writes") == 0,
            "physical-input accounting mismatch")

    touch = object_at(evidence, "touch_input")
    require(touch.get("status") == "ready" and
            touch.get("press_events") == touch.get("release_events") == 0 and
            touch.get("pressed") is False and
            touch.get("missed_presses") == 0 and
            touch.get("synthetic_presses") == 0,
            "touch-input accounting mismatch")

    final_ui = object_at(evidence, "final_ui")
    require(final_ui.get("page") == "survey" and
            final_ui.get("parent_page") == "home" and
            final_ui.get("selected_id") == "wifi" and
            final_ui.get("wifi_product_view") == "networks" and
            final_ui.get("runtime_owner") == "wifi" and
            final_ui.get("lease_mask") == 15 and
            final_ui.get("workflow_state") == "running" and
            int(final_ui.get("network_count", 0)) > 0 and
            int(final_ui.get("wifi_scan_cycles", 0)) > 0,
            "final UI mismatch")

    interpretation = object_at(evidence, "interpretation")
    require(interpretation.get("input_loss_observed") is False and
            interpretation.get("two_level_route_consistent_with_observation")
                is True and
            interpretation.get(
                "home_to_wifi_menu_then_networks_provenance_complete") is False,
            "diagnostic limitation changed")

    serialized = EVIDENCE.read_text(encoding="utf-8").lower()
    for forbidden in ("/dev/", "usbmodem", "\"ssid\"", "\"bssid\"", "mac:"):
        require(forbidden not in serialized,
                f"privacy-minimal observation contains {forbidden!r}")
    print(
        "long_idle_input_observation: PASS; no input loss is visible, the "
        "two-level route is consistent, and per-action page provenance is "
        "explicitly not claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
