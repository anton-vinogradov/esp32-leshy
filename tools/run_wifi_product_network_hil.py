#!/usr/bin/env python3
"""Two ordinary Leshy builds. UI actions only; never flashes or configures Mac Wi-Fi.

Creates a bounded own AP via Self-check. Proves AP-name discovery/retention, not
client-association name enrichment. Raw observations/screens stay private.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from esp_app_identity import app_elf_sha256
from profile_hil_board import serial_metadata

def require(value, message):
    if not value: raise RuntimeError(message)

def exact_port(port, expected):
    observed = serial_metadata(port)["serial_number"].replace(":", "").lower()
    require(observed == expected.replace(":", "").lower(), "wrong physical board")
    return observed

def bssid_hash(value):
    result = 2166136261
    for byte in bytes.fromhex(value):
        result = ((result ^ byte) * 16777619) & 0xffffffff
    return result

def countdown_diff(before, after):
    require(len(before) == len(after) == 240 * 320 * 2, "incomplete TFT frame")
    counts = {"dynamic_pixels": 0, "static_pixels": 0}
    for pixel in range(240 * 320):
        if before[2*pixel:2*pixel+2] != after[2*pixel:2*pixel+2]:
            counts["dynamic_pixels" if 238 <= pixel // 240 < 258 else "static_pixels"] += 1
    return counts

def main():
    from capture_1x_ui import PassiveSerial, synchronize_console
    from run_1x_product_home_hil import stabilized_boot_metrics
    from run_1x_product_survey_hil import action, best_effort_cleanup, capture, query
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("source", "receiver"):
        parser.add_argument("--" + role + "-port", required=True)
        parser.add_argument("--" + role + "-mac", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(args.source_port != args.receiver_port, "ports must differ")
    require(args.source_mac.replace(":", "").lower() !=
            args.receiver_mac.replace(":", "").lower(), "physical boards must differ")
    board_identities = {
        role: hashlib.sha256(exact_port(getattr(args, role + "_port"),
            getattr(args, role + "_mac")).encode()).hexdigest()
        for role in ("source", "receiver")}
    require(not args.output.exists(), "output must be new")
    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    shutil.copyfile(args.firmware, args.output / "firmware.bin")
    image = args.output / "firmware.bin"
    report = {"schema": "leshy.wifi_product_network.run.v1", "status": "in_progress",
              "scope": "ordinary_product_ap_names_not_client_frame_integration",
              "source_commit": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], text=True).strip(),
              "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
              "app_elf_sha256": app_elf_sha256(image), "failures": [],
              "board_identities": board_identities,
              "states": {}, "screens": {}, "cleanup": {}}

    def checkpoint(step):
        report.update(step=step, updated_unix_s=time.time())
        temporary = args.output / "run.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(args.output / "run.json")

    def ui(device): return query(device, b"ui.state", "leshy.ui.v1", "state")
    def ap(device):
        return query(device, b"wifi.test-network.state", "leshy.wifi.test_network.v1", "state")
    def screen(device, name):
        checkpoint("capture:" + name)
        report["screens"][name] = capture(device, frames, name)
    def root_item(device, identifier):
        require(ui(device)["page"] == "home", "Home required")
        for _ in range(20):
            if ui(device)["selection"] == 0: break
            action(device, "up")
        for _ in range(20):
            if ui(device)["selected_id"] == identifier:
                return action(device, "right")
            action(device, "down")
        raise RuntimeError("missing root item: " + identifier)

    checkpoint("preflight")
    with ExitStack() as stack:
        devices = {}
        try:
            for role in ("source", "receiver"):
                device = stack.enter_context(PassiveSerial(
                    getattr(args, role + "_port"), 115200, timeout=.1))
                devices[role] = device
                synchronize_console(device, 10)
                boot, _ = stabilized_boot_metrics(device)
                require(boot["app_elf_sha256"] == report["app_elf_sha256"], "wrong product image")
                state = ui(device)
                require(state["page"] == "home" and state["lease_mask"] == 0, "board not idle")
                report[role + "_boot"] = boot
            source, receiver = devices["source"], devices["receiver"]
            checkpoint("source_menu")
            root_item(source, "device")
            for _ in range(9): action(source, "up")
            for _ in range(7): action(source, "down")
            action(source, "right")
            require(ui(source)["self_test_view"] == "mode_menu", "self-check menu missing")
            for _ in range(3): action(source, "up")
            action(source, "down")
            action(source, "down")
            action(source, "right")
            source_view = ui(source)
            require(source_view["self_test_view"] == "wifi_network" and
                    source_view["self_test_read_only"] is False and
                    source_view["self_test_status"] == "not_run",
                    "ordinary transmitting tool must not claim read-only or Pass")
            state = ap(source)
            require(not state["active"] and not state["radio_started"] and
                    state["cleanup_complete"], "menu must not start AP")
            report["states"]["menu_off"] = state
            screen(source, "source-ready")
            # Normal visibility control, then touch the real Start row.
            if not state["hidden"]:
                action(source, "up")
                action(source, "right")
            require(ap(source)["hidden"] and not ap(source)["active"], "hidden setup started radio")
            checkpoint("receiver_menu")
            root_item(receiver, "wifi")
            action(receiver, "right")
            require(ui(receiver)["wifi_product_view"] == "networks", "networks missing")
            checkpoint("source_start_touch")
            query(source, b"ui.touch 120 180", "leshy.touch.frontend.v1", "state")
            started = ap(source)
            report["states"]["started"] = started
            require(started["active"] and started["hidden"] and started["radio_started"] and
                    started["power_quarter_dbm"] == 8 and started["lease_mask"] == 3,
                    "touch did not start bounded product AP")
            screen(source, "source-running")
            time.sleep(1.2)
            screen(source, "source-running-later")
            report["countdown_pixels"] = countdown_diff(
                (frames / "source-running.rgb565").read_bytes(),
                (frames / "source-running-later.rgb565").read_bytes())
            require(report["countdown_pixels"]["static_pixels"] == 0 and
                    report["countdown_pixels"]["dynamic_pixels"] > 0, "countdown repaints static UI")
            identity = bssid_hash(started["bssid"])
            checkpoint("find_exact_ap")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = ui(receiver)
                if state["wifi_network_selected_identity_hash"] == identity: break
                if state["wifi_network_selection"] + 1 >= state["wifi_network_visible_size"]:
                    for _ in range(32):
                        if ui(receiver)["wifi_network_selection"] == 0: break
                        action(receiver, "up")
                    time.sleep(.1)
                else: action(receiver, "down")
            require(state["wifi_network_selected_identity_hash"] == identity, "own AP not found")
            action(receiver, "right")

            def observe(name, known, minimum=0):
                checkpoint(name)
                deadline = time.monotonic() + 13
                while time.monotonic() < deadline:
                    s = query(receiver, b"wifi.network.detail", "leshy.wifi.network_detail.v1", "state")
                    require(s["identity_hash"] == identity and s["active"] and s["passive"] and
                            not s["active_probe_allowed"], "receiver lost exact passive AP")
                    if s["ssid_known"] == known and s["signal_samples"] >= minimum:
                        report["states"][name] = s
                        screen(receiver, name)
                        return s
                    time.sleep(.15)
                raise TimeoutError(name + " not observed")

            hidden = observe("hidden", False)
            negative = observe("hidden_no_name", False, hidden["signal_samples"] + 2)
            action(source, "up")
            action(source, "right")
            visible = ap(source)
            require(visible["active"] and not visible["hidden"] and
                    visible["bssid"] == started["bssid"], "visibility changed BSSID")
            report["states"]["visible_source"] = visible
            known = observe("resolved", True, negative["signal_samples"] + 1)
            require(known["hidden_resolutions"] > hidden["hidden_resolutions"], "resolution not recorded")
            action(source, "right")
            require(ap(source)["hidden"], "hide action failed")
            observe("retained", True, known["signal_samples"] + 2)
            action(source, "left")
            stopped = ap(source)
            require(not stopped["radio_started"] and stopped["cleanup_complete"] and
                    stopped["lease_mask"] == 1 and stopped["stop_reason"] == 1, "Left stop failed")
            report["states"]["user_stop"] = stopped
            checkpoint("deadline")
            action(source, "down")
            deadline_start = time.monotonic()
            action(source, "right")
            second = ap(source)
            report["states"]["deadline_start"] = second
            require(second["active"] and 58 <= second["remaining_s"] <= 60,
                    "second explicit start failed")
            deadline = time.monotonic() + 64
            while time.monotonic() < deadline:
                ended = ap(source)
                if not ended["active"]: break
                time.sleep(.4)
            require(not ended["radio_started"] and ended["cleanup_complete"] and
                    ended["stop_reason"] == 2 and ended["lease_mask"] == 1, "deadline stop failed")
            report["deadline_observed_s"] = round(time.monotonic() - deadline_start, 3)
            require(59 <= report["deadline_observed_s"] <= 63,
                    "physical deadline outside timing bounds")
            report["states"]["deadline"] = ended
            screen(source, "source-deadline")
            report["status"] = "pass"
        except (Exception, KeyboardInterrupt) as error:
            report["status"] = "failed"
            report["failures"].append(f"{type(error).__name__}: {error}")
            # Preserve the reason before ordinary Back/Stop cleanup changes it.
            # Reads only; no retry, restart, radio start or deadline renewal.
            report["failure_snapshot"] = {}
            checkpoint("failure_snapshot")
            for role, device in devices.items():
                snapshot = report["failure_snapshot"][role] = {}
                for name, command, schema in (
                    ("ui", b"ui.state", "leshy.ui.v1"),
                    ("safety", b"safety.state", "leshy.safety.v1"),
                    ("test_network", b"wifi.test-network.state", "leshy.wifi.test_network.v1"),
                ):
                    try:
                        snapshot[name] = query(device, command, schema, "state")
                    except Exception as diagnostic_error:
                        snapshot[name] = {"unavailable": str(diagnostic_error)}
                checkpoint("failure_snapshot:" + role)
        finally:
            for role, device in devices.items():
                checkpoint("cleanup:" + role)
                result = best_effort_cleanup(device)
                report["cleanup"][role] = result
                if not result["complete"]:
                    report["status"] = "failed"
                    report["failures"].append(role + " cleanup incomplete")
                else:
                    try:
                        boot, _ = stabilized_boot_metrics(device)
                        report[role + "_final_boot"] = boot
                        if boot["app_elf_sha256"] != report["app_elf_sha256"]:
                            raise RuntimeError("final image changed")
                        final = result["final_state"]
                        for key in ("survey_scan_dropped", "survey_dropped",
                                    "survey_timeline_overflow", "survey_product_store_bytes_written",
                                    "survey_product_filesystem_mount_attempts"):
                            require(final.get(key) == 0, role + " nonzero/missing " + key)
                    except Exception as error:
                        report["status"] = "failed"
                        report["failures"].append(str(error))
            checkpoint("terminal")
    print(json.dumps({k: report[k] for k in ("status", "failures")}))
    return 0 if report["status"] == "pass" else 1

if __name__ == "__main__": raise SystemExit(main())
