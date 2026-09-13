#!/usr/bin/env python3
"""Exact two-DIV AP-name baseline; no laptop networking or DUT reflash.

Private full-flash backup must exist and match its hash before any fixture write.
Fixed WPA2 AP only; no injection, deauthentication, DHCP, routing or Internet.
This exercises the existing SDK AP-name path, not client-name provenance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from esp_app_identity import app_elf_sha256, app_elf_sha256_from_bytes
from profile_hil_board import serial_metadata
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import query, action, capture, best_effort_cleanup
from run_1x_prerelease_hil import esptool_environment

SCHEMA = "leshy.hil.wifi_name_fixture.v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_hash(bssid):
    value = 2166136261
    for byte in bytes.fromhex(bssid):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def exact_port(port, expected):
    actual = serial_metadata(port)["serial_number"].replace(":", "").lower()
    if actual != expected.replace(":", "").lower():
        raise RuntimeError("physical board identity mismatch")


def fixture_query(device, command, timeout=3):
    device.reset_input_buffer()
    device.write(command.encode() + b"\n")
    return read_json(device, SCHEMA, "state", timeout)


def fixture_ready(device):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            return fixture_query(device, "state", 1)
        except TimeoutError:
            pass
    raise TimeoutError("fixture did not become ready")


def require(value, why):
    if not value:
        raise RuntimeError(why)

def flash_exact(port, image, offset, verify=False):
    base = [sys.executable, "-m", "esptool", "--chip", "esp32s3",
            "--port", port, "--baud", "921600"]
    env = esptool_environment()
    subprocess.run(base + ["--after", "no_reset", "write_flash", hex(offset),
                          str(image)], env=env, check=True, timeout=180)
    if verify:
        subprocess.run(base + ["--before", "no_reset", "--after", "no_reset",
                              "verify_flash", hex(offset), str(image)],
                       env=env, check=True, timeout=120)
    subprocess.run(base + ["--before", "no_reset", "--after", "watchdog_reset",
                          "read_mac"], env=env, check=True, timeout=30)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dut-port", required=True)
    p.add_argument("--dut-mac", required=True)
    p.add_argument("--dut-app-sha", required=True)
    p.add_argument("--fixture-port", required=True)
    p.add_argument("--fixture-mac", required=True)
    p.add_argument("--fixture-image", type=Path, required=True)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--backup-sha", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    require(args.dut_port != args.fixture_port, "roles must use different ports")
    require(args.dut_mac != args.fixture_mac, "roles must use different boards")
    exact_port(args.dut_port, args.dut_mac)
    exact_port(args.fixture_port, args.fixture_mac)
    require(args.backup.stat().st_size == 0x1000000 and
            sha(args.backup) == args.backup_sha, "full backup is not exact")
    with args.backup.open("rb") as saved:
        saved.seek(0x10000)
        original_app = app_elf_sha256_from_bytes(saved.read(512))
    require(not args.output.exists(), "output must be new")
    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    image = args.output / "fixture.bin"
    shutil.copyfile(args.fixture_image, image)
    fixture_app = app_elf_sha256(image)
    report = {
        "schema": "leshy.wifi_name_two_board.run.v1",
        "status": "in_progress", "failures": [], "restore_complete": False,
        "dut_app_elf_sha256": args.dut_app_sha,
        "fixture_app_elf_sha256": fixture_app,
        "fixture_image_sha256": sha(image),
        "backup_sha256": args.backup_sha, "original_app_elf_sha256": original_app,
        "scope": "sdk_ap_hidden_visible_hidden_not_client_frame_integration",
        "states": {}, "screens": {},
    }

    def checkpoint(step):
        report["step"] = step
        report["updated_unix_s"] = time.time()
        temporary = args.output / "run.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(args.output / "run.json")

    flashed = False
    checkpoint("preflight")
    try:
        with PassiveSerial(args.dut_port, 115200, timeout=0.1) as dut:
            synchronize_console(dut, 10)
            boot, _ = stabilized_boot_metrics(dut)
            require(boot["app_elf_sha256"] == args.dut_app_sha, "wrong DUT image")
            before = query(dut, b"ui.state", "leshy.ui.v1", "state")
            require(before["page"] == "home" and before["lease_mask"] == 0,
                    "DUT must be idle Home")
            report["before"] = before
        checkpoint("flash_fixture")
        exact_port(args.fixture_port, args.fixture_mac)
        flashed = True  # Even a partially failed flash requires restoration.
        flash_exact(args.fixture_port, image, 0x10000)
        with PassiveSerial(args.fixture_port, 115200, timeout=0.1) as fixture, \
             PassiveSerial(args.dut_port, 115200, timeout=0.1) as dut:
            initial = fixture_ready(fixture)
            require(initial["app_elf_sha256"] == fixture_app and
                    initial["mac"] == args.fixture_mac.replace(":", "").lower() and
                    not initial["active"] and not initial["radio_started"] and
                    initial["watchdog"], "fixture boot/identity not safe")
            report["fixture_boot"] = initial
            synchronize_console(dut, 10)

            def ui():
                return query(dut, b"ui.state", "leshy.ui.v1", "state")

            try:
                checkpoint("open_networks")
                s = ui()
                for _ in range(12):
                    if s["selection"] == 0:
                        break
                    s = action(dut, "up")
                action(dut, "right")
                require(ui()["wifi_product_view"] == "menu", "Wi-Fi root not open")
                action(dut, "right")
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    s = ui()
                    if s["wifi_product_view"] == "networks" and s.get(
                            "survey_product_wifi_scan_cycles", 0) >= 1:
                        break
                    time.sleep(0.15)
                require(s["wifi_product_view"] == "networks", "networks did not start")
                checkpoint("start_hidden_fixture")
                nonce = secrets.token_hex(8)
                started = fixture_query(fixture,
                    f"begin {fixture_app} {initial['mac']} {nonce}")
                require(started["active"] and started["hidden"] and
                        started["radio_started"] and started["power_quarter_dbm"] == 8,
                        "fixed hidden AP did not start")
                report["fixture_started"] = started
                expected_identity = identity_hash(started["bssid"])
                checkpoint("select_exact_hidden_bssid")
                # Use actual navigation and exact identity; never the SSID of
                # an unrelated nearby AP. No test-only DUT mutation is needed.
                deadline = time.monotonic() + 18
                while time.monotonic() < deadline:
                    s = ui()
                    if s["wifi_network_selected_identity_hash"] == expected_identity:
                        break
                    if s["wifi_network_selection"] + 1 >= s["wifi_network_visible_size"]:
                        for _ in range(32):
                            if s["wifi_network_selection"] == 0: break
                            s = action(dut, "up")
                        time.sleep(0.15)
                    else:
                        action(dut, "down")
                require(s["wifi_network_selected_identity_hash"] == expected_identity,
                        "fixture BSSID not observed in bounded passive window")
                action(dut, "right")

                def observe(name, known, minimum_samples=None):
                    checkpoint(name)
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        detail = query(dut, b"wifi.network.detail",
                                       "leshy.wifi.network_detail.v1", "state")
                        require(detail["identity_hash"] == expected_identity,
                                "selected BSSID changed")
                        require(detail["active"] and detail["passive"] and
                                not detail["active_probe_allowed"], "DUT is not live RX-only")
                        if detail["ssid_known"] == known and (
                                minimum_samples is None or detail["signal_samples"] >= minimum_samples):
                            report["states"][name] = detail
                            report["screens"][name] = capture(dut, frames, name)
                            checkpoint(name + "_observed")
                            return detail
                        time.sleep(0.2)
                    raise TimeoutError(name + " not observed")

                hidden = observe("hidden", False)
                negative = observe("hidden_still_unknown", False, hidden["signal_samples"] + 2)
                checkpoint("reveal_same_ap")
                visible = fixture_query(fixture, "visible " + nonce)
                require(visible["active"] and not visible["hidden"] and
                        visible["bssid"] == started["bssid"], "reveal changed fixture identity")
                report["fixture_visible"] = visible
                known = observe("visible_name", True, negative["signal_samples"] + 1)
                require(known["hidden_resolutions"] > hidden["hidden_resolutions"],
                        "catalog did not record hidden-name resolution")
                checkpoint("hide_again")
                again = fixture_query(fixture, "hidden " + nonce)
                require(again["active"] and again["hidden"], "fixture did not hide again")
                report["fixture_hidden_again"] = again
                observe("known_name_retained", True, known["signal_samples"] + 2)
                stopped = fixture_query(fixture, "stop")
                require(not stopped["active"] and not stopped["radio_started"], "AP did not stop")
                report["fixture_stop"] = stopped
                # Independently exercise the hard deadline without host keepalive.
                checkpoint("fixture_deadline")
                final_nonce = secrets.token_hex(8)
                fixture_query(fixture, f"begin {fixture_app} {initial['mac']} {final_nonce}")
                deadline = time.monotonic() + 64
                while time.monotonic() < deadline:
                    ended = fixture_query(fixture, "state")
                    if not ended["active"]:
                        break
                    time.sleep(0.4)
                require(not ended["active"] and not ended["radio_started"] and
                        ended["stop_reason"] == "deadline", "fixture deadline failed")
                report["fixture_deadline"] = ended
            finally:
                checkpoint("stop_radios")
                try:
                    report["fixture_final"] = fixture_query(fixture, "stop")
                finally:
                    report["dut_cleanup"] = best_effort_cleanup(dut)
                    final = ui()
                    report["after"] = final
                    require(final["page"] == "home" and final["runtime_owner"] == "none"
                            and final["lease_mask"] == 0, "DUT cleanup incomplete")
                    require(report["dut_cleanup"].get("complete"), "DUT teardown incomplete")
                    for key in ("survey_scan_dropped", "survey_dropped",
                                "survey_timeline_overflow", "survey_product_store_bytes_written",
                                "survey_product_filesystem_mount_attempts"):
                        require(final.get(key) == 0, "nonzero/missing final " + key)
                    metrics, _ = stabilized_boot_metrics(dut)
                    report["heap_final"] = {k: metrics[k] for k in
                                           ("heap_total", "heap_free", "heap_min_free")}
        report["status"] = "pass"
    except (Exception, KeyboardInterrupt) as error:
        report["status"] = "failed"
        report["failures"].append(f"{type(error).__name__}: {error}")
    finally:
        if flashed:
            checkpoint("restore_original_full_flash")
            try:
                exact_port(args.fixture_port, args.fixture_mac)
                require(sha(args.backup) == args.backup_sha, "backup changed before restoration")
                flash_exact(args.fixture_port, args.backup, 0, verify=True)
                report["restored_flash_verified"] = True
                with PassiveSerial(args.fixture_port, 115200, timeout=0.1) as original:
                    synchronize_console(original, 15)
                    boot, _ = stabilized_boot_metrics(original)
                    require(boot["app_elf_sha256"] == original_app,
                            "original application not restored")
                    report["restored_boot"] = boot
                    restored = query(original, b"ui.state", "leshy.ui.v1", "state")
                    require(restored["page"] == "home" and restored["lease_mask"] == 0,
                            "restored original not idle")
                    report["restore_complete"] = True
            except Exception as error:
                report["status"] = "failed"
                report["failures"].append(f"RESTORE: {type(error).__name__}: {error}")
        checkpoint("terminal")
    print(json.dumps({k: report[k] for k in ("status", "failures", "restore_complete")}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
