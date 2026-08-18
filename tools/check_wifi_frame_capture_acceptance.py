#!/usr/bin/env python3
"""Fail closed unless the exact 0.78 volatile Wi-Fi Capture is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-wifi-frame-capture-0.78.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-wifi-frame-capture-0.78"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "0bc06d2573f5b2ea72572fd07566194996c67e95"
RUNNER_COMMIT = "36ec549dcc495124e4e2b19c4500bf2d1a8d6fa9"


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
            evidence.get("schema") == "leshy.wifi_frame_capture_acceptance.v1" and
            evidence.get("status") == "pass_volatile_wifi_frame_capture_checkpoint" and
            evidence.get("passed") is True and evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT and
            evidence.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")
    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.78.0-wifi-frame-capture",
        "firmware_sha256": "68841ec64c341b079afb83a4e5f2382cf01de949565596a7512ec12590a2568b",
        "factory_sha256": "4e3f3401f696b62e7dd3245d7db484ee1f83403d37a1fb4da2d46386c248e993",
        "app_elf_sha256": "b62345dc5245d99a975a00fb47e3c4b54d3db922654f34674243d03e1e827647",
        "map_sha256": "f4188a5e8be455f9f0207533a9ff3bda498d727ed083bc2b61e11b3e5fc342c6",
        "firmware_bytes": 1446400, "factory_bytes": 1511936,
        "linked_flash_bytes": 1446000, "linked_ram_bytes": 152376,
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
    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_wifi_frame_capture_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures,
                hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.wifi_frame_capture_hil.run.v1" and
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
        ready = run.get("boot", {}).get("ready", {})
        recovery = run.get("boot", {}).get("recovery", {})
        require(failures,
                ready.get("version") == candidate.get("version") and
                ready.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                ready.get("heap_total") == physical.get("heap_total") and
                ready.get("heap_free") == physical.get("heap_free") and
                ready.get("heap_min_free") == physical.get("heap_min_free") and
                ready.get("buzzer_inactive") is True and ready.get("input_detected") is True,
                "boot candidate/heap/safety mismatch")
        require(failures,
                recovery.get("status") == "admitted" and
                recovery.get("expected_fingerprint") == CID and
                recovery.get("observed_fingerprint") == CID and
                recovery.get("generation") == physical.get("generation") and
                recovery.get("observations") == physical.get("prior_observations") and
                recovery.get("mounted_read_only") is True and
                recovery.get("physical_write_calls") == 0 and
                recovery.get("cleanup_complete") is True and recovery.get("owned_after") == 0,
                "read-only boot recovery mismatch")
        setup = run.get("setup", {})
        running = run.get("running", {})
        complete = run.get("complete", {})
        require(failures,
                setup.get("state") == "idle" and setup.get("lease_mask") == 3 and
                setup.get("maximum_frames") == 16 and setup.get("snap_length") == 256 and
                setup.get("rx_only") is True and setup.get("passive_only") is True and
                setup.get("volatile_ram") is True and setup.get("storage_written") is False,
                "Capture setup contract mismatch")
        require(failures,
                running.get("state") == "running" and running.get("cleanup_complete") is False and
                running.get("frames_accepted") == 15 and running.get("payload_bytes") == 3840 and
                running.get("lease_mask") == 3,
                "Capture running checkpoint mismatch")
        require(failures,
                complete.get("state") == "complete" and complete.get("cleanup_complete") is True and
                complete.get("frames_reported") == physical.get("reported_frames") and
                complete.get("frames_accepted") == physical.get("accepted_frames") and
                complete.get("frames_dropped_capacity") == physical.get("dropped_capacity") and
                complete.get("frames_dropped_invalid") == physical.get("dropped_invalid") and
                complete.get("payload_bytes") == physical.get("captured_frame_bytes") and
                complete.get("pcap_available") is True and
                complete.get("application_connect_calls") == 0 and
                complete.get("application_raw_tx_calls") == 0 and
                complete.get("storage_written") is False,
                "Capture terminal accounting mismatch")
        summary = run.get("pcap", {}).get("summary", {})
        require(failures,
                summary.get("magic") == "a1b2c3d4" and summary.get("version") == "2.4" and
                summary.get("linktype") == physical.get("pcap_linktype") == 127 and
                summary.get("snaplen") == physical.get("pcap_snaplen") == 271 and
                summary.get("records") == physical.get("pcap_records") == 16 and
                summary.get("bytes") == physical.get("pcap_bytes") == 4616 and
                summary.get("captured_frame_bytes") == physical.get("captured_frame_bytes") and
                summary.get("original_frame_bytes") == physical.get("original_frame_bytes") and
                summary.get("sha256") == physical.get("pcap_sha256") and
                summary.get("frequencies_mhz") == physical.get("frequencies_mhz") and
                summary.get("rssi_min_dbm") == physical.get("rssi_min_dbm") and
                summary.get("rssi_max_dbm") == physical.get("rssi_max_dbm") and
                sum(summary.get("frame_types", {}).values()) == 16 and
                summary.get("payload_retained") is False,
                "streamed PCAP summary mismatch")
        require(failures, run.get("privacy") == {
            "pcap_retained_in_evidence": False,
            "raw_80211_payload_retained_in_evidence": False,
            "retained_pcap_summary": "hash_counts_tuning_rssi_range_only",
        }, "privacy retention contract mismatch")
        scrubbed = run.get("scrubbed", {})
        final = run.get("final", {})
        require(failures,
                scrubbed.get("state") == "idle" and scrubbed.get("frames_reported") == 0 and
                scrubbed.get("frames_accepted") == 0 and scrubbed.get("payload_bytes") == 0 and
                scrubbed.get("pcap_available") is False and scrubbed.get("lease_mask") == 0 and
                final.get("page") == "home" and
                final.get("runtime_owner") == physical.get("final_owner") == "none" and
                final.get("lease_mask") == physical.get("final_lease_mask") == 0 and
                run.get("cleanup", {}).get("complete") is True,
                "scrub/final cleanup mismatch")
        captures = run.get("captures", {})
        require(failures, set(captures) == {"setup", "running", "result", "home", "home_last"} and
                len(captures) == physical.get("screen_count") == 5,
                "TFT capture set mismatch")
        for key, record in captures.items():
            filename = key.replace("_", "-") + ".png"
            path = BUNDLE / "frames" / filename
            require(failures,
                    path.is_file() and png_dimensions(path) == (240, 320) and
                    digest(path) == record.get("png_sha256"),
                    f"{key} TFT capture mismatch")
        require(failures,
                digest(BUNDLE / "frames/result.png") == physical.get("result_png_sha256"),
                "result TFT binding mismatch")

    require(failures, evidence.get("accepted_contract") and
            all(value is True for value in evidence["accepted_contract"].values()),
            "accepted contract is incomplete")
    require(failures, evidence.get("open_scope") == {
        "atomic_persistent_capture_and_library_entry": True,
        "privacy_controls_and_user_selected_retention": True,
        "conditional_nrf24_cc1101_gps_contracts": True,
        "applicable_full_guided_self_test": True,
        "controlled_power_cut": True,
        "eight_hour_multisource_endurance": True,
        "release_promotion": True,
    }, "open scope mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-079", "E-AUTO-043", "E-HIL-103", "E-CAPTURE-001",
    ], "evidence IDs mismatch")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("Wi-Fi frame Capture acceptance passed: exact 0.78 candidate, bounded RX-only "
          "RAM, 16-record radiotap PCAP, privacy-safe retained evidence, five TFT "
          "frames, read-only prior session, scrubbed payload and final lease 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
