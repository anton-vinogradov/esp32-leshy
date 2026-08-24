#!/usr/bin/env python3
"""Retain the exact one-board S5.5 runtime-completeness HIL pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.139.0-s5-runtime-complete"
CID = "FE343253440000002000000055019CB7"
EVIDENCE_IDS = ["E-BUILD-139", "E-AUTO-100", "E-HIL-160",
                "E-POWER-001", "E-STORAGE-032", "E-RADIO-018"]
SOURCE_FILES = {
    "entry": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "board": "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h",
    "power_h": "firmware/leshy1/src/services/power/PowerSafetyPolicy.h",
    "power_cpp": "firmware/leshy1/src/services/power/PowerSafetyPolicy.cpp",
    "store_h": "firmware/leshy1/src/storage/ProductStorePolicy.h",
    "store_cpp": "firmware/leshy1/src/storage/ProductStorePolicy.cpp",
    "inventory_h": "firmware/leshy1/src/domain/hardware/HardwareInventory.h",
    "inventory_cpp": "firmware/leshy1/src/domain/hardware/HardwareInventory.cpp",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "platform": "firmware/leshy1/platformio.ini",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(commit: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(completed.returncode == 0,
            f"candidate source blob missing: {relative}")
    return completed.stdout


def verify_run(run: dict[str, Any], source: Path,
               factory: Path) -> None:
    candidate = run.get("candidate", {})
    records = run.get("records", {})
    power = records.get("power_before", {})
    low = records.get("low_voltage", {})
    sleep = records.get("sleep", {})
    after_sleep = records.get("power_after_public_sleep", {})
    fixture = records.get("subghz_fixture", {})
    capture = records.get("subghz_complete", {})
    saved = records.get("subghz_saved", {})
    final = records.get("ui_final", {})
    outputs = records.get("outputs_final", {})
    hil_end = records.get("hil_end", {})
    scope = run.get("scope", {})
    require(run.get("schema") ==
                "leshy.s5_runtime_completeness_hil.run.v1" and
            run.get("passed") is True and
            run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("expected_cid") == CID and
            candidate.get("version") == VERSION and
            candidate.get("flashed") is True,
            "source is not the exact fresh-flash S5.5 pass")
    require(digest(source / "firmware.bin") ==
                candidate.get("firmware_sha256") and
            digest(source / "firmware.elf") ==
                candidate.get("app_elf_sha256") and
            digest(source / "firmware.map") ==
                candidate.get("map_sha256") and
            digest(source / "run_1x_s5_runtime_completeness_hil.py") ==
                candidate.get("runner_sha256"),
            "candidate artifact identity mismatch")
    require(power.get("assembly_profile") ==
                "stock-rf-no-gps-no-pn532" and
            power.get("manager_address") == 117 and
            power.get("manager_address_ack") is True and
            power.get("manager_identified") is False and
            power.get("voltage_available") is False and
            power.get("voltage_source") ==
                "gpio2_forbidden_buzzer_shared" and
            power.get("write_disposition") == "atomic_only" and
            power.get("gps") == "not_applicable" and
            power.get("pn532") == "not_applicable",
            "truthful assembly/power profile mismatch")
    require(low.get("status") == "pass" and
            low.get("samples") == 3 and
            low.get("store_permit") == "power_unsafe" and
            low.get("write_disposition") ==
                "prohibited_low_voltage" and
            low.get("physical_storage_opened") is False and
            low.get("physical_write_calls") == 0 and
            low.get("generation_before") == low.get("generation_after") ==
                run.get("generation_before"),
            "low-voltage fail-closed proof mismatch")
    require(sleep.get("status") == "pass" and
            sleep.get("sleep_kind") == "esp32_light_sleep" and
            sleep.get("requested_us") == 300000 and
            280000 <= int(sleep.get("elapsed_us", 0)) <= 800000 and
            sleep.get("wakeup") == "timer" and
            sleep.get("heap_before") == sleep.get("heap_after") and
            sleep.get("minimum_heap_before") ==
                sleep.get("minimum_heap_after") and
            sleep.get("generation_before") == sleep.get("generation_after") and
            sleep.get("physical_write_calls") == 0 and
            sleep.get("radio_tx_commands") == 0 and
            sleep.get("lease_mask") == 0 and
            sleep.get("backlight_restored") is True and
            sleep.get("input_task_retained") is True and
            after_sleep.get("sleep_count") == 2 and
            after_sleep.get("last_sleep_requested_us") == 1000000,
            "real light-sleep/resume proof mismatch")
    require(fixture.get("status") == "ready" and
            fixture.get("software_fixture") is True and
            fixture.get("physical_signal") is False and
            fixture.get("rx_only_semantics") is True and
            fixture.get("frequency_khz") == 433920 and
            fixture.get("pulses") == 3 and
            fixture.get("application_tx_calls") == 0 and
            fixture.get("radio_tx_commands") == 0 and
            capture.get("physical_no_tx_verified") is True and
            capture.get("tx_strobes") == 0 and
            capture.get("pa_table_writes") == 0 and
            capture.get("fifo_writes") == 0 and
            saved.get("persist_state") == "saved" and
            saved.get("storage_written") is True and
            saved.get("persist_generation") ==
                run.get("generation_after_store") ==
                run.get("generation_before") + 1 and
            int(saved.get("heap_free_before_mount", 0)) > 0 and
            int(saved.get("heap_largest_before_mount", 0)) > 0,
            "RX-only Sub-GHz Store proof mismatch")
    require(final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            outputs.get("software_quiesce_complete") is True and
            outputs.get("buzzer_inactive") is True and
            outputs.get("nrf_ce_inactive") is True and
            hil_end.get("status") == "ended" and
            hil_end.get("active") is False,
            "final cleanup/HIL-session proof mismatch")
    require(scope == {
        "actual_light_sleep": True,
        "low_voltage_injection": True,
        "low_voltage_physical_write_calls": 0,
        "manual_button_presses": 0,
        "physical_subghz_positive_gate_closed": False,
        "screenshots_automatic": True,
        "subghz_application_tx_calls": 0,
        "subghz_normal_store_authorized": True,
        "subghz_physical_signal": False,
        "subghz_software_fixture": True,
    }, "scope/claim boundary mismatch")
    require(digest(factory) ==
                "c45cfa3ebc0524c0249a1515ac8a7c31c9ec8da9a6cf4e60a964bd5c5acc1284",
            "factory image identity mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--static-ram-bytes", required=True, type=int)
    parser.add_argument("--linked-flash-bytes", required=True, type=int)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    summary = args.summary.resolve()
    factory = args.factory.resolve()
    require(not destination.exists() and not summary.exists(),
            "destination and summary must not exist")
    required = [source / "run.json", source / "firmware.bin",
                source / "firmware.elf", source / "firmware.map",
                source / "run_1x_s5_runtime_completeness_hil.py", factory]
    require(all(path.is_file() for path in required),
            "required runtime artifact missing")
    run = load(source / "run.json")
    verify_run(run, source, factory)
    commit = run["candidate"]["source_commit"]
    runner = ROOT / "tools/run_1x_s5_runtime_completeness_hil.py"
    contract = ROOT / "tools/check_s5_runtime_completeness_contract.py"
    packer = Path(__file__).resolve()
    require(digest(runner) == run["candidate"]["runner_sha256"],
            "working runner differs from executed runner")
    source_check = subprocess.run(
        [sys.executable, str(contract)], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(source_check.returncode == 0,
            f"source contract failed: {source_check.stdout}")
    for relative in (*SOURCE_FILES.values(),
                     "tools/run_1x_s5_runtime_completeness_hil.py",
                     "tools/check_s5_runtime_completeness_contract.py"):
        require((ROOT / relative).read_bytes() == git_blob(commit, relative),
                f"working source differs from candidate: {relative}")

    shutil.copytree(source, destination / "run")
    shutil.copy2(factory, destination / "firmware.factory.bin")
    tools_dir = destination / "tools"
    tools_dir.mkdir()
    for tool in (runner, contract, packer):
        shutil.copy2(tool, tools_dir / tool.name)
    source_dir = destination / "source"
    source_dir.mkdir()
    source_hashes: dict[str, str] = {}
    for label, relative in SOURCE_FILES.items():
        target = source_dir / Path(relative).name
        shutil.copy2(ROOT / relative, target)
        source_hashes[label] = digest(target)

    candidate = run["candidate"]
    records = run["records"]
    provenance = {
        "schema": "leshy.s5_runtime_completeness_hil.provenance.v1",
        "version": VERSION,
        "cid": CID,
        "source_commit": commit,
        "firmware_sha256": candidate["firmware_sha256"],
        "factory_sha256": digest(destination / "firmware.factory.bin"),
        "elf_sha256": candidate["app_elf_sha256"],
        "map_sha256": candidate["map_sha256"],
        "runner_sha256": digest(tools_dir / runner.name),
        "source_guard_sha256": digest(tools_dir / contract.name),
        "retainer_sha256": digest(tools_dir / packer.name),
        "source_sha256": source_hashes,
        "run_sha256": digest(destination / "run/run.json"),
        "app_image_bytes": (destination / "run/firmware.bin").stat().st_size,
        "factory_image_bytes":
            (destination / "firmware.factory.bin").stat().st_size,
        "elf_file_bytes": (destination / "run/firmware.elf").stat().st_size,
        "map_file_bytes": (destination / "run/firmware.map").stat().st_size,
        "static_ram_bytes": args.static_ram_bytes,
        "linked_flash_bytes": args.linked_flash_bytes,
        "tft_states": sum(
            1 for value in records.values()
            if isinstance(value, dict) and "frame_begin" in value),
    }
    write(destination / "provenance.json", provenance)
    indexed = sorted(path for path in destination.rglob("*") if path.is_file())
    manifest = destination / "artifacts.sha256"
    manifest.write_text("".join(
        f"{digest(path)}  {path.relative_to(destination)}\n"
        for path in indexed), encoding="utf-8")
    low = records["low_voltage"]
    sleep = records["sleep"]
    saved = records["subghz_saved"]
    summary_value = {
        "schema": "leshy.s5_runtime_completeness.acceptance.v1",
        "status": "pass_runtime_checkpoint_physical_rf_open",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": provenance,
        "evidence": {
            "artifact_index_sha256": digest(manifest),
            "files": len(indexed) + 1,
            "tft_states": provenance["tft_states"],
        },
        "verified": {
            "assembly_profile": records["power_before"]["assembly_profile"],
            "manager_address": records["power_before"]["manager_address"],
            "manager_address_ack": True,
            "voltage_available": False,
            "gps": "not_applicable",
            "pn532": "not_applicable",
            "low_voltage_samples": low["samples"],
            "low_voltage_write_calls": low["physical_write_calls"],
            "light_sleep_requested_us": sleep["requested_us"],
            "light_sleep_elapsed_us": sleep["elapsed_us"],
            "sleep_heap_invariant": sleep["heap_before"] == sleep["heap_after"],
            "generation_before": run["generation_before"],
            "generation_after_store": run["generation_after_store"],
            "subghz_frequency_khz": saved["frequency_khz"],
            "subghz_pulses": saved["pulses"],
            "subghz_storage_written": saved["storage_written"],
            "subghz_application_tx_calls": saved["application_tx_calls"],
            "final_lease_mask": records["ui_final"]["lease_mask"],
            "hil_session_ended": records["hil_end"]["active"] is False,
        },
        "limits": {
            "physical_subghz_positive_signal": False,
            "subghz_capture_source": "HIL-only RX software fixture",
            "radio_transmit_authorized": False,
            "gps_present_on_stock_assembly": False,
            "pn532_present_on_stock_assembly": False,
            "s5_exit_gate_closed": False,
            "open_gate": "qualified physical nRF/Sub-GHz source and two-board regression",
        },
    }
    write(summary, summary_value)
    print(json.dumps({"bundle": str(destination), "summary": str(summary),
                      "files": len(indexed) + 1, "status": "pass"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
