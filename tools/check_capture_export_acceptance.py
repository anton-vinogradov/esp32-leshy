#!/usr/bin/env python3
"""Fail closed unless the exact 0.77 capture/export checkpoint is intact."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-capture-export-0.77.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-capture-export-0.77"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "b9e9346f8ea708ba976440f586b48f47eec616d6"
CSV_HEADER = [
    "session_id", "sequence", "monotonic_us", "radio", "frequency_khz",
    "channel", "rssi_dbm", "identity_hex", "label_hex",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def verify_index(failures: list[str], index: Path) -> None:
    require(failures, index.is_file(), "artifact index missing")
    if not index.is_file():
        return
    expected: dict[str, str] = {}
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
            continue
        expected[parts[1]] = parts[0]
    for relative, expected_hash in expected.items():
        path = BUNDLE / relative
        require(failures, path.is_file(), f"indexed artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected_hash,
                    f"indexed artifact hash mismatch: {relative}")
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual,
            "artifact index is not an exact bundle inventory")


def verify_boot(failures: list[str], record: dict[str, Any],
                candidate: dict[str, Any], generation: int,
                observations: int) -> None:
    ready = record.get("ready", {})
    recovery = record.get("recovery", {})
    require(failures,
            ready.get("version") == candidate.get("version") and
            ready.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
            ready.get("heap_total") == 234020 and
            ready.get("heap_free") == 169400 and
            ready.get("heap_min_free") == 149880 and
            ready.get("buzzer_inactive") is True and
            ready.get("input_detected") is True,
            "boot candidate/heap/safety mismatch")
    attempts = recovery.get("attempts")
    require(failures,
            recovery.get("status") == "admitted" and
            recovery.get("expected_fingerprint") == CID and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("fingerprint_matched") is True and
            recovery.get("generation") == generation and
            recovery.get("observations") == observations and
            isinstance(attempts, int) and 1 <= attempts <= 8 and
            recovery.get("transient_retries") == attempts - 1 and
            recovery.get("timeout_restarts") == 0 and
            recovery.get("mounted_read_only") is True and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("cleanup_complete") is True and
            recovery.get("owned_after") == 0,
            "boot read-only recovery mismatch")


def verify_csv(failures: list[str], run: dict[str, Any], physical: dict[str, Any]) -> None:
    path = BUNDLE / "observations.csv"
    require(failures,
            path.is_file() and digest(path) == physical.get("csv_sha256") and
            path.stat().st_size == physical.get("csv_bytes"),
            "retained CSV binding mismatch")
    if not path.is_file():
        return
    payload = path.read_bytes()
    require(failures,
            payload.count(b"\r\n") == 48 and b"\n" not in payload.replace(b"\r\n", b""),
            "CSV line endings/count mismatch")
    with path.open("r", encoding="ascii", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        require(failures, reader.fieldnames == CSV_HEADER, "CSV header mismatch")
    require(failures, len(rows) == 47, "CSV row count mismatch")
    require(failures,
            [int(row["sequence"]) for row in rows] == list(range(1, 48)),
            "CSV sequence is not exact")
    require(failures,
            all(int(first["monotonic_us"]) <= int(second["monotonic_us"])
                for first, second in zip(rows, rows[1:])),
            "CSV monotonic order mismatch")
    require(failures,
            sum(row["radio"] == "wifi" for row in rows) == 16 and
            sum(row["radio"] == "ble" for row in rows) == 31 and
            all(-127 <= int(row["rssi_dbm"]) <= 0 for row in rows),
            "CSV source/RSSI accounting mismatch")
    framing = run.get("csv_export", {})
    require(failures,
            framing.get("rows_validated") == 47 and
            framing.get("begin", {}).get("records") == 47 and
            framing.get("begin", {}).get("line_endings") == "crlf" and
            framing.get("end", {}).get("status") == "complete" and
            framing.get("end", {}).get("bytes") == len(payload) == 3275,
            "CSV framing evidence mismatch")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.capture_export_acceptance.v1" and
            evidence.get("status") == "pass_capture_export_checkpoint" and
            evidence.get("passed") is True and
            evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT,
            "acceptance identity mismatch")
    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.77.0-capture-export",
        "firmware_sha256": "60d968344049e5faf9b24bca01bbdf5655ae7d81280692d513035a7af9364b4d",
        "factory_sha256": "cfe5c9c1c50d6e3fded9033384090547ae0daa938dc82790bd4666627ced09fa",
        "app_elf_sha256": "ae41dd3c7daa6ae34d5fba0eb652775b8db4bf8b863711a26b79df0106b58268",
        "map_sha256": "82f7d7d4a48be1b7b32e3fd96af9699619b36468309d9d7450342491bc3d14ce",
        "firmware_bytes": 1433216,
        "factory_bytes": 1498752,
        "linked_flash_bytes": 1432812,
        "linked_ram_bytes": 147688,
        "rtc_noinit_bytes": 60,
    }, "exact candidate metadata mismatch")
    physical = evidence.get("physical", {})
    run_path = BUNDLE / "run.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures,
            run_path.is_file() and digest(run_path) == physical.get("run_sha256") and
            physical.get("run_path") == str(run_path.relative_to(ROOT)),
            "physical run binding mismatch")
    require(failures,
            index_path.is_file() and digest(index_path) == physical.get("artifact_index_sha256") and
            physical.get("artifact_index_path") == str(index_path.relative_to(ROOT)),
            "artifact index binding mismatch")
    verify_index(failures, index_path)
    for field, filename in (("firmware_sha256", "firmware.bin"),
                            ("factory_sha256", "firmware.factory.bin")):
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == candidate.get(field),
                f"retained {filename} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures,
                app_elf_sha256(BUNDLE / "firmware.bin") == candidate.get("app_elf_sha256"),
                "retained app identity mismatch")
    runner_blob = git_blob(SOURCE_COMMIT, "tools/run_1x_capture_export_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.capture_export_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256") and
                run.get("candidate") == {
                    "version": candidate.get("version"),
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "flashed": True,
                }, "physical run identity mismatch")
        verify_boot(failures, run.get("post_flash", {}), candidate, 81, 45)
        verify_boot(failures, run.get("boot_before", {}), candidate, 81, 45)
        verify_boot(failures, run.get("boot_after", {}), candidate, 82, 47)
        running = run.get("running", {})
        require(failures,
                running.get("survey_product_wifi_scan_cycles") == 1 and
                running.get("survey_product_ble_scan_cycles") == 1 and
                running.get("survey_scan_accepted") == 16 and
                running.get("survey_ble_scan_accepted") == 31 and
                running.get("survey_observations") == 47 and
                running.get("survey_forwarded") == 47 and
                running.get("survey_dropped") == 0 and
                running.get("survey_queue_depth") == 0 and
                running.get("survey_queue_high_water") == 11 and
                running.get("survey_timeline_overflow") == 0,
                "dual-source runtime mismatch")
        committed = run.get("committed", {})
        require(failures,
                committed.get("survey_generation") == 82 and
                committed.get("survey_observations") == 47 and
                committed.get("survey_product_store_bytes_written") == 2473 and
                committed.get("survey_timeline_persisted_windows") == 6 and
                committed.get("survey_timeline_evicted_windows") == 0 and
                committed.get("survey_timeline_overflow") == 0,
                "schema-v3 commit mismatch")
        metadata = run.get("capture_metadata", {})
        require(failures,
                metadata.get("status") == "valid" and
                metadata.get("generation") == 82 and
                metadata.get("immutable") is True and
                metadata.get("observations") == 47 and
                metadata.get("sources") == {"wifi": 16, "ble": 31} and
                metadata.get("build") == {"app_elf_sha256": candidate.get("app_elf_sha256")} and
                metadata.get("receive", {}).get("mode") == "passive" and
                metadata.get("receive", {}).get("selected_mask") == 3 and
                metadata.get("location") == {"status": "not_recorded"} and
                metadata.get("payload") == {"status": "not_captured", "bytes": 0} and
                metadata.get("exports", {}).get("pcap") == "unavailable_no_frame_payload" and
                metadata.get("radio_touched") is False,
                "immutable capture metadata mismatch")
        verify_csv(failures, run, physical)
        require(failures, run.get("pcap_status") == {
            "schema": "leshy.library.pcap.v1", "kind": "artifact",
            "status": "unavailable_no_frame_payload", "generation": 82,
            "session_id": "product-passive-live", "records": 0, "bytes": 0,
            "radio_touched": False,
        }, "honest PCAP status mismatch")
        captures = run.get("captures", {})
        require(failures, len(captures) == physical.get("screen_count") == 10,
                "TFT capture count mismatch")
        for key, record in captures.items():
            filename = key.replace("_", "-") + ".png"
            path = BUNDLE / "frames" / filename
            require(failures,
                    path.is_file() and png_dimensions(path) == (240, 320) and
                    digest(path) == record.get("png_sha256"),
                    f"{key} TFT capture mismatch")
        export_screen = BUNDLE / "frames/export-ready.png"
        require(failures,
                export_screen.is_file() and
                digest(export_screen) == physical.get("export_ready_png_sha256"),
                "export-ready TFT binding mismatch")
        final = run.get("final", {})
        require(failures,
                final.get("page") == "home" and
                final.get("runtime_owner") == physical.get("final_owner") == "none" and
                final.get("lease_mask") == physical.get("final_lease_mask") == 0 and
                final.get("library_generation") == 82 and
                run.get("cleanup_after", {}).get("complete") is True,
                "final cleanup/lease mismatch")

    require(failures,
            evidence.get("accepted_contract") and
            all(value is True for value in evidence["accepted_contract"].values()),
            "accepted contract is incomplete")
    require(failures, evidence.get("open_scope") == {
        "raw_frame_capture_and_compatible_pcap": True,
        "conditional_nrf24_cc1101_gps_contracts": True,
        "applicable_full_guided_self_test": True,
        "controlled_power_cut": True,
        "eight_hour_multisource_endurance": True,
        "release_promotion": True,
    }, "open scope mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-078", "E-AUTO-042", "E-HIL-102", "E-SURVEY-015",
    ], "evidence IDs mismatch")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Capture/export acceptance passed: exact 0.77 candidate, immutable schema-v3 "
          "metadata, 47-row canonical CSV, honest PCAP N/A, cold recovery, ten TFT "
          "frames, invariant heap, zero drops and final lease 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
