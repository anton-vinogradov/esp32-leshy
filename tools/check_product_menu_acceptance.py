#!/usr/bin/env python3
"""Fail closed unless the exact 0.90 product-menu proof is intact."""

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
SUMMARY = ROOT / "tests/hil/evidence/board-01-product-menu-0.90.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-menu-0.90"
VERSION = "0.90.0-product-menu"
SOURCE_COMMIT = "1181619c9435346bce1d3e8d710737d5460e702f"
RUNNER_COMMIT = "fbeb93e814bd069c2dfae738ec1c5a5dea771248"
FIRMWARE = "d166634abb48c461a2566929c4ef3ed3bdc406ff197bc02b16463c608e141e4a"
FACTORY = "555100379df462c8c8d5fe56627b9027f48d761b632b124569077061c1a38fad"
APP = "dbc8234cb4c206191d10cd83ba166f5acd6eb1f2b4ab8156cff61608c5160575"
RUNNER = "db9ff0e8cff8368e104e55527fa495d00b83422b67814a9134a4d4da17640237"
INDEX = "d603c34e05e6d0329450fb3ddbafbaba906d48da821c87c61c2f01d3880f0356"
SCREENS = {
    "home_product_top": ("home-product-top", "home", 0, "survey"),
    "home_product_bottom": ("home-product-bottom", "home", 5, "device"),
    "device_top": ("device-top", "device", 0, "device"),
    "self_test_nested": ("self-test-nested", "self_test", 1, "device"),
    "diagnostics_nested": ("diagnostics-nested", "diagnostics", 2, "device"),
    "device_bottom": ("device-bottom", "device", 3, "device"),
    "about": ("about", "about", 3, "device"),
    "home_final": ("home-final", "home", 0, "survey"),
}


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


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.90 product-menu evidence is missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.product_menu_acceptance.v1" and
            summary.get("status") == "pass_product_menu_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-091", "E-AUTO-055", "E-HIL-115", "E-UX-014"],
            "summary identity mismatch")
    require(failures, candidate == {
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "runner_commit": RUNNER_COMMIT,
        "firmware_sha256": FIRMWARE,
        "factory_sha256": FACTORY,
        "app_elf_sha256": APP,
        "runner_sha256": RUNNER,
        "firmware_bytes": 1500784,
        "factory_bytes": 1566320,
        "static_ram_bytes": 149936,
        "linked_flash_bytes": 1500384,
    }, "candidate identity/size mismatch")
    require(failures, verify_index(failures) == evidence.get("files") == 33,
            "retained file count mismatch")
    for name, expected in {
        "run.original.json": evidence.get("original_run_sha256"),
        "run.json": evidence.get("canonical_run_sha256"),
        "runner-failure.json": evidence.get("failed_run_sha256"),
        "provenance.json": evidence.get("provenance_sha256"),
        "artifacts.sha256": evidence.get("artifact_index_sha256"),
    }.items():
        path = BUNDLE / name
        require(failures, path.is_file() and digest(path) == expected,
                f"summary binding mismatch: {name}")

    require(failures,
            digest(BUNDLE / "firmware.bin") == FIRMWARE and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY and
            digest(BUNDLE / "firmware.elf") == APP and
            digest(BUNDLE / "runner.py") == RUNNER and
            app_elf_sha256(BUNDLE / "firmware.bin") == APP,
            "retained binary/runner binding mismatch")
    provenance = load(BUNDLE / "provenance.json")
    require(failures,
            provenance.get("source_commit") == SOURCE_COMMIT and
            provenance.get("runner_commit") == RUNNER_COMMIT and
            provenance.get("version") == VERSION,
            "retained provenance mismatch")

    catalog = git_blob(
        SOURCE_COMMIT, "firmware/leshy1/src/domain/apps/AppCatalog.cpp")
    entry = git_blob(
        SOURCE_COMMIT, "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    controller = git_blob(
        SOURCE_COMMIT, "firmware/leshy1/src/ui/UiController.cpp")
    runner = git_blob(RUNNER_COMMIT, "tools/run_1x_product_menu_hil.py")
    require(failures, catalog is not None and all(token in catalog for token in (
        b'"survey"', b'"capture"', b'"library"', b'"targets"',
        b'"lab"', b'"device"', b'7, false', b'8, false', b'9, true')),
        "product-first Home source contract mismatch")
    require(failures, entry is not None and
            b"constexpr std::uint8_t kDeviceItemCount = 4" in entry and
            b"5, 6, 1, kAboutPage" in entry and
            b"uiController.openChild(pages[deviceSelection])" in entry and
            b"TouchTargetLayout::HomeRows" in entry,
            "nested Device/touch source contract mismatch")
    require(failures, controller is not None and
            b"page_ = parentPage_" in controller and
            b"parentPage_ = kRootPage" in controller,
            "one-level parent navigation source contract mismatch")
    require(failures, runner is not None and digest(BUNDLE / "runner.py") ==
            hashlib.sha256(runner).hexdigest(),
            "runner Git source binding mismatch")

    run = load(BUNDLE / "run.json")
    original = load(BUNDLE / "run.original.json")
    run_candidate = run.get("candidate", {})
    require(failures,
            run.get("schema") == "leshy.product_menu_hil.run.v1" and
            run.get("status") == "pass" and run.get("passed") is True and
            run.get("failures") == [] and
            run_candidate.get("version") == VERSION and
            run_candidate.get("firmware_sha256") == FIRMWARE and
            run_candidate.get("app_elf_sha256") == APP and
            run_candidate.get("runner_sha256") == RUNNER and
            original.get("candidate") == run_candidate,
            "passing run identity mismatch")

    screens = run.get("screens", {})
    require(failures, set(screens) == set(SCREENS) and
            evidence.get("tft_states") == 8,
            "exact eight TFT states are required")
    for key, (basename, page, position, selected_id) in SCREENS.items():
        record = screens.get(key, {})
        state = record.get("state", {})
        png = BUNDLE / f"{basename}.png"
        raw = BUNDLE / f"{basename}.rgb565"
        trace = BUNDLE / f"{basename}.json"
        data = png.read_bytes() if png.is_file() else b""
        dimensions = struct.unpack(">II", data[16:24]) \
            if len(data) >= 24 else None
        actual_position = state.get("selection") if page == "home" \
            else state.get("device_selection")
        require(failures,
                dimensions == (240, 320) and raw.stat().st_size == 153600 and
                digest(png) == record.get("png_sha256") and
                digest(raw) == record.get("rgb565_sha256") and
                digest(trace) == record.get("trace_sha256") and
                state.get("page") == page and actual_position == position and
                state.get("selected_id") == selected_id,
                f"TFT/state binding mismatch: {key}")

    final = run.get("final_state", {})
    touch = run.get("states", {}).get("touch", {})
    metrics = run.get("states", {}).get("metrics", {})
    require(failures,
            [final.get("page"), final.get("selection"),
             final.get("selected_id"), final.get("runtime_owner"),
             final.get("lease_mask")] == ["home", 0, "survey", "none", 0],
            "final Home/cleanup mismatch")
    require(failures,
            touch.get("handled_presses") == 1 and
            touch.get("missed_presses") == 2 and
            touch.get("synthetic_presses") == 3 and
            touch.get("footer_interactive") is False and
            touch.get("touch_back_enabled") is False,
            "touch target/chrome policy mismatch")
    require(failures,
            metrics.get("version") == VERSION and
            metrics.get("app_elf_sha256") == APP and
            [metrics.get("heap_total"), metrics.get("heap_free"),
             metrics.get("heap_min_free")] == [231772, 166812, 147460] and
            metrics.get("buzzer_inactive") is True and
            metrics.get("input_detected") is True,
            "boot safety/resource facts mismatch")

    failed = load(BUNDLE / "runner-failure.json")
    regression = summary.get("regression", {})
    require(failures,
            failed.get("status") == "failed" and
            failed.get("passed") is False and
            failed.get("candidate", {}).get("flashed") is True and
            failed.get("candidate", {}).get("firmware_sha256") == FIRMWARE and
            failed.get("failures") == [
                "RuntimeError: disabled Home item targets: revision=4, expected 3"
            ] and regression.get("product_defect") is False and
            regression.get("candidate_was_reflashed_for_retry") is False,
            "initial runner-only failure is not retained honestly")
    require(failures,
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0 and
            summary.get("limits") == {
                "product_menu_complete": True,
                "targets_implemented": False,
                "lab_implemented": False,
                "controlled_power_cut_complete": False,
                "demo_s4_complete": False,
            }, "summary claims/limits mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.90 product-first menu proof is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
