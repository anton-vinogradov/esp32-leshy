#!/usr/bin/env python3
"""Focused physical HIL for Leshy-owned per-session Wi-Fi identities."""

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


SCHEMA = "leshy.wifi_own_identity_hil.run.v1"
IDENTITY_SCHEMA = "leshy.wifi.own_identity.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def identity_state(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"wifi.identity.state", IDENTITY_SCHEMA, "state")


def focus_device(device: PassiveSerial) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(20):
        if state.get("selected_id") == "device":
            return state
        state = action(device, "down")
    raise RuntimeError(f"cannot focus Device: {state}")


def focus_wifi(device: PassiveSerial) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(20):
        if state.get("selected_id") == "wifi":
            return state
        state = action(device, "up")
    raise RuntimeError(f"cannot focus Wi-Fi: {state}")


def wait_private_application(
        device: PassiveSerial, after_generation: int,
        timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = identity_state(device)
        if (last.get("mode") == "private_per_session" and
                last.get("provenance") == "generated_private_session" and
                int(last.get("generation", 0)) > after_generation and
                int(last.get("station_applications", 0)) > 0 and
                last.get("failures") == 0 and
                last.get("last_error") == 0 and
                last.get("local_admin") is True and
                last.get("unicast") is True and
                last.get("differs_from_hardware") is True and
                last.get("raw_address_retained") is False and
                last.get("nearby_identity_modified") is False):
            return last
        time.sleep(0.2)
    raise RuntimeError(f"private identity was not applied: {last}")


def open_networks(device: PassiveSerial) -> dict[str, Any]:
    home = focus_wifi(device)
    require(home.get("runtime_owner") == "none" and
            home.get("lease_mask") == 0,
            f"Wi-Fi Home is not clean: {home}")
    menu = action(device, "right")
    require(menu.get("page") == "survey" and
            menu.get("runtime_owner") == "wifi" and
            menu.get("wifi_product_view") == "menu",
            f"cannot open Wi-Fi tasks: {menu}")
    networks = action(device, "right")
    require(networks.get("page") == "survey" and
            networks.get("wifi_product_view") == "networks",
            f"cannot start nearby-network receiver: {networks}")
    return networks


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
    if status or args.source_commit != head:
        parser.error("exact HIL requires one clean committed candidate/harness")

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
        "source_commit": head,
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
    try:
        flash_candidate(args.port, retained["firmware"], 0x10000,
                        args.flash_baud)
        record["flash_count"] = 1
        write_json(args.output / "run.json", record)
        time.sleep(1.0)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 30.0)
            metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics.get("version") == args.expected_version and
                    metrics.get("app_elf_sha256") == app_identity,
                    f"wrong candidate booted: {metrics}")
            recovery = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == EXPECTED_CID and
                    recovery.get("observed_fingerprint") == EXPECTED_CID and
                    recovery.get("mounted_read_only") is True and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"exact product media unavailable: {recovery}")

            admission = TemporaryProtectedUiAdmissionHil(device, app_identity)
            admission.start()
            focus_device(device)
            opened_device = action(device, "right")
            require(opened_device.get("page") == "device",
                    f"cannot open Device: {opened_device}")
            action(device, "down")
            connection_focus = action(device, "down")
            require(connection_focus.get("device_selection") == 2,
                    f"cannot focus Connection: {connection_focus}")
            connection = action(device, "right")
            action(device, "down")
            privacy_focus = action(device, "down")
            require(connection.get("page") == "connectivity" and
                    privacy_focus.get("connectivity_selection") == 2,
                    f"cannot focus Identity privacy: {privacy_focus}")
            privacy = action(device, "right")
            require(privacy.get("connectivity_view") == 3,
                    f"cannot open Identity privacy: {privacy}")

            initial_identity = identity_state(device)
            if int(privacy.get("connectivity_selection", 0)) == 1:
                action(device, "up")
                action(device, "right")
            hardware_focus = action(device, "down")
            hardware_selected_ui = action(device, "right")
            hardware_selected = identity_state(device)
            require(hardware_focus.get("connectivity_selection") == 1 and
                    hardware_selected.get("mode") == "hardware" and
                    hardware_selected.get("provenance") == "hardware" and
                    hardware_selected.get("raw_address_retained") is False,
                    f"hardware opt-out is not truthful: {hardware_selected_ui} "
                    f"{hardware_selected}")
            private_focus = action(device, "up")
            private_selected_ui = action(device, "right")
            private_selected = identity_state(device)
            require(private_focus.get("connectivity_selection") == 0 and
                    private_selected.get("mode") == "private_per_session" and
                    private_selected.get("persisted_value") == "mode_only" and
                    private_selected.get("raw_address_retained") is False,
                    f"private mode was not restored: {private_selected_ui} "
                    f"{private_selected}")

            action(device, "left")
            cleanup_before_first = best_effort_cleanup(device)
            require(cleanup_before_first.get("complete") is True,
                    f"cannot leave privacy UI: {cleanup_before_first}")
            before_generation = int(private_selected.get("generation", 0))
            first_networks = open_networks(device)
            first_application = wait_private_application(
                device, before_generation)
            cleanup_between = best_effort_cleanup(device)
            require(cleanup_between.get("complete") is True,
                    f"first receiver cleanup failed: {cleanup_between}")

            second_networks = open_networks(device)
            second_application = wait_private_application(
                device, int(first_application["generation"]))
            require(int(second_application["station_applications"]) >
                    int(first_application["station_applications"]),
                    "second receiver session did not apply a fresh identity")
            cleanup_final = best_effort_cleanup(device)
            require(cleanup_final.get("complete") is True,
                    f"second receiver cleanup failed: {cleanup_final}")
            admission.close()
            final = query(device, b"ui.state", "leshy.ui.v1", "state")
            final_identity = identity_state(device)
            safe_outputs = query(
                device, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            require(final.get("page") == "home" and
                    final.get("runtime_owner") == "none" and
                    final.get("lease_mask") == 0 and
                    final_identity.get("mode") == "private_per_session" and
                    final_identity.get("raw_address_retained") is False and
                    final_identity.get("failures") == 0,
                    f"final cleanup/identity failed: {final} {final_identity}")
            require(safe_outputs.get("buzzer_inactive") is True and
                    safe_outputs.get("nrf_ce_inactive") is True and
                    safe_outputs.get("software_quiesce_complete") is True,
                    f"safe outputs not preserved: {safe_outputs}")

            record.update({
                "status": "pass",
                "outcome": "pass",
                "boot": metrics,
                "storage": recovery,
                "connection": connection,
                "privacy": privacy,
                "initial_identity": initial_identity,
                "hardware_selected": hardware_selected,
                "private_selected": private_selected,
                "first_networks": first_networks,
                "first_application": first_application,
                "second_networks": second_networks,
                "second_application": second_application,
                "safe_outputs": safe_outputs,
                "protected_ui_admission": admission.evidence(),
                "final": final,
                "final_identity": final_identity,
                "cleanup": {
                    "before_first": cleanup_before_first,
                    "between": cleanup_between,
                    "final": cleanup_final,
                },
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
        if admission is not None:
            try:
                with PassiveSerial(
                        args.port, 115200, timeout=0.25) as cleanup_device:
                    synchronize_console(cleanup_device, 10.0)
                    admission.rebind(cleanup_device)
                    admission.close()
                record["protected_ui_admission"] = admission.evidence()
            except Exception as cleanup_exc:
                record["cleanup_error"] = str(cleanup_exc)
        write_json(args.output / "run.json", record)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
