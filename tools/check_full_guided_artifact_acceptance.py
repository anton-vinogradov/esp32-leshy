#!/usr/bin/env python3
"""Fail closed unless the exact 0.85 Full/Guided artifact proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-full-guided-artifacts-0.85.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-full-guided-artifacts-0.85"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "a8a49b7ed7221697c4e0a8aeadfba8cda3f0bfb7"
INITIAL_SOURCE_COMMIT = "22c6ac7ffc5811394a6c95bb057293ace433071e"
RUNNER_COMMIT = "820b3c6a5e7368022b3bce589c8c2214af8dbc4e"
CAPTURES = {
    "modes": "modes",
    "quick_result": "quick-result",
    "preflight": "preflight",
    "visual_dialog_confirm": "visual-dialog-confirm",
    "visual_unavailable": "visual-unavailable",
    "visual_degraded": "visual-degraded",
    "visual_error": "visual-error",
    "visual_running": "visual-running",
    "active_checks": "active-checks",
    "active_artifacts": "active-artifacts",
    "full_result": "full-result",
    "home": "home",
}
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
    ("full.s4.spectrum.nrf24.receive", "pass"),
    ("full.s4.spectrum.cc1101.receive", "pass"),
    ("full.s4.storage.recovery.audit", "pass"),
    ("full.s4.library.export.audit", "pass"),
    ("full.s4.capture.pcap.audit", "pass"),
    ("full.capability.coverage", "blocked"),
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
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


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


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def checks(report: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [(item.get("id"), item.get("status"))
            for item in report.get("checks", [])]


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "top-level evidence missing")
    require(failures, BUNDLE.is_dir(), "retained bundle missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    candidate = evidence.get("candidate", {})
    retained = evidence.get("evidence", {})
    verified = evidence.get("verified", {})
    history = evidence.get("failure_history", {})
    limits = evidence.get("limits", {})
    require(failures,
            evidence.get("schema") ==
                "leshy.full_guided_artifact_acceptance.v1" and
            evidence.get("status") ==
                "pass_read_only_artifact_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.85.0-full-guided-artifacts" and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")

    run_path = BUNDLE / "run.json"
    failed_path = BUNDLE / "failed-telemetry-truncation.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures, run_path.is_file() and
            digest(run_path) == retained.get("run_sha256"),
            "passing run binding mismatch")
    require(failures, failed_path.is_file() and
            digest(failed_path) == history.get("failed_run_sha256"),
            "failed run binding mismatch")
    require(failures, index_path.is_file() and
            digest(index_path) == retained.get("artifact_index_sha256"),
            "artifact-index binding mismatch")
    verify_index(failures, index_path)
    require(failures, retained.get("files") == 43 and
            retained.get("tft_states") == 12,
            "retained inventory/count mismatch")

    for field, filename in (
        ("firmware_sha256", "firmware.bin"),
        ("factory_sha256", "firmware.factory.bin"),
        ("app_elf_sha256", "firmware.elf"),
        ("map_sha256", "firmware.map"),
    ):
        path = BUNDLE / filename
        require(failures, path.is_file() and digest(path) == candidate.get(field),
                f"retained {filename} mismatch")
    if (BUNDLE / "firmware.bin").is_file():
        require(failures, app_elf_sha256(BUNDLE / "firmware.bin") ==
                candidate.get("app_elf_sha256"),
                "embedded app identity mismatch")
    require(failures,
            (BUNDLE / "firmware.bin").stat().st_size ==
                candidate.get("app_bytes") and
            (BUNDLE / "firmware.factory.bin").stat().st_size ==
                candidate.get("factory_bytes"), "candidate size mismatch")

    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_full_guided_rf_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() ==
                retained.get("runner_sha256"),
            "runner source binding mismatch")
    source_blob = git_blob(
        SOURCE_COMMIT,
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    header_blob = git_blob(
        SOURCE_COMMIT,
        "firmware/leshy1/src/apps/self_test/SelfTestController.h")
    config_blob = git_blob(SOURCE_COMMIT, "firmware/leshy1/platformio.ini")
    require(failures, source_blob is not None and
            b"char diagnosticJson[4608]" in source_blob and
            b"leshy.self_test.active_artifact.v1" in source_blob and
            b"fullGuidedArtifactStartAfterUs" in source_blob,
            "source artifact/cancellation contract mismatch")
    require(failures, header_blob is not None and
            b"kPlanVersion = 6" in header_blob and
            b"kCapacity = 25" in header_blob,
            "source plan-v6 contract mismatch")
    require(failures, config_blob is not None and
            b"0.85.0-full-guided-artifacts" in config_blob,
            "source version mismatch")

    if failed_path.is_file():
        failed = load(failed_path)
        require(failures,
                failed.get("schema") ==
                    "leshy.full_guided_artifact_self_test_hil.run.v1" and
                failed.get("passed") is False and
                failed.get("gate_eligible") is False and
                failed.get("candidate", {}).get("source_commit") ==
                    INITIAL_SOURCE_COMMIT and
                failed.get("candidate", {}).get("flashed") is True and
                failed.get("runner_source_sha256") ==
                    retained.get("runner_sha256") and
                failed.get("cleanup_before", {}).get("complete") is False and
                failed.get("failures") == [
                    "self_test_phase: RuntimeError: initial cleanup did not "
                    "reach Home/lease 0",
                    "cleanup_after: terminal zero lease unproven",
                ], "retained fail-closed telemetry result mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") ==
                    "leshy.full_guided_artifact_self_test_hil.run.v1" and
                run.get("passed") is True and
                run.get("gate_eligible") is True and
                run.get("failures") == [] and
                run.get("expected_cid") == CID and
                run.get("runner_source_sha256") ==
                    retained.get("runner_sha256") and
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
                [boot.get("heap_total"), boot.get("heap_free")] ==
                    [verified.get("heap_total"), verified.get("heap_free")],
                "boot identity/heap mismatch")
        quick = run.get("quick_report", {})
        full = run.get("full_report", {})
        require(failures,
                checks(quick) == [(item, "pass") for item in QUICK_IDS] and
                quick.get("plan_version") == 6 and
                quick.get("passed") == 8 and quick.get("failed") == 0 and
                quick.get("read_only") is True,
                "Quick result mismatch")
        require(failures,
                checks(full) == FULL_CHECKS and
                full.get("plan_version") == 6 and
                [full.get("passed"), full.get("failed"),
                 full.get("blocked"), full.get("not_applicable")] ==
                    [21, 0, 1, 3] and
                full.get("side_effects") == {
                    "radio_tx_commands": 0, "storage_write_commands": 0,
                    "buzzer_activations": 0,
                }, "Full result mismatch")
        artifact = run.get("active_artifact", {})
        recovery = artifact.get("recovery", {})
        library = artifact.get("library", {})
        capture = artifact.get("capture", {})
        require(failures,
                artifact.get("step") == "complete" and
                artifact.get("read_only") is True and
                artifact.get("expected_cid") == CID and
                artifact.get("cleanup_complete") is True and
                artifact.get("side_effects") == {
                    "radio_tx_commands": 0, "storage_write_commands": 0,
                    "blocked_write_attempts": 0,
                } and recovery == {
                    "complete": True, "passed": True, "status": "admitted",
                    "generation_before": 83, "generation_after": 83,
                    "observations_before": 0, "observations_after": 0,
                    "mounted_read_only": True, "cleanup_complete": True,
                } and library == {
                    "complete": True, "passed": True, "json_bytes": 432,
                    "metadata_bytes": 880, "csv_records": 0,
                    "csv_bytes": 94,
                } and capture == {
                    "complete": True, "applicable": True, "passed": True,
                    "pcap_frames": 16, "pcap_bytes": 2773,
                    "pcap_fnv1a": 673903271,
                }, "active artifact report mismatch")
        active_rf = run.get("active_rf", {})
        require(failures,
                active_rf.get("step") == "complete" and
                active_rf.get("cleanup_complete") is True and
                active_rf.get("nrf24", {}).get("wire") == {
                    "register_reads": 93, "register_writes": 95,
                    "spi_bytes_clocked": 376,
                    "receive_ce_high_events": 83,
                } and active_rf.get("cc1101", {}).get("wire") == {
                    "register_reads": 2097, "register_writes": 208,
                    "spi_bytes_clocked": 4804, "command_strobes": 194,
                    "reset_strobes": 1, "receive_strobes": 64,
                    "idle_strobes": 129,
                } and all(value == 0 for value in
                    active_rf.get("side_effects", {}).values()),
                "active RF regression mismatch")
        before = run.get("recovery_before", {})
        after = run.get("recovery_after", {})
        require(failures,
                before.get("generation") == after.get("generation") == 83 and
                before.get("observations") == after.get("observations") == 0 and
                before.get("physical_write_calls") ==
                    after.get("physical_write_calls") == 0 and
                after.get("cleanup_complete") is True,
                "persistent artifact continuity mismatch")
        require(failures,
                run.get("input", {}).get("read_errors") == 0 and
                run.get("input", {}).get("queue_drops") == 0 and
                run.get("safe_outputs", {}).get("buzzer_inactive") is True and
                run.get("cleanup_after", {}).get("complete") is True and
                run.get("cleanup_after", {}).get("final_state", {}).get(
                    "runtime_owner") == "none" and
                run.get("cleanup_after", {}).get("final_state", {}).get(
                    "lease_mask") == 0,
                "input/output/final cleanup mismatch")
        captures = run.get("captures", {})
        require(failures, set(captures) == set(CAPTURES),
                "TFT capture set mismatch")
        for capture_name, capture_record in captures.items():
            basename = CAPTURES.get(capture_name, "missing")
            png = BUNDLE / "frames" / f"{basename}.png"
            rgb = BUNDLE / "frames" / f"{basename}.rgb565"
            require(failures,
                    png.is_file() and rgb.is_file() and
                    png_dimensions(png) == (240, 320) and
                    digest(png) == capture_record.get("png_sha256") and
                    digest(rgb) == capture_record.get("rgb565_sha256") and
                    rgb.stat().st_size == 153600,
                    f"TFT capture mismatch: {capture_name}")

    require(failures, limits == {
        "new_survey_or_capture_started": False,
        "user_data_written": False,
        "capture_pcap_check_requires_a_persisted_frame_artifact": True,
        "physical_rf_silence_instrumented": False,
        "controlled_power_cut_complete": False,
        "eight_hour_endurance_complete": False,
        "demo_s4_complete": False,
        "release_gate_eligible": False,
    }, "acceptance limits are not explicit")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(
        "PASS: exact 0.85 Full/Guided recovery, Library and persisted PCAP "
        "artifact evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
