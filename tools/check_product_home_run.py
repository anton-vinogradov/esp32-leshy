#!/usr/bin/env python3
"""Independent fail-closed verifier for a product Home HIL run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SCHEMA = "leshy.product_home_hil.run.v1"
HOME_ITEMS = [
    "wifi", "ble", "spectrum24", "subghz", "capture", "library", "device",
]
SCREENS = {
    "home_top": "home-top",
    "home_bottom": "home-bottom",
    "wifi": "wifi",
    "ble": "ble",
    "nrf_spectrum": "nrf-spectrum",
    "nrf_waterfall": "nrf-waterfall",
    "cc_band_menu": "cc-band-menu",
    "cc_spectrum": "cc-spectrum",
    "cc_waterfall": "cc-waterfall",
    "capture": "capture",
    "library": "library",
    "device": "device",
    "home_final": "home-final",
}
PIXEL_WATERFALL_SCREENS = {
    "nrf_waterfall_next": "nrf-waterfall-next",
    "nrf_traffic": "nrf-traffic-waterfall",
    "cc_waterfall_next": "cc-waterfall-next",
}
IDENTITY_SCREENS = {"home_en": "home-en"}
SUBGHZ_MODE_SCREENS = {"subghz_modes": "subghz-modes"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def verify_receiver_paced_waterfall(
        failures: list[str], label: str, report: dict[str, Any],
        expected_rows: int, require_full: bool) -> None:
    rows = report.get("history_rows")
    consumed = report.get("waterfall_measurements_consumed")
    source_sweeps = report.get("waterfall_source_sweeps")
    require(failures,
            report.get("waterfall_cadence") == "receiver_sweep" and
            report.get("waterfall_fill_target_us") == 0 and
            report.get("waterfall_row_period_us") == 0 and
            report.get("waterfall_measurements_skipped") == 0 and
            all(isinstance(value, int)
                for value in (rows, consumed, source_sweeps)) and
            consumed == source_sweeps and consumed >= rows,
            f"{label} receiver-paced one-to-one mismatch")
    if require_full:
        require(failures,
                rows == expected_rows and consumed >= expected_rows and
                report.get("waterfall_full") is True and
                report.get("waterfall_fill_elapsed_us", 0) > 0,
                f"{label} receiver-paced full history mismatch")


def verify_cc_retries(failures: list[str], label: str,
                      report: dict[str, Any]) -> None:
    wire = report.get("wire", {})
    timeouts = wire.get("receive_ready_timeouts")
    retries = wire.get("transient_retries")
    select_timeouts = wire.get("select_ready_timeouts")
    recovery_attempts = wire.get("recovery_attempts")
    recoveries = wire.get("recoveries")
    samples = report.get("adapter_samples")
    require(failures,
            all(isinstance(value, int) for value in (
                timeouts, retries, select_timeouts, recovery_attempts,
                recoveries, samples)) and
            retries == timeouts and 0 <= retries <= samples and
            0 <= recoveries <= recovery_attempts <=
                select_timeouts <= samples,
            f"{label} bounded retry/recovery mismatch")


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


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
        path = root / relative
        indexed.add(relative)
        require(failures, path.is_file(), f"indexed artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
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
    require(failures, root.is_dir(), "run directory missing")
    run_path = root / "run.json"
    require(failures, run_path.is_file(), "run.json missing")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    run = load(run_path)
    require(failures, run.get("schema") == SCHEMA, "run schema mismatch")
    require(failures, run.get("passed") is True and
            run.get("gate_eligible") is True and not run.get("failures"),
            "run is not a clean flashed pass")
    require(failures, run.get("home_items") == HOME_ITEMS,
            "Home item order/content mismatch")
    candidate = run.get("candidate", {})
    firmware = root / "firmware.bin"
    require(failures, candidate.get("version") == args.expected_version,
            "candidate version mismatch")
    require(failures, candidate.get("source_commit") == args.source_commit,
            "candidate source commit mismatch")
    require(failures, candidate.get("flashed") is True,
            "candidate flash not proven")
    require(failures, firmware.is_file(), "retained candidate missing")
    if firmware.is_file():
        require(failures, candidate.get("firmware_sha256") == digest(firmware),
                "candidate firmware hash mismatch")
        require(failures,
                candidate.get("app_elf_sha256") == app_elf_sha256(firmware),
                "candidate embedded ELF identity mismatch")
    require(failures, run.get("expected_cid") == args.expected_cid,
            "exact CID mismatch")

    boot = run.get("boot", {})
    boot_samples = run.get("boot_metrics_samples", [])
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures, boot.get("version") == args.expected_version and
            boot.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            boot.get("buzzer_inactive") is True and
            boot.get("input_detected") is True,
            "boot identity/health mismatch")
    stabilized_metrics_present = "boot_metrics_stabilized" in run or \
        "boot_metrics_samples" in run
    if stabilized_metrics_present:
        require(failures,
                run.get("boot_metrics_stabilized") is True and
                isinstance(boot_samples, list) and
                2 <= len(boot_samples) <= 4,
                "diagnostic heap baseline stabilization missing")
    if stabilized_metrics_present and isinstance(boot_samples, list) and \
            len(boot_samples) >= 2:
        heap_keys = ("heap_total", "heap_free", "heap_min_free")
        require(failures,
                all(boot_samples[-1].get(key) ==
                    boot_samples[-2].get(key) for key in heap_keys),
                "final diagnostic heap samples are not stable")
        require(failures, boot_samples[-1] == boot,
                "boot baseline is not the final stabilized sample")
    for label, recovery in (("before", before), ("after", after)):
        require(failures,
                recovery.get("status") == "admitted" and
                recovery.get("observed_fingerprint") == args.expected_cid and
                recovery.get("read_only_guaranteed") is True and
                recovery.get("physical_write_calls") == 0 and
                recovery.get("cleanup_complete") is True,
                f"{label} recovery mismatch")
    require(failures,
            before.get("generation") == after.get("generation") and
            before.get("observations") == after.get("observations"),
            "persistent product continuity mismatch")

    scope = run.get("scope", {})
    pixel_contract = scope.get("waterfall_chrome_static_verified") is True
    expected_rows = 224 if pixel_contract else 112
    expected_period_us = 13_392 if pixel_contract else 26_785
    reports = run.get("reports", {})
    for prefix, owner in (("nrf", "spectrum24"), ("cc", "subghz")):
        spectrum = reports.get(f"{prefix}_spectrum", {})
        waterfall = reports.get(f"{prefix}_waterfall", {})
        stopped = reports.get(f"{prefix}_stopped", {})
        require(failures,
                spectrum.get("display_mode") == "spectrum" and
                spectrum.get("state") == "running" and
                spectrum.get("current_owner") == owner and
                spectrum.get("current_lease_mask") == 9 and
                spectrum.get("rx_only") is True,
                f"{prefix} spectrum contract mismatch")
        require(failures,
                waterfall.get("display_mode") == "waterfall" and
                waterfall.get("state") == "running" and
                waterfall.get("history_rows", 0) >= (16 if prefix == "nrf" else 8) and
                waterfall.get("current_owner") == owner and
                waterfall.get("current_lease_mask") == 9,
                f"{prefix} waterfall contract mismatch")
        require(failures,
                stopped.get("view") == "none" and
                stopped.get("state") == "idle" and
                stopped.get("adapter_active") is False and
                stopped.get("cleanup_complete") is True and
                stopped.get("current_owner") == "none" and
                stopped.get("current_lease_mask") == 0,
                f"{prefix} cleanup mismatch")
        side_effects = waterfall.get("side_effects", {})
        forbidden = ("tx_mode_entries", "tx_payload_commands", "tx_strobes",
                     "pa_table_writes", "fifo_writes", "storage_writes")
        require(failures,
                all(side_effects.get(key, 0) == 0 for key in forbidden),
                f"{prefix} receive-only side effects mismatch")
        if prefix == "cc" and pixel_contract:
            for label, report in (("spectrum", spectrum),
                                  ("waterfall", waterfall)):
                if report.get("waterfall_cadence") == "receiver_sweep":
                    verify_cc_retries(failures, f"CC1101 {label}", report)
                else:
                    wire = report.get("wire", {})
                    timeouts = wire.get("receive_ready_timeouts")
                    retries = wire.get("transient_retries")
                    samples = report.get("adapter_samples")
                    require(failures,
                            all(isinstance(value, int)
                                for value in (timeouts, retries, samples)) and
                            retries == timeouts and 0 <= retries <= samples,
                            f"CC1101 {label} bounded retry mismatch")
        if waterfall.get("waterfall_cadence") == "receiver_sweep":
            verify_receiver_paced_waterfall(
                failures, f"{prefix} spectrum", spectrum,
                expected_rows, False)
            verify_receiver_paced_waterfall(
                failures, f"{prefix} waterfall", waterfall,
                expected_rows, True)
        elif "waterfall_fill_target_us" in spectrum or \
                "waterfall_fill_target_us" in waterfall:
            for label, report in (("spectrum", spectrum),
                                  ("waterfall", waterfall)):
                require(failures,
                        report.get("history_rows") == expected_rows and
                        report.get("waterfall_fill_target_us") == 3_000_000 and
                        report.get("waterfall_row_period_us") ==
                            expected_period_us and
                        report.get("waterfall_full") is True and
                        2_700_000 <=
                            report.get("waterfall_fill_elapsed_us", 0) <=
                            3_000_000,
                        f"{prefix} {label} three-second waterfall mismatch")

    cc_fill_keys = {key for key in reports if key.startswith("cc_fill_")}
    if cc_fill_keys:
        require(failures, cc_fill_keys ==
                {"cc_fill_315", "cc_fill_868", "cc_fill_915"},
                "CC1101 waterfall timing band coverage mismatch")
        for band in ("315", "868", "915"):
            report = reports.get(f"cc_fill_{band}", {})
            require(failures, report.get("band") == band,
                    f"CC1101 {band} band mismatch")
            receiver_paced = report.get("waterfall_cadence") == \
                "receiver_sweep"
            if receiver_paced:
                verify_receiver_paced_waterfall(
                    failures, f"CC1101 {band}", report,
                    expected_rows, True)
            else:
                require(failures,
                        report.get("history_rows") == expected_rows and
                        report.get("waterfall_fill_target_us") == 3_000_000 and
                        report.get("waterfall_full") is True and
                        2_700_000 <=
                            report.get("waterfall_fill_elapsed_us", 0) <=
                            3_000_000,
                        f"CC1101 {band} three-second waterfall mismatch")
            if pixel_contract:
                if receiver_paced:
                    verify_cc_retries(
                        failures, f"CC1101 {band}", report)
                else:
                    wire = report.get("wire", {})
                    require(failures,
                            wire.get("receive_ready_timeouts") ==
                                wire.get("transient_retries") and
                            isinstance(wire.get("transient_retries"), int) and
                            0 <= wire.get("transient_retries") <=
                                report.get("adapter_samples", -1),
                            f"CC1101 {band} bounded retry mismatch")
            host_elapsed = report.get("host_fill_elapsed_ms", 0)
            if receiver_paced:
                require(failures, host_elapsed > 0,
                        f"CC1101 {band} host-observed fill missing")
            else:
                require(failures, 2700 <= host_elapsed <= 3100,
                        f"CC1101 {band} host-observed fill mismatch")
        if reports.get("nrf_waterfall", {}).get(
                "waterfall_cadence") != "receiver_sweep":
            for key in ("nrf_spectrum", "cc_spectrum"):
                host_elapsed = reports.get(key, {}).get(
                    "host_fill_elapsed_ms", 0)
                require(failures, 2700 <= host_elapsed <= 3100,
                        f"{key} host-observed fill mismatch")

    if pixel_contract:
        pixel_changes = run.get("waterfall_pixel_changes", {})
        for receiver in ("nrf", "cc"):
            change = pixel_changes.get(receiver, {})
            require(failures,
                    change.get("graph_changed_pixels", 0) > 0 and
                    change.get("chrome_changed_pixels") == 0,
                    f"{receiver} waterfall-only pixel update mismatch")

    screens = run.get("screens", {})
    identity_contract = scope.get("home_identity") == \
        "bilingual_brand_and_version"
    expected_screens = dict(SCREENS)
    if "subghz_modes" in screens:
        expected_screens.update(SUBGHZ_MODE_SCREENS)
    if pixel_contract:
        expected_screens.update(PIXEL_WATERFALL_SCREENS)
    if identity_contract:
        expected_screens.update(IDENTITY_SCREENS)
    require(failures, set(screens) == set(expected_screens),
            "screen set mismatch")
    for key, stem in expected_screens.items():
        record = screens.get(key, {})
        raw = root / "frames" / f"{stem}.rgb565"
        png = root / "frames" / f"{stem}.png"
        metadata = root / "frames" / f"{stem}.json"
        require(failures, raw.is_file() and raw.stat().st_size == 153600,
                f"{key} RGB565 frame missing/invalid")
        require(failures, png.is_file() and png_size(png) == (240, 320),
                f"{key} PNG missing/invalid")
        require(failures, metadata.is_file(), f"{key} metadata missing")
        if raw.is_file() and png.is_file():
            require(failures,
                    record.get("rgb565_sha256") == digest(raw) and
                    record.get("png_sha256") == digest(png),
                    f"{key} screenshot hash mismatch")

    input_state = run.get("input", {})
    safe = run.get("safe_outputs", {})
    metrics_after = run.get("metrics_after", {})
    require(failures,
            input_state.get("status") == "ready" and
            input_state.get("read_errors") == 0 and
            input_state.get("queue_drops") == 0,
            "input health mismatch")
    require(failures, safe.get("buzzer_inactive") is True and
            safe.get("buzzer_level") == "low", "buzzer invariant mismatch")
    require(failures, metrics_after.get("heap_free") == boot.get("heap_free"),
            "heap baseline mismatch")
    for label in ("cleanup_before", "cleanup_after"):
        cleanup = run.get(label, {})
        final = cleanup.get("final_state", {})
        require(failures, cleanup.get("complete") is True and
                final.get("page") == "home" and
                final.get("runtime_owner") == "none" and
                final.get("lease_mask") == 0,
                f"{label} terminal state mismatch")
    expected_scope = {
        "single_flash": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "software_rx_only_counters_verified": True,
        "rf_instrument_available": False,
        "storage_write_authorized": False,
    }
    if pixel_contract:
        expected_scope["waterfall_chrome_static_verified"] = True
    if identity_contract:
        expected_scope["home_identity"] = "bilingual_brand_and_version"
        require(failures,
                screens.get("home_en", {}).get("state", {}).get("language") ==
                    "en" and
                screens.get("home_final", {}).get("state", {}).get("language") ==
                    "ru",
                "bilingual Home capture state mismatch")
    if "exact_flash_reused" in scope:
        reused = scope.get("exact_flash_reused") is True
        expected_scope["exact_flash_reused"] = reused
        require(failures,
                candidate.get("flash_mode") ==
                    ("reuse_exact" if reused else "fresh") and
                candidate.get("flashed") is True,
                "candidate flash-mode binding mismatch")
    require(failures, scope == expected_scope, "automation scope mismatch")
    verify_manifest(failures, root)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(json.dumps({
        "status": "pass", "version": args.expected_version,
        "home_items": HOME_ITEMS, "screens": len(expected_screens),
        "nrf_history_rows": reports["nrf_waterfall"]["history_rows"],
        "cc_history_rows": reports["cc_waterfall"]["history_rows"],
        "final_lease_mask": run["cleanup_after"]["final_state"]["lease_mask"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
