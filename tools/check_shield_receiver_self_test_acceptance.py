#!/usr/bin/env python3
"""Fail closed unless the exact 0.81 read-only shield receiver proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-shield-receiver-self-test-0.81.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-shield-receiver-self-test-0.81"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "b125470ab32212a5452d7c8d3624f1e5c759cb38"
RUNNER_COMMIT = "ea0e50022f78d7d55c3160a00a1a18d39e2ad5aa"
QUICK_IDS = [
    "quick.build.identity", "quick.board.profile", "quick.runtime.heap",
    "quick.display.ready", "quick.input.frontend", "quick.input.queue",
    "quick.output.buzzer", "quick.resource.scope",
]
FULL_CHECKS = [
    *[(check_id, "pass") for check_id in QUICK_IDS],
    ("full.ui.common_states", "pass"),
    ("full.s3.survey.persistence", "pass"),
    ("full.s4.radio.ble.passive", "pass"),
    ("full.s4.capture.wifi.passive", "pass"),
    ("full.s4.storage.enrolled", "pass"),
    ("full.s4.library.recovery", "pass"),
    ("full.s4.capture.persistence", "pass"),
    ("full.assembly.gps", "not_applicable"),
    ("full.assembly.pn532", "not_applicable"),
    ("full.shield.ir", "not_applicable"),
    ("full.s4.shield.receivers", "pass"),
    ("full.capability.coverage", "blocked"),
]
CAPTURES = {
    "modes", "quick_result", "preflight", "visual_dialog_confirm",
    "visual_unavailable", "visual_degraded", "visual_error", "visual_running",
    "full_result", "home",
}


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
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual,
            "artifact index is not an exact bundle inventory")
    for relative, expected_hash in expected.items():
        path = BUNDLE / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"indexed artifact mismatch: {relative}")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    require(failures,
            evidence.get("schema") == "leshy.shield_receiver_self_test_acceptance.v1" and
            evidence.get("status") == "pass_read_only_shield_receiver_checkpoint" and
            evidence.get("passed") is True and evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT and
            evidence.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")
    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.81.0-shield-receiver-probe",
        "firmware_sha256": "2d0bc0cf424bb0497f4ba6841e262240d6b689947b61461f353e012a5cb58379",
        "factory_sha256": "fb667d4da6318ee1f197cacaf30c1acffe383f7b49e3019c0c033f9694e6c120",
        "app_elf_sha256": "e86968d448992e140c23e882373b222b9bd4478bf3320d14e83c1011a4acd033",
        "map_sha256": "963efe9b66278d6020bebc8bd7f3e320f5d1bd74910470b60cb0c4efd669a6f1",
        "firmware_bytes": 1459632, "factory_bytes": 1525168,
        "linked_flash_bytes": 1459232, "linked_ram_bytes": 152552,
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
    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_self_test_coverage_hil.py")
    require(failures, runner_blob is not None, "runner source blob missing")
    if runner_blob is not None:
        require(failures, hashlib.sha256(runner_blob).hexdigest() == physical.get("runner_sha256"),
                "runner source binding mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") == "leshy.shield_receiver_self_test_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256") and
                run.get("candidate") == {
                    "version": candidate.get("version"), "source_commit": SOURCE_COMMIT,
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"), "flashed": True,
                }, "physical run identity mismatch")
        boot = run.get("boot", {})
        require(failures,
                boot.get("version") == candidate.get("version") and
                boot.get("app_elf_sha256") == candidate.get("app_elf_sha256") and
                boot.get("profile") == evidence.get("profile") and
                (boot.get("heap_total"), boot.get("heap_free"), boot.get("heap_min_free")) ==
                (physical.get("heap_total"), physical.get("heap_free"),
                 physical.get("heap_min_free")) and
                boot.get("input_detected") is True and boot.get("buzzer_inactive") is True,
                "boot identity/resource/safety mismatch")
        for label in ("recovery_before", "recovery_after"):
            recovery = run.get(label, {})
            require(failures,
                    recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == CID and
                    recovery.get("observed_fingerprint") == CID and
                    recovery.get("generation") == physical.get("generation") == 83 and
                    recovery.get("observations") == physical.get("observations") == 0 and
                    recovery.get("mounted_read_only") is True and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("blocked_write_attempts") == 0 and
                    recovery.get("cleanup_complete") is True and
                    recovery.get("owned_after") == 0,
                    f"{label} recovery/continuity mismatch")

        quick = run.get("quick_report", {})
        full = run.get("full_report", {})
        require(failures,
                quick.get("schema") == "leshy.self_test.report.v1" and
                quick.get("plan_version") == 4 and quick.get("mode") == "quick" and
                quick.get("status") == "pass" and quick.get("read_only") is True and
                (quick.get("passed"), quick.get("failed"), quick.get("blocked"),
                 quick.get("not_applicable")) == (8, 0, 0, 0) and
                [(item.get("id"), item.get("status")) for item in quick.get("checks", [])] ==
                [(check_id, "pass") for check_id in QUICK_IDS],
                "Quick plan/report mismatch")
        require(failures,
                full.get("schema") == "leshy.self_test.report.v1" and
                full.get("plan_version") == 4 and full.get("mode") == "full_guided" and
                full.get("status") == "blocked" and full.get("read_only") is True and
                (full.get("passed"), full.get("failed"), full.get("blocked"),
                 full.get("not_applicable")) == (16, 0, 1, 3) and
                [(item.get("id"), item.get("status")) for item in full.get("checks", [])] ==
                FULL_CHECKS,
                "Full/Guided plan/report mismatch")
        expected_facts = {
            "persistent_survey_ready": True, "passive_ble_ready": True,
            "passive_wifi_capture_ready": True, "enrolled_storage_ready": True,
            "persistent_library_ready": True, "persistent_wifi_capture_ready": True,
            "gps_declared": False, "pn532_declared": False, "ir_declared": False,
            "shield_receivers_applicable": True,
            "shield_receiver_probe_complete": True,
            "shield_receiver_probe_passed": True,
        }
        require(failures,
                all(full.get("facts", {}).get(key) is value
                    for key, value in expected_facts.items()),
                "S3/S4/shield capability facts mismatch")
        for label, report in (("Quick", quick), ("Full", full)):
            require(failures, report.get("side_effects") == {
                "radio_tx_commands": 0, "storage_write_commands": 0,
                "buzzer_activations": 0,
            }, f"{label} side effects mismatch")
            require(failures,
                    report.get("current_owner") == "self-test" and
                    report.get("current_lease_mask") == 1,
                    f"{label} UI-only lease mismatch")

        shield = run.get("shield_receiver_probe", {})
        wire = shield.get("wire", {})
        effects = shield.get("side_effects", {})
        nrf = shield.get("nrf", [])
        cc = shield.get("cc1101", {})
        require(failures,
                shield.get("schema") == "leshy.shield.receiver_probe.v1" and
                shield.get("status") == "pass" and shield.get("read_only") is True and
                shield.get("profile_declared") is True and
                shield.get("gps_excluded_by_profile") is True and
                shield.get("pn532_excluded_by_profile") is True and
                shield.get("resource_acquired") is True and
                shield.get("resource_released") is True and
                shield.get("cleanup_complete") is True and
                shield.get("current_owner") == "self-test" and
                shield.get("current_lease_mask") == 1 and
                shield.get("nrf_slot3_gated") is True and
                shield.get("gpio21_stable_high") is True and
                shield.get("detected_receivers") == physical.get("detected_receivers") == 3,
                "shield probe identity/resource/safety mismatch")
        require(failures,
                wire == {"nrf_register_reads": 8, "cc_status_reads": 2,
                         "spi_bytes_clocked": 20} and
                effects == {"nrf_ce_high_events": 0, "cc_command_strobes": 0,
                            "radio_tx_commands": 0} and
                wire.get("nrf_register_reads") == physical.get("nrf_register_reads") and
                wire.get("cc_status_reads") == physical.get("cc_status_reads") and
                wire.get("spi_bytes_clocked") == physical.get("spi_bytes_clocked"),
                "shield wire/side-effect bound mismatch")
        require(failures,
                len(nrf) == 2 and [item.get("slot") for item in nrf] == [1, 2] and
                all(item.get("detected") is True and
                    isinstance(item.get("status"), int) and item.get("status") < 128 and
                    isinstance(item.get("channel"), int) and item.get("channel") <= 125
                    for item in nrf),
                "nRF24 identity plausibility mismatch")
        require(failures,
                cc.get("ready") is True and cc.get("detected") is True and
                isinstance(cc.get("status"), int) and cc.get("status") != 255 and
                cc.get("partnum") == physical.get("cc_partnum") == 0 and
                cc.get("version") == physical.get("cc_version") == 20,
                "CC1101 identity mismatch")

        input_state = run.get("input", {})
        safe = run.get("safe_outputs", {})
        final = run.get("final", {})
        require(failures,
                input_state.get("status") == "ready" and
                input_state.get("read_errors") == 0 and input_state.get("queue_drops") == 0 and
                safe.get("buzzer_inactive") is True and safe.get("buzzer_level") == "low" and
                final.get("page") == "home" and
                final.get("self_test_passed") == 16 and final.get("self_test_failed") == 0 and
                final.get("self_test_blocked") == 1 and
                final.get("runtime_owner") == physical.get("final_owner") == "none" and
                final.get("lease_mask") == physical.get("final_lease_mask") == 0 and
                run.get("cleanup_before", {}).get("complete") is True and
                run.get("cleanup_after", {}).get("complete") is True,
                "input/output/final cleanup mismatch")
        require(failures, run.get("privacy") == {
            "raw_80211_payload_retained_in_evidence": False,
            "pcap_retained_in_evidence": False,
            "self_test_report_contains_nearby_identifiers": False,
        }, "privacy retention contract mismatch")
        captures = run.get("captures", {})
        require(failures, set(captures) == CAPTURES and
                len(captures) == physical.get("screen_count") == 10,
                "TFT capture set mismatch")
        for name, item in captures.items():
            stem = name.replace("_", "-")
            png = BUNDLE / "frames" / f"{stem}.png"
            rgb = BUNDLE / "frames" / f"{stem}.rgb565"
            state = BUNDLE / "frames" / f"{stem}.json"
            require(failures,
                    png.is_file() and rgb.is_file() and state.is_file() and
                    png_dimensions(png) == (240, 320) and len(rgb.read_bytes()) == 153600 and
                    digest(png) == item.get("png_sha256") and
                    digest(rgb) == item.get("rgb565_sha256") and
                    item.get("frame_begin", {}).get("bytes") == 153600,
                    f"TFT capture mismatch: {name}")
        require(failures,
                captures.get("preflight", {}).get("png_sha256") ==
                physical.get("preflight_png_sha256") and
                captures.get("full_result", {}).get("png_sha256") ==
                physical.get("full_result_png_sha256"),
                "reviewed TFT anchor mismatch")

    limitations = evidence.get("limitations", {})
    require(failures,
            limitations.get("physical_rf_silence_is_not_claimed_without_an_rf_detector") is True and
            limitations.get("nrf_slot_three_remains_gated_by_hw_t08") is True and
            limitations.get("receiver_identity_is_not_passive_activity_or_spectrum_capture") is True,
            "required physical limitations are not explicit")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.81 read-only shield receiver Self-Test evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
