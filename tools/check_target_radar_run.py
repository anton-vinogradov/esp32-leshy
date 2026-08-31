#!/usr/bin/env python3
"""Independent acceptance checker for a focused Targets Radar HIL run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    run_dir = args.run.resolve()
    run = load(run_dir / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.targets_radar_hil.run.v1",
            "wrong run schema")
    require(run.get("status") == "pass" and run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "run is not a clean pass")
    require(candidate.get("version") == args.expected_version and
            candidate.get("source_commit") == args.source_commit and
            run.get("expected_cid") == args.expected_cid,
            "candidate or CID binding mismatch")
    require(run.get("radio_tx_commands") == 0 and
            run.get("active_probe_commands") == 0 and
            run.get("ambient_frames_retained_by_firmware") is False,
            "passive/privacy contract mismatch")
    lifecycles = run.get("lifecycles", [])
    radios = [item.get("radio") for item in lifecycles]
    require(len(lifecycles) == 4 and
            radios.count("wifi") == radios.count("ble") == 2,
            "exactly two Wi-Fi and two BLE lifecycles required")
    for item in lifecycles:
        first = item["first"]
        second = item["second"]
        after = item["after"]
        pixels = item["pixel_changes"]
        require(int(second["samples"]) > int(first["samples"]),
                "signal samples did not advance")
        require(int(second["full_repaints"]) == int(first["full_repaints"]) and
                int(second["content_clears"]) == int(first["content_clears"]) and
                int(second["delta_repaints"]) > int(first["delta_repaints"]),
                "continuous screen update was not atomic")
        require(pixels["identity_changed_pixels"] == 0 and
                pixels["chrome_changed_pixels"] == 0 and
                pixels["live_changed_pixels"] > 0,
                "pixel changes escaped live region")
        require(item["selected_graph_fingerprint"] ==
                item["restored"]["selected_graph_fingerprint"],
                "selected Target graph changed")
        require(item.get("target_id_stable") is True and
                item.get("restore_match") in {"target_id", "radio_identity"} and
                item.get("source_lifecycle_proven") is True and
                item.get("live_match") is True,
                "identity, restore, source, or live-match proof missing")
        require(after.get("status") == "idle" and
                after.get("overlay_open") is False and
                after.get("task_active") is False and
                after.get("cleanup_complete") is True and
                after.get("blocked_write_attempts") == 0 and
                after.get("physical_write_calls") == 0 and
                int(item["heap_free_after"]) +
                    int(item.get("heap_tolerance", 512)) >=
                    int(item["heap_free_before"]),
                "cleanup/write/heap invariant mismatch")
    before = run["recovery_before"]
    after = run["recovery_after"]
    require(before["generation"] == after["generation"] and
            before["observations"] == after["observations"] and
            after["physical_write_calls"] == 0 and
            after["blocked_write_attempts"] == 0,
            "product media changed")
    require(run["input"]["read_errors"] == 0 and
            run["input"]["queue_drops"] == 0 and
            run["safe_outputs"]["buzzer_inactive"] is True and
            run["cleanup"]["complete"] is True and
            run["cleanup"]["final_state"].get("page") == "home" and
            run["cleanup"]["final_state"].get("runtime_owner") == "none" and
            run["cleanup"]["final_state"].get("lease_mask") == 0 and
            run["cleanup"]["final_state"].get(
                "survey_product_worker_ready") is True,
            "input/output/final cleanup mismatch")
    print("Targets Radar HIL run passed independent acceptance")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
