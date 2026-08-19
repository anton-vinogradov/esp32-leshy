#!/usr/bin/env python3
"""Fail closed unless the exact 0.95 inline physical-key proof remains intact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-inline-key-hints-0.95.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-inline-key-hints-0.95"
VERSION = "0.95.0-inline-key-hints"
SOURCE = "d277468ddc3feb912d214c3802c890df52071d66"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "dfaad4bd396567a3612e88bc74b4dcab4e0a28a99bd278b0e2cbf01b79aace5e"
FACTORY = "98fed12859c708892df39e23d8062384ee592e89a672f2e4146995cc50bc3ace"
APP = "ee5aaed813c9f5a4c8a253d2d144ffaaa6499b5f327a7f7ceb49e6f2825bc261"
MAP = "64f5262ed3bf07aeb1e734e5cbc79ebc2b527da11ce8f193fbc40fcbf40cd756"
RUNNER = "68a7c84066207cd1b5f860f0c8f3135dd589513ebb3297521ebc9ae86b3a1229"
CHECKER = "1724c45300acd7f36c00df214693d93dfa9a06a88bcedfd5452dac333a143b01"
GATE = "990f8deb3857ae0b700c0dee7b2fc7edbaeaf3a5ea239fcdcd1e0a3c1be86caa"
INDEX = "5043ae5bdf7f9fa0c0e92826e8c5572f9dabb7409d1fcd2244db5c34cd85dbbf"
PROVENANCE = "e37ea53fdbd61cc86441d052b0b8df103ba52f8f1049c1689dba826344431e5e"
RUN = "9a6d9a506a336c4a9378f85288b346c4644188558f527ca189c2a2859839f279"
OPAQUE = {"firmware.bin", "firmware.factory.bin", "firmware.elf", "firmware.map"}
FRAME_HASHES = {
    "frames/cc-band-menu.png": "9e79aa67aa268ff3a30165944101f1df9271e4cb691b80b45c0e5383f1e291a2",
    "frames/device.png": "8310f2882e599014cfc0162455840e9100d1220099804dc9bb2110cadb602406",
    "frames/home-en.png": "ee18f000bc17be277fbb0aca03508116239af33dd45930acdc91fea8d5f41a85",
    "frames/home-final.png": "d420d83ebad062f38b08b4b36f953d1c8e9f12aacb860186194015271c44102a",
    "frames/nrf-spectrum.png": "8e2b06e575b42cd83d6be6c3cd1df060cb7453acf34974426047f69ae1d52055",
    "frames/wifi.png": "32dba6a36dae680d5cee6daa4bcb42ab44aa36813aa17969c108387ae7777cae",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_manifest(failures: list[str], tracked_only: bool) -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX,
            "artifact index mismatch")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        indexed.add(relative)
        path = BUNDLE / relative
        if tracked_only and relative in OPAQUE:
            continue
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    require(failures, OPAQUE <= indexed, "opaque candidate bindings missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.95 inline key-hint evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.product_home_acceptance.v1" and
            summary.get("status") == "pass_inline_key_hints_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-096", "E-AUTO-060", "E-HIL-120", "E-UX-019"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("checker_sha256") == CHECKER and
            candidate.get("gate_sha256") == GATE and
            [candidate.get("firmware_bytes"), candidate.get("factory_bytes"),
             candidate.get("static_ram_bytes"), candidate.get("linked_flash_bytes")] ==
                [1506832, 1572368, 159856, 1506428],
            "candidate identity/size mismatch")
    require(failures, evidence == {
        "artifact_index_sha256": INDEX, "files": 52,
        "provenance_sha256": PROVENANCE, "run_sha256": RUN,
        "tft_states": 14,
    }, "evidence summary mismatch")
    require(failures, verified.get("navigation_legend") == {
        "layout": "single_baseline", "font": "Roboto Condensed Medium 12",
        "color": "text_secondary", "left_order": "key_then_label",
        "middle_order": "key_then_label", "right_order": "label_then_ok_right",
        "outer_inset_px": 6, "gap_px": 4, "footer_height_px": 26,
        "touch_target": False,
    }, "verified inline legend contract mismatch")
    require(failures,
            verified.get("languages") == ["en", "ru"] and
            verified.get("manual_button_presses") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0 and
            verified.get("heap") == [221852, 156892, 137540],
            "verified runtime claims mismatch")

    verify_manifest(failures, args.tracked_only)
    for relative, expected in FRAME_HASHES.items():
        require(failures, (BUNDLE / relative).is_file() and
                digest(BUNDLE / relative) == expected,
                f"exact TFT frame mismatch: {relative}")

    run = load(BUNDLE / "run.json")
    screens = run.get("screens", {})
    require(failures,
            run.get("passed") is True and not run.get("failures") and
            run.get("expected_cid") == CID and len(screens) == 14 and
            screens.get("home_en", {}).get("state", {}).get("language") == "en" and
            screens.get("home_final", {}).get("state", {}).get("language") == "ru" and
            run.get("cleanup_after", {}).get("final_state", {}).get("lease_mask") == 0,
            "physical route/final cleanup mismatch")

    renderer = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    strings = git_blob("firmware/leshy1/src/ui/UiStrings.def")
    platform = git_blob("firmware/leshy1/platformio.ini")
    legacy = git_blob("src/features/display/Fonts.cpp")
    require(failures, renderer is not None and all(token in renderer for token in (
        b"kNavigationInset = 6", b"kNavigationGap = 4",
        b"kRobotoCondensedMetaAscent +", b"Palette::TextSecondary",
        b"x + labelWidth + kNavigationGap")) and
        b"bounds.y + 11" not in renderer[renderer.find(b"void renderNavigationCell"):
                                                renderer.find(b"void renderNavigationFooter")],
        "single-baseline renderer source mismatch")
    require(failures, strings is not None and all(token in strings for token in (
        '"Back", u8"Назад"'.encode(), '"Select", u8"Выбор"'.encode(),
        '"Enter", u8"Вход"'.encode())),
        "mixed-case EN/RU navigation strings mismatch")
    require(failures, platform is not None and
            b'LESHY1_VERSION=\\"0.95.0-inline-key-hints\\"' in platform,
            "exact build version source mismatch")
    require(failures, legacy is not None and all(token in legacy for token in (
        b"drawString(left, 6, 309)", b"drawString(right, 234, 309)",
        b"setTextDatum(ML_DATUM)", b"setTextDatum(MR_DATUM)")),
        "0.x edge-aligned footer precedent mismatch")

    if not args.tracked_only:
        for name, expected in (("firmware.bin", FIRMWARE),
                               ("firmware.factory.bin", FACTORY),
                               ("firmware.elf", APP), ("firmware.map", MAP)):
            require(failures, (BUNDLE / name).is_file() and
                    digest(BUNDLE / name) == expected,
                    f"opaque candidate mismatch: {name}")
        if (BUNDLE / "firmware.bin").is_file():
            require(failures, app_elf_sha256(BUNDLE / "firmware.bin") == APP,
                    "embedded ELF identity mismatch")
        check = subprocess.run(
            [str(BUNDLE / "checker.py"), "--run", str(BUNDLE),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")})
        require(failures, check.returncode == 0,
                f"retained independent checker failed: {check.stdout}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "tft_states": 14,
        "layout": "single_baseline", "font": "Roboto Condensed Medium 12",
        "manual_button_presses": 0, "final_lease_mask": 0,
        "evidence_mode": "tracked" if args.tracked_only else "full",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
