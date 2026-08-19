#!/usr/bin/env python3
"""Flash once and exercise the complete product Home on board-01."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.product_home_hil.run.v1"
NRF_SCHEMA = "leshy.nrf24.spectrum.v1"
CC_SCHEMA = "leshy.cc1101.spectrum.v1"
HOME_ITEMS = (
    "wifi", "ble", "spectrum24", "subghz", "capture", "library", "device",
)
WATERFALL_ROWS = 224
WATERFALL_FILL_US = 3_000_000
WATERFALL_GRAPH_Y = 54
WATERFALL_GRAPH_BOTTOM = 278


def read_only_query(device: PassiveSerial, command: bytes, schema: str,
                    kind: str, timeout: float = 5.0,
                    maximum_attempts: int = 2) -> dict[str, Any]:
    """Retry a state query once without ever replaying an action command."""
    errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = query(device, command, schema, kind, timeout=timeout)
            record["host_transport_attempts"] = attempt
            record["host_transport_transient_retries"] = attempt - 1
            record["host_transport_transient_errors"] = errors
            return record
        except TimeoutError as error:
            if attempt == maximum_attempts:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable state-query retry state")


def require_only_waterfall_changed(
        frames: Path, first: str, second: str) -> dict[str, int]:
    before = (frames / f"{first}.rgb565").read_bytes()
    after = (frames / f"{second}.rgb565").read_bytes()
    expected = 240 * 320 * 2
    if len(before) != expected or len(after) != expected:
        raise RuntimeError("waterfall comparison requires two complete TFT frames")
    graph_changed = 0
    chrome_changed = 0
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if WATERFALL_GRAPH_Y <= y < WATERFALL_GRAPH_BOTTOM:
                graph_changed += 1
            else:
                chrome_changed += 1
    if graph_changed == 0:
        raise RuntimeError(f"{first}: waterfall pixels did not advance")
    if chrome_changed != 0:
        raise RuntimeError(
            f"{first}: {chrome_changed} pixels changed outside the waterfall")
    return {"graph_changed_pixels": graph_changed,
            "chrome_changed_pixels": chrome_changed}


def home_selection(device: PassiveSerial, index: int) -> dict[str, Any]:
    current = read_only_query(
        device, b"ui.state", "leshy.ui.v1", "state")
    if current.get("page") != "home":
        raise RuntimeError(f"Home expected before selection {index}: {current}")
    while int(current.get("selection", -1)) > index:
        current = action(device, "up")
    while int(current.get("selection", -1)) < index:
        current = action(device, "down")
    failures = expect(current, {
        "page": "home", "selection": index, "selected_id": HOME_ITEMS[index],
        "selected_enabled": True, "runtime_owner": "none", "lease_mask": 0,
    }, f"home_{HOME_ITEMS[index]}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return current


def wait_report(device: PassiveSerial, command: bytes, schema: str,
                minimum_rows: int, timeout: float = 12.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report = read_only_query(device, command, schema, "state")
        if int(report.get("history_rows", 0)) >= minimum_rows:
            return report
        time.sleep(0.05)
    raise TimeoutError(
        f"{schema} did not accumulate {minimum_rows} waterfall rows: {report}")


def require_exact(record: dict[str, Any], expected: dict[str, Any],
                  label: str) -> None:
    failures = expect(record, expected, label)
    if failures:
        raise RuntimeError("; ".join(failures))


def require_waterfall_timing(record: dict[str, Any], label: str) -> None:
    require_exact(record, {
        "history_rows": WATERFALL_ROWS,
        "waterfall_fill_target_us": WATERFALL_FILL_US,
        "waterfall_row_period_us": WATERFALL_FILL_US // WATERFALL_ROWS,
        "waterfall_full": True,
    }, label)
    elapsed = int(record.get("waterfall_fill_elapsed_us", 0))
    minimum = 2_700_000
    if elapsed < minimum or elapsed > WATERFALL_FILL_US:
        raise RuntimeError(
            f"{label}: waterfall fill {elapsed} us outside "
            f"{minimum}..{WATERFALL_FILL_US} us")
    if "host_fill_elapsed_ms" in record:
        host_elapsed = float(record["host_fill_elapsed_ms"])
        if host_elapsed < 2700.0 or host_elapsed > 3100.0:
            raise RuntimeError(
                f"{label}: host-observed fill {host_elapsed} ms outside "
                "2700..3100 ms")


def require_cc_retry_accounting(record: dict[str, Any], label: str) -> None:
    wire = record.get("wire", {})
    timeouts = wire.get("receive_ready_timeouts")
    retries = wire.get("transient_retries")
    samples = record.get("adapter_samples")
    if not all(isinstance(value, int)
               for value in (timeouts, retries, samples)) or \
            retries != timeouts or not 0 <= retries <= samples:
        raise RuntimeError(
            f"{label}: invalid bounded RX-ready retry accounting "
            f"{timeouts!r}/{retries!r}/{samples!r}")


def wait_full_waterfall(
        device: PassiveSerial, command: bytes, schema: str,
        timeout: float = 12.0) -> dict[str, Any]:
    started = time.monotonic()
    report = wait_report(
        device, command, schema, WATERFALL_ROWS, timeout=timeout)
    report["host_fill_elapsed_ms"] = round(
        (time.monotonic() - started) * 1000.0, 3)
    return report


def stabilized_boot_metrics(
        device: PassiveSerial,
        maximum_attempts: int = 4) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Warm the diagnostic channel and return a proven steady heap baseline."""
    samples: list[dict[str, Any]] = []
    heap_keys = ("heap_total", "heap_free", "heap_min_free")
    for _ in range(maximum_attempts):
        sample = read_only_query(
            device, b"metrics", "leshy.boot.v1", "ready")
        samples.append(sample)
        if len(samples) < 2:
            continue
        previous = samples[-2]
        if all(sample.get(key) == previous.get(key) for key in heap_keys):
            return sample, samples
    raise RuntimeError(
        f"diagnostic heap baseline did not stabilize in {maximum_attempts} "
        f"attempts: {samples}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full Git commit ID")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    waterfall_pixel_changes: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery_before = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                home_selection(device, 0)
                screens["home_top"] = capture(device, frames, "home-top")
                for index, item in enumerate(HOME_ITEMS):
                    current = home_selection(device, index)
                    trace.append(current)
                screens["home_bottom"] = capture(device, frames, "home-bottom")

                home_selection(device, 0)
                wifi = action(device, "right")
                trace.append(wifi)
                require_exact(wifi, {
                    "page": "survey", "selected_id": "wifi",
                    "runtime_owner": "wifi", "lease_mask": 15,
                    "survey_setup_view": "plan", "survey_setup_selection": 0,
                    "survey_source_selected_mask": 1,
                    "survey_source_selected_count": 1,
                    "survey_source_can_start": True,
                }, "wifi_entry")
                screens["wifi"] = capture(device, frames, "wifi")
                trace.append(action(device, "left"))
                home_selection(device, 1)
                ble = action(device, "right")
                trace.append(ble)
                require_exact(ble, {
                    "page": "survey", "selected_id": "ble",
                    "runtime_owner": "ble", "lease_mask": 15,
                    "survey_setup_view": "plan", "survey_setup_selection": 0,
                    "survey_source_selected_mask": 2,
                    "survey_source_selected_count": 1,
                    "survey_source_can_start": True,
                }, "ble_entry")
                screens["ble"] = capture(device, frames, "ble")
                trace.append(action(device, "left"))

                home_selection(device, 2)
                nrf = action(device, "right")
                trace.append(nrf)
                require_exact(nrf, {
                    "page": "survey", "selected_id": "spectrum24",
                    "runtime_event": "nrf24_spectrum_running",
                    "runtime_owner": "spectrum24", "lease_mask": 9,
                }, "nrf_entry")
                reports["nrf_spectrum"] = wait_full_waterfall(
                    device, b"hardware.nrf24.spectrum", NRF_SCHEMA)
                require_waterfall_timing(
                    reports["nrf_spectrum"], "nrf_waterfall_timing")
                require_exact(reports["nrf_spectrum"], {
                    "view": "live", "display_mode": "spectrum",
                    "metric": "signal",
                    "state": "running", "rx_only": True,
                    "all_available_antennas": True,
                    "volatile": True, "current_owner": "spectrum24",
                    "current_lease_mask": 9,
                }, "nrf_spectrum")
                screens["nrf_spectrum"] = capture(
                    device, frames, "nrf-spectrum")
                trace.append(action(device, "down"))
                reports["nrf_waterfall"] = wait_report(
                    device, b"hardware.nrf24.spectrum", NRF_SCHEMA,
                    WATERFALL_ROWS)
                require_waterfall_timing(
                    reports["nrf_waterfall"], "nrf_waterfall_view_timing")
                require_exact(reports["nrf_waterfall"], {
                    "view": "live", "display_mode": "waterfall",
                    "state": "running", "rx_only": True,
                    "current_owner": "spectrum24", "current_lease_mask": 9,
                }, "nrf_waterfall")
                screens["nrf_waterfall"] = capture(
                    device, frames, "nrf-waterfall")
                time.sleep(0.08)
                screens["nrf_waterfall_next"] = capture(
                    device, frames, "nrf-waterfall-next")
                waterfall_pixel_changes["nrf"] = require_only_waterfall_changed(
                    frames, "nrf-waterfall", "nrf-waterfall-next")
                trace.append(action(device, "right"))
                reports["nrf_traffic"] = wait_full_waterfall(
                    device, b"hardware.nrf24.spectrum", NRF_SCHEMA)
                require_exact(reports["nrf_traffic"], {
                    "view": "live", "display_mode": "waterfall",
                    "metric": "traffic",
                    "traffic_semantics": "activity_above_baseline",
                    "state": "running", "rx_only": True,
                    "all_available_antennas": True,
                    "volatile": True, "current_owner": "spectrum24",
                    "current_lease_mask": 9,
                }, "nrf_traffic")
                screens["nrf_traffic"] = capture(
                    device, frames, "nrf-traffic-waterfall")
                trace.append(action(device, "right"))
                signal_again = read_only_query(
                    device, b"hardware.nrf24.spectrum", NRF_SCHEMA, "state")
                require_exact(signal_again, {
                    "display_mode": "waterfall", "metric": "signal",
                    "state": "running",
                }, "nrf_signal_again")
                trace.append(action(device, "up"))
                trace.append(action(device, "left"))
                stopped_nrf = read_only_query(
                    device, b"hardware.nrf24.spectrum", NRF_SCHEMA, "state")
                require_exact(stopped_nrf, {
                    "view": "none", "state": "idle", "adapter_active": False,
                    "cleanup_complete": True, "current_owner": "none",
                    "current_lease_mask": 0,
                }, "nrf_cleanup")
                reports["nrf_stopped"] = stopped_nrf

                home_selection(device, 3)
                cc_menu = action(device, "right")
                trace.append(cc_menu)
                require_exact(cc_menu, {
                    "page": "survey", "selected_id": "subghz",
                    "runtime_event": "cc1101_spectrum_band_menu",
                    "runtime_owner": "subghz", "lease_mask": 9,
                }, "cc_band_menu")
                screens["cc_band_menu"] = capture(
                    device, frames, "cc-band-menu")
                trace.append(action(device, "right"))
                reports["cc_spectrum"] = wait_full_waterfall(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA)
                require_waterfall_timing(
                    reports["cc_spectrum"], "cc_433_waterfall_timing")
                require_cc_retry_accounting(
                    reports["cc_spectrum"], "cc_433_retry_accounting")
                require_exact(reports["cc_spectrum"], {
                    "view": "live", "display_mode": "spectrum",
                    "state": "running", "band": "433", "rx_only": True,
                    "volatile": True, "current_owner": "subghz",
                    "current_lease_mask": 9,
                }, "cc_spectrum")
                screens["cc_spectrum"] = capture(
                    device, frames, "cc-spectrum")
                trace.append(action(device, "down"))
                reports["cc_waterfall"] = wait_report(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA,
                    WATERFALL_ROWS,
                    timeout=24.0)
                require_waterfall_timing(
                    reports["cc_waterfall"], "cc_433_waterfall_view_timing")
                require_cc_retry_accounting(
                    reports["cc_waterfall"], "cc_433_view_retry_accounting")
                require_exact(reports["cc_waterfall"], {
                    "view": "live", "display_mode": "waterfall",
                    "state": "running", "band": "433", "rx_only": True,
                    "current_owner": "subghz", "current_lease_mask": 9,
                }, "cc_waterfall")
                screens["cc_waterfall"] = capture(
                    device, frames, "cc-waterfall")
                time.sleep(0.08)
                screens["cc_waterfall_next"] = capture(
                    device, frames, "cc-waterfall-next")
                waterfall_pixel_changes["cc"] = require_only_waterfall_changed(
                    frames, "cc-waterfall", "cc-waterfall-next")
                trace.append(action(device, "right"))
                cc_paused_before = read_only_query(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA, "state")
                time.sleep(0.35)
                cc_paused_after = read_only_query(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA, "state")
                if cc_paused_after.get("state") != "paused" or \
                        cc_paused_after.get("adapter_samples") != \
                        cc_paused_before.get("adapter_samples"):
                    raise RuntimeError("CC1101 pause did not freeze samples")
                trace.append(action(device, "right"))
                trace.append(action(device, "up"))
                band_menu = action(device, "left")
                trace.append(band_menu)
                require_exact(band_menu, {
                    "page": "survey", "selected_id": "subghz",
                    "runtime_owner": "subghz", "lease_mask": 9,
                }, "cc_return_to_band_menu")
                for band, moves in (
                    ("868", ("down",)),
                    ("915", ("down",)),
                    ("315", ("up", "up", "up")),
                ):
                    for move in moves:
                        trace.append(action(device, move))
                    trace.append(action(device, "right"))
                    fill = wait_full_waterfall(
                        device, b"hardware.cc1101.spectrum", CC_SCHEMA,
                        timeout=24.0)
                    require_exact(fill, {
                        "view": "live", "display_mode": "spectrum",
                        "state": "running", "band": band,
                        "rx_only": True, "volatile": True,
                        "current_owner": "subghz", "current_lease_mask": 9,
                    }, f"cc_{band}_spectrum")
                    require_waterfall_timing(
                        fill, f"cc_{band}_waterfall_timing")
                    require_cc_retry_accounting(
                        fill, f"cc_{band}_retry_accounting")
                    reports[f"cc_fill_{band}"] = fill
                    returned = action(device, "left")
                    trace.append(returned)
                    require_exact(returned, {
                        "page": "survey", "selected_id": "subghz",
                        "runtime_owner": "subghz", "lease_mask": 9,
                    }, f"cc_{band}_return_to_band_menu")
                trace.append(action(device, "left"))
                stopped_cc = read_only_query(
                    device, b"hardware.cc1101.spectrum", CC_SCHEMA, "state")
                require_exact(stopped_cc, {
                    "view": "none", "state": "idle", "adapter_active": False,
                    "cleanup_complete": True, "current_owner": "none",
                    "current_lease_mask": 0,
                }, "cc_cleanup")
                reports["cc_stopped"] = stopped_cc

                for index, item, page, owner, lease in (
                    (4, "capture", "capture", "capture", 3),
                    (5, "library", "library", "library", 5),
                    (6, "device", "device", "device", 1),
                ):
                    home_selection(device, index)
                    opened = action(device, "right")
                    trace.append(opened)
                    require_exact(opened, {
                        "page": page, "selected_id": item,
                        "runtime_owner": owner, "lease_mask": lease,
                    }, f"{item}_entry")
                    screens[item] = capture(device, frames, item)
                    trace.append(action(device, "left"))

                home_selection(device, 0)
                query(device, b"ui.language en", "leshy.ui.v1", "state")
                screens["home_en"] = capture(device, frames, "home-en")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")
                screens["home_final"] = capture(device, frames, "home-final")
                input_state = read_only_query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                safe_outputs = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                metrics_after = read_only_query(
                    device, b"metrics", "leshy.boot.v1", "ready")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "buzzer_level": "low",
                }, "safe_outputs"))
                for key in ("generation", "observations"):
                    if recovery_after.get(key) != recovery_before.get(key):
                        failures.append(f"persistent {key} changed")
                if recovery_after.get("physical_write_calls") != 0:
                    failures.append("physical SD write observed")
                if metrics_after.get("heap_free") != boot.get("heap_free"):
                    failures.append("heap free did not return to boot baseline")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_after.get("complete"):
                    failures.append("cleanup_after: Home/zero lease unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": bool(args.flash) and not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "home_items": list(HOME_ITEMS),
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "boot_metrics_stabilized": bool(boot_metrics_samples) and
            len(boot_metrics_samples) >= 2,
        "recovery_before": recovery_before,
        "reports": reports,
        "waterfall_pixel_changes": waterfall_pixel_changes,
        "screens": screens,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "recovery_after": recovery_after,
        "metrics_after": metrics_after,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "scope": {
            "single_flash": True,
            "manual_button_presses": 0,
            "screenshots_automatic": True,
            "waterfall_chrome_static_verified": True,
            "software_rx_only_counters_verified": True,
            "rf_instrument_available": False,
            "storage_write_authorized": False,
            "home_identity": "bilingual_brand_and_version",
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "output": str(args.output),
        "screens": sorted(screens),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
