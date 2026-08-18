#!/usr/bin/env python3
"""Fail closed unless the exact 0.80 S3/S4 Self-Test proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-self-test-coverage-0.80.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-self-test-coverage-0.80"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "a1b65999252e2dac67bab9d2de00a787081afc1b"
RUNNER_COMMIT = "33b7eb6ee180f17adadd321ad655a38a7d7f0005"
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
    ("full.s4.shield.receivers", "blocked"),
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
            evidence.get("schema") == "leshy.self_test_coverage_acceptance.v1" and
            evidence.get("status") == "pass_s3_s4_self_test_coverage_checkpoint" and
            evidence.get("passed") is True and evidence.get("board") == "board-01" and
            evidence.get("profile") == "esp32-div-v2-n16" and
            evidence.get("observed_cid") == CID and
            evidence.get("source_commit") == SOURCE_COMMIT and
            evidence.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")
    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.80.0-self-test-coverage",
        "firmware_sha256": "7c409a8913aeee080f3046cae2d56716bc79f35857ef562fb4065bff297cfd06",
        "factory_sha256": "69fe24c7c68ed4695c77e80f1fa13ea34eb1b06d475ecf30fd954cd56d914485",
        "app_elf_sha256": "4aea8541435117fd86074c3d28a1e48c7c60afb70d8582758b6a8236a0e88d38",
        "map_sha256": "5b61e02eecb78506fad45b25533245584d31b0a9c99b90a09e58fdaaa8375270",
        "firmware_bytes": 1456416, "factory_bytes": 1521952,
        "linked_flash_bytes": 1456012, "linked_ram_bytes": 152520,
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
                run.get("schema") == "leshy.self_test_coverage_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
                run.get("run_id") == physical.get("run_id") and
                run.get("runner_source_sha256") == physical.get("runner_sha256") and
                run.get("candidate") == {
                    "version": candidate.get("version"),
                    "source_commit": SOURCE_COMMIT,
                    "firmware_sha256": candidate.get("firmware_sha256"),
                    "app_elf_sha256": candidate.get("app_elf_sha256"),
                    "flashed": True,
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
        before = run.get("recovery_before", {})
        after = run.get("recovery_after", {})
        for label, recovery in (("before", before), ("after", after)):
            require(failures,
                    recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == CID and
                    recovery.get("observed_fingerprint") == CID and
                    recovery.get("generation") == physical.get("generation") and
                    recovery.get("observations") == physical.get("observations") and
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
                quick.get("plan_version") == 3 and quick.get("mode") == "quick" and
                quick.get("status") == "pass" and quick.get("read_only") is True and
                (quick.get("passed"), quick.get("failed"), quick.get("blocked"),
                 quick.get("not_applicable")) == (8, 0, 0, 0) and
                [(item.get("id"), item.get("status")) for item in quick.get("checks", [])] ==
                [(check_id, "pass") for check_id in QUICK_IDS],
                "Quick plan/report mismatch")
        require(failures,
                full.get("schema") == "leshy.self_test.report.v1" and
                full.get("plan_version") == 3 and full.get("mode") == "full_guided" and
                full.get("status") == "blocked" and full.get("read_only") is True and
                (full.get("passed"), full.get("failed"), full.get("blocked"),
                 full.get("not_applicable")) == (15, 0, 2, 3) and
                [(item.get("id"), item.get("status")) for item in full.get("checks", [])] ==
                FULL_CHECKS,
                "Full/Guided plan/report mismatch")
        expected_facts = {
            "persistent_survey_ready": True, "passive_ble_ready": True,
            "passive_wifi_capture_ready": True, "enrolled_storage_ready": True,
            "persistent_library_ready": True, "persistent_wifi_capture_ready": True,
            "gps_declared": False, "pn532_declared": False, "ir_declared": False,
        }
        require(failures,
                all(full.get("facts", {}).get(key) is value
                    for key, value in expected_facts.items()),
                "S3/S4 capability facts mismatch")
        for label, report in (("Quick", quick), ("Full", full)):
            require(failures, report.get("side_effects") == {
                "radio_tx_commands": 0,
                "storage_write_commands": 0,
                "buzzer_activations": 0,
            }, f"{label} side effects mismatch")
            require(failures,
                    report.get("current_owner") == "self-test" and
                    report.get("current_lease_mask") == 1,
                    f"{label} UI-only lease mismatch")
        input_state = run.get("input", {})
        safe = run.get("safe_outputs", {})
        final = run.get("final", {})
        require(failures,
                input_state.get("status") == "ready" and
                input_state.get("read_errors") == 0 and input_state.get("queue_drops") == 0 and
                safe.get("buzzer_inactive") is True and safe.get("buzzer_level") == "low" and
                final.get("page") == "home" and
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
        require(failures, set(captures) == CAPTURES and len(captures) == physical.get("screen_count"),
                "TFT capture set mismatch")
        for name, item in captures.items():
            png = BUNDLE / "frames" / f"{name.replace('_', '-')}.png"
            rgb = BUNDLE / "frames" / f"{name.replace('_', '-')}.rgb565"
            state = BUNDLE / "frames" / f"{name.replace('_', '-')}.json"
            require(failures,
                    png.is_file() and rgb.is_file() and state.is_file() and
                    png_dimensions(png) == (240, 320) and len(rgb.read_bytes()) == 153600 and
                    digest(png) == item.get("png_sha256") and
                    digest(rgb) == item.get("rgb565_sha256"),
                    f"TFT capture mismatch: {name}")
        require(failures,
                captures.get("modes", {}).get("png_sha256") == physical.get("modes_png_sha256") and
                captures.get("full_result", {}).get("png_sha256") ==
                physical.get("full_result_png_sha256"),
                "reviewed TFT anchor mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.80 S3/S4 Self-Test coverage evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
