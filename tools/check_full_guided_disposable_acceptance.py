#!/usr/bin/env python3
"""Fail closed unless the exact 0.86 disposable Full/Guided proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-full-guided-disposable-0.86.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-full-guided-disposable-0.86"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "827fd5d7479d4b808dce960728f4e03c7fce7797"
INITIAL_SOURCE_COMMIT = "97392f084e11fc1ab73b6d3af97edcad27557b84"
RUNNER_COMMIT = INITIAL_SOURCE_COMMIT
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
    ("full.s4.storage.disposable.commit", "pass"),
    ("full.s4.storage.disposable.remount", "pass"),
    ("full.s4.library.disposable.export", "pass"),
    ("full.s4.storage.disposable.cleanup", "pass"),
    ("full.capability.coverage", "blocked"),
]
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
    "active_disposable": "active-disposable",
    "full_result": "full-result",
    "home": "home",
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
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


def checks(report: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [(item.get("id"), item.get("status"))
            for item in report.get("checks", [])]


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
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
    require(failures, BUNDLE.is_dir(), "retained bundle missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    candidate = evidence.get("candidate", {})
    retained = evidence.get("evidence", {})
    verified = evidence.get("verified", {})
    history = evidence.get("failure_history", {})
    require(failures,
            evidence.get("schema") ==
                "leshy.full_guided_disposable_acceptance.v1" and
            evidence.get("status") == "pass_disposable_storage_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.86.0-full-guided-disposable" and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")

    run_path = BUNDLE / "run.json"
    failed_path = BUNDLE / "failed-missing-timeline.json"
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
    require(failures, retained.get("files") == 45 and
            retained.get("tft_states") == 13,
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
                candidate.get("factory_bytes"),
            "candidate size mismatch")

    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_full_guided_rf_hil.py")
    source_blob = git_blob(
        SOURCE_COMMIT,
        "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    header_blob = git_blob(
        SOURCE_COMMIT,
        "firmware/leshy1/src/apps/self_test/SelfTestController.h")
    config_blob = git_blob(SOURCE_COMMIT, "firmware/leshy1/platformio.ini")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() ==
                retained.get("runner_sha256"),
            "runner source binding mismatch")
    require(failures, source_blob is not None and
            b'kFullGuidedDisposableRunId = "full-guided-v7"' in source_blob and
            b"littleFsResetSession.startTimeline(" in source_blob and
            b"littleFsResetSession.finalizeTimeline(" in source_blob and
            b"char diagnosticJson[5120]" in source_blob,
            "source disposable/timeline contract mismatch")
    require(failures, header_blob is not None and
            b"kPlanVersion = 7" in header_blob and
            b"kCapacity = 29" in header_blob,
            "source plan-v7 contract mismatch")
    require(failures, config_blob is not None and
            b"0.86.0-full-guided-disposable" in config_blob,
            "source version mismatch")

    if failed_path.is_file():
        failed = load(failed_path)
        artifact = failed.get("active_artifact", {})
        disposable = artifact.get("disposable", {})
        require(failures,
                failed.get("schema") ==
                    "leshy.full_guided_disposable_self_test_hil.run.v2" and
                failed.get("passed") is False and
                failed.get("gate_eligible") is False and
                failed.get("candidate", {}).get("source_commit") ==
                    INITIAL_SOURCE_COMMIT and
                failed.get("runner_source_sha256") ==
                    retained.get("runner_sha256") and
                disposable.get("identity_passed") is True and
                disposable.get("scratch_created") is True and
                disposable.get("commit_complete") is True and
                disposable.get("commit_passed") is False and
                disposable.get("write_calls") == 0 and
                disposable.get("write_bytes") == 0 and
                disposable.get("cleanup_passed") is True and
                disposable.get("scratch_removed") is True and
                artifact.get("product_continuity", {}).get("passed") is True and
                failed.get("cleanup_after", {}).get("complete") is True,
                "retained fail-closed missing-timeline result mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") ==
                    "leshy.full_guided_disposable_self_test_hil.run.v2" and
                run.get("passed") is True and
                run.get("gate_eligible") is True and
                run.get("failures") == [] and
                run.get("expected_cid") == CID and
                run.get("runner_source_sha256") == retained.get("runner_sha256") and
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
                quick.get("plan_version") == 7 and
                [quick.get("passed"), quick.get("failed"),
                 quick.get("blocked"), quick.get("not_applicable")] ==
                    [8, 0, 0, 0] and quick.get("read_only") is True,
                "Quick result mismatch")
        require(failures,
                checks(full) == FULL_CHECKS and
                full.get("plan_version") == 7 and
                [full.get("passed"), full.get("failed"),
                 full.get("blocked"), full.get("not_applicable")] ==
                    [25, 0, 1, 3] and
                full.get("side_effects") == {
                    "radio_tx_commands": 0,
                    "storage_write_commands": 3,
                    "storage_write_bytes": 504,
                    "product_storage_write_commands": 0,
                    "buzzer_activations": 0,
                }, "Full result mismatch")

        artifact = run.get("active_artifact", {})
        disposable = artifact.get("disposable", {})
        require(failures,
                artifact.get("step") == "complete" and
                artifact.get("read_only") is False and
                artifact.get("expected_cid") == CID and
                artifact.get("cleanup_complete") is True and
                disposable == {
                    "run_id": "full-guided-v7",
                    "scratch_path": "/leshy-hil/full-guided-v7",
                    "observed_cid": CID,
                    "identity_passed": True,
                    "scratch_preexisting": False,
                    "scratch_created": True,
                    "commit_complete": True,
                    "commit_passed": True,
                    "generation": 1,
                    "observations": 3,
                    "write_calls": 3,
                    "write_bytes": 504,
                    "file_syncs": 3,
                    "directory_syncs": 3,
                    "remount_complete": True,
                    "remount_passed": True,
                    "export_complete": True,
                    "export_passed": True,
                    "json_bytes": 876,
                    "metadata_bytes": 862,
                    "csv_records": 3,
                    "csv_bytes": 297,
                    "cleanup_complete": True,
                    "cleanup_passed": True,
                    "files_removed": 3,
                    "scratch_removed": True,
                } and artifact.get("product_continuity") == {
                    "complete": True, "passed": True,
                    "generation_final": 83, "observations_final": 0,
                } and artifact.get("side_effects") == {
                    "radio_tx_commands": 0,
                    "disposable_storage_write_commands": 3,
                    "disposable_storage_write_bytes": 504,
                    "product_storage_write_commands": 0,
                    "blocked_write_attempts": 0,
                }, "disposable artifact/continuity mismatch")

        for label in ("recovery_before", "recovery_after"):
            recovery = run.get(label, {})
            require(failures,
                    recovery.get("status") == "admitted" and
                    recovery.get("expected_fingerprint") == CID and
                    recovery.get("observed_fingerprint") == CID and
                    recovery.get("generation") == 83 and
                    recovery.get("observations") == 0 and
                    recovery.get("physical_write_calls") == 0 and
                    recovery.get("cleanup_complete") is True,
                    f"{label} continuity mismatch")

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

        final = run.get("cleanup_after", {}).get("final_state", {})
        require(failures,
                run.get("input", {}).get("read_errors") == 0 and
                run.get("input", {}).get("queue_drops") == 0 and
                run.get("safe_outputs", {}).get("buzzer_inactive") is True and
                run.get("cleanup_after", {}).get("complete") is True and
                final.get("page") == "home" and
                final.get("runtime_owner") == "none" and
                final.get("lease_mask") == 0,
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

    require(failures, evidence.get("limits") == {
        "disposable_scratch_written": True,
        "product_data_written": False,
        "raw_capture_retained_in_evidence": False,
        "physical_rf_silence_instrumented": False,
        "controlled_power_cut_complete": False,
        "one_hour_endurance_complete": False,
        "demo_s4_complete": False,
        "release_gate_eligible": False,
    }, "acceptance limits are not explicit")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(
        "PASS: exact 0.86 Full/Guided disposable commit, read-only remount, "
        "export, cleanup and product continuity evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
