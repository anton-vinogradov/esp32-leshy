#!/usr/bin/env python3
"""Independent fail-closed verifier for a Bluetooth Nearby HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.ble_nearby_hil.run.v1"
SCREENS = {
    "ble_devices_first": "ble-devices-first",
    "ble_devices_second": "ble-devices-second",
    "ble_detail_first": "ble-detail-first",
    "ble_detail_second": "ble-detail-second",
    "home_after": "ble-home-after",
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
    require(failures, indexed == actual, "manifest coverage mismatch")


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
    require(failures, firmware.is_file(), "candidate firmware missing")
    if firmware.is_file():
        require(failures, candidate.get("firmware_sha256") == digest(firmware),
                "firmware hash mismatch")
        require(failures,
                candidate.get("app_elf_sha256") == app_elf_sha256(firmware),
                "embedded app identity mismatch")

    first = run.get("live_first", {})
    second = run.get("live_second", {})
    require(failures,
            first.get("ble_product_view") == "devices" and
            first.get("survey_product_status") == "running" and
            first.get("survey_product_active_source_mask") == 2 and
            first.get("ble_devices_strongest_first") is True and
            isinstance(first.get("ble_devices_unique"), int) and
            first.get("ble_devices_unique", 0) >= 1 and
            first.get("survey_ble_scan_status") == "valid" and
            first.get("survey_ble_scan_accepted") ==
                first.get("survey_ble_scan_read") and
            first.get("survey_ble_scan_dropped") == 0 and
            first.get("survey_dropped") == 0,
            "first live BLE scan mismatch")
    require(failures,
            second.get("survey_product_ble_scan_cycles", 0) >
                first.get("survey_product_ble_scan_cycles", 0) and
            second.get("ble_devices_strongest_first") is True and
            second.get("ble_device_catalog_revision", 0) >
                first.get("ble_device_catalog_revision", 0),
            "live BLE catalog did not advance")
    require(failures,
            run.get("list_pixel_changes", {}).get(
                "content_changed_pixels", 0) > 0 and
            run.get("list_pixel_changes", {}).get(
                "chrome_changed_pixels") == 0,
            "live redraw escaped content rows")
    require(failures, run.get("detail_pixel_changes") == {
                "content_changed_pixels": 0, "chrome_changed_pixels": 0},
            "BLE detail changed during background scan")

    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    scope = run.get("scope", {})
    require(failures,
            first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free") and
            scope.get("two_complete_ble_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "BLE heap plateau changed")
    require(failures,
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_ble_only") is True and
            scope.get("active_scan") is False and
            scope.get("storage_write_authorized") is False,
            "automation/passive scope mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures,
            before.get("generation") == after.get("generation") and
            before.get("observations") == after.get("observations") and
            after.get("physical_write_calls") == 0,
            "read-only product continuity mismatch")
    require(failures,
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("input", {}).get("read_errors") == 0,
            "input frontend mismatch")
    require(failures, run.get("safe_outputs", {}).get("buzzer_inactive") is True,
            "buzzer safe state mismatch")
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures,
            run.get("cleanup_after", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("ble_product_view") == "none",
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
        "status": "pass", "version": args.expected_version,
        "unique_devices": second.get("ble_devices_unique"),
        "list_chrome_changed_pixels": 0,
        "detail_changed_pixels": 0, "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
