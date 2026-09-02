#!/usr/bin/env python3
"""Independent fail-closed verifier for a Wi-Fi networks HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.wifi_networks_hil.run.v1"
SCREENS = {
    "wifi_menu": "wifi-menu",
    "wifi_menu_after": "wifi-menu-after",
    "wifi_networks_first": "wifi-networks-first",
    "wifi_networks_second": "wifi-networks-second",
    "wifi_network_detail_first": "wifi-network-detail-first",
    "wifi_network_detail_second": "wifi-network-detail-second",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def verify_manifest(failures: list[str], root: Path) -> None:
    manifest = root / "artifacts.sha256"
    require(failures, manifest.is_file(), "artifacts.sha256 missing")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"invalid manifest line: {line!r}")
            continue
        expected, relative = parts
        target = root / relative
        indexed.add(relative)
        require(failures, target.is_file(), f"indexed artifact missing: {relative}")
        if target.is_file():
            require(failures, digest(target) == expected,
                    f"artifact hash mismatch: {relative}")
    actual = {
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, indexed == actual,
            f"manifest coverage differs: missing={sorted(actual-indexed)}, "
            f"extra={sorted(indexed-actual)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    failures: list[str] = []
    run_file = root / "run.json"
    require(failures, run_file.is_file(), "run.json missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    run: dict[str, Any] = json.loads(run_file.read_text(encoding="utf-8"))
    require(failures, run.get("schema") == SCHEMA, "run schema mismatch")
    require(failures, run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "run is not a clean pass")
    candidate = run.get("candidate", {})
    firmware = root / "firmware.bin"
    require(failures, candidate.get("version") == args.expected_version,
            "candidate version mismatch")
    require(failures, candidate.get("source_commit") == args.source_commit,
            "candidate source commit mismatch")
    require(failures, candidate.get("flashed") is True and
            candidate.get("flash_mode") in ("fresh", "reuse_exact"),
            "physical exact-flash binding missing")
    require(failures, run.get("expected_cid") == args.expected_cid,
            "CID mismatch")
    require(failures, firmware.is_file(), "retained candidate missing")
    if firmware.is_file():
        require(failures, candidate.get("firmware_sha256") == digest(firmware),
                "firmware hash mismatch")
        require(failures,
                candidate.get("app_elf_sha256") == app_elf_sha256(firmware),
                "embedded app identity mismatch")

    first = run.get("live_first", {})
    second = run.get("live_second", {})
    require(failures,
            first.get("wifi_product_view") == "networks" and
            first.get("survey_product_status") == "running" and
            first.get("survey_product_active_source_mask") == 1 and
            first.get("wifi_networks_strongest_first") is True and
            isinstance(first.get("wifi_networks_unique"), int) and
            first.get("wifi_networks_unique", 0) >= 2 and
            first.get("survey_scan_status") == "valid" and
            first.get("survey_scan_accepted") == first.get("survey_scan_read") and
            first.get("survey_scan_dropped") == 0 and
            first.get("survey_dropped") == 0 and
            first.get("survey_product_store_open_attempted") is False and
            first.get("survey_product_store_bytes_written") == 0,
            "first live Wi-Fi scan mismatch")
    require(failures,
            isinstance(second.get("survey_product_wifi_scan_cycles"), int) and
            second.get("wifi_networks_strongest_first") is True and
            second.get("survey_product_wifi_scan_cycles", 0) >
                first.get("survey_product_wifi_scan_cycles", 0) and
            second.get("wifi_network_catalog_revision", 0) >
                first.get("wifi_network_catalog_revision", 0),
            "live catalog did not advance")
    require(failures, run.get("list_pixel_changes", {}).get(
                "content_changed_pixels", 0) > 0 and
            run.get("list_pixel_changes", {}).get(
                "chrome_changed_pixels") == 0,
            "live redraw escaped the data region")
    scope = run.get("scope", {})
    focus_frames = run.get("list_focus_frames", {})
    require(failures,
            focus_frames.get("first", {}).get("continuous") is True and
            focus_frames.get("first", {}).get("background_distinct") is True and
            focus_frames.get("first", {}).get("mismatches") == [] and
            focus_frames.get("second", {}).get("continuous") is True and
            focus_frames.get("second", {}).get("background_distinct") is True and
            focus_frames.get("second", {}).get("mismatches") == [] and
            scope.get("selected_focus_frame_continuous") is True,
            "selected live-list focus frame is incomplete")
    intelligence = scope.get("network_intelligence") is True
    live_radar = scope.get("network_live_radar") is True
    if intelligence:
        facts_first = run.get("detail_facts_first", {})
        facts_second = run.get("detail_facts_second", {})
        if live_radar:
            require(failures,
                    run.get("detail_pixel_changes", {}).get(
                        "content_changed_pixels", 0) > 0 and
                    run.get("detail_pixel_changes", {}).get(
                        "chrome_changed_pixels") == 0 and
                    run.get("detail_outside_radar_pixels") == 0,
                    "network radar redraw escaped its bounded card")
            for name, facts in (("first", facts_first),
                                ("second", facts_second)):
                require(failures,
                        isinstance(facts.get("signal_samples"), int) and
                        isinstance(facts.get("minimum_rssi_dbm"), int) and
                        isinstance(facts.get("maximum_rssi_dbm"), int) and
                        isinstance(facts.get("rssi_trend_db"), int) and
                        facts.get("minimum_rssi_dbm", 1) <=
                            facts.get("rssi_dbm", 0) <=
                            facts.get("maximum_rssi_dbm", -1),
                        f"{name} network radar telemetry is invalid")
            require(failures,
                    facts_second.get("signal_samples", 0) >
                        facts_first.get("signal_samples", 0) and
                    facts_second.get("minimum_rssi_dbm", 0) <=
                        facts_first.get("minimum_rssi_dbm", 0) and
                    facts_second.get("maximum_rssi_dbm", 0) >=
                        facts_first.get("maximum_rssi_dbm", 0) and
                    (any(facts_second.get(field) != facts_first.get(field)
                         for field in (
                            "rssi_dbm", "minimum_rssi_dbm",
                            "maximum_rssi_dbm")) or
                     (1 if facts_second.get("rssi_trend_db", 0) >= 4 else
                      (-1 if facts_second.get("rssi_trend_db", 0) <= -4
                       else 0)) !=
                     (1 if facts_first.get("rssi_trend_db", 0) >= 4 else
                      (-1 if facts_first.get("rssi_trend_db", 0) <= -4
                       else 0))),
                    "network radar did not advance on a physical sample")
        else:
            require(failures,
                    run.get("detail_pixel_changes", {}).get(
                        "chrome_changed_pixels") == 0 and
                    run.get("detail_outside_signal_pixels") == 0,
                    "network passport redraw escaped the live RSSI line")
        require(failures,
                facts_first.get("active") is True and
                facts_first.get("passive") is True and
                facts_first.get("active_probe_allowed") is False and
                facts_first.get("ssid_known") is True and
                facts_first.get("vendor_known") is True and
                bool(facts_first.get("vendor")) and
                facts_first.get("facts_known") is True and
                facts_first.get("authentication") != "UNKNOWN" and
                facts_first.get("channel_width") != "WIDTH ?" and
                isinstance(facts_first.get("phy_mask"), int) and
                facts_first.get("phy_mask", 0) != 0 and
                isinstance(facts_first.get("identity_hash"), int) and
                facts_first.get("identity_hash", 0) != 0,
                "physical network intelligence passport is incomplete")
        for field in (
                "identity_hash", "vendor", "authentication",
                "pairwise_cipher", "group_cipher", "channel_width",
                "phy_mask", "channel", "frequency_khz"):
            require(failures, facts_second.get(field) == facts_first.get(field),
                    f"network passport changed identity/fact: {field}")
    else:
        require(failures, run.get("detail_pixel_changes") == {
                    "content_changed_pixels": 0, "chrome_changed_pixels": 0},
                "network detail changed during background scan")

    navigation_first = run.get("navigation_first", {})
    navigation_second = run.get("navigation_second", {})
    require(failures,
            navigation_first.get("wifi_product_view") == "networks" and
            navigation_first.get("wifi_network_focus_user_owned") is True and
            navigation_first.get("wifi_network_navigation_locked") is False and
            navigation_first.get("wifi_networks_strongest_first") is True and
            navigation_first.get("wifi_network_selection", 0) > 0 and
            isinstance(navigation_first.get(
                "wifi_network_selected_identity_hash"), int) and
            navigation_first.get("wifi_network_selected_identity_hash", 0) != 0,
            "user-owned live navigation was not established")
    require(failures,
            navigation_second.get("wifi_network_focus_user_owned") is True and
            navigation_second.get("wifi_network_navigation_locked") is False and
            navigation_second.get("wifi_networks_strongest_first") is True and
            navigation_second.get("survey_product_wifi_scan_cycles", 0) >=
                navigation_first.get("survey_product_wifi_scan_cycles", 0) + 2 and
            navigation_second.get("wifi_network_catalog_revision", 0) >
                navigation_first.get("wifi_network_catalog_revision", 0) and
            navigation_second.get("wifi_network_selection", 0) > 0 and
            navigation_second.get("wifi_network_selection", 0) <
                navigation_second.get("wifi_network_visible_size", 0) and
            navigation_second.get("wifi_network_selected_identity_hash") ==
                navigation_first.get("wifi_network_selected_identity_hash"),
            "selected identity did not survive strongest-first live scans")

    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    warmup = scope.get("bounded_one_time_heap_warmup_bytes")
    require(failures, isinstance(warmup, int) and 0 <= warmup <= 2048,
            "bounded Wi-Fi heap warm-up proof missing")
    require(failures, first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free") and
            scope.get("two_complete_wifi_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "heap plateau changed across Wi-Fi lifecycles")
    require(failures, scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_wifi_only") is True and
            scope.get("storage_write_authorized") is False and
            scope.get("storage_untouched_during_live_list") is True and
            scope.get("selected_focus_frame_continuous") is True and
            ((isinstance(scope.get("navigation_press_count"), int) and
              scope.get("navigation_press_count", 0) >= 8)
             if intelligence else scope.get("navigation_press_count") == 8) and
            scope.get("live_order_remains_strongest_first") is True and
            scope.get("cursor_not_reset_after_user_navigation") is True and
            scope.get("selected_identity_preserved_during_live_sort") is True,
            "automation/passive scope mismatch")
    if intelligence:
        require(failures, scope.get("network_vendor_lookup") is True and
                scope.get("network_driver_facts") is True,
                "network intelligence scope mismatch")
        if live_radar:
            require(failures,
                    scope.get("detail_live_radar_only") is True and
                    scope.get("detail_live_signal_card_only") is False,
                    "network live-radar scope mismatch")
        else:
            require(failures,
                    scope.get("detail_live_signal_card_only") is True,
                    "network RSSI-line scope mismatch")

    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures, before.get("generation") == after.get("generation") and
            before.get("observations") == after.get("observations") and
            after.get("physical_write_calls") == 0,
            "read-only product continuity mismatch")
    require(failures, run.get("input", {}).get("queue_drops") == 0 and
            run.get("input", {}).get("read_errors") == 0,
            "input frontend mismatch")
    require(failures, run.get("safe_outputs", {}).get("buzzer_inactive") is True,
            "buzzer safe state mismatch")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures, run.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "final cleanup/lease mismatch")
    require(failures, set(run.get("screens", {})) == set(SCREENS),
            "screen inventory mismatch")
    for key, name in SCREENS.items():
        screen = run.get("screens", {}).get(key, {})
        for suffix, hash_key in (("png", "png_sha256"),
                                 ("rgb565", "rgb565_sha256")):
            path = root / "frames" / f"{name}.{suffix}"
            require(failures, path.is_file(), f"{name}.{suffix} missing")
            if path.is_file():
                require(failures, screen.get(hash_key) == digest(path),
                        f"{name}.{suffix} hash mismatch")
    verify_manifest(failures, root)
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "status": "pass",
        "version": args.expected_version,
        "unique_networks": second.get("wifi_networks_unique"),
        "chrome_changed_pixels": 0,
        "detail_changed_pixels": run.get(
            "detail_pixel_changes", {}).get("content_changed_pixels"),
        "network_intelligence": intelligence,
        "network_live_radar": live_radar,
        "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
