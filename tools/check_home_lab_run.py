#!/usr/bin/env python3
"""Independently check the focused Home -> Lab -> Home physical delta."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from check_visual_system_acceptance import decode_png


RUN_SCHEMA = "leshy.top_level_menu_smoke_hil.run.v1"
UI_SCHEMA = "leshy.ui.v1"
DANGER_RGB = (247, 93, 90)
FOCUS_RGB = (247, 199, 66)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def analyze(run_dir: Path, home_png: Path, home_trace: Path, *,
            version: str, cid: str, source_commit: str) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    run = load(run_path)
    trace = load(home_trace)
    candidate = run.get("candidate", {})
    require(run.get("schema") == RUN_SCHEMA and run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "focused menu run did not pass")
    require(candidate.get("version") == version and
            candidate.get("source_commit") == source_commit and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("verified") is True and
            run.get("expected_cid") == cid,
            "candidate identity or exact-CID binding mismatch")
    menus = run.get("menus", [])
    require(len(menus) == 1 and menus[0].get("id") == "lab" and
            menus[0].get("index") == 7 and menus[0].get("passed") is True and
            menus[0].get("failures") == [],
            "exact Lab-only delta missing")
    menu = menus[0]
    focus = menu.get("home_focus", {})
    require(focus.get("page") == "home" and
            focus.get("selected_id") == "lab" and
            focus.get("runtime_owner") == "none" and
            focus.get("lease_mask") == 0,
            "direct Lab Home focus is not clean")
    samples = menu.get("dwell_samples", [])
    require(len(samples) >= 2 and all(
        sample.get("page") == "lab" and
        sample.get("selected_id") == "lab" and
        sample.get("runtime_owner") == "lab" and
        sample.get("lease_mask") == 1
        for sample in samples), "Lab did not remain stable during dwell")
    settled = menu.get("home_settled", {})
    require(settled.get("page") == "home" and
            settled.get("selected_id") == "lab" and
            settled.get("runtime_owner") == "none" and
            settled.get("lease_mask") == 0,
            "Lab return did not restore clean Home")
    require(run.get("catalog_boundary") == {
        "checked": False, "reason": "delta_subset"},
        "delta run incorrectly claims the full catalog")
    safe = run.get("safe_outputs", {})
    inputs = run.get("input", {})
    require(safe.get("buzzer_inactive") is True and
            safe.get("nrf_ce_inactive") is True and
            safe.get("software_quiesce_complete") is True and
            inputs.get("status") == "ready" and
            inputs.get("read_errors") == 0 and
            inputs.get("queue_drops") == 0,
            "safe-output or input contract failed")
    final = run.get("post_hil_end", {})
    require(final.get("hil", {}).get("active") is False and
            final.get("ui", {}).get("page") == "home" and
            final.get("ui", {}).get("runtime_owner") == "none" and
            final.get("ui", {}).get("lease_mask") == 0,
            "terminal HIL/Home cleanup failed")

    require(trace.get("schema") == "leshy.ui.hil.v1" and
            trace.get("actions") == [] and
            trace.get("png_sha256") == digest(home_png),
            "Home capture binding mismatch")
    home = trace.get("post_capture_state", {})
    require(home.get("schema") == UI_SCHEMA and home.get("page") == "home" and
            home.get("selected_id") == "lab" and home.get("selection") == 7 and
            home.get("runtime_owner") == "none" and home.get("lease_mask") == 0,
            "captured Home is not focused on direct Lab")
    width, height, rows = decode_png(home_png)
    pixels = [pixel for row in rows for pixel in row]
    danger_pixels = pixels.count(DANGER_RGB)
    focus_pixels = pixels.count(FOCUS_RGB)
    require((width, height) == (240, 320) and danger_pixels >= 1000 and
            focus_pixels >= 400,
            "real-TFT Home lacks independent danger text and focus treatment")
    return {
        "run_sha256": digest(run_path),
        "firmware_sha256": candidate.get("firmware_sha256"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "lab_dwell_samples": len(samples),
        "danger_pixels": danger_pixels,
        "focus_pixels": focus_pixels,
        "home_png_sha256": digest(home_png),
        "home_trace_sha256": digest(home_trace),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--home-png", required=True, type=Path)
    parser.add_argument("--home-trace", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = analyze(args.run, args.home_png, args.home_trace,
                     version=args.expected_version, cid=args.expected_cid,
                     source_commit=args.source_commit)
    print(json.dumps({"status": "pass", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
