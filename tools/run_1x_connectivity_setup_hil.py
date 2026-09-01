#!/usr/bin/env python3
"""Focused, no-radio-TX HIL for Device -> Connection (WF-16)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import action, best_effort_cleanup, query
from run_1x_ui_typography_hil import normalize_home
from temporary_device_lock_hil import TemporaryProtectedUiAdmissionHil


SCHEMA = "leshy.connectivity_setup_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def web_state(device: PassiveSerial) -> dict[str, Any]:
    return query(
        device, b"companion.web.state", "leshy.companion.web.v1", "state")


def focus_device(device: PassiveSerial) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(20):
        if state.get("selected_id") == "device":
            return state
        state = action(device, "down")
    raise RuntimeError(f"cannot focus Device: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")

    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    candidate_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", args.source_commit, head],
        cwd=root, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode == 0
    if status or not candidate_is_ancestor:
        parser.error("exact HIL requires a clean committed candidate/harness")

    args.output.mkdir(parents=True)
    retained = {
        "firmware": args.output / "firmware.bin",
        "elf": args.output / "firmware.elf",
        "map": args.output / "firmware.map",
    }
    shutil.copyfile(args.firmware, retained["firmware"])
    shutil.copyfile(args.elf, retained["elf"])
    shutil.copyfile(args.map, retained["map"])
    app_identity = app_elf_sha256(retained["firmware"])
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "harness_commit": head,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(retained["firmware"]),
            "elf_sha256": sha256_file(retained["elf"]),
            "map_sha256": sha256_file(retained["map"]),
            "app_elf_sha256": app_identity,
        },
        "target": {
            "port": args.port,
            "ports_opened": [args.port],
            "clone_ports_opened": 0,
            "cardputer_ports_opened": 0,
        },
        "host_network_tools_invoked": False,
        "active_mac_wifi_touched": False,
        "wifi_softap_started": False,
        "raw_radio_tx_commands": 0,
    }
    write_json(args.output / "run.json", record)

    admission: TemporaryProtectedUiAdmissionHil | None = None
    device: PassiveSerial | None = None
    try:
        flash_candidate(args.port, retained["firmware"], 0x10000,
                        args.flash_baud)
        record["flash_count"] = 1
        write_json(args.output / "run.json", record)
        time.sleep(1.0)
        with PassiveSerial(args.port, 115200, timeout=0.25) as active:
            device = active
            synchronize_console(active, 30.0)
            metrics = query(active, b"metrics", "leshy.boot.v1", "ready")
            require(metrics.get("version") == args.expected_version and
                    metrics.get("app_elf_sha256") == app_identity,
                    f"wrong candidate booted: {metrics}")
            recovery = query(
                active, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == EXPECTED_CID and
                    recovery.get("observed_fingerprint") == EXPECTED_CID and
                    recovery.get("mounted_read_only") is True and
                    recovery.get("blocked_write_attempts") == 0 and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"exact product media unavailable: {recovery}")

            admission = TemporaryProtectedUiAdmissionHil(active, app_identity)
            admission.start()
            home = focus_device(active)
            opened_device = action(active, "right")
            require(opened_device.get("page") == "device" and
                    opened_device.get("runtime_owner") == "device" and
                    opened_device.get("lease_mask") == 1,
                    f"cannot open Device: {opened_device}")
            connection_focus = action(active, "down")
            connection_focus = action(active, "down")
            require(connection_focus.get("device_selection") == 2,
                    f"cannot focus Connection: {connection_focus}")

            connection = action(active, "right")
            inert_initial = web_state(active)
            require(connection.get("page") == "connectivity" and
                    connection.get("connectivity_view") == 0 and
                    connection.get("connectivity_selection") == 0 and
                    connection.get("runtime_owner") == "device" and
                    inert_initial.get("overlay_open") is False and
                    inert_initial.get("authorized") is False and
                    inert_initial.get("server_active") is False and
                    inert_initial.get("credential_present") is False and
                    inert_initial.get("network_core_ready") is False,
                    f"Connection menu is not inert: {connection} {inert_initial}")

            usb = action(active, "right")
            inert_usb = web_state(active)
            require(usb.get("page") == "connectivity" and
                    usb.get("connectivity_view") == 1 and
                    inert_usb.get("authorized") is False and
                    inert_usb.get("server_active") is False and
                    inert_usb.get("credential_present") is False and
                    inert_usb.get("network_core_ready") is False,
                    f"USB guide changed networking: {usb} {inert_usb}")
            menu = action(active, "left")
            wifi_focus = action(active, "down")
            require(menu.get("connectivity_view") == 0 and
                    wifi_focus.get("connectivity_selection") == 1,
                    f"cannot select temporary Wi-Fi: {menu} {wifi_focus}")

            staged_ui = action(active, "right", timeout=45.0)
            staged = web_state(active)
            require(staged_ui.get("page") == "targets" and
                    staged_ui.get("runtime_owner") == "targets" and
                    staged.get("overlay_open") is True and
                    staged.get("authorized") is False and
                    staged.get("server_active") is False and
                    staged.get("credential_present") is False and
                    staged.get("network_core_ready") is False and
                    staged.get("associated_stations") == 0,
                    f"first Wi-Fi selection crossed confirmation: "
                    f"{staged_ui} {staged}")

            stopped_ui = action(active, "left")
            stopped = web_state(active)
            require(stopped_ui.get("page") == "targets" and
                    stopped.get("overlay_open") is False and
                    stopped.get("authorized") is False and
                    stopped.get("server_active") is False and
                    stopped.get("credential_present") is False and
                    stopped.get("network_core_ready") is False and
                    stopped.get("cleanup_complete") is True,
                    f"staged Wi-Fi cleanup failed: {stopped_ui} {stopped}")

            cleanup = best_effort_cleanup(active)
            require(cleanup.get("complete") is True,
                    f"final UI cleanup failed: {cleanup}")
            admission.close()
            final = query(active, b"ui.state", "leshy.ui.v1", "state")
            final_web = web_state(active)
            require(final.get("page") == "home" and
                    final.get("runtime_owner") == "none" and
                    final.get("lease_mask") == 0 and
                    final_web.get("authorized") is False and
                    final_web.get("server_active") is False and
                    final_web.get("credential_present") is False and
                    final_web.get("network_core_ready") is False,
                    f"final cleanup is incomplete: {final} {final_web}")

            record.update({
                "status": "pass",
                "outcome": "pass",
                "boot": metrics,
                "storage": recovery,
                "home": home,
                "device": opened_device,
                "connection": connection,
                "usb_guide": usb,
                "temporary_wifi_staged": staged,
                "temporary_wifi_stopped": stopped,
                "protected_ui_admission": admission.evidence(),
                "final": final,
                "final_web": final_web,
                "credential_created": False,
                "credential_exported": False,
                "survey_library_network_dependency_created": False,
            })
            write_json(args.output / "run.json", record)
        print(json.dumps({
            "schema": SCHEMA,
            "status": "pass",
            "run": str(args.output / "run.json"),
        }, sort_keys=True))
        return 0
    except Exception as exc:
        record["status"] = "failed"
        record["outcome"] = "failed"
        record["error"] = str(exc)
        if admission is not None and device is not None:
            try:
                admission.close()
                record["protected_ui_admission"] = admission.evidence()
            except Exception as cleanup_exc:
                record["cleanup_error"] = str(cleanup_exc)
        write_json(args.output / "run.json", record)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
