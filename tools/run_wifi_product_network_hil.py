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

def name_countdown_diff(before, after):
    require(len(before) == len(after) == 240 * 320 * 2, "incomplete TFT frame")
    counts = {"dynamic_pixels": 0, "static_pixels": 0}
    for pixel in range(240 * 320):
        if before[2*pixel:2*pixel+2] != after[2*pixel:2*pixel+2]:
            counts["dynamic_pixels" if 158 <= pixel // 240 < 182 else "static_pixels"] += 1
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
    parser.add_argument("--name-listen", action="store_true",
                        help="Also verify ordinary 20-second selected-name listening (not client association)")
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
              "name_listener_requested": args.name_listen,
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
        class TracedSerial(PassiveSerial):
            """Private, bounded, flushed command/JSON trace; no binary GRAM."""
            def trace(self, direction, data):
                if not data: return
                record = json.dumps({"monotonic_s": time.monotonic(),
                    "direction": direction, "hex": data.hex()}) + "\n"
                self.trace_stats["bytes_observed"] += len(data)
                if direction == "rx" and not data.endswith(b"\n"):
                    self.trace_stats["partial_lines"] += 1
                if self.trace_stats["file_bytes"] + len(record) <= 4 * 1024 * 1024:
                    self.trace_file.write(record)
                    self.trace_file.flush()
                    self.trace_stats["file_bytes"] += len(record)
                else: self.trace_stats["truncated"] = True

            def readline(self, *args, **kwargs):
                data = super().readline(*args, **kwargs)
                self.trace("rx", data)
                return data

            def write(self, data):
                self.trace("tx", data)
                return super().write(data)

        devices = {}
        try:
            for role in ("source", "receiver"):
                trace_file = stack.enter_context((args.output / (role + "-console.jsonl")).open("x"))
                device = stack.enter_context(TracedSerial(
                    getattr(args, role + "_port"), 115200, timeout=.1))
                device.trace_file = trace_file
                device.trace_stats = {"file_bytes": 0, "bytes_observed": 0,
                                      "partial_lines": 0, "truncated": False}
                report.setdefault("console_traces", {})[role] = device.trace_stats
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
            if args.name_listen:
                checkpoint("name_listener")
                # A fresh, explicitly started AP window for the receiver delta.
                action(source, "left")
                action(source, "down")
                action(source, "right")
                name_source = ap(source)
                require(name_source["active"] and name_source["hidden"], "fresh hidden AP missing")
                report["states"]["name_source"] = name_source
                # Session privacy deliberately changes the own AP identity on
                # every Start. Re-select the new target; do not wait for the old
                # AP to reappear and misdiagnose a correct receiver as stale.
                identity = bssid_hash(name_source["bssid"])
                action(receiver, "left")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    state = ui(receiver)
                    if state["wifi_network_selected_identity_hash"] == identity: break
                    if state["wifi_network_selection"] + 1 >= state["wifi_network_visible_size"]:
                        for _ in range(32):
                            if ui(receiver)["wifi_network_selection"] == 0: break
                            action(receiver, "up")
                    else: action(receiver, "down")
                require(state["wifi_network_selected_identity_hash"] == identity, "new private AP not found")
                action(receiver, "right")
                for key in ("right", "down", "down", "right", "right", "right"):
                    action(receiver, key)
                def detail():
                    s = query(receiver, b"wifi.network.detail", "leshy.wifi.network_detail.v1", "state")
                    require(s["identity_hash"] == identity and s["ui_page"] == "listen_name",
                            "name listener lost target/page")
                    return s
                def wait_name(label, predicate, timeout=10):
                    checkpoint(label)
                    end = time.monotonic() + timeout
                    while time.monotonic() < end:
                        s = detail()
                        if predicate(s):
                            report["states"][label] = s
                            return s
                        require(s["name_listen_state"] != "failed", "name listener failed: " + s["name_listen_status"])
                        time.sleep(.1)
                    raise TimeoutError(label)
                ready = detail()
                require(ready["name_listen_state"] == "idle" and not ready["name_receiver_owned"], "page started receiver")
                require(ready["name_window_duration_ms"] == 0 and not ready["name_window_found"] and
                        not ready["name_scan_restored"], "new page retained old window result")
                require(not ready["ssid_known"], "fresh hidden target unexpectedly named")
                report["states"]["name_ready"] = ready
                screen(receiver, "name-ready")
                action(receiver, "right")
                require(detail()["name_listen_state"] == "idle", "Right must not start listening")
                action(receiver, "select")
                running = wait_name("name_running", lambda s: s["name_listen_state"] == "running")
                screen(receiver, "name-running")
                time.sleep(1.2)
                screen(receiver, "name-running-later")
                report["name_countdown_pixels"] = name_countdown_diff(
                    (frames / "name-running.rgb565").read_bytes(),
                    (frames / "name-running-later.rgb565").read_bytes())
                require(report["name_countdown_pixels"]["static_pixels"] == 0 and
                        report["name_countdown_pixels"]["dynamic_pixels"] > 0, "name timer repaints static screen")
                negative_name = wait_name("name_deadline", lambda s: s["name_listen_state"] == "result", 23)
                require(not negative_name["name_window_found"] and negative_name["name_scan_restored"] and
                        not negative_name["name_receiver_owned"] and
                        20000 <= negative_name["name_window_duration_ms"] <= 21000,
                        "hidden name timeout/restore failed")
                resumed = wait_name("name_scan_resumed", lambda s: s["signal_samples"] > running["signal_samples"])
                screen(receiver, "name-timeout")
                # Listener is active before AP visibility changes: SDK scans
                # cannot account for the new window's name evidence.
                action(receiver, "select")
                positive_start = wait_name("name_positive_start", lambda s: s["name_listen_state"] == "running")
                action(source, "up")
                action(source, "right")
                require(not ap(source)["hidden"] and ap(source)["active"], "visible AP missing")
                positive = wait_name("name_ap_frame", lambda s: s["name_window_found"])
                require(positive["name_window_source"] == 1 and positive["name_ap_confirmed"] and
                        positive["signal_samples"] == positive_start["signal_samples"],
                        "name-only AP evidence changed RSSI observations")
                action(source, "right")
                require(ap(source)["hidden"], "hide after name evidence failed")
                screen(receiver, "name-found")
                query(receiver, b"ui.touch 120 265", "leshy.touch.frontend.v1", "state")
                stopped_name = wait_name("name_touch_stop", lambda s: s["name_listen_state"] == "result")
                require(stopped_name["name_scan_restored"] and not stopped_name["name_receiver_owned"] and
                        0 < stopped_name["name_window_duration_ms"] < 20000 and stopped_name["name_window_found"],
                        "touch stop/retention/restore failed")
                wait_name("name_after_stop_scan", lambda s: s["signal_samples"] > positive["signal_samples"])
                for _ in range(5): action(receiver, "left")
                require(ui(receiver)["wifi_product_view"] == "networks", "name Back path did not return to list")
                report["name_listener_scope"] = "passive_ap_frames_timeout_touch_stop_restore_no_client_association"
                after_name_ui = ui(receiver)
                report["name_history_retention"] = {k:after_name_ui.get(k) for k in
                    ("survey_received", "survey_forwarded", "survey_dropped", "survey_scan_dropped")}
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
