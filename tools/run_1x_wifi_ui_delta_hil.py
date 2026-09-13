#!/usr/bin/env python3
"""Bounded Wi-Fi UI delta: exact board/image, product key/touch paths, RX only.

No flash, enrollment, laptop-network changes, TX or password capture. Checkpoint
before each step and clean up in finally. Screenshots remain private work output.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from profile_hil_board import serial_metadata
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import action, best_effort_cleanup, capture, query
from run_1x_wifi_channels_hil import changed_pixels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--expected-mac", required=True)
    p.add_argument("--firmware", required=True, type=Path)
    p.add_argument("--expected-version", required=True)
    p.add_argument("--language", choices=("ru", "en"))
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    assert serial_metadata(args.port)["serial_number"].upper() == args.expected_mac.upper()
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    shutil.copyfile(args.firmware, args.output / "firmware.bin")
    report = {"schema": "leshy.wifi_ui_delta.v1", "status": "in_progress",
              "firmware_sha256": hashlib.sha256(args.firmware.read_bytes()).hexdigest(),
              "app_elf_sha256": app_elf_sha256(args.firmware),
              "expected_version": args.expected_version, "steps": [], "failures": []}

    def checkpoint(step):
        report["step"] = step
        report["updated_unix_s"] = time.time()
        temporary = args.output / "run.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(args.output / "run.json")

    def require(condition, description):
        if not condition:
            raise AssertionError(description)

    checkpoint("open")
    try:
        connection = PassiveSerial(args.port, 115200, timeout=0.1)
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append(f"open: {type(error).__name__}: {error}")
        report["cleanup_complete"] = False
        checkpoint("terminal")
        raise
    original_language = None
    with connection as device:
        def state():
            return query(device, b"ui.state", "leshy.ui.v1", "state")

        def key(value):
            checkpoint("key:" + value)
            result = action(device, value)
            report["steps"].append({k: result.get(k) for k in (
                "page", "wifi_product_view", "wifi_product_selection",
                "runtime_event", "runtime_owner", "lease_mask",
                "render_mode", "render_outcome")})
            return result

        def detail(page):
            s = query(device, b"wifi.network.detail", "leshy.wifi.network_detail.v1", "state")
            require(s.get("ui_page") == page, f"expected {page}, got {s.get('ui_page')}")
            require(s.get("active") and s.get("passive"), "selected AP must remain live RX")
            require(not s.get("active_probe_allowed"), "active probes forbidden")
            require(s.get("live_list_direct_fallbacks") == 0, "list compositor fallback")
            report.setdefault("pages", {})[page] = {
                k: s[k] for k in ("ui_page", "ui_selection", "signal_samples", "rssi_dbm")}
            return s

        def screen(name):
            checkpoint("capture:" + name)
            record = capture(device, frames, name)
            report.setdefault("screens", {})[name] = {k: record.get(k) for k in (
                "png_sha256", "rgb565_sha256")}
            return record

        try:
            checkpoint("synchronize")
            synchronize_console(device, 15)
            boot, _ = stabilized_boot_metrics(device)
            require(boot.get("firmware") == args.expected_version or
                    boot.get("version") == args.expected_version, "firmware version mismatch")
            require(boot.get("app_elf_sha256") == report["app_elf_sha256"], "firmware hash mismatch")
            s = state()
            require(s.get("page") == "home" and s.get("lease_mask") == 0, "board not idle Home")
            original_language = s.get("language")
            if args.language and args.language != original_language:
                s = query(device, ("ui.language " + args.language).encode(), "leshy.ui.v1", "state")
                require(s.get("language") == args.language, "language switch failed")
            for _ in range(9):
                if s.get("selection") == 0: break
                s = key("up")
            s = key("right")
            require(s.get("wifi_product_view") == "menu", "Wi-Fi menu entry failed")
            s = key("select")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                s = state()
                if int(s.get("wifi_networks_unique", 0)) > 0: break
                time.sleep(0.2)
            require(int(s.get("wifi_networks_unique", 0)) > 0, "no access points received")
            key("select")
            detail("summary")
            screen("summary")
            key("select")
            detail("radar")
            screen("radar")
            key("back")
            detail("summary")
            checkpoint("touch:radar")
            touch = query(device, b"ui.touch 120 235", "leshy.touch.frontend.v1", "state")
            require(touch.get("last_changed"), "radar touch target missed")
            detail("radar")
            key("back")
            checkpoint("touch:actions")
            touch = query(device, b"ui.touch 120 274", "leshy.touch.frontend.v1", "state")
            require(touch.get("last_changed"), "actions touch target missed")
            detail("actions")
            key("back")
            key("right")
            detail("actions")
            screen("actions")
            key("select")
            detail("protection")
            screen("protection")
            key("back")
            key("down")
            before_intro = screen("before-password-steps")
            s = key("right")
            require(s.get("wifi_product_view") == "password_check_intro", "preflight missing")
            require(s.get("render_outcome") != "no_change", "unpainted preflight scene")
            intro = screen("password-steps")
            require(intro["rgb565_sha256"] != before_intro["rgb565_sha256"],
                    "preflight frame unchanged from actions")
            s = key("right")
            require(s.get("wifi_product_view") == "password_check_intro", "Right started capture")
            repeated_intro = screen("password-steps-stable")
            require(intro["rgb565_sha256"] == repeated_intro["rgb565_sha256"],
                    "static preflight unnecessarily changed")
            key("back")
            detail("actions")
            key("down")
            key("right")
            detail("information")
            screen("information")
            for page in ("identity", "protection", "radio", "observed"):
                key("right")
                detail(page)
                screen(page)
                key("back")
                detail("information")
                key("down")
            key("back")
            key("back")
            detail("summary")
            before = detail("summary")
            time.sleep(3)
            after = detail("summary")
            require(after["signal_samples"] >= before["signal_samples"], "signal continuity")
            key("back")
            key("back")
            require(state().get("wifi_product_view") == "menu", "network cleanup to menu")
            key("down")
            key("down")
            key("right")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                s = state()
                if s.get("wifi_channel_measured_mask") == 8191: break
                time.sleep(0.2)
            require(s.get("wifi_product_view") == "channels" and
                    s.get("wifi_channel_monitor_active"), "channel monitor inactive")
            require(s.get("wifi_channel_measured_mask") == 8191, "13-channel coverage missing")
            screen("channels-first")
            time.sleep(3)
            screen("channels-second")
            report["channel_pixels"] = changed_pixels(frames, "channels-first", "channels-second")
            require(report["channel_pixels"]["static_changed_pixels"] == 0,
                    "channel static chrome changed")
            report["channels"] = {k: s[k] for k in (
                "wifi_channel_measured_mask", "wifi_channel_completed_sweeps",
                "wifi_channel_monitor_active")}
            report["status"] = "passed"
        except (Exception, KeyboardInterrupt) as error:
            report["status"] = "failed"
            report["failures"].append(f"{type(error).__name__}: {error}")
        finally:
            checkpoint("cleanup")
            cleanup = best_effort_cleanup(device)
            report["cleanup_complete"] = cleanup.get("complete", False)
            if not report["cleanup_complete"]:
                report["status"] = "failed"
                report["failures"].append("Home / zero lease cleanup incomplete")
            try:
                final = state()
                report["final"] = {k: final.get(k) for k in (
                    "page", "runtime_owner", "lease_mask", "survey_scan_dropped",
                    "survey_dropped", "survey_timeline_overflow",
                    "survey_product_store_bytes_written", "survey_product_filesystem_mount_attempts")}
                require(final.get("page") == "home" and final.get("runtime_owner") == "none"
                        and final.get("lease_mask") == 0, "final owner/lease")
                for k in ("survey_scan_dropped", "survey_dropped", "survey_timeline_overflow",
                          "survey_product_store_bytes_written", "survey_product_filesystem_mount_attempts"):
                    require(final.get(k) == 0, f"nonzero/missing final {k}")
                metrics, _ = stabilized_boot_metrics(device)
                report["heap_final"] = {k: metrics.get(k) for k in (
                    "heap_total", "heap_free", "heap_min_free")}
            except Exception as error:
                report["status"] = "failed"
                report["failures"].append(f"final audit: {error}")
            if args.language and original_language in ("en", "ru"):
                try:
                    restored = query(device, ("ui.language " + original_language).encode(), "leshy.ui.v1", "state")
                    require(restored.get("language") == original_language, "language restore failed")
                except Exception as error:
                    report["status"] = "failed"
                    report["failures"].append(f"language restore: {error}")
            checkpoint("terminal")
    print(json.dumps({k: report[k] for k in ("status", "failures", "cleanup_complete")}))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
