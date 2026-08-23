#!/usr/bin/env python3
"""Independent fail-closed verifier for a Wi-Fi Channels HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.wifi_channels_hil.run.v2"
SCREENS = {
    "wifi_menu": "wifi-menu",
    "wifi_menu_after": "wifi-menu-after",
    "wifi_channels_first": "wifi-channels-first",
    "wifi_channels_second": "wifi-channels-second",
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
            candidate.get("flash_mode") == "fresh",
            "fresh physical exact-flash binding missing")
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
    for label, state in (("first", first), ("second", second)):
        require(failures,
                state.get("wifi_product_view") == "channels" and
                state.get("wifi_channel_monitor_active") is True and
                state.get("wifi_device_nvs_disabled") is True and
                state.get("wifi_device_volatile_storage_only") is True and
                state.get("wifi_channel_measured_mask") == 8191 and
                state.get("wifi_channel_completed_sweeps", 0) >= 2 and
                state.get("wifi_channel_frames_reported", 0) > 0 and
                state.get("wifi_channel_invalid_frames") == 0 and
                state.get("wifi_channel_best_primary") in (1, 6, 11),
                f"{label} passive channel observation mismatch")
    require(failures,
            second.get("wifi_channel_revision", 0) >
                first.get("wifi_channel_revision", 0) and
            second.get("wifi_channel_completed_sweeps", 0) >
                first.get("wifi_channel_completed_sweeps", 0) and
            second.get("wifi_channel_frames_reported", 0) >
                first.get("wifi_channel_frames_reported", 0),
            "live channel measurements did not advance")
    changes = run.get("pixel_changes", {})
    require(failures,
            changes.get("dynamic_changed_pixels", 0) > 0 and
            changes.get("static_changed_pixels") == 0,
            "live redraw escaped graph/recommendation regions")
    average_gray = run.get("average_gray_pixels", {})
    require(failures,
            average_gray.get("first", 0) > 0 and
            average_gray.get("second", 0) > 0,
            "gray session-average bars are not physically visible")

    for label in ("monitor_after_first", "monitor_after_second"):
        state = run.get(label, {})
        require(failures,
                state.get("wifi_channel_monitor_active") is False and
                state.get("wifi_channel_monitor_cleanup_complete") is True,
                f"{label} cleanup mismatch")
    first_heap = run.get("metrics_after_first", {})
    final_heap = run.get("metrics_after", {})
    scope = run.get("scope", {})
    require(failures,
            first_heap.get("heap_total") == final_heap.get("heap_total") and
            first_heap.get("heap_free") == final_heap.get("heap_free") and
            scope.get("two_complete_wifi_lifecycles") is True and
            scope.get("zero_heap_drift_after_warmup") is True,
            "post-warm heap plateau changed across channel lifecycles")
    require(failures,
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_receive_only") is True and
            scope.get("channels_measured") == list(range(1, 14)) and
            scope.get("lower_bound_airtime_estimate") is True and
            scope.get("recommended_primary_channels") == [1, 6, 11] and
            scope.get("average_load_rendered_gray") is True and
            scope.get("recommendation_uses_session_average") is True and
            scope.get("minimum_average_dwells_per_channel") == 2 and
            scope.get("static_pixels_unchanged_during_live_refresh") is True and
            scope.get("storage_write_authorized") is False,
            "automation/passive/no-flicker scope mismatch")

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
            final.get("lease_mask") == 0 and
            final.get("safety_latched") is False,
            "final cleanup/safety/lease mismatch")
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
        "frames": second.get("wifi_channel_frames_reported"),
        "sweeps": second.get("wifi_channel_completed_sweeps"),
        "dynamic_changed_pixels": changes.get("dynamic_changed_pixels"),
        "static_changed_pixels": 0,
        "average_gray_pixels": average_gray,
        "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
