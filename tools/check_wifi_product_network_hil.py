#!/usr/bin/env python3
"""Check ordinary two-DIV Wi-Fi evidence and export no ambient identities."""
import argparse
import hashlib
import json
from pathlib import Path
from esp_app_identity import app_elf_sha256
from run_wifi_product_network_hil import bssid_hash, countdown_diff

SCREENS = {"source-ready", "source-running", "source-running-later", "hidden",
           "hidden_no_name", "resolved", "retained", "source-deadline"}
FINAL = {"page": "home", "runtime_owner": "none", "lease_mask": 0,
         "safety_latched": False, "safety_state": "armed",
         "survey_scan_dropped": 0, "survey_dropped": 0,
         "survey_timeline_overflow": 0, "survey_product_store_bytes_written": 0,
         "survey_product_filesystem_mount_attempts": 0}


def check(run, folder):
    failures = []
    def need(ok, label):
        if not ok: failures.append(label)
    need(run.get("schema") == "leshy.wifi_product_network.run.v1", "schema")
    need(run.get("status") == "pass" and run.get("failures") == [], "runner result")
    boards = run.get("board_identities", {})
    need(set(boards) == {"source", "receiver"} and len(set(boards.values())) == 2,
         "two distinct physical identities")
    need(all(len(v) == 64 and set(v) <= set("0123456789abcdef") for v in boards.values()),
         "physical identity digests")
    image = folder / "firmware.bin"
    try:
        need(hashlib.sha256(image.read_bytes()).hexdigest() == run.get("image_sha256"), "image digest")
        need(app_elf_sha256(image) == run.get("app_elf_sha256"), "embedded app identity")
    except (OSError, ValueError):
        need(False, "retained application")
    for role in ("source", "receiver"):
        for suffix in ("_boot", "_final_boot"):
            need(run.get(role + suffix, {}).get("app_elf_sha256") == run.get("app_elf_sha256"),
                 role + suffix + " exact app")
        cleanup = run.get("cleanup", {}).get(role, {})
        need(cleanup.get("complete") is True, role + " cleanup")
        final = cleanup.get("final_state", {})
        for k, v in FINAL.items(): need(final.get(k) == v, role + " final " + k)
    states = run.get("states", {})
    for name, expected in {
        "menu_off": {"active": False, "radio_started": False, "cleanup_complete": True, "lease_mask": 1},
        "started": {"active": True, "radio_started": True, "hidden": True, "lease_mask": 3, "power_quarter_dbm": 8, "error": 0},
        "visible_source": {"active": True, "radio_started": True, "hidden": False, "lease_mask": 3},
        "user_stop": {"active": False, "radio_started": False, "cleanup_complete": True, "stop_reason": 1, "lease_mask": 1},
        "deadline_start": {"active": True, "radio_started": True, "lease_mask": 3, "power_quarter_dbm": 8, "error": 0},
        "deadline": {"active": False, "radio_started": False, "cleanup_complete": True, "stop_reason": 2, "lease_mask": 1},
    }.items():
        state = states.get(name, {})
        for k, v in expected.items(): need(state.get(k) == v, name + " " + k)
        need(state.get("limit_ms") == 60000 and state.get("channel") == 6, name + " bounds")
    started, visible = states.get("started", {}), states.get("visible_source", {})
    try:
        mac = started["bssid"]
        need(len(mac) == 12 and int(mac, 16) != 0, "AP BSSID")
        identity = bssid_hash(mac)
        need(started.get("ssid") == "LESHY-TEST-" + mac[-4:].upper(), "own SSID")
        need(visible.get("bssid") == mac and visible.get("ssid") == started.get("ssid"), "visibility continuity")
        need(0 < visible.get("remaining_s", 0) < started.get("remaining_s", 0) <= 60, "no visibility renewal")
    except (KeyError, ValueError):
        identity = None
        need(False, "AP identity")
    samples = []
    for name, known in (("hidden", False), ("hidden_no_name", False), ("resolved", True), ("retained", True)):
        state = states.get(name, {})
        need(state.get("identity_hash") == identity and identity is not None, name + " identity")
        for k, v in {"active": True, "passive": True, "active_probe_allowed": False,
                     "ssid_known": known, "channel": 6, "authentication": "WPA2-PSK"}.items():
            need(state.get(k) == v, name + " " + k)
        samples.append(state.get("signal_samples", 0))
        for k in ("list_content_clears", "list_slot_clears", "live_list_direct_fallbacks",
                  "live_list_row_allocation_failures"):
            need(state.get(k) == 0, name + " " + k)
    need(0 < samples[0] < samples[1] < samples[2] < samples[3], "fresh radio observations")
    need(states.get("resolved", {}).get("hidden_resolutions", 0) >
         states.get("hidden", {}).get("hidden_resolutions", 0), "name resolution event")
    need(59 <= run.get("deadline_observed_s", 0) <= 63, "independent deadline timing")
    screens = run.get("screens", {})
    need(SCREENS <= set(screens), "required TFT screens")
    for name in SCREENS:
        record = screens.get(name, {})
        for ext, key in (("png", "png_sha256"), ("rgb565", "rgb565_sha256")):
            path = folder / "frames" / (name + "." + ext)
            need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record.get(key), name + " " + ext)
            if ext == "rgb565":
                need(path.is_file() and path.stat().st_size == 153600, name + " complete TFT")
        begin, end = record.get("frame_begin", {}), record.get("frame_end", {})
        need(begin.get("width") == 240 and begin.get("height") == 320 and
             begin.get("format") == "rgb565be" and begin.get("bytes") == end.get("bytes") == 153600 and
             begin.get("revision") == end.get("revision") == record.get("state", {}).get("revision"), name + " frame continuity")
    for name in ("source-ready", "source-running", "source-running-later", "source-deadline"):
        state = screens.get(name, {}).get("state", {})
        need(state.get("self_test_view") == "wifi_network" and
             state.get("self_test_read_only") is False and state.get("self_test_status") == "not_run",
             name + " honest tool status")
    try:
        pixels = countdown_diff((folder / "frames/source-running.rgb565").read_bytes(),
                                (folder / "frames/source-running-later.rgb565").read_bytes())
        need(pixels == run.get("countdown_pixels") and pixels["static_pixels"] == 0 and
             pixels["dynamic_pixels"] > 0, "countdown final-pixel delta")
    except (OSError, RuntimeError):
        need(False, "complete countdown pixels")
    if run.get('credential_display_requested'):
        try:
            def region(name):
                raw = (folder / 'frames' / (name + '.rgb565')).read_bytes()
                return raw[74 * 240 * 2:93 * 240 * 2]
            idle, active, ended = (region(name) for name in ('source-ready', 'source-running', 'source-deadline'))
            need(len(idle) == len(active) == len(ended) == 19 * 240 * 2 and
                 idle != active and idle == ended, 'ephemeral credential TFT region')
            need(run.get('credential_pixels') == {'shown_region_changed': True, 'inactive_region_restored': True},
                 'credential pixel report')
        except OSError: need(False, 'credential TFT unavailable')
    return failures


def summary(run, raw, failures):
    return {"schema": "leshy.wifi_product_network.acceptance.v1",
            "status": "passed" if not failures else "failed", "failures": failures,
            "app_elf_sha256": run.get("app_elf_sha256"), "image_sha256": run.get("image_sha256"),
            "version": run.get("source_boot", {}).get("version"),
            "source_commit": run.get("source_commit"), "run_sha256": hashlib.sha256(raw).hexdigest(),
            "boards": 2, "ordinary_product_ui_only": True,
            "name_states": {k: {field: run["states"][k][field] for field in
                ("ssid_known", "signal_samples", "hidden_resolutions")}
                for k in ("hidden", "hidden_no_name", "resolved", "retained")},
            "deadline_observed_s": run.get("deadline_observed_s"),
            "countdown_pixels": run.get("countdown_pixels"),
            "credential_pixels": run.get("credential_pixels"),
            "final": {role: {k: run["cleanup"][role]["final_state"].get(k) for k in FINAL}
                      for role in ("source", "receiver")},
            "heap": {role: {k: run[role + "_final_boot"].get(k) for k in
                     ("heap_total", "heap_free", "heap_min_free")} for role in ("source", "receiver")},
            "screens": {name: {k: run["screens"][name][k] for k in
                        ("png_sha256", "rgb565_sha256")} for name in sorted(SCREENS)},
            "limits": "AP hidden-visible-hidden discovery only, not client-frame name enrichment. No physical BOOT/lock-fault injection, association/internet, optical flicker, heap-invariance, endurance or broad-matrix acceptance. Startup-power interval uses PHY default."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    raw = args.run.read_bytes()
    run = json.loads(raw)
    failures = check(run, args.run.parent)
    if failures:
        print(json.dumps({"status": "failed", "failures": failures}))
        raise SystemExit(1)
    if args.summary:
        with args.summary.open("x") as output:
            output.write(json.dumps(summary(run, raw, failures), indent=2) + "\n")
    print("ordinary two-DIV Wi-Fi evidence verified; private identities excluded")
