#!/usr/bin/env python3
"""Independent fail-closed verifier for a Wi-Fi packet recorder HIL run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.wifi_capture_product_hil.run.v1"
SCREENS = {
    "setup": "wifi-capture-setup",
    "running_first": "wifi-capture-running-first",
    "running_second": "wifi-capture-running-second",
    "result": "wifi-capture-result",
    "confirm": "wifi-capture-confirm",
    "wifi_menu_after": "wifi-menu-after-capture",
    "home": "home-final",
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


def verify_capture(failures: list[str], lifecycle: dict[str, Any],
                   label: str) -> None:
    running = lifecycle.get("running", {})
    complete = lifecycle.get("complete", {})
    summary = lifecycle.get("pcap", {}).get("summary", {})
    accepted = complete.get("frames_accepted", 0)
    reported = complete.get("frames_reported", -1)
    capacity = complete.get("frames_dropped_capacity", -1)
    invalid = complete.get("frames_dropped_invalid", -1)
    payload = complete.get("payload_bytes", 0)
    require(failures,
            running.get("state") == "running" and
            running.get("passive_only") is True and
            running.get("rx_only") is True and
            running.get("application_connect_calls") == 0 and
            running.get("application_raw_tx_calls") == 0 and
            running.get("storage_written") is False and
            running.get("duration_ms") == 10000 and
            running.get("channel_dwell_ms") == 120 and
            running.get("snap_length") == 256 and
            running.get("maximum_frames") == 16 and
            running.get("lease_mask") == 15,
            f"{label} running passive/bounded contract mismatch")
    require(failures,
            complete.get("state") == "complete" and
            complete.get("cleanup_complete") is True and
            complete.get("driver_error") == 0 and
            complete.get("pcap_available") is True and
            complete.get("storage_written") is False and
            complete.get("lease_mask") == 15 and
            isinstance(accepted, int) and 1 <= accepted <= 16 and
            reported == accepted + capacity + invalid and invalid == 0 and
            accepted <= payload <= accepted * 256,
            f"{label} complete frame accounting mismatch")
    require(failures,
            summary.get("records") == accepted and
            summary.get("captured_frame_bytes") == payload and
            summary.get("payload_retained") is False and
            summary.get("linktype") == 127 and
            summary.get("version") == "2.4" and
            len(str(summary.get("sha256", ""))) == 64,
            f"{label} radiotap PCAP mismatch")


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

    first = run.get("first", {})
    second = run.get("second", {})
    verify_capture(failures, first, "first")
    verify_capture(failures, second, "second")
    changes = first.get("pixel_changes", {})
    require(failures,
            changes.get("live_changed_pixels", 0) > 0 and
            changes.get("static_changed_pixels") == 0,
            "live redraw escaped packet/channel/drop metric rows")
    confirm = run.get("privacy_confirm", {})
    cancelled = run.get("privacy_cancelled", {})
    require(failures,
            confirm.get("state") == "complete" and
            confirm.get("persist_state") == "confirm" and
            confirm.get("persist_status") == "awaiting_confirmation" and
            confirm.get("storage_written") is False and
            confirm.get("lease_mask") == 15,
            "explicit privacy confirmation mismatch")
    require(failures,
            cancelled.get("state") == "complete" and
            cancelled.get("persist_state") == "volatile" and
            cancelled.get("storage_written") is False and
            cancelled.get("lease_mask") == 15,
            "privacy cancellation mismatch")
    scrubbed = run.get("scrubbed", {})
    require(failures,
            scrubbed.get("state") == "idle" and
            scrubbed.get("frames_reported") == 0 and
            scrubbed.get("frames_accepted") == 0 and
            scrubbed.get("payload_bytes") == 0 and
            scrubbed.get("pcap_available") is False and
            scrubbed.get("lease_mask") == 15,
            "Back did not scrub volatile frame payload")

    heap_first = run.get("metrics_after_first", {})
    heap_second = run.get("metrics_after_second", {})
    scope = run.get("scope", {})
    require(failures,
            heap_first.get("heap_total") == heap_second.get("heap_total") and
            heap_first.get("heap_free") == heap_second.get("heap_free"),
            "heap plateau changed across product capture lifecycles")
    require(failures,
            scope.get("single_flash") is True and
            scope.get("manual_button_presses") == 0 and
            scope.get("screenshots_automatic") is True and
            scope.get("passive_receive_only") is True and
            scope.get("bounded_ram_capture") is True and
            scope.get("raw_80211_payload_retained_in_evidence") is False and
            scope.get("pcap_retained_in_evidence") is False and
            scope.get("privacy_confirmation_tested_without_storage_write") is True and
            scope.get("static_pixels_unchanged_during_live_refresh") is True and
            scope.get("two_complete_wifi_lifecycles") is True and
            scope.get("storage_write_authorized") is False,
            "automation/passive/privacy/no-flicker scope mismatch")

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
        "status": "pass", "version": args.expected_version,
        "first_frames": first["complete"]["frames_accepted"],
        "second_frames": second["complete"]["frames_accepted"],
        "live_changed_pixels": changes["live_changed_pixels"],
        "static_changed_pixels": 0, "final_lease_mask": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
