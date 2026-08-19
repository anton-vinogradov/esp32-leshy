#!/usr/bin/env python3
"""Fail closed unless the exact 0.91 compact status proof is intact."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-clean-status-0.91.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-clean-status-0.91"
VERSION = "0.91.0-clean-status"
SOURCE = "1826e135158f5e5a525177e0e7a9205fd1b92996"
RADIO_RUNNER_COMMIT = "a59670cf2d63b8e9b40bc96cb9f7607b08ced3ed"
FIRMWARE = "f8634f0c3d98d55bc92773e8f67f22d59b50ff5f29e266ff4bbbd3d5adf738e0"
FACTORY = "9ac4a6bafe19edde9106089e5223c16f4433e6203a99dc3f79597ab05da768d8"
APP = "ab8096df7cf67a0e61bcbc4cbf00717896b6d47c128a685fd5ae9d7fd7733830"
MENU_RUNNER = "d7ec116ab666ad9cc1cad1c2a3b7b0180258b7444a22cfd8b83a511ad095d9cd"
RADIO_RUNNER = "c4dcf471493cbdc3d5bb0365ceff641c483b3ce6048100e417e59fdbda9ca22c"
INDEX = "fb48ffb7cadbf7da6bcb8c4452713f5f8264674fffed59bb0095016dc9ca5970"
IDLE_HEADER = "0a735b28d7671790e86f5d68a1732758e0ae7db912de5bbdc83520f41bb6e465"
ACTIVE_HEADER = "7e9f14e86ef5aa2ab9403724b9455eb9ef03648f9830543291ae78de07330c74"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_index(failures: list[str]) -> int:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX,
            "artifact index hash mismatch")
    if not manifest.is_file():
        return 0
    entries: dict[str, str] = {}
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"malformed artifact-index line {number}")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in entries:
            failures.append(f"unsafe/duplicate artifact path: {name}")
            continue
        path = BUNDLE / relative
        require(failures, path.is_file() and digest(path) == expected,
                f"artifact mismatch: {name}")
        entries[name] = expected
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, set(entries) == actual,
            "artifact index does not exactly cover bundle")
    return len(actual) + 1


def dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes() if path.is_file() else b""
    return struct.unpack(">II", data[16:24]) if len(data) >= 24 else None


def header_crop(path: Path) -> str:
    data = path.read_bytes()
    crop = b"".join(
        data[y * 480 + 150 * 2:y * 480 + 240 * 2]
        for y in range(34))
    return hashlib.sha256(crop).hexdigest()


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.91 clean-status evidence is missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.clean_status_acceptance.v1" and
            summary.get("status") == "pass_clean_status_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-092", "E-AUTO-056", "E-HIL-116", "E-UX-015"],
            "summary identity mismatch")
    require(failures, candidate == {
        "version": VERSION,
        "source_commit": SOURCE,
        "menu_runner_commit": SOURCE,
        "radio_runner_commit": RADIO_RUNNER_COMMIT,
        "firmware_sha256": FIRMWARE,
        "factory_sha256": FACTORY,
        "app_elf_sha256": APP,
        "menu_runner_sha256": MENU_RUNNER,
        "radio_runner_sha256": RADIO_RUNNER,
        "firmware_bytes": 1500912,
        "factory_bytes": 1566448,
        "static_ram_bytes": 149936,
        "linked_flash_bytes": 1500508,
    }, "candidate identity/size mismatch")
    require(failures, verify_index(failures) == evidence.get("files") == 54,
            "retained file count mismatch")
    require(failures,
            digest(BUNDLE / "provenance.json") ==
                evidence.get("provenance_sha256") and
            digest(BUNDLE / "menu/run.json") ==
                evidence.get("menu_run_sha256") and
            digest(BUNDLE / "radio/run.json") ==
                evidence.get("radio_run_sha256"),
            "summary-to-bundle binding mismatch")
    require(failures,
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "firmware.elf") == APP and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP and
            digest(BUNDLE / "product-menu-runner.py") == MENU_RUNNER and
            digest(BUNDLE / "nrf24-spectrum-runner.py") == RADIO_RUNNER,
            "retained binary/runner binding mismatch")

    entry = git_blob(
        SOURCE, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    theme = git_blob(SOURCE, "firmware/leshy1/src/ui/VisualTheme.h")
    touch = git_blob(SOURCE, "firmware/leshy1/src/ui/TouchTargets.cpp")
    menu_runner = git_blob(SOURCE, "tools/run_1x_product_menu_hil.py")
    radio_runner = git_blob(
        RADIO_RUNNER_COMMIT, "tools/run_1x_nrf24_spectrum_hil.py")
    require(failures, entry is not None and all(token in entry for token in (
        b"void renderHeaderStatus()", b'"SD OK"', b'"SD !"', b'"SD --"',
        b'"RF RX"', b'"RF --"', b"headerRadioReceiving()",
        b"constexpr std::uint8_t kVisibleHomeRows = 4")) and
        b"void renderInput(" not in entry,
        "truthful header/no-debug-chrome source contract mismatch")
    require(failures, theme is not None and all(token in theme for token in (
        b"HeaderHeight = 34", b"ContentTop = 66",
        b"FooterDividerY = 282", b"HintHeight = 26")),
        "compact geometry source contract mismatch")
    require(failures, touch is not None and b"rows = 4" in touch,
            "four-row touch source contract mismatch")
    require(failures,
            menu_runner is not None and
            hashlib.sha256(menu_runner).hexdigest() == MENU_RUNNER and
            radio_runner is not None and
            hashlib.sha256(radio_runner).hexdigest() == RADIO_RUNNER,
            "runner Git source binding mismatch")

    menu = load(BUNDLE / "menu/run.json")
    screens = menu.get("screens", {})
    require(failures,
            menu.get("status") == "pass" and menu.get("passed") is True and
            menu.get("failures") == [] and len(screens) == 8 and
            evidence.get("menu_tft_states") == 8,
            "menu HIL result mismatch")
    for key, record in screens.items():
        png = BUNDLE / "menu" / Path(record.get("png_path", "")).name
        raw = BUNDLE / "menu" / Path(record.get("rgb565_path", "")).name
        require(failures,
                dimensions(png) == (240, 320) and
                raw.is_file() and raw.stat().st_size == 153600 and
                digest(png) == record.get("png_sha256") and
                digest(raw) == record.get("rgb565_sha256"),
                f"menu TFT binding mismatch: {key}")
    final_menu = menu.get("final_state", {})
    menu_touch = menu.get("states", {}).get("touch", {})
    metrics = menu.get("states", {}).get("metrics", {})
    require(failures,
            [final_menu.get("page"), final_menu.get("runtime_owner"),
             final_menu.get("lease_mask")] == ["home", "none", 0] and
            menu_touch.get("footer_interactive") is False and
            menu_touch.get("touch_back_enabled") is False and
            [metrics.get("heap_total"), metrics.get("heap_free"),
             metrics.get("heap_min_free")] == [231772, 166812, 147460],
            "menu cleanup/touch/heap mismatch")

    radio = load(BUNDLE / "radio/run.json")
    captures = radio.get("captures", {})
    require(failures,
            radio.get("schema") == "leshy.nrf24_spectrum_hil.run.v1" and
            radio.get("passed") is True and radio.get("failures") == [] and
            radio.get("candidate", {}).get("source_commit") == SOURCE and
            radio.get("runner_source_sha256") == RADIO_RUNNER and
            len(captures) == evidence.get("radio_tft_states") == 6,
            "radio HIL identity mismatch")
    for key, record in captures.items():
        basename = key.replace("_", "-")
        png = BUNDLE / "radio/frames" / f"{basename}.png"
        raw = BUNDLE / "radio/frames" / f"{basename}.rgb565"
        require(failures,
                dimensions(png) == (240, 320) and
                raw.is_file() and raw.stat().st_size == 153600 and
                digest(png) == record.get("png_sha256") and
                digest(raw) == record.get("rgb565_sha256"),
                f"radio TFT binding mismatch: {key}")
    running = radio.get("reports", {}).get("running", {})
    paused_before = radio.get("reports", {}).get("paused_before", {})
    paused_after = radio.get("reports", {}).get("paused_after", {})
    resumed = radio.get("reports", {}).get("resumed", {})
    stopped = radio.get("reports", {}).get("stopped", {})
    zero_effects = {
        "cc_command_strobes": 0, "storage_writes": 0,
        "tx_mode_entries": 0, "tx_payload_commands": 0,
    }
    require(failures,
            running.get("state") == "running" and
            running.get("adapter_active") is True and
            paused_before.get("state") == "paused" and
            paused_before.get("sweeps") == paused_after.get("sweeps") == 13 and
            resumed.get("state") == "running" and resumed.get("sweeps") == 20 and
            stopped.get("state") == "idle" and
            stopped.get("cleanup_complete") is True and
            all(report.get("side_effects") == zero_effects for report in (
                running, paused_before, paused_after, resumed, stopped)),
            "receive-only RF lifecycle mismatch")
    recovery_before = radio.get("recovery_before", {})
    recovery_after = radio.get("recovery_after", {})
    final_radio = radio.get("cleanup_after", {}).get("final_state", {})
    require(failures,
            radio.get("cleanup_after", {}).get("complete") is True and
            [final_radio.get("page"), final_radio.get("runtime_owner"),
             final_radio.get("lease_mask")] == ["home", "none", 0] and
            [recovery_before.get("generation"),
             recovery_before.get("observations")] == [95, 0] and
            [recovery_after.get("generation"),
             recovery_after.get("observations")] == [95, 0] and
            radio.get("metrics_after", {}).get("heap_free") ==
                radio.get("boot", {}).get("heap_free") == 166812 and
            radio.get("input", {}).get("read_errors") == 0 and
            radio.get("input", {}).get("queue_drops") == 0,
            "radio continuity/final cleanup mismatch")

    running_crop = header_crop(BUNDLE / "radio/frames/running.rgb565")
    paused_crop = header_crop(BUNDLE / "radio/frames/paused.rgb565")
    home_crop = header_crop(BUNDLE / "radio/frames/home.rgb565")
    require(failures,
            running_crop == evidence.get("receiving_header_crop_sha256") ==
                ACTIVE_HEADER and
            paused_crop == home_crop ==
                evidence.get("idle_header_crop_sha256") == IDLE_HEADER and
            running_crop != paused_crop,
            "active/idle header framebuffer states are not exact")
    require(failures,
            verified.get("visible_home_rows") == 4 and
            verified.get("raw_input_visible") is False and
            verified.get("storage_status_idle") == "SD OK" and
            verified.get("radio_status_idle") == "RF --" and
            verified.get("radio_status_receiving") == "RF RX" and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0,
            "verified claims mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass",
        "version": VERSION,
        "files": evidence.get("files"),
        "menu_tft_states": evidence.get("menu_tft_states"),
        "radio_tft_states": evidence.get("radio_tft_states"),
        "visible_home_rows": verified.get("visible_home_rows"),
        "idle_header": verified.get("radio_status_idle"),
        "active_header": verified.get("radio_status_receiving"),
        "final_lease_mask": verified.get("final_lease_mask"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
