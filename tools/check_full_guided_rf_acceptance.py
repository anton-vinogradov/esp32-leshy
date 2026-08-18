#!/usr/bin/env python3
"""Fail closed unless the exact 0.84 active Full/Guided RF proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-full-guided-rf-0.84.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-full-guided-rf-0.84"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "32aad3c231c5d8cf887501717147886ffdbc4ec6"
RUNNER_COMMIT = "04915eaea602bf4516a5103af5e32033e4d6b727"
INITIAL_RUNNER_COMMIT = "392322abc899f02f87b01f25f462c34bb3288832"
CAPTURES = {
    "modes", "quick_result", "preflight", "visual_dialog_confirm",
    "visual_unavailable", "visual_degraded", "visual_error",
    "visual_running", "active_checks", "full_result", "home",
}
QUICK_IDS = [
    "quick.build.identity",
    "quick.board.profile",
    "quick.runtime.heap",
    "quick.display.ready",
    "quick.input.frontend",
    "quick.input.queue",
    "quick.output.buzzer",
    "quick.resource.scope",
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


def report_checks(report: dict[str, Any]) -> list[tuple[Any, Any]]:
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
    failure_history = evidence.get("failure_history", {})
    limits = evidence.get("limits", {})
    require(failures,
            evidence.get("schema") == "leshy.full_guided_rf_acceptance.v1" and
            evidence.get("status") == "pass_active_receive_only_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.84.0-full-guided-rf" and
            candidate.get("source_commit") == SOURCE_COMMIT and
            candidate.get("runner_commit") == RUNNER_COMMIT,
            "acceptance identity mismatch")

    run_path = BUNDLE / "run.json"
    failed_path = BUNDLE / "failed-runner-model.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures, run_path.is_file() and
            digest(run_path) == retained.get("run_sha256"),
            "passing run binding mismatch")
    require(failures, failed_path.is_file() and
            digest(failed_path) == retained.get("failed_runner_model_sha256"),
            "failed runner-model binding mismatch")
    require(failures, index_path.is_file() and
            digest(index_path) == retained.get("artifact_index_sha256"),
            "artifact-index binding mismatch")
    verify_index(failures, index_path)
    require(failures, retained.get("files") == 40 and
            retained.get("tft_states") == 11,
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
            (BUNDLE / "firmware.bin").stat().st_size == candidate.get("app_bytes") and
            (BUNDLE / "firmware.factory.bin").stat().st_size ==
                candidate.get("factory_bytes"), "candidate size mismatch")

    runner_blob = git_blob(RUNNER_COMMIT, "tools/run_1x_full_guided_rf_hil.py")
    initial_runner_blob = git_blob(
        INITIAL_RUNNER_COMMIT, "tools/run_1x_full_guided_rf_hil.py")
    require(failures, runner_blob is not None and
            hashlib.sha256(runner_blob).hexdigest() ==
                retained.get("runner_sha256"),
            "passing runner source binding mismatch")
    require(failures, initial_runner_blob is not None and
            hashlib.sha256(initial_runner_blob).hexdigest() ==
                failure_history.get("initial_runner_sha256"),
            "initial runner source binding mismatch")

    if failed_path.is_file():
        failed = load(failed_path)
        failed_items = failed.get("failures", [])
        require(failures,
                failed.get("schema") ==
                    "leshy.full_guided_rf_self_test_hil.run.v1" and
                failed.get("passed") is False and
                failed.get("gate_eligible") is False and
                failed.get("runner_source_sha256") ==
                    failure_history.get("initial_runner_sha256") and
                len(failed_items) == 1 and
                failed_items[0].startswith("CC1101 active wire differs:") and
                failed.get("active_rf", {}).get("cc1101", {}).get(
                    "wire", {}).get("command_strobes") == 194 and
                failed.get("active_rf", {}).get("side_effects", {}).get(
                    "radio_tx_commands") == 0 and
                failed.get("cleanup_after", {}).get("complete") is True,
                "retained fail-closed runner-model result mismatch")

    if run_path.is_file():
        run = load(run_path)
        require(failures,
                run.get("schema") ==
                    "leshy.full_guided_rf_self_test_hil.run.v1" and
                run.get("passed") is True and run.get("gate_eligible") is True and
                run.get("failures") == [] and run.get("expected_cid") == CID and
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
                [boot.get("heap_total"), boot.get("heap_free"),
                 boot.get("heap_min_free")] == [228644, 163900, 144504],
                "boot identity or heap baseline mismatch")
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

        quick = run.get("quick_report", {})
        require(failures,
                quick.get("schema") == "leshy.self_test.report.v1" and
                quick.get("plan_version") == 5 and quick.get("mode") == "quick" and
                quick.get("status") == "pass" and quick.get("read_only") is True and
                [quick.get("passed"), quick.get("failed"), quick.get("blocked"),
                 quick.get("not_applicable")] == [8, 0, 0, 0] and
                report_checks(quick) == [(item, "pass") for item in QUICK_IDS],
                "Quick plan-v5 result mismatch")
        full = run.get("full_report", {})
        require(failures,
                full.get("schema") == "leshy.self_test.report.v1" and
                full.get("plan_version") == 5 and
                full.get("mode") == "full_guided" and
                full.get("status") == "blocked" and
                full.get("read_only") is False and
                [full.get("passed"), full.get("failed"), full.get("blocked"),
                 full.get("not_applicable")] == [18, 0, 1, 3] and
                report_checks(full) == FULL_CHECKS and
                full.get("side_effects") == {
                    "buzzer_activations": 0, "radio_tx_commands": 0,
                    "storage_write_commands": 0,
                }, "Full/Guided plan-v5 result mismatch")
        facts = full.get("facts", {})
        for fact in (
            "shield_receivers_applicable", "shield_receiver_probe_complete",
            "shield_receiver_probe_passed", "nrf24_spectrum_exercise_complete",
            "nrf24_spectrum_exercise_passed",
            "cc1101_spectrum_exercise_complete",
            "cc1101_spectrum_exercise_passed", "resource_scope_clean",
        ):
            require(failures, facts.get(fact) is True,
                    f"Full/Guided fact is not true: {fact}")

        active = run.get("active_rf", {})
        nrf = active.get("nrf24", {})
        cc = active.get("cc1101", {})
        require(failures,
                active.get("schema") == "leshy.self_test.active_rf.v1" and
                active.get("plan_version") == 5 and active.get("step") == "complete" and
                active.get("rx_only") is True and
                active.get("resource_acquired") is True and
                active.get("resource_released") is True and
                active.get("cleanup_complete") is True and
                active.get("current_owner") == "self-test" and
                active.get("current_lease_mask") == 1,
                "active RF lifecycle mismatch")
        require(failures,
                [nrf.get("complete"), nrf.get("passed"), nrf.get("sweeps"),
                 nrf.get("channels"), nrf.get("modules"),
                 nrf.get("cleanup_complete")] == [True, True, 1, 83, 2, True] and
                nrf.get("wire") == {
                    "register_reads": 93, "register_writes": 95,
                    "spi_bytes_clocked": 376, "receive_ce_high_events": 83,
                }, "active nRF24 accounting mismatch")
        cc_wire = cc.get("wire", {})
        require(failures,
                [cc.get("complete"), cc.get("passed"), cc.get("band"),
                 cc.get("bins"), cc.get("cleanup_complete")] ==
                    [True, True, "433", 64, True] and
                cc_wire == {
                    "register_reads": 2060, "register_writes": 208,
                    "spi_bytes_clocked": 4730, "command_strobes": 194,
                    "reset_strobes": 1, "receive_strobes": 64,
                    "idle_strobes": 129,
                } and
                cc_wire.get("spi_bytes_clocked") ==
                    2 * (cc_wire.get("register_reads") +
                         cc_wire.get("register_writes")) +
                    cc_wire.get("command_strobes"),
                "active CC1101 accounting mismatch")
        require(failures, active.get("side_effects") == {
            "radio_tx_commands": 0, "nrf_tx_mode_entries": 0,
            "nrf_tx_payload_commands": 0, "cc_tx_strobes": 0,
            "cc_pa_table_writes": 0, "cc_fifo_writes": 0,
            "cc_rejected_strobes": 0, "storage_write_commands": 0,
        }, "active RF side effects mismatch")

        shield = run.get("shield_receiver_probe", {})
        require(failures,
                shield.get("status") == "pass" and
                shield.get("detected_receivers") == 3 and
                shield.get("nrf_slot3_gated") is True and
                shield.get("gpio21_stable_high") is True and
                shield.get("wire") == {
                    "nrf_register_reads": 8, "cc_status_reads": 2,
                    "spi_bytes_clocked": 20,
                } and shield.get("side_effects") == {
                    "nrf_ce_high_events": 0, "cc_command_strobes": 0,
                    "radio_tx_commands": 0,
                }, "shield identity probe mismatch")
        require(failures,
                run.get("input", {}).get("read_errors") == 0 and
                run.get("input", {}).get("queue_drops") == 0 and
                run.get("safe_outputs", {}).get("buzzer_inactive") is True and
                run.get("cleanup_after", {}).get("complete") is True and
                run.get("final", {}).get("page") == "home" and
                run.get("final", {}).get("runtime_owner") == "none" and
                run.get("final", {}).get("lease_mask") == 0,
                "input/safe-output/final cleanup mismatch")
        require(failures, set(run.get("captures", {})) == CAPTURES,
                "capture set mismatch")

    for label in CAPTURES:
        stem = label.replace("_", "-")
        png = BUNDLE / "frames" / f"{stem}.png"
        rgb = BUNDLE / "frames" / f"{stem}.rgb565"
        metadata = BUNDLE / "frames" / f"{stem}.json"
        require(failures, png.is_file() and png_dimensions(png) == (240, 320),
                f"invalid {label} PNG")
        require(failures, rgb.is_file() and rgb.stat().st_size == 240 * 320 * 2,
                f"invalid {label} RGB frame")
        require(failures, metadata.is_file(), f"missing {label} metadata")

    require(failures,
            [verified.get("quick_passed"), verified.get("full_checks"),
             verified.get("full_passed"), verified.get("full_failed"),
             verified.get("full_blocked"),
             verified.get("full_not_applicable")] == [8, 22, 18, 0, 1, 3] and
            verified.get("active_rf_receive_only") is True and
            verified.get("radio_tx_commands") == 0 and
            verified.get("storage_write_commands") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0 and
            failure_history.get("classification") ==
                "runner_expectation_error" and
            failure_history.get("product_failure") is False and
            failure_history.get("corrected_model_regression_passed") is True and
            limits.get("physical_rf_silence_measured") is False and
            limits.get("rf_instrument_available") is False and
            limits.get("full_capability_coverage") == "blocked_until_s5_s7" and
            limits.get("controlled_power_cut") == "next_checkpoint" and
            limits.get("multi_source_endurance") == "open" and
            limits.get("demo_s4_closed") is False and
            limits.get("release_promoted") is False,
            "accepted facts, failure history or scope limits were weakened")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.84 active Full/Guided RF evidence is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
