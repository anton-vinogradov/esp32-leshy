#!/usr/bin/env python3
"""Fail closed unless the exact 0.79 persistent Wi-Fi Capture proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-persistent-wifi-capture-0.79.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-persistent-wifi-capture-0.79"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "8568547b73b6424b8c9734eefb8396caea0eb575"
RUNNER_COMMIT = "2e4a9e15ad1461eff851f51e026026881440e5f0"


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


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.persistent_wifi_capture_acceptance.v1" and
            evidence.get("status") == "pass_persistent_wifi_capture_checkpoint" and
            evidence.get("passed") is True and evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT and
            evidence.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")
    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.79.0-persistent-frame-capture",
        "firmware_sha256": "9e4a76fb8b955566599f0cd06fd96082c09dafe58127fb60fa9baa74077ef337",
        "factory_sha256": "0c3fb99af1952ba482fdf2c9f8033625b00ecdf764d6c42ecee10d16fbe22769",
        "app_elf_sha256": "0b1a83a7dec23ebbaa667cad9ba48cbfba8a4990a555a79f7b9c59fa2c7ce309",
        "map_sha256": "6c15c56ce8bcf45e76121a3e9d1e57b3d5dfbe221c98f96f7125c0064d6a9a0f",
        "firmware_bytes": 1454832, "factory_bytes": 1520368,
        "linked_flash_bytes": 1454428, "linked_ram_bytes": 152424,
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
    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_persistent_wifi_capture_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.persistent_wifi_capture_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256") and
                run.get("candidate") == {
                    "version": candidate.get("version"),
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "source_commit": SOURCE_COMMIT, "flashed": True,
                }, "physical run identity mismatch")
        before = run.get("boot_before", {})
        after = run.get("boot_after", {})
        before_ready = before.get("ready", {})
        after_ready = after.get("ready", {})
        before_recovery = before.get("recovery", {})
        after_recovery = after.get("recovery", {})
        heap = (physical.get("heap_total"), physical.get("heap_free"),
                physical.get("heap_min_free"))
        require(failures,
                before_ready.get("version") == candidate.get("version") and
                before_ready.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                (before_ready.get("heap_total"), before_ready.get("heap_free"),
                 before_ready.get("heap_min_free")) == heap and
                (after_ready.get("heap_total"), after_ready.get("heap_free"),
                 after_ready.get("heap_min_free")) == heap and
                before_ready.get("buzzer_inactive") is True and
                after_ready.get("buzzer_inactive") is True and
                before_ready.get("input_detected") is True and
                after_ready.get("input_detected") is True,
                "cold-reboot candidate/heap/safety mismatch")
        require(failures,
                before_recovery.get("status") == "admitted" and
                before_recovery.get("generation") == physical.get("generation_before") and
                before_recovery.get("observations") == physical.get("prior_observations") and
                after_recovery.get("status") == "admitted" and
                after_recovery.get("expected_fingerprint") == CID and
                after_recovery.get("observed_fingerprint") == CID and
                after_recovery.get("generation") == physical.get("generation_after") and
                after_recovery.get("observations") == 0 and
                after_recovery.get("mounted_read_only") is True and
                after_recovery.get("physical_write_calls") == 0 and
                after_recovery.get("cleanup_complete") is True and
                after_recovery.get("owned_after") == 0,
                "atomic generation/cold recovery mismatch")
        capture = run.get("capture", {})
        setup = capture.get("setup", {})
        complete = capture.get("complete", {})
        confirm = capture.get("confirm", {})
        saved = capture.get("saved", {})
        scrubbed = capture.get("scrubbed", {})
        require(failures,
                setup.get("state") == "idle" and setup.get("lease_mask") == 3 and
                setup.get("maximum_frames") == 16 and setup.get("snap_length") == 256 and
                setup.get("rx_only") is True and setup.get("passive_only") is True,
                "Capture setup contract mismatch")
        require(failures,
                complete.get("state") == "complete" and
                complete.get("frames_reported") == physical.get("reported_frames") and
                complete.get("frames_accepted") == physical.get("accepted_frames") and
                complete.get("frames_dropped_capacity") == physical.get("dropped_capacity") and
                complete.get("frames_dropped_invalid") == physical.get("dropped_invalid") and
                complete.get("payload_bytes") == physical.get("captured_frame_bytes") and
                complete.get("application_connect_calls") == 0 and
                complete.get("application_raw_tx_calls") == 0 and
                complete.get("storage_written") is False,
                "Capture terminal accounting mismatch")
        require(failures,
                confirm.get("persist_state") == "confirm" and
                confirm.get("persist_status") == "awaiting_confirmation" and
                confirm.get("storage_written") is False and confirm.get("lease_mask") == 1 and
                saved.get("persist_state") == "saved" and
                saved.get("persist_status") == "saved" and
                saved.get("persist_generation") == physical.get("generation_after") and
                saved.get("storage_written") is True and saved.get("lease_mask") == 1,
                "explicit privacy-confirmed save mismatch")
        summary = run.get("live_pcap", {}).get("summary", {})
        equivalence = run.get("pcap_equivalence", {})
        require(failures,
                summary.get("magic") == "a1b2c3d4" and summary.get("version") == "2.4" and
                summary.get("linktype") == physical.get("pcap_linktype") == 127 and
                summary.get("snaplen") == physical.get("pcap_snaplen") == 271 and
                summary.get("records") == physical.get("pcap_records") == 16 and
                summary.get("bytes") == physical.get("pcap_bytes") == 2773 and
                summary.get("captured_frame_bytes") == physical.get("captured_frame_bytes") and
                summary.get("original_frame_bytes") == physical.get("original_frame_bytes") and
                summary.get("sha256") == physical.get("pcap_sha256") and
                summary.get("frequencies_mhz") == physical.get("frequencies_mhz") and
                summary.get("rssi_min_dbm") == physical.get("rssi_min_dbm") and
                summary.get("rssi_max_dbm") == physical.get("rssi_max_dbm") and
                equivalence == {"byte_exact": True, "bytes": 2773,
                                "sha256": physical.get("pcap_sha256")},
                "live/cold PCAP equivalence mismatch")
        metadata = run.get("library", {}).get("metadata", {})
        library_begin = run.get("library", {}).get("pcap_begin", {})
        require(failures,
                metadata.get("generation") == physical.get("generation_after") and
                metadata.get("persistent") is True and metadata.get("integrity") == "valid" and
                metadata.get("radio_touched") is False and metadata.get("observations") == 0 and
                metadata.get("payload") == {
                    "status": "captured_raw_80211", "bytes": 2253,
                    "records": 16, "snap_length": 256, "format": "ieee80211",
                } and metadata.get("exports", {}).get("pcap") == "available_radiotap" and
                library_begin.get("generation") == physical.get("generation_after") and
                library_begin.get("persistent") is True and
                library_begin.get("radio_touched") is False,
                "cold Library metadata/PCAP mismatch")
        require(failures,
                scrubbed.get("state") == "idle" and scrubbed.get("frames_accepted") == 0 and
                scrubbed.get("payload_bytes") == 0 and scrubbed.get("pcap_available") is False and
                scrubbed.get("lease_mask") == 0 and
                run.get("final", {}).get("page") == "home" and
                run.get("final", {}).get("runtime_owner") == physical.get("final_owner") == "none" and
                run.get("final", {}).get("lease_mask") == physical.get("final_lease_mask") == 0 and
                run.get("cleanup_before", {}).get("complete") is True and
                run.get("cleanup_after", {}).get("complete") is True,
                "scrub/final cleanup mismatch")
        require(failures, run.get("privacy") == {
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "persistent_payload_location": "enrolled_product_sd_only",
            "retained_pcap_summary": "hash_counts_tuning_rssi_range_only",
        }, "privacy retention contract mismatch")
        captures = run.get("captures", {})
        expected_captures = {
            "setup", "running", "result", "confirm", "saved", "home",
            "library_list", "library_detail", "library_export",
        }
        require(failures, set(captures) == expected_captures and
                len(captures) == physical.get("screen_count") == 9,
                "TFT capture set mismatch")
        for key, record in captures.items():
            filename = key.replace("_", "-") + ".png"
            path = BUNDLE / "frames" / filename
            require(failures,
                    path.is_file() and png_dimensions(path) == (240, 320) and
                    digest(path) == record.get("png_sha256"),
                    f"{key} TFT capture mismatch")
        require(failures,
                digest(BUNDLE / "frames/saved.png") == physical.get("saved_png_sha256") and
                digest(BUNDLE / "frames/library-export.png") ==
                physical.get("library_export_png_sha256"),
                "saved/Library TFT binding mismatch")

    require(failures, evidence.get("accepted_contract") and
            all(value is True for value in evidence["accepted_contract"].values()),
            "accepted contract is incomplete")
    require(failures, evidence.get("open_scope") == {
        "conditional_nrf24_cc1101_gps_contracts": True,
        "applicable_full_guided_self_test": True,
        "controlled_power_cut": True,
        "eight_hour_multisource_endurance": True,
        "stage_demo_s4": True,
        "release_promotion": True,
    }, "open scope mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-080", "E-AUTO-044", "E-HIL-104", "E-CAPTURE-002",
    ], "evidence IDs mismatch")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Persistent Wi-Fi Capture acceptance passed: exact 0.79 candidate, "
          "explicit privacy-confirmed atomic save, schema-v4 cold reopen, byte-exact "
          "Library PCAP, heap invariance, nine TFT frames and final lease 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
