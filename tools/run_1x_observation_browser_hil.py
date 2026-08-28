#!/usr/bin/env python3
"""Validate the user-facing Survey observation browser on exact hardware."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_passive_ble_hil import (
    DUAL_MASK,
    committed_failures,
    export_failures,
    running_failures,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    recovered_failures,
    reset_capture,
    open_latest_library,
    valid_cid,
    wait_ui_state,
)


RUN_SCHEMA = "leshy.observation_browser_hil.run.v1"


def browser_failures(state: dict[str, Any], *, view: str, filter_name: str,
                     focused: bool, selected_radio: str | None = None) -> list[str]:
    failures = expect(state, {
        "view": view,
        "filter": filter_name,
        "filter_focused": focused,
        "read_only_query": True,
        "radio_touched": False,
        "storage_touched": False,
    }, f"browser.{filter_name}.{view}")
    total = state.get("total")
    visible = state.get("visible")
    if not isinstance(total, int) or total < 2:
        failures.append(f"browser.{filter_name}: expected populated session")
    if not isinstance(visible, int) or visible < 1:
        failures.append(f"browser.{filter_name}: expected visible observations")
    elif isinstance(total, int) and visible > total:
        failures.append(f"browser.{filter_name}: visible exceeds total")
    if selected_radio is None:
        return failures
    failures.extend(expect(state, {
        "selected": True,
        "selected_radio": selected_radio,
        "history_valid": True,
    }, f"browser.{filter_name}.selection"))
    samples = state.get("history_samples")
    retained = state.get("history_retained")
    minimum = state.get("history_min_rssi_dbm")
    maximum = state.get("history_max_rssi_dbm")
    latest = state.get("history_latest_rssi_dbm")
    if not isinstance(samples, int) or samples < 1:
        failures.append(f"browser.{filter_name}: history sample count invalid")
    if not isinstance(retained, int) or retained < 1 or retained > 12:
        failures.append(f"browser.{filter_name}: retained history outside 1..12")
    if isinstance(samples, int) and isinstance(retained, int) and \
            retained != min(samples, 12):
        failures.append(f"browser.{filter_name}: retained history mismatch")
    if not all(isinstance(value, int) for value in (minimum, maximum, latest)):
        failures.append(f"browser.{filter_name}: RSSI bounds missing")
    elif not minimum <= latest <= maximum:
        failures.append(f"browser.{filter_name}: RSSI bounds inconsistent")
    return failures


def paused_failures(state: dict[str, Any]) -> list[str]:
    failures = expect(state, {
        "page": "survey",
        "runtime_owner": "survey",
        "lease_mask": 15,
        "survey_workflow_state": "running",
        "survey_product_status": "paused",
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_cleanup_complete": False,
        "survey_product_source_active": False,
        "survey_product_scan_active": False,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_timeline_state": "stopped",
        "survey_timeline_healthy": True,
        "survey_timeline_queue_depth": 0,
        "survey_timeline_overflow": 0,
        "survey_timeline_wifi_dropped": 0,
        "survey_timeline_ble_dropped": 0,
        "survey_timeline_archive_status": "finalized",
    }, "paused")
    observations = state.get("survey_observations")
    forwarded = state.get("survey_forwarded")
    if not isinstance(observations, int) or observations < 2 or \
            forwarded != observations:
        failures.append("paused.observations: snapshot accounting mismatch")
    return failures


def main() -> int:
    from capture_1x_ui import PassiveSerial, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    parser.add_argument("--post-flash-ready-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be exactly 32 uppercase hexadecimal characters")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    browsers: dict[str, Any] = {}
    boot_before: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    timing_before: dict[str, Any] = {}
    running: dict[str, Any] = {}
    paused: dict[str, Any] = {}
    committed: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    boot_after: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    timing_after: dict[str, Any] = {}
    exported: dict[str, Any] = {}
    final: dict[str, Any] = {}
    cleanup_after: dict[str, Any] = {"attempted": False}
    post_flash: dict[str, Any] = {}

    try:
        if args.flash:
            flash_candidate(args.port, candidate, args.flash_offset,
                            args.flash_baud)
            # esptool already hard-resets the target. Wait for that boot to
            # reach the command loop before issuing our independent cold-reset
            # proof; resetting one second into SD recovery can interrupt a live
            # card transaction and tests the harness rather than the product.
            time.sleep(0.5)
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                synchronize_console(device, args.post_flash_ready_seconds)
                post_flash_ready = query(
                    device, b"metrics", "leshy.boot.v1", "ready",
                )
                post_flash_recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                post_flash = {
                    "ready": post_flash_ready,
                    "recovery": post_flash_recovery,
                }
                failures.extend(boot_failures(
                    post_flash_ready, post_flash_recovery,
                    args.expected_version, app_identity, args.expected_cid,
                ))
            if failures:
                raise RuntimeError("post-flash boot contract failed")
        boot_before, recovery_before, timing_before = reset_capture(
            args.port, args.output, "boot-before", args.boot_seconds
        )
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state",
                )
                failures.extend(boot_failures(
                    boot_before, recovery_before, args.expected_version,
                    app_identity, args.expected_cid,
                ))
                before_generation = int(recovery_before.get("generation", 0))
                if failures:
                    raise RuntimeError("preflight boot contract failed")

                trace.append(action(device, "down"))
                setup = action(device, "select")
                trace.append(setup)
                failures.extend(expect(setup, {
                    "page": "survey",
                    "survey_setup_view": "plan",
                    "survey_source_selected_mask": DUAL_MASK,
                    "survey_source_selected_count": 2,
                    "survey_source_can_start": True,
                }, "setup"))
                captures["setup"] = capture(device, frames, "setup")
                trace.append(action(device, "down"))
                trace.append(action(device, "select"))

                if not failures:
                    running = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "running" and
                            state.get("survey_product_wifi_scan_cycles", 0) >= 1 and
                            state.get("survey_product_ble_scan_cycles", 0) >= 1 and
                            state.get("survey_scan_accepted", 0) >= 1 and
                            state.get("survey_ble_scan_accepted", 0) >= 1 and
                            state.get("survey_timeline_archived_windows", 0) >= 4
                        ),
                        70.0,
                        "dual Survey did not populate both browser sources",
                    )
                    trace.append(running)
                    failures.extend(running_failures(running))

                if not failures:
                    trace.append(action(device, "up"))
                    paused = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "paused" and
                            state.get("survey_timeline_state") == "stopped"
                        ),
                        12.0,
                        "browser interaction did not freeze the RF snapshot",
                    )
                    trace.append(paused)
                    failures.extend(paused_failures(paused))
                    captures["all_list"] = capture(device, frames, "all-list")
                    focused = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["all_focused"] = focused
                    failures.extend(browser_failures(
                        focused, view="list", filter_name="all", focused=True
                    ))
                    trace.append(action(device, "select"))
                    menu = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["filter_menu"] = menu
                    failures.extend(browser_failures(
                        menu, view="filter", filter_name="all", focused=True
                    ))
                    captures["filter_menu"] = capture(
                        device, frames, "filter-menu"
                    )

                if not failures:
                    trace.append(action(device, "down"))
                    trace.append(action(device, "select"))
                    wifi_focused = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["wifi_focused"] = wifi_focused
                    failures.extend(browser_failures(
                        wifi_focused, view="list", filter_name="wifi",
                        focused=True,
                    ))
                    trace.append(action(device, "down"))
                    wifi_list = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["wifi_list"] = wifi_list
                    failures.extend(browser_failures(
                        wifi_list, view="list", filter_name="wifi",
                        focused=False, selected_radio="wifi",
                    ))
                    captures["wifi_list"] = capture(device, frames, "wifi-list")
                    trace.append(action(device, "select"))
                    wifi_detail = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["wifi_detail"] = wifi_detail
                    failures.extend(browser_failures(
                        wifi_detail, view="detail", filter_name="wifi",
                        focused=False, selected_radio="wifi",
                    ))
                    captures["wifi_detail"] = capture(
                        device, frames, "wifi-detail"
                    )

                if not failures:
                    trace.append(action(device, "back"))
                    trace.append(action(device, "up"))
                    trace.append(action(device, "select"))
                    trace.append(action(device, "down"))
                    trace.append(action(device, "select"))
                    ble_focused = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["ble_focused"] = ble_focused
                    failures.extend(browser_failures(
                        ble_focused, view="list", filter_name="ble", focused=True
                    ))
                    trace.append(action(device, "down"))
                    ble_list = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["ble_list"] = ble_list
                    failures.extend(browser_failures(
                        ble_list, view="list", filter_name="ble",
                        focused=False, selected_radio="ble",
                    ))
                    captures["ble_list"] = capture(device, frames, "ble-list")
                    trace.append(action(device, "right"))
                    ble_detail = query(
                        device, b"survey.browser",
                        "leshy.survey.browser.v1", "state",
                    )
                    browsers["ble_detail"] = ble_detail
                    failures.extend(browser_failures(
                        ble_detail, view="detail", filter_name="ble",
                        focused=False, selected_radio="ble",
                    ))
                    captures["ble_detail"] = capture(
                        device, frames, "ble-detail"
                    )

                if not failures:
                    trace.append(action(device, "select"))
                    committed = wait_ui_state(
                        device,
                        lambda state: (
                            state.get("survey_product_status") == "committed" and
                            state.get("survey_workflow_state") == "result"
                        ),
                        25.0,
                        "browser Survey did not commit",
                    )
                    trace.append(committed)
                    failures.extend(committed_failures(
                        committed, before_generation + 1
                    ))
                    captures["committed"] = capture(
                        device, frames, "committed"
                    )
                    trace.append(action(device, "back"))
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_before = best_effort_cleanup(device)
                if not cleanup_before.get("complete"):
                    failures.append("cleanup_before: terminal zero-lease state unproven")

        if committed and not failures:
            boot_after, recovery_after, timing_after = reset_capture(
                args.port, args.output, "boot-after", args.boot_seconds
            )
            generation = int(committed["survey_generation"])
            observations = int(committed["survey_observations"])
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                try:
                    synchronize_console(device)
                    recovery_after = query(
                        device, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state",
                    )
                    failures.extend(boot_failures(
                        boot_after, recovery_after, args.expected_version,
                        app_identity, args.expected_cid,
                    ))
                    failures.extend(recovered_failures(
                        recovery_after, generation, observations,
                        args.expected_cid,
                    ))
                    open_latest_library(device, trace)
                    trace.append(action(device, "right"))
                    captures["library_detail"] = capture(
                        device, frames, "library-detail"
                    )
                    trace.append(action(device, "right"))
                    exported = query(
                        device, b"library.export",
                        "leshy.library.export.v1", "artifact",
                    )
                    failures.extend(export_failures(
                        exported, generation, observations
                    ))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                    final = query(device, b"ui.state", "leshy.ui.v1", "state")
                    failures.extend(expect(final, {
                        "page": "home",
                        "runtime_owner": "none",
                        "lease_mask": 0,
                    }, "final"))
                except Exception as error:
                    failures.append(f"post_boot: {type(error).__name__}: {error}")
                finally:
                    cleanup_after = best_effort_cleanup(device)
                    if not cleanup_after.get("complete"):
                        failures.append("cleanup_after: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
        },
        "expected_cid": args.expected_cid,
        "post_flash": post_flash,
        "boot_before": {"ready": boot_before, "recovery": recovery_before,
                        "timing": timing_before},
        "running": running,
        "paused": paused,
        "browser": browsers,
        "committed": committed,
        "cleanup_before": cleanup_before,
        "boot_after": {"ready": boot_after, "recovery": recovery_after,
                       "timing": timing_after},
        "library_export": exported,
        "final": final,
        "cleanup_after": cleanup_after,
        "captures": captures,
        "trace": trace,
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": result["failures"],
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
