#!/usr/bin/env python3
"""Fail closed on incomplete IR Protocol Workbench physical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "leshy.protocol_workbench_hil.run.v1"
HEX64 = set("0123456789abcdef")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run_path = args.run.resolve()
    root = run_path.parent
    value: dict[str, Any] = json.loads(run_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    need(value.get("schema") == SCHEMA, "schema mismatch")
    need(value.get("status") == "pass" and value.get("passed") is True,
         "run did not pass")
    need(value.get("failures") == [], "run retained failures")
    need(value.get("exact_port") == "/dev/cu.usbmodem2101",
         "run is not bound to original board-01")
    policy = value.get("policy", {})
    need(policy.get("mac_wifi_controlled") is False, "Mac Wi-Fi was controlled")
    need(policy.get("clone_port_touched") is False, "clone port was touched")
    need(policy.get("radio_tx_commands") == 0, "radio TX was requested")
    need(policy.get("fixture_storage") == "bounded_ram",
         "fixture was not RAM-only")
    need(policy.get("product_storage_writes") == 0,
         "product storage write was requested")
    need(policy.get("annotation_task_flow") == "mark_range_and_meaning",
         "annotation task flow was not exercised")
    candidate = value.get("candidate", {})
    need(candidate.get("fresh_flash") is True, "candidate was not freshly flashed")
    for key in ("firmware_sha256", "app_elf_sha256"):
        item = candidate.get(key)
        need(isinstance(item, str) and len(item) == 64 and set(item) <= HEX64,
             f"candidate.{key} invalid")

    records = value.get("records", {})
    opened = records.get("opened", {})
    need(opened.get("status") == "opened" and
         opened.get("page") == "protocol_workbench" and
         opened.get("analysis_status") == "valid",
         "workbench did not open with valid analysis")
    need(opened.get("protocol") == "nec" and opened.get("pulses") == 67,
         "workbench did not analyze the retained NEC vector")
    need(opened.get("read_only") is True and
         opened.get("radio_touched") is False and
         opened.get("application_tx_calls") == 0 and
         opened.get("storage_mounted") is False and
         opened.get("storage_written") is False,
         "fixture crossed a receive-only/RAM-only boundary")
    fingerprint = opened.get("source_fingerprint")
    need(isinstance(fingerprint, str) and len(fingerprint) == 16,
         "source fingerprint invalid")
    need(isinstance(opened.get("base_unit_us"), int) and
         opened.get("base_unit_us") > 0 and
         opened.get("timing_bands", 0) >= 2,
         "timing analysis is not useful")

    for index, name in enumerate(("frame_0", "frame_1", "frame_2")):
        frame = records.get(name, {})
        need(frame.get("bytes") == 153600, f"{name} size invalid")
        sha = frame.get("sha256")
        path = root / "frames" / f"pulse-{index:02d}.rgb565"
        need(path.is_file(), f"{path.name} missing")
        if path.is_file():
            need(digest(path) == sha, f"{path.name} hash mismatch")
        need((root / "frames" / f"pulse-{index:02d}.png").is_file(),
             f"pulse-{index:02d}.png missing")
    for name in ("delta_0_1", "delta_1_2"):
        delta = records.get(name, {})
        need(isinstance(delta.get("changed_pixels"), int) and
             delta.get("changed_pixels") > 0, f"{name} changed nothing")
        need(delta.get("outside_allowed_regions") == 0,
             f"{name} repainted static pixels")
    need(records.get("state_1", {}).get("selected_pulse") == 1 and
         records.get("state_2", {}).get("selected_pulse") == 2,
         "pulse navigation sequence invalid")
    need(records.get("ui_1", {}).get("ui_full_repaints") ==
         records.get("ui_2", {}).get("ui_full_repaints"),
         "pulse navigation performed a full repaint")
    need(records.get("ui_2", {}).get("ui_delta_repaints", 0) >
         records.get("ui_1", {}).get("ui_delta_repaints", 0),
         "pulse navigation did not increment delta repaint count")

    annotation_frames = {
        "frame_actions": "annotation-actions",
        "frame_end_before": "annotation-end-before",
        "frame_end_after": "annotation-end-after",
        "frame_mark_result": "annotation-mark-result",
        "frame_marked_waveform": "annotation-marked-waveform",
    }
    for record_name, file_name in annotation_frames.items():
        frame = records.get(record_name, {})
        need(frame.get("bytes") == 153600, f"{record_name} size invalid")
        sha = frame.get("sha256")
        raw_path = root / "frames" / f"{file_name}.rgb565"
        need(raw_path.is_file(), f"{raw_path.name} missing")
        if raw_path.is_file():
            need(digest(raw_path) == sha, f"{raw_path.name} hash mismatch")
        need((root / "frames" / f"{file_name}.png").is_file(),
             f"{file_name}.png missing")
    need(records.get("state_actions", {}).get("annotation_view") == 1 and
         records.get("state_start", {}).get("annotation_view") == 2 and
         records.get("state_end", {}).get("annotation_view") == 3 and
         records.get("state_kind", {}).get("annotation_view") == 4 and
         records.get("state_mark", {}).get("annotation_view") == 5,
         "annotation task views were not traversed")
    marked = records.get("state_marked_waveform", {})
    need(marked.get("annotation_view") == 0 and
         marked.get("annotations") == 1 and
         marked.get("annotation_dirty") is True and
         marked.get("annotation_store_generation") == 0,
         "derived mark did not return to the waveform")
    annotation_delta = records.get("delta_annotation_end", {})
    need(isinstance(annotation_delta.get("changed_pixels"), int) and
         annotation_delta.get("changed_pixels") > 0,
         "annotation range move changed nothing")
    need(annotation_delta.get("outside_allowed_regions") == 0,
         "annotation range move repainted static pixels")
    need(records.get("ui_end", {}).get("ui_full_repaints") ==
         records.get("ui_end_move", {}).get("ui_full_repaints"),
         "annotation range move performed a full repaint")
    need(records.get("ui_end_move", {}).get("ui_delta_repaints", 0) >
         records.get("ui_end", {}).get("ui_delta_repaints", 0),
         "annotation range move did not increment delta repaint count")

    before = records.get("recovery_before", {})
    after = records.get("recovery_after", {})
    for key in ("generation", "observations", "expected_fingerprint",
                "observed_fingerprint"):
        need(before.get(key) == after.get(key),
             f"storage continuity changed: {key}")
    need(after.get("physical_write_calls") == 0 and
         after.get("mounted_read_only") is True and
         after.get("read_only_guaranteed") is True,
         "storage proof is not read-only")
    clear = records.get("clear", {})
    need(clear.get("status") == "cleared" and
         clear.get("fixture_active") is False and
         clear.get("page") == "home" and
         clear.get("runtime_owner") == "none" and
         clear.get("lease_mask") == 0 and
         clear.get("cleanup_complete") is True,
         "fixture cleanup did not reach Home/lease 0")
    need(len(value.get("hil_sessions", [])) == 2 and
         value["hil_sessions"][0].get("status") == "begun" and
         value["hil_sessions"][1].get("status") == "ended",
         "HIL session lifecycle incomplete")
    for name in ("firmware.bin", "firmware.elf", "firmware.map",
                 "artifacts.sha256"):
        need((root / name).is_file(), f"artifact missing: {name}")

    if failures:
        print(json.dumps({"passed": False, "failures": failures}, sort_keys=True))
        return 1
    print("Protocol Workbench HIL accepted: exact TFT dirty regions, RAM-only NEC analysis, zero TX/writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
