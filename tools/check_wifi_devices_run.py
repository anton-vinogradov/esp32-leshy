#!/usr/bin/env python3
"""Independent fail-closed verifier for a Wi-Fi devices HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.wifi_devices_hil.run.v4"
SCREENS = {
    "wifi_menu": "wifi-menu",
    "wifi_menu_after": "wifi-menu-after",
    "wifi_devices_first": "wifi-devices-first",
    "wifi_devices_second": "wifi-devices-second",
    "wifi_device_detail_first": "wifi-device-live-detail-first",
    "wifi_device_detail_second": "wifi-device-live-detail-second",
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
            first.get("wifi_product_view") == "devices" and
            first.get("wifi_device_monitor_active") is True and
            first.get("wifi_device_nvs_disabled") is True and
            first.get("wifi_device_volatile_storage_only") is True and
            first.get("wifi_devices_strongest_first") is True and
            first.get("wifi_devices_unique", 0) >= 1 and
            first.get("wifi_device_clients_accepted", 0) >= 1 and
            first.get("wifi_device_channel_hops", 0) >= 13 and
            first.get("wifi_device_clients_dropped") == 0,
            "first passive device observation mismatch")
    require(failures,
            second.get("wifi_device_catalog_revision", 0) >
                first.get("wifi_device_catalog_revision", 0) and
            second.get("wifi_devices_strongest_first") is True and
            second.get("wifi_device_clients_accepted", 0) >
                first.get("wifi_device_clients_accepted", 0) and
            second.get("wifi_device_clients_dropped") == 0,
            "live device catalog did not advance")
    require(failures,
            run.get("list_pixel_changes", {}).get("content_changed_pixels", -1) >= 0 and
            run.get("list_pixel_changes", {}).get("chrome_changed_pixels") == 0,
            "live redraw escaped the data rows")
    detail_pixels = run.get("detail_pixel_changes", {})
    detail_visual_input_changed = run.get("detail_visual_input_changed") is True
    require(failures,
            detail_pixels.get("identity_changed_pixels") == 0 and
            detail_pixels.get("live_changed_pixels", -1) >= 0 and
            (not detail_visual_input_changed or
             detail_pixels.get("live_changed_pixels", 0) > 0) and
            detail_pixels.get("chrome_changed_pixels") == 0,
            "integrated detail changed identity/chrome or did not update radar")
    detail_first = run.get("detail_first", {})
    detail_second = run.get("detail_second", {})
    require(failures,
            detail_first.get("wifi_product_view") == "device_detail" and
            detail_first.get("wifi_device_channel_locked") is True and
            detail_second.get("wifi_product_view") == "device_detail" and
            detail_second.get("wifi_device_channel_locked") is True and
            detail_second.get("wifi_device_clients_accepted", 0) >
                detail_first.get("wifi_device_clients_accepted", 0) and
            detail_second.get("wifi_device_catalog_revision", 0) >
                detail_first.get("wifi_device_catalog_revision", 0) and
            detail_second.get("wifi_device_detail_last_seen_us", 0) >
                detail_first.get("wifi_device_detail_last_seen_us", 0) and
            detail_second.get("wifi_device_channel_hops") ==
                detail_first.get("wifi_device_channel_hops"),
            "integrated channel-locked detail did not receive live updates")
    require(failures,
            detail_first.get("wifi_device_oui_database_available") is True and
            detail_first.get("wifi_device_oui_records") == 39984 and
            detail_first.get("wifi_device_navigation_locked") is True,
            "device intelligence/OUI/navigation contract mismatch")
    detail_oracle_first = run.get("detail_oracle_first", {})
    detail_oracle_second = run.get("detail_oracle_second", {})
    require(failures,
            detail_oracle_first.get("active") is True and
            detail_oracle_first.get("passive") is True and
            detail_oracle_first.get("active_probe_allowed") is False and
            detail_oracle_first.get("channel_locked") is True and
            detail_oracle_first.get("detail_content_clears") == 1 and
            detail_oracle_first.get("radar_full_repaints") == 1 and
            detail_oracle_first.get("radar_delta_repaints", -1) >= 0 and
            detail_oracle_first.get(
                "atomic_text_row_allocation_failures") == 0 and
            detail_oracle_first.get("direct_text_row_fallbacks") == 0,
            "initial device-detail render contract mismatch")
    require(failures,
            detail_oracle_second.get("active") is True and
            detail_oracle_second.get("identity_hash") ==
                detail_oracle_first.get("identity_hash") and
            detail_oracle_second.get("signal_samples", 0) >
                detail_oracle_first.get("signal_samples", 0) and
            detail_oracle_second.get("detail_content_clears") ==
                detail_oracle_first.get("detail_content_clears") and
            detail_oracle_second.get("radar_full_repaints") ==
                detail_oracle_first.get("radar_full_repaints") and
            detail_oracle_second.get("radar_delta_repaints", 0) >
                detail_oracle_first.get("radar_delta_repaints", 0) and
            detail_oracle_second.get(
                "atomic_text_row_allocation_failures") == 0 and
            detail_oracle_second.get("direct_text_row_fallbacks") == 0,
            "device-detail update was not an identity-stable bounded delta")
    for label in ("monitor_after_first", "monitor_after_second"):
        state = run.get(label, {})
        require(failures,
                state.get("wifi_device_monitor_active") is False and
                state.get("wifi_device_monitor_cleanup_complete") is True and
                state.get("wifi_device_clients_dropped") == 0,
                f"{label} cleanup mismatch")
    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    scope = run.get("scope", {})
    require(failures,
            first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free") and
            scope.get("two_complete_wifi_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "heap plateau changed across device monitor lifecycles")
    require(failures,
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_client_inference_only") is True and
            scope.get("access_point_beacons_excluded") is True and
            scope.get("channels_listened") == list(range(1, 14)) and
            scope.get("live_redraw_data_rows_only") is True and
            scope.get("integrated_live_device_detail") is True and
            scope.get("device_identity_region_stable") is True and
            scope.get("embedded_ieee_oui_records") == 39984 and
            scope.get("passive_probe_association_wps_fingerprint") is True and
            scope.get("identity_stable_device_navigation") is True and
            scope.get("channel_locked_live_radar") is True and
            scope.get("live_detail_redraw_live_region_only") is True and
            scope.get("live_detail_atomic_rows") is True and
            scope.get("live_detail_no_full_repaint_after_entry") is True and
            scope.get("storage_write_authorized") is False and
            scope.get("product_device_lock_namespace_mutated") is False,
            "automation/passive/no-flicker scope mismatch")

    lock = run.get("device_lock_fixture", {})
    require(failures,
            lock.get("active_at_end") is False and
            lock.get("begun") is True and
            lock.get("configured") is True and
            lock.get("cleanup_proven") is True and
            lock.get("hil_ended") is True and
            lock.get("isolated_namespace") is True and
            lock.get("pin_length") == 6 and
            lock.get("pin_or_digest_retained") is False and
            lock.get("product_namespace_written_or_erased") is False and
            lock.get("whole_nvs_read_or_copied") is False,
            "isolated Device Lock fixture was not safely removed")

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
        "unique_devices": second.get("wifi_devices_unique"),
        "channel_hops": second.get("wifi_device_channel_hops"),
        "chrome_changed_pixels": 0,
        "identity_changed_pixels": detail_pixels.get(
            "identity_changed_pixels"),
        "live_detail_changed_pixels": detail_pixels.get(
            "live_changed_pixels"),
        "oui_records": 39984,
        "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
