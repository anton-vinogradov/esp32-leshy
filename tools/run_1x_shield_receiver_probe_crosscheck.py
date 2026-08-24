#!/usr/bin/env python3
"""Cross-check one DIV RF shield with an exact known-positive product image."""

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
    expect,
    query,
)


RUN_SCHEMA = "leshy.shield_receiver_crosscheck.run.v1"
PROBE_SCHEMA = "leshy.shield.receiver_probe.v1"


def probe_contract_failures(
    report: dict[str, Any], require_bus_characterization: bool = False,
    require_isolated_main_characterization: bool = False,
    require_carrier_csn_characterization: bool = False,
) -> list[str]:
    expected = {
        "schema_version": 1,
        "read_only": True,
        "profile_declared": True,
        "gps_excluded_by_profile": True,
        "pn532_excluded_by_profile": True,
        "nrf_slot3_gated": True,
        "resource_acquired": True,
        "resource_released": True,
        # Self-Test is a Device child page; the runtime lease remains owned by
        # the launched top-level Device app throughout the guarded probe.
        "current_owner": "device",
        "current_lease_mask": 1,
    }
    if require_isolated_main_characterization:
        expected.update({
            "status": "failed",
            "detected_receivers": 0,
            "gpio21_stable_high": False,
            "cleanup_complete": False,
        })
    elif require_carrier_csn_characterization:
        expected.update({
            "status": "failed",
            "detected_receivers": 0,
        })
    else:
        expected.update({
            "gpio21_stable_high": True,
            "cleanup_complete": True,
        })
    failures = expect(report, expected, "shield_receiver_probe")
    expected_wire = ({
        "nrf_register_reads": 0,
        "cc_status_reads": 0,
        "spi_bytes_clocked": 0,
    } if (require_isolated_main_characterization or
          require_carrier_csn_characterization) else {
        "nrf_register_reads": 8,
        "cc_status_reads": 2,
        "spi_bytes_clocked": 20,
    })
    if report.get("wire") != expected_wire:
        failures.append(f"unexpected wire bounds: {report.get('wire')!r}")
    if report.get("side_effects") != {
        "nrf_ce_high_events": 0,
        "cc_command_strobes": 0,
        "radio_tx_commands": 0,
    }:
        failures.append(
            f"unexpected probe side effects: {report.get('side_effects')!r}")
    if require_carrier_csn_characterization:
        bus = report.get("bus_line", {})
        failures.extend(expect(bus, {
            "complete": False,
            "samples_per_pull": 32,
            "nrf_nop_reads": 0,
            "bitbang_spi_bytes_clocked": 0,
        }, "shield_receiver_probe.bus_line"))
        nop = bus.get("nrf_nop")
        if not isinstance(nop, list) or len(nop) != 2:
            failures.append(f"unexpected carrier nRF NOP records: {nop!r}")
        elif any(
            row.get("slot") != slot or
            row.get("pull_down_status") != 0xFF or
            row.get("pull_up_status") != 0xFF
            for slot, row in enumerate(nop, start=1)
        ):
            failures.append(f"carrier probe clocked or changed nRF NOP: {nop!r}")
        for field in (
            "idle_pull_down_high_samples", "idle_pull_up_high_samples",
        ):
            value = bus.get(field)
            if not isinstance(value, int) or not 0 <= value <= 32:
                failures.append(f"invalid carrier {field}: {value!r}")
            elif value not in (0, 32):
                failures.append(f"unstable carrier {field}: {value!r}")
        chip_selects = report.get("chip_selects", {})
        failures.extend(expect(chip_selects, {
            "complete": True,
            "samples_per_pin": 32,
        }, "shield_receiver_probe.chip_selects"))
        nrf = chip_selects.get("nrf")
        expected_pins = [(1, 4), (2, 48), (3, 21)]
        if not isinstance(nrf, list) or len(nrf) != 3:
            failures.append(f"unexpected carrier nRF CSN records: {nrf!r}")
        else:
            for row, (slot, gpio) in zip(nrf, expected_pins):
                value = row.get("pull_up_high_samples")
                if row.get("slot") != slot or row.get("gpio") != gpio:
                    failures.append(
                        f"unexpected carrier nRF CSN identity: {row!r}")
                if not isinstance(value, int) or not 0 <= value <= 32:
                    failures.append(
                        f"invalid carrier nRF CSN sample count: {row!r}")
                elif value not in (0, 32):
                    failures.append(
                        f"unstable carrier nRF CSN sample count: {row!r}")
        cc = chip_selects.get("cc1101", {})
        cc_samples = cc.get("pull_up_high_samples")
        if cc.get("gpio") != 5 or not isinstance(cc_samples, int) or not (
                0 <= cc_samples <= 32):
            failures.append(f"unexpected carrier CC1101 CSN record: {cc!r}")
        elif cc_samples not in (0, 32):
            failures.append(f"unstable carrier CC1101 CSN record: {cc!r}")
        for field in ("gpio21_stable_high", "cleanup_complete"):
            if not isinstance(report.get(field), bool):
                failures.append(
                    f"shield_receiver_probe.{field}: expected bool")
        if isinstance(nrf, list) and len(nrf) == 3:
            slot3_samples = nrf[2].get("pull_up_high_samples")
            if slot3_samples == 32:
                failures.extend(expect(report, {
                    "gpio21_stable_high": True,
                    "cleanup_complete": True,
                }, "shield_receiver_probe.carrier_cleanup"))
            elif slot3_samples == 0:
                failures.extend(expect(report, {
                    "gpio21_stable_high": False,
                    "cleanup_complete": False,
                }, "shield_receiver_probe.carrier_cleanup"))
    elif require_isolated_main_characterization:
        bus = report.get("bus_line", {})
        failures.extend(expect(bus, {
            "complete": False,
            "samples_per_pull": 32,
            "nrf_nop_reads": 0,
            "bitbang_spi_bytes_clocked": 0,
        }, "shield_receiver_probe.bus_line"))
        nop = bus.get("nrf_nop")
        if not isinstance(nop, list) or len(nop) != 2:
            failures.append(f"unexpected isolated nRF NOP records: {nop!r}")
        elif any(
            row.get("slot") != slot or
            row.get("pull_down_status") != 0xFF or
            row.get("pull_up_status") != 0xFF
            for slot, row in enumerate(nop, start=1)
        ):
            failures.append(f"isolated probe clocked or changed nRF NOP: {nop!r}")
        for field in (
            "idle_pull_down_high_samples", "idle_pull_up_high_samples",
        ):
            value = bus.get(field)
            if not isinstance(value, int) or not 0 <= value <= 32:
                failures.append(f"invalid isolated {field}: {value!r}")
    elif require_bus_characterization:
        bus = report.get("bus_line", {})
        failures.extend(expect(bus, {
            "complete": True,
            "samples_per_pull": 32,
            "nrf_nop_reads": 4,
            "bitbang_spi_bytes_clocked": 4,
        }, "shield_receiver_probe.bus_line"))
        nop = bus.get("nrf_nop")
        if not isinstance(nop, list) or len(nop) != 2:
            failures.append(f"unexpected nRF NOP characterization: {nop!r}")
        elif [row.get("slot") for row in nop] != [1, 2]:
            failures.append(f"unexpected nRF NOP slots: {nop!r}")
    return failures


def isolated_main_outcome(report: dict[str, Any]) -> str:
    bus = report.get("bus_line", {})
    down = bus.get("idle_pull_down_high_samples")
    up = bus.get("idle_pull_up_high_samples")
    if down == 0 and up == 32:
        return "isolated_main_gpio_follows_pulls"
    if down == 0 and up == 0:
        return "isolated_main_gpio_stuck_low"
    if down == 32 and up == 32:
        return "isolated_main_gpio_stuck_high"
    return "isolated_main_gpio_unstable"


def carrier_csn_outcome(report: dict[str, Any]) -> str:
    chip_selects = report.get("chip_selects", {})
    nrf = chip_selects.get("nrf", [])
    cc = chip_selects.get("cc1101", {})
    samples = [
        row.get("pull_up_high_samples")
        for row in nrf if isinstance(row, dict)
    ]
    samples.append(cc.get("pull_up_high_samples"))
    if len(samples) != 4 or any(not isinstance(value, int)
                                for value in samples):
        return "carrier_csn_characterization_incomplete"
    if any(value == 0 for value in samples):
        return "carrier_csn_stuck_low"
    if any(value != 32 for value in samples):
        return "carrier_csn_unstable"
    bus = report.get("bus_line", {})
    down = bus.get("idle_pull_down_high_samples")
    up = bus.get("idle_pull_up_high_samples")
    if down == 0 and up == 0:
        return "carrier_csn_high_miso_low"
    if down == 32 and up == 32:
        return "carrier_csn_high_miso_high"
    if down == 0 and up == 32:
        return "carrier_csn_high_miso_follows_pulls"
    return "carrier_csn_high_miso_unstable"


def normalize_home(device: Any) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(8):
        if int(state.get("selection", -1)) == 0:
            return trace
        state = action(device, "up")
        trace.append(state)
    raise RuntimeError("could not normalize Home selection")


def navigate_home_to(device: Any, target_id: str) -> list[dict[str, Any]]:
    """Select a Home item by its public identity, not its menu position."""
    trace: list[dict[str, Any]] = []
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(16):
        if state.get("page") != "home":
            raise RuntimeError(
                f"left Home while seeking {target_id!r}: {state.get('page')!r}")
        if state.get("selected_id") == target_id:
            return trace
        state = action(device, "down")
        trace.append(state)
    raise RuntimeError(f"could not select Home item {target_id!r}")


def navigate_device_to(device: Any, target_selection: int) -> list[dict[str, Any]]:
    """Select a Device submenu item from its observable selection index."""
    trace: list[dict[str, Any]] = []
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(8):
        if state.get("page") != "device":
            raise RuntimeError(
                "left Device while seeking selection "
                f"{target_selection}: {state.get('page')!r}")
        selection = int(state.get("device_selection", -1))
        if selection == target_selection:
            return trace
        state = action(device, "down" if selection < target_selection else "up")
        trace.append(state)
    raise RuntimeError(
        f"could not select Device item {target_selection}")


def cleanup_reached_legacy_home(cleanup: dict[str, Any]) -> bool:
    state = cleanup.get("final_state", {})
    return (
        state.get("page") == "home" and
        state.get("runtime_owner") == "none" and
        state.get("lease_mask") == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    image_mode = parser.add_mutually_exclusive_group(required=True)
    image_mode.add_argument("--flash", action="store_true")
    image_mode.add_argument(
        "--reuse-current", action="store_true",
        help=("do not write flash; fail closed unless the running version and "
              "app ELF identity match the supplied exact image"),
    )
    parser.add_argument("--require-bus-characterization", action="store_true")
    parser.add_argument(
        "--require-isolated-main-characterization", action="store_true",
        help=("accept an intentionally absent RF carrier, require pull-only "
              "GPIO13 sampling and reject every SPI clock or receiver read"),
    )
    parser.add_argument(
        "--require-carrier-csn-characterization", action="store_true",
        help=("require pull-up sampling of all four RF carrier chip-select "
              "lines plus GPIO13, and reject every SPI clock or command"),
    )
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    characterization_modes = sum((
        args.require_bus_characterization,
        args.require_isolated_main_characterization,
        args.require_carrier_csn_characterization,
    ))
    if characterization_modes > 1:
        parser.error("characterization requirements are mutually exclusive")
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    probe: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot = query(device, b"metrics", "leshy.boot.v1", "ready")
                failures.extend(expect(boot, {
                    "version": args.expected_version,
                    "app_elf_sha256": app_identity,
                }, "boot"))
                if failures:
                    raise RuntimeError("boot identity differs")
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_reached_legacy_home(cleanup_before):
                    raise RuntimeError("initial cleanup did not reach Home/lease 0")

                trace.extend(normalize_home(device))
                trace.extend(navigate_home_to(device, "device"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "device",
                    "device_selection": 0,
                    "lease_mask": 1,
                }, "device_menu"))
                trace.extend(navigate_device_to(device, 1))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "page": "self_test",
                    "self_test_view": "mode_menu",
                    "self_test_mode": "quick",
                    "lease_mask": 1,
                }, "mode_menu"))
                trace.append(action(device, "down"))
                state = action(device, "right")
                trace.append(state)
                failures.extend(expect(state, {
                    "self_test_view": "preflight",
                    "self_test_mode": "full_guided",
                    "lease_mask": 1,
                }, "preflight"))

                for expected_visual in (
                    "dialog_confirm", "unavailable", "degraded", "error",
                    "running",
                ):
                    state = action(device, "right")
                    trace.append(state)
                    failures.extend(expect(state, {
                        "self_test_view": "visual_check",
                        "self_test_visual_state": expected_visual,
                        "self_test_mode": "full_guided",
                        "lease_mask": 1,
                    }, f"visual_{expected_visual}"))

                # The next public action synchronously runs only the guarded
                # receiver-identity probe in plan v4, then enters its result.
                state = action(device, "right")
                trace.append(state)
                probe = query(
                    device, b"hardware.shield.receivers",
                    PROBE_SCHEMA, "report",
                )
                failures.extend(probe_contract_failures(
                    probe, args.require_bus_characterization,
                    args.require_isolated_main_characterization,
                    args.require_carrier_csn_characterization))
                safe_outputs = query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state",
                )
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True,
                    "buzzer_level": "low",
                }, "safe_outputs"))
            except Exception as error:
                failures.append(
                    f"probe_phase: {type(error).__name__}: {error}")
            finally:
                cleanup_after = best_effort_cleanup(device)
                if not cleanup_reached_legacy_home(cleanup_after):
                    failures.append("cleanup_after: terminal Home/lease 0 unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    detected = int(probe.get("detected_receivers", 0))
    outcome = (carrier_csn_outcome(probe)
               if args.require_carrier_csn_characterization else (
                   isolated_main_outcome(probe)
                   if args.require_isolated_main_characterization else (
                   "all_receivers_detected" if detected == 3 else
                   "partial_receivers_detected" if detected > 0 else
                   "no_receivers_detected")))
    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": not failures,
        "failures": failures,
        "outcome": outcome,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "exact_image_reused": args.reuse_current,
        },
        "boot": boot,
        "shield_receiver_probe": probe,
        "safe_outputs": safe_outputs,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "limits": {
            "read_only_identity": True,
            "rf_transmission_authorized": False,
            "isolated_main_characterization":
                args.require_isolated_main_characterization,
            "rf_carrier_required_absent":
                args.require_isolated_main_characterization,
            "carrier_csn_characterization":
                args.require_carrier_csn_characterization,
            "rf_carrier_required_present":
                args.require_carrier_csn_characterization,
            "storage_required": False,
            "stage_or_phase_promotion": False,
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "outcome": result["outcome"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
