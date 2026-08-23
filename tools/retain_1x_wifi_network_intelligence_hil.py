#!/usr/bin/env python3
"""Retain exact physical evidence for Wi-Fi network intelligence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from retain_1x_signal_order_hil import digest, load, require, write


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.118.0-wifi-network-intelligence"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-118", "E-AUTO-082", "E-HIL-142", "E-UX-037"]
FAILED_SOURCE_COMMIT = "013875a81d347fefcaa8ea0e9a507dddb0344313"
SOURCE_FILES = {
    "renderer": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "strings": "firmware/leshy1/src/ui/UiStrings.def",
    "observation": "firmware/leshy1/src/domain/observations/Observation.h",
    "contract_h": "firmware/leshy1/src/drivers/wifi/WifiPassiveContract.h",
    "contract_cpp": "firmware/leshy1/src/drivers/wifi/WifiPassiveContract.cpp",
    "adapter_h": "firmware/leshy1/src/platform/arduino/BoardWifiPassiveScanner.h",
    "adapter_cpp": "firmware/leshy1/src/platform/arduino/BoardWifiPassiveScanner.cpp",
    "catalog_h": "firmware/leshy1/src/apps/wifi/WifiNetworkCatalog.h",
    "catalog_cpp": "firmware/leshy1/src/apps/wifi/WifiNetworkCatalog.cpp",
    "navigation": "firmware/leshy1/src/apps/wifi/WifiNetworkNavigationOrder.h",
    "oui_h": "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.h",
    "oui_cpp": "firmware/leshy1/src/apps/wifi/WifiOuiDatabase.cpp",
    "source_guard": "tools/check_wifi_networks_contract.py",
    "native_tests": "tests/native/clean_target_tests.cpp",
}


def verify_intelligence(run: dict[str, Any]) -> None:
    scope = run.get("scope", {})
    first = run.get("detail_facts_first", {})
    second = run.get("detail_facts_second", {})
    require(scope.get("network_intelligence") is True and
            scope.get("network_vendor_lookup") is True and
            scope.get("network_driver_facts") is True and
            scope.get("detail_live_rssi_line_only") is True,
            "network-intelligence scope missing")
    require(first.get("active") is True and
            first.get("passive") is True and
            first.get("active_probe_allowed") is False and
            first.get("ssid_known") is True and
            first.get("vendor_known") is True and
            bool(first.get("vendor")) and
            first.get("facts_known") is True and
            first.get("authentication") != "UNKNOWN" and
            first.get("channel_width") != "WIDTH ?" and
            first.get("phy_mask", 0) != 0 and
            first.get("identity_hash", 0) != 0,
            "physical network passport is incomplete")
    for field in (
            "identity_hash", "vendor", "authentication", "pairwise_cipher",
            "group_cipher", "channel_width", "phy_mask", "channel",
            "frequency_khz"):
        require(second.get(field) == first.get(field),
                f"network identity/fact changed: {field}")
    require(run.get("detail_outside_signal_pixels") == 0 and
            run.get("detail_pixel_changes", {}).get("chrome_changed_pixels") == 0,
            "network detail redraw escaped the live signal line")


def run_check(command: list[str], message: str) -> None:
    checked = subprocess.run(
        command, cwd=ROOT, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(checked.returncode == 0, f"{message}: {checked.stdout}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--failed-source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--firmware-source-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()

    source = args.source.resolve()
    failed_source = args.failed_source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    runner = ROOT / "tools/run_1x_wifi_networks_hil.py"
    checker = ROOT / "tools/check_wifi_networks_run.py"
    source_guard = ROOT / "tools/check_wifi_networks_contract.py"
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    require(len(args.firmware_source_commit) == 40 and
            len(args.runner_commit) == 40, "commits must be full IDs")
    for artifact in (
            source / "run.json", source / "firmware.bin",
            source / "artifacts.sha256", failed_source / "run.json",
            failed_source / "firmware.bin", failed_source / "artifacts.sha256",
            runner, checker, source_guard, args.factory.resolve(),
            args.elf.resolve(), args.map.resolve()):
        require(artifact.is_file(), f"artifact missing: {artifact}")

    run = load(source / "run.json")
    failed_run = load(failed_source / "run.json")
    candidate = run.get("candidate", {})
    require(run.get("schema") == "leshy.wifi_networks_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [], "source run is not a clean pass")
    require(candidate.get("version") == VERSION and
            candidate.get("source_commit") == args.firmware_source_commit and
            candidate.get("flash_mode") == "fresh" and
            candidate.get("flashed") is True and run.get("expected_cid") == CID,
            "exact fresh-flash candidate binding mismatch")
    require(run.get("runner_source_sha256") == digest(runner),
            "runner source hash mismatch")
    verify_intelligence(run)

    failed_candidate = failed_run.get("candidate", {})
    failed_messages = "\n".join(failed_run.get("failures", []))
    require(failed_run.get("schema") == "leshy.wifi_networks_hil.run.v1" and
            failed_run.get("passed") is False and
            failed_run.get("gate_eligible") is False and
            failed_candidate.get("version") == VERSION and
            failed_candidate.get("source_commit") == FAILED_SOURCE_COMMIT and
            failed_candidate.get("flash_mode") == "fresh" and
            "state_overflow" in failed_messages and
            failed_run.get("cleanup_after", {}).get("complete") is False,
            "fail-closed predecessor binding mismatch")

    run_check([
        sys.executable, str(checker), "--run", str(source),
        "--expected-version", VERSION, "--expected-cid", CID,
        "--source-commit", args.firmware_source_commit,
    ], "independent run check failed")
    run_check([sys.executable, str(source_guard)],
              "source contract check failed")

    destination.mkdir(parents=True)
    shutil.copytree(source, destination / "run")
    shutil.copytree(failed_source, destination / "failed-predecessor")
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    for tool in (runner, checker, source_guard):
        shutil.copy2(tool, tools_dir / tool.name)
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        original = ROOT / relative
        target = source_dir / Path(relative).name
        shutil.copy2(original, target)
        source_hashes[label] = digest(target)
    for artifact, name in (
            (args.factory.resolve(), "firmware.factory.bin"),
            (args.elf.resolve(), "firmware.elf"),
            (args.map.resolve(), "firmware.map")):
        shutil.copy2(artifact, destination / name)

    firmware = destination / "run/firmware.bin"
    provenance = {
        "schema": "leshy.wifi_network_intelligence_hil.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "firmware_source_commit": args.firmware_source_commit,
        "runner_commit": args.runner_commit,
        "firmware_sha256": digest(firmware),
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_file_sha256": digest(destination / "firmware.elf"),
        "map_sha256": digest(destination / "firmware.map"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "app_image_bytes": firmware.stat().st_size,
        "factory_image_bytes": (destination / "firmware.factory.bin").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "runner_sha256": digest(tools_dir / runner.name),
        "checker_sha256": digest(tools_dir / checker.name),
        "source_guard_sha256": digest(tools_dir / source_guard.name),
        "source_sha256": source_hashes,
        "run_sha256": digest(destination / "run/run.json"),
        "failed_predecessor_run_sha256": digest(
            destination / "failed-predecessor/run.json"),
        "tft_states": len(run.get("screens", {})),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")

    facts = run["detail_facts_second"]
    metrics = run["metrics_after"]
    recovery = run["recovery_after"]
    final = run["cleanup_after"]["final_state"]
    summary_value = {
        "schema": "leshy.wifi_network_intelligence.acceptance.v1",
        "status": "pass_wifi_network_intelligence",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "failed_predecessor": {
            "source_commit": FAILED_SOURCE_COMMIT,
            "failure": "state_overflow",
            "cleanup_unproven": True,
            "retained": True,
        },
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": provenance["tft_states"],
        },
        "verified": {
            "fresh_flashes": 1,
            "manual_button_presses": 0,
            "unique_networks_first": run["live_first"]["wifi_networks_unique"],
            "unique_networks_second": run["live_second"]["wifi_networks_unique"],
            "network_identity_hash": facts["identity_hash"],
            "ssid_known": facts["ssid_known"],
            "vendor": facts["vendor"],
            "authentication": facts["authentication"],
            "pairwise_cipher": facts["pairwise_cipher"],
            "group_cipher": facts["group_cipher"],
            "channel": facts["channel"],
            "frequency_khz": facts["frequency_khz"],
            "channel_width": facts["channel_width"],
            "phy_mask": facts["phy_mask"],
            "country": facts["country"],
            "passive_only": True,
            "active_probe_allowed": False,
            "hidden_ssid_monotonic_resolution_host_tested": True,
            "hidden_ssid_resolutions_observed_in_ambient_hil": facts[
                "hidden_resolutions"],
            "network_facts_stable": True,
            "list_changed_pixels": run["list_pixel_changes"][
                "content_changed_pixels"],
            "detail_outside_signal_changed_pixels": run[
                "detail_outside_signal_pixels"],
            "chrome_changed_pixels": 0,
            "two_complete_wifi_lifecycles": True,
            "heap_total_bytes": metrics["heap_total"],
            "heap_free_bytes": metrics["heap_free"],
            "heap_min_free_bytes": metrics["heap_min_free"],
            "zero_heap_drift_after_warmup": True,
            "library_generation": recovery["generation"],
            "library_observations": recovery["observations"],
            "physical_sd_write_calls": recovery["physical_write_calls"],
            "buzzer_inactive": run["safe_outputs"]["buzzer_inactive"],
            "final_page": final["page"],
            "final_runtime_owner": final["runtime_owner"],
            "final_lease_mask": final["lease_mask"],
        },
    }
    write(summary, summary_value)
    print(json.dumps({
        "status": "retained", "files": len(indexed) + 1,
        "tft_states": provenance["tft_states"],
        "vendor": facts["vendor"],
        "hidden_resolutions": facts["hidden_resolutions"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
