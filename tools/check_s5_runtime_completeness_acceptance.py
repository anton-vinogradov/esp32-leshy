#!/usr/bin/env python3
"""Fail closed unless the exact retained S5.5 runtime proof is intact."""

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
BUNDLE = ROOT / "tests/hil/evidence/board-01-s5-runtime-completeness-0.139"
SUMMARY = ROOT / "tests/hil/evidence/board-01-s5-runtime-completeness-0.139.json"
VERSION = "0.139.0-s5-runtime-complete"
CID = "FE343253440000002000000055019CB7"
SOURCE = "6fce0e8337e2b9758ea229ffc393e0071f5e51cf"
SUMMARY_SHA256 = "4036752a2123936ba80c34bf9f552a5c1d0f9c724a2ecc969b683f0fdede22b1"
PROVENANCE_SHA256 = "5adaa644aeddfc9eb60c102e9df4cdb9ec0ff6b57848b548131c1d2e034afc9b"
INDEX_SHA256 = "2c40f1c1ac9ed7634fddd2591e627e151f1b97020417f1cce55b51a36103c33c"
RUN_SHA256 = "c72573a24b71e0dcc7e28e386629f9d0a101262ad6c270c3781979a7d764cb5c"
FIRMWARE_SHA256 = "5c7e8e86ea31595332c07303c5cd0c5804fd2955531d2019345edc585b177878"
FACTORY_SHA256 = "c45cfa3ebc0524c0249a1515ac8a7c31c9ec8da9a6cf4e60a964bd5c5acc1284"
ELF_SHA256 = "a8b2c46af001c360216b9eddc2db367105bd4662e9ed75a0624929a2227512e4"
MAP_SHA256 = "bd659ef07aff6f54ad184c236b197a2e982f09ae73b8f3d1617478548431163a"
RUNNER_SHA256 = "aa10e897a4235a62412dcfc2c7e2f6d71e92e977398626207a5451fe5e6d00e8"
CONTRACT_SHA256 = "1d49d4671503284a0c140395ba66473602b875cfeb66c45a0c68c0fd6c4b10b5"
RETAINER_SHA256 = "2951d868494a4e5436f8ba46c7b65cf134e753c7e99de8d1960d195ee753d599"
EVIDENCE_IDS = ["E-BUILD-139", "E-AUTO-100", "E-HIL-160",
                "E-POWER-001", "E-STORAGE-032", "E-RADIO-018"]
SOURCE_FILES = {
    "board": "firmware/leshy1/src/boards/esp32_div_v2/BoardProfile.h",
    "entry": "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "inventory_cpp": "firmware/leshy1/src/domain/hardware/HardwareInventory.cpp",
    "inventory_h": "firmware/leshy1/src/domain/hardware/HardwareInventory.h",
    "native_tests": "tests/native/clean_target_tests.cpp",
    "platform": "firmware/leshy1/platformio.ini",
    "power_cpp": "firmware/leshy1/src/services/power/PowerSafetyPolicy.cpp",
    "power_h": "firmware/leshy1/src/services/power/PowerSafetyPolicy.h",
    "store_cpp": "firmware/leshy1/src/storage/ProductStorePolicy.cpp",
    "store_h": "firmware/leshy1/src/storage/ProductStorePolicy.h",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, relative: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24] if path.is_file() else b""
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def verify_manifest(failures: list[str]) -> int:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX_SHA256,
            "artifact index identity mismatch")
    if not manifest.is_file():
        return 0
    indexed: set[str] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"malformed artifact-index line {number}")
            continue
        expected, relative = match.groups()
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in indexed:
            failures.append(f"unsafe/duplicate artifact path: {relative}")
            continue
        artifact = BUNDLE / path
        require(failures, artifact.is_file() and digest(artifact) == expected,
                f"artifact mismatch: {relative}")
        indexed.add(relative)
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, indexed == actual,
            "artifact index does not exactly cover bundle")
    return len(actual) + 1


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "S5.5 runtime-completeness evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    require(failures, digest(SUMMARY) == SUMMARY_SHA256,
            "acceptance summary identity mismatch")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    require(failures,
            summary.get("schema") ==
                "leshy.s5_runtime_completeness.acceptance.v1" and
            summary.get("status") ==
                "pass_runtime_checkpoint_physical_rf_open" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == EVIDENCE_IDS,
            "acceptance summary contract mismatch")
    require(failures, candidate == provenance and
            digest(BUNDLE / "provenance.json") == PROVENANCE_SHA256 and
            provenance.get("schema") ==
                "leshy.s5_runtime_completeness_hil.provenance.v1" and
            provenance.get("version") == VERSION and
            provenance.get("cid") == CID and
            provenance.get("source_commit") == SOURCE and
            provenance.get("firmware_sha256") == FIRMWARE_SHA256 and
            provenance.get("factory_sha256") == FACTORY_SHA256 and
            provenance.get("elf_sha256") == ELF_SHA256 and
            provenance.get("map_sha256") == MAP_SHA256 and
            provenance.get("runner_sha256") == RUNNER_SHA256 and
            provenance.get("source_guard_sha256") == CONTRACT_SHA256 and
            provenance.get("retainer_sha256") == RETAINER_SHA256 and
            provenance.get("run_sha256") == RUN_SHA256 and
            provenance.get("static_ram_bytes") == 208304 and
            provenance.get("linked_flash_bytes") == 3078272 and
            provenance.get("app_image_bytes") == 3078768 and
            provenance.get("factory_image_bytes") == 3144304 and
            provenance.get("elf_file_bytes") == 22735676 and
            provenance.get("map_file_bytes") == 17918189 and
            provenance.get("tft_states") == 3,
            "candidate provenance mismatch")
    require(failures,
            verify_manifest(failures) == evidence.get("files") == 31 and
            evidence.get("artifact_index_sha256") == INDEX_SHA256 and
            evidence.get("tft_states") == 3,
            "evidence inventory mismatch")
    require(failures,
            digest(BUNDLE / "run/run.json") == RUN_SHA256 and
            digest(BUNDLE / "run/firmware.bin") == FIRMWARE_SHA256 and
            app_elf_sha256(BUNDLE / "run/firmware.bin") == ELF_SHA256 and
            digest(BUNDLE / "run/firmware.elf") == ELF_SHA256 and
            digest(BUNDLE / "run/firmware.map") == MAP_SHA256 and
            digest(BUNDLE / "firmware.factory.bin") == FACTORY_SHA256 and
            digest(BUNDLE / "tools/run_1x_s5_runtime_completeness_hil.py") ==
                RUNNER_SHA256 and
            digest(BUNDLE / "tools/check_s5_runtime_completeness_contract.py") ==
                CONTRACT_SHA256 and
            digest(BUNDLE / "tools/retain_1x_s5_runtime_completeness_hil.py") ==
                RETAINER_SHA256,
            "retained binary/tool identity mismatch")
    for label, relative in SOURCE_FILES.items():
        retained = BUNDLE / "source" / Path(relative).name
        blob = git_blob(SOURCE, relative)
        expected = provenance.get("source_sha256", {}).get(label)
        require(failures, blob is not None and retained.is_file() and
                digest(retained) == expected and
                hashlib.sha256(blob).hexdigest() == expected,
                f"candidate source binding mismatch: {label}")
    for relative, expected in (
        ("tools/run_1x_s5_runtime_completeness_hil.py", RUNNER_SHA256),
        ("tools/check_s5_runtime_completeness_contract.py", CONTRACT_SHA256),
    ):
        blob = git_blob(SOURCE, relative)
        require(failures, blob is not None and
                hashlib.sha256(blob).hexdigest() == expected,
                f"candidate tool binding mismatch: {relative}")

    run = load(BUNDLE / "run/run.json")
    records = run.get("records", {})
    require(failures,
            run.get("schema") ==
                "leshy.s5_runtime_completeness_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate") == {
                "app_elf_sha256": ELF_SHA256,
                "firmware_sha256": FIRMWARE_SHA256,
                "flashed": True,
                "map_sha256": MAP_SHA256,
                "runner_sha256": RUNNER_SHA256,
                "source_commit": SOURCE,
                "version": VERSION,
            } and run.get("generation_before") == 109 and
            run.get("generation_after_store") == 110,
            "exact HIL run identity/continuity mismatch")
    require(failures, summary.get("verified") == {
        "assembly_profile": "stock-rf-no-gps-no-pn532",
        "final_lease_mask": 0,
        "generation_after_store": 110,
        "generation_before": 109,
        "gps": "not_applicable",
        "hil_session_ended": True,
        "light_sleep_elapsed_us": 291608,
        "light_sleep_requested_us": 300000,
        "low_voltage_samples": 3,
        "low_voltage_write_calls": 0,
        "manager_address": 117,
        "manager_address_ack": True,
        "pn532": "not_applicable",
        "sleep_heap_invariant": True,
        "subghz_application_tx_calls": 0,
        "subghz_frequency_khz": 433920,
        "subghz_pulses": 3,
        "subghz_storage_written": True,
        "voltage_available": False,
    }, "verified runtime facts mismatch")
    require(failures, summary.get("limits") == {
        "gps_present_on_stock_assembly": False,
        "open_gate": "qualified physical nRF/Sub-GHz source and two-board regression",
        "physical_subghz_positive_signal": False,
        "pn532_present_on_stock_assembly": False,
        "radio_transmit_authorized": False,
        "s5_exit_gate_closed": False,
        "subghz_capture_source": "HIL-only RX software fixture",
    }, "claim boundary mismatch")
    low = records.get("low_voltage", {})
    sleep = records.get("sleep", {})
    saved = records.get("subghz_saved", {})
    require(failures,
            low.get("status") == "pass" and
            low.get("physical_storage_opened") is False and
            low.get("physical_write_calls") == 0 and
            low.get("generation_before") == low.get("generation_after") == 109 and
            sleep.get("status") == "pass" and
            sleep.get("sleep_kind") == "esp32_light_sleep" and
            sleep.get("heap_before") == sleep.get("heap_after") == 100736 and
            sleep.get("minimum_heap_before") ==
                sleep.get("minimum_heap_after") == 86548 and
            sleep.get("radio_tx_commands") == 0 and
            saved.get("persist_state") == "saved" and
            saved.get("storage_written") is True and
            saved.get("persist_generation") == 110 and
            saved.get("application_tx_calls") == 0 and
            saved.get("tx_strobes") == saved.get("pa_table_writes") ==
                saved.get("fifo_writes") == 0 and
            records.get("ui_final", {}).get("page") == "home" and
            records.get("ui_final", {}).get("runtime_owner") == "none" and
            records.get("ui_final", {}).get("lease_mask") == 0 and
            records.get("hil_end", {}).get("active") is False,
            "runtime safety/store/final cleanup mismatch")
    for name in ("home-final", "power-runtime",
                 "subghz-software-fixture-saved"):
        png = BUNDLE / "run/frames" / f"{name}.png"
        raw = BUNDLE / "run/frames" / f"{name}.rgb565"
        require(failures, png_size(png) == (240, 320) and
                raw.is_file() and raw.stat().st_size == 153600,
                f"automatic TFT evidence mismatch: {name}")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("S5.5 runtime-completeness acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
