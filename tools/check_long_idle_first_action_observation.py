#!/usr/bin/env python3
"""Validate the privacy-minimal dev.378 long-idle first-action snapshot."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-long-idle-first-action-1.0.0-dev.378.json")
CAPTURE_TOOL = ROOT / "tools/snapshot_1x_long_idle_action.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"long-idle first-action observation failed: {message}")


def object_at(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    require(isinstance(result, dict), f"missing object {key}")
    return result


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
            "leshy.long_idle_first_action.observation.v1", "schema mismatch")
    require(evidence.get("status") == "pass_physical_key_observation",
            "status mismatch")

    candidate = object_at(evidence, "candidate")
    require(candidate == {
        "version": "1.0.0-dev.378",
        "firmware_source_commit":
            "c4293a4adaabb1c46ca3cc66f84805dd2938a8d3",
        "app_elf_sha256":
            "709c213c5a9f6ef989dd9f38bb7db0f707bfd09093ff87f3230c98cd50ce8a86",
        "firmware_sha256":
            "8c1c0bd62aa4b6807b78153afb6493f6c8e258e4754970467738a23dd85a4e83",
        "factory_sha256":
            "ac69d0ea1ba383f60048d1e9147f4ff5b50a7139060a684ab2492e9cee701c08",
        "elf_file_sha256":
            "709c213c5a9f6ef989dd9f38bb7db0f707bfd09093ff87f3230c98cd50ce8a86",
    }, "candidate mismatch")
    source = str(candidate["firmware_source_commit"])
    ini = git_blob(source, "firmware/leshy1/platformio.ini")
    touch_header = git_blob(
        source, "firmware/leshy1/src/platform/arduino/BoardTouchInput.h")
    touch_source = git_blob(
        source, "firmware/leshy1/src/platform/arduino/BoardTouchInput.cpp")
    require(b'LESHY1_VERSION=\\"1.0.0-dev.378\\"' in ini,
            "source version mismatch")
    require(b"kCandidatePressureThreshold = 20" in touch_header and
            b"kPressureThreshold = 80" in touch_header and
            b"getTouchRawZ() > kCandidatePressureThreshold" in touch_source,
            "source touch thresholds are not bound")

    capture = object_at(evidence, "capture")
    require(hashlib.sha256(CAPTURE_TOOL.read_bytes()).hexdigest() ==
            capture.get("capture_tool_sha256"), "capture tool hash mismatch")
    require(capture.get("read_only") is True, "capture was not read-only")
    for key in (
            "device_reset", "device_reflashed", "cardputer_connected_or_opened",
            "active_host_wifi_touched", "ambient_identifiers_retained",
            "raw_capture_retained"):
        require(capture.get(key) is False, f"capture boundary mismatch: {key}")

    report = object_at(evidence, "operator_report")
    require(report.get("operator_confirmed_fixed") is True and
            report.get("screen_touch_claimed") is False,
            "operator/machine provenance boundary mismatch")

    physical = object_at(evidence, "physical_input")
    require(physical.get("status") == "ready" and
            physical.get("task_started") is True and
            physical.get("poll_period_ms") == 5 and
            physical.get("maximum_sample_gap_ms") == 5 and
            physical.get("valid_samples") == 8_510_301 and
            physical.get("minimum_sample_coverage_ms") == 42_551_505 and
            physical.get("raw_transitions") ==
                physical.get("stable_transitions") == 2 and
            physical.get("press_events") ==
                physical.get("release_events") ==
                physical.get("dispatched_press_events") == 1 and
            physical.get("select_presses") == 1 and
            physical.get("last_dispatched_action") == "select" and
            physical.get("last_dispatched_changed") is True and
            physical.get("read_errors") == 0 and
            physical.get("ambiguous_presses") == 0 and
            physical.get("queue_drops") == 0 and
            physical.get("hot_path_serial_writes") == 0,
            "physical first-action accounting mismatch")

    touch = object_at(evidence, "touch_input")
    require(touch.get("status") == "ready" and
            touch.get("candidate_pressure_threshold") == 20 and
            touch.get("pressure_threshold") == 80 and
            touch.get("press_events") == touch.get("release_events") ==
                touch.get("handled_presses") == 0 and
            touch.get("synthetic_presses") == 0,
            "touch provenance boundary mismatch")

    final_state = object_at(evidence, "final_state")
    safety = object_at(final_state, "safety")
    ui = object_at(final_state, "ui")
    require(safety.get("state") == "armed" and
            safety.get("reason") == "none" and
            safety.get("latched") is False and
            safety.get("runtime_owner") == "none" and
            safety.get("lease_mask") == 0 and
            ui.get("page") == "home" and
            ui.get("runtime_owner") == "none" and
            ui.get("lease_mask") == 0,
            "final cleanup mismatch")

    interpretation = object_at(evidence, "interpretation")
    require(interpretation.get("physical_first_action_observed") is True and
            interpretation.get("physical_first_action_changed_ui") is True and
            interpretation.get("input_loss_observed") is False and
            interpretation.get("touch_fix_physical_acceptance") is False,
            "interpretation boundary changed")

    serialized = EVIDENCE.read_text(encoding="utf-8").lower()
    for forbidden in ("/dev/", "usbmodem", '"ssid"', '"bssid"', "mac:"):
        require(forbidden not in serialized,
                f"privacy-minimal evidence contains {forbidden!r}")
    print(
        "long_idle_first_action_observation: PASS; one physical Select after "
        "42,551,505 ms minimum sample coverage changed UI with zero input "
        "loss; physical touch acceptance remains explicitly open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
