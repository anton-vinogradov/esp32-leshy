#!/usr/bin/env python3
"""Independently validate retained Wi-Fi UI frames and emit a private-safe digest."""
import argparse
import hashlib
import json
from pathlib import Path
from esp_app_identity import app_elf_sha256

PAGES = {"summary", "radar", "actions", "information", "identity",
         "protection", "radio", "observed"}
MENU_STATES = {
    "entry": ("menu", "root", 0), "root_last": ("menu", "root", 3),
    "observe_entry": ("menu", "observe", 3), "observe_first": ("menu", "observe", 3),
    "visit": ("visit", "observe", 3), "visit_back": ("menu", "observe", 3),
    "guard": ("airspace_guard_profile", "observe", 0),
    "guard_back": ("menu", "observe", 4), "root_back": ("menu", "root", 3),
    "reentry": ("menu", "root", 0),
}


def check(run, frames):
    failures = []

    def need(ok, message):
        if not ok:
            failures.append(message)

    need(run.get("schema") == "leshy.wifi_ui_delta.v1", "run schema")
    need(run.get("status") == "passed" and run.get("failures") == [], "runner outcome")
    need(run.get("cleanup_complete") is True, "cleanup")
    scope = run.get("slice", "card")
    need(scope in ("card", "menu"), "known UI slice")
    required_screens = ({"root-observe-selected", "observe-menu", "visit-setup",
                         "guard-profile", "root-menu"} if scope == "menu" else
                        {"before-password-steps", "password-steps", "password-steps-stable"})
    need(required_screens <= set(run.get("screens", {})), "required screen hashes")
    if scope == "card":
        need(set(run.get("pages", {})) == PAGES, "eight navigation pages")
    for page, state in run.get("pages", {}).items():
        need(state.get("ui_page") == page, "page identity")
    for name, record in run.get("screens", {}).items():
        for ext, field in (("png", "png_sha256"), ("rgb565", "rgb565_sha256")):
            file = frames / f"{name}.{ext}"
            need(file.is_file() and
                 hashlib.sha256(file.read_bytes()).hexdigest() == record.get(field),
                 f"{name}: {field}")
    if scope == "card":
        raw = []
        for name in ("before-password-steps", "password-steps", "password-steps-stable"):
            file = frames / f"{name}.rgb565"
            data = file.read_bytes() if file.is_file() else b""
            need(len(data) == 240 * 320 * 2, f"{name}: complete TFT")
            raw.append(data)
        need(bool(raw[0]) and raw[0] != raw[1], "preflight must replace actions pixels")
        need(bool(raw[1]) and raw[1] == raw[2], "preflight stable after non-start key")
        need(run.get("channels", {}).get("wifi_channel_measured_mask") == 8191,
             "13 measured channels")
        need(run.get("channel_pixels", {}).get("static_changed_pixels") == 0,
             "channel chrome immutable")
    elif scope == "menu":
        for name, expected in MENU_STATES.items():
            state = run.get("menu_states", {}).get(name, {})
            actual = tuple(state.get(k) for k in (
                "wifi_product_view", "wifi_product_menu_section", "wifi_product_selection"))
            need(actual == expected, f"menu route {name}")
        for name in ("root-observe-selected", "observe-menu", "visit-setup",
                     "guard-profile", "root-menu"):
            file = frames / f"{name}.rgb565"
            need(file.is_file() and file.stat().st_size == 240 * 320 * 2,
                 f"{name}: complete TFT")
        images = run.get("screens", {})
        need(images.get("root-observe-selected", {}).get("rgb565_sha256") !=
             images.get("observe-menu", {}).get("rgb565_sha256"), "menu scene repainted")
    final = run.get("final", {})
    for k, value in {"page": "home", "runtime_owner": "none", "lease_mask": 0,
                     "survey_scan_dropped": 0, "survey_dropped": 0,
                     "survey_timeline_overflow": 0,
                     "survey_product_store_bytes_written": 0,
                     "survey_product_filesystem_mount_attempts": 0}.items():
        need(final.get(k) == value, f"final {k}")
    return failures


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    data = args.run.read_bytes()
    run = json.loads(data)
    failures = check(run, args.run.parent / "frames")
    image = args.run.parent / "firmware.bin"
    if not image.is_file() or hashlib.sha256(image.read_bytes()).hexdigest() != run.get("firmware_sha256"):
        failures.append("exact retained firmware")
    elif app_elf_sha256(image) != run.get("app_elf_sha256"):
        failures.append("exact embedded application identity")
    # Public output deliberately excludes SSIDs, BSSIDs, raw frames, paths and USB identity.
    summary = {
        "schema": "leshy.wifi_ui_delta.acceptance.v1",
        "status": "passed" if not failures else "failed",
        "version": run.get("expected_version"),
        "slice": run.get("slice", "card"),
        "run_sha256": hashlib.sha256(data).hexdigest(),
        "app_sha256": run.get("firmware_sha256"),
        "app_elf_sha256": run.get("app_elf_sha256"),
        "pages": sorted(run.get("pages", {})),
        "frames_count": len(run.get("screens", {})),
        "channel_pixels": run.get("channel_pixels"),
        "channels": run.get("channels"),
        "menu_states": run.get("menu_states"),
        "final": run.get("final"),
        "heap_final": run.get("heap_final"),
        "failures": failures,
        "scope": "board-03 RX-only keys and synthetic touch through product dispatch; no password recording",
        "limits": "Not physical finger/optical flicker acceptance, hidden-name fixture, full matrix or endurance.",
    }
    if args.summary:
        if args.summary.exists():
            parser.error("refusing to overwrite retained evidence")
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
