#!/usr/bin/env python3
"""One-flash physical delta HIL for explainable Target correlation review."""

from __future__ import annotations

import argparse
import json
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_json, synchronize_console
from check_targets_stack_elf_contract import stack_frames
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    capture,
    query,
    reset_capture,
)
from run_1x_targets_hil import run_survey_cycle
from run_1x_targets_notes_hil import close_targets, wait_mutation
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.targets_correlation_hil.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
MAX_FRESH_SURVEY_CYCLES = 4
FIXTURE_SCHEMA = "leshy.hil.correlation_fixture.v1"


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def open_targets(device: PassiveSerial) -> dict[str, Any]:
    home = normalize_home(device)
    for _ in range(5):
        home = action(device, "down")
    require(home, "select Targets", page="home", selection=5,
            selected_id="targets")
    action(device, "right")
    listed = query(device, b"targets.state",
                   "leshy.targets.product.v1", "state")
    if listed.get("status") != "ready":
        raise RuntimeError(
            f"Targets load rejected with exact admission state: {listed}")
    require(listed, "Targets list", status="ready", page_open=True,
            workspace_allocated=True, view="list", compare_available=True,
            read_only=False, write_enabled=False,
            blocked_write_attempts=0, filesystem_mount_error=0,
            cleanup_complete=True, lease_mask=13)
    attempts = int(listed.get("filesystem_mount_attempts", 0))
    retries = int(listed.get("filesystem_mount_transient_retries", -1))
    if not 1 <= attempts <= 3 or retries != attempts - 1:
        raise RuntimeError(
            f"unbounded or inconsistent mount recovery: {listed}")
    return listed


def find_proposal(device: PassiveSerial,
                  listed: dict[str, Any]) -> dict[str, Any] | None:
    for _ in range(int(listed.get("target_count", 0))):
        action(device, "down")
        selected = query(device, b"targets.state",
                         "leshy.targets.product.v1", "state")
        if int(selected.get("correlation_count", 0)) > 0:
            return selected
    return None


def validate_proposal(state: dict[str, Any]) -> None:
    require(state, "correlation proposal", status="ready",
            correlation_proposal_present=True,
            correlation_known_loaded=True,
            correlation_candidate_loaded=True,
            correlation_stale=False)
    proposal_id = state.get("correlation_proposal_id")
    identity = state.get("correlation_candidate_identity_hex")
    if (not isinstance(proposal_id, str) or len(proposal_id) != 32 or
            any(value not in "0123456789ABCDEF" for value in proposal_id)):
        raise RuntimeError(f"invalid proposal ID: {state}")
    if (not isinstance(identity, str) or len(identity) != 12 or
            any(value not in "0123456789ABCDEF" for value in identity)):
        raise RuntimeError(f"invalid pending identity: {state}")
    if state.get("correlation_confidence") not in ("medium", "high"):
        raise RuntimeError(f"weak correlation escaped review: {state}")
    # Advertised-name (260) plus signal-trend (220) has a hard maximum of 480;
    # medium confidence begins at the domain threshold of 350.
    if (int(state.get("correlation_score_permille", 0)) < 350 or
            int(state.get("correlation_feature_count", 0)) != 2 or
            state.get("correlation_feature_kind") != "advertised_name" or
            int(state.get("correlation_feature_strength_permille", 0)) != 1000 or
            int(state.get("correlation_feature_awarded_points", 0)) <= 0):
        raise RuntimeError(f"proposal is not explainable: {state}")
    baseline = int(state.get("baseline_generation", 0))
    current = int(state.get("current_generation", 0))
    if (int(state.get("correlation_known_generation", 0)) != baseline or
            int(state.get("correlation_candidate_generation", 0)) != current or
            int(state.get("correlation_known_sequence", 0)) <= 0 or
            int(state.get("correlation_candidate_sequence", 0)) <= 0):
        raise RuntimeError(f"proposal evidence is not exact: {state}")
    known_radio = int(state.get("correlation_known_radio", 0))
    candidate_radio = int(state.get("correlation_candidate_radio", 0))
    if known_radio not in (1, 2) or candidate_radio not in (1, 2):
        raise RuntimeError(f"proposal radio is invalid: {state}")
    if known_radio == 1 and candidate_radio == 1:
        raise RuntimeError(f"Wi-Fi to Wi-Fi correlation is forbidden: {state}")
    if abs(int(state.get("correlation_known_rssi_dbm", 0)) -
           int(state.get("correlation_candidate_rssi_dbm", 0))) > 20:
        raise RuntimeError(f"proposal exceeds the signal bound: {state}")


def fixture_mode(device: PassiveSerial, mode: str) -> dict[str, Any]:
    device.reset_input_buffer()
    device.write(f"mode {mode}\n".encode("ascii"))
    device.flush()
    state = read_json(device, FIXTURE_SCHEMA, "state", timeout=8.0)
    if (state.get("mode") != mode or
            state.get("wifi_tx") != (mode == "wifi") or
            state.get("ble_tx") != (mode == "ble")):
        raise RuntimeError(f"external fixture mode failed: {state}")
    time.sleep(0.5)
    return state


def check_atomic_accept(state: dict[str, Any], generation: int,
                        decision_count: int) -> None:
    require(state, "atomic correlation accept", mutation_state="saved",
            mutation_status="saved", mutation_correlation=True,
            mutation_correlation_kind="accept",
            mutation_correlation_status="accepted",
            mutation_persisted=True, mutation_generation=generation,
            target_state_generation=generation,
            correlation_decision_count=decision_count,
            mutation_expected_cid=EXPECTED_CID,
            mutation_observed_cid=EXPECTED_CID,
            cleanup_complete=True, lease_mask=13)
    attempts = int(state.get("mutation_identity_attempts", 0))
    retries = int(state.get("mutation_identity_transient_retries", -1))
    if (not 1 <= attempts <= 8 or retries != attempts - 1 or
            not 0 < int(state.get("mutation_action_us", 0)) <= 10000 or
            not 0 < int(state.get("mutation_elapsed_us", 0)) <= 8000000 or
            int(state.get("mutation_bytes_written", 0)) <= 0 or
            int(state.get("mutation_write_calls", 0)) < 3 or
            int(state.get("mutation_file_syncs", 0)) < 3 or
            int(state.get("mutation_directory_syncs", 0)) < 3):
        raise RuntimeError(f"unbounded or incomplete correlation store: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="reuse the already-running candidate after exact hash verification",
    )
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--fixture-port",
        help="optional external low-power Wi-Fi/BLE correlation beacon",
    )
    parser.add_argument(
        "--external-ble-label",
        help="BLE local name advertised by --external-ble-executable",
    )
    parser.add_argument(
        "--external-ble-executable", type=Path,
        help="bounded macOS CoreBluetooth fixture executable",
    )
    args = parser.parse_args()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    if args.fixture_port is not None and args.external_ble_label is not None:
        parser.error("choose at most one external fixture mechanism")
    if ((args.external_ble_label is None) !=
            (args.external_ble_executable is None)):
        parser.error(
            "--external-ble-label and --external-ble-executable are a pair")
    if (args.external_ble_executable is not None and
            not args.external_ble_executable.is_file()):
        parser.error("external BLE fixture executable is missing")
    if (args.external_ble_label is not None and
            not 1 <= len(args.external_ble_label.encode("utf-8")) <= 29):
        parser.error("external BLE label must occupy 1..29 UTF-8 bytes")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")
    try:
        checked_stack_frames = stack_frames(args.elf)
    except (FileNotFoundError, subprocess.CalledProcessError,
            ValueError) as error:
        parser.error(f"unsafe or unverifiable Targets stack: {error}")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    trace: list[dict[str, Any]] = []
    states: dict[str, Any] = {}
    screens: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    fixture_states: list[dict[str, Any]] = []
    fixture_record: dict[str, Any] = {
        "kind": "second_div" if args.fixture_port is not None else (
            "macos_corebluetooth" if args.external_ble_label is not None else
            "none"),
        "port": args.fixture_port,
        "label": ("LESHY-HIL-CORR" if args.fixture_port is not None else
                  args.external_ble_label),
        "states": fixture_states,
        "dut_remained_passive": True,
    }
    if args.external_ble_executable is not None:
        fixture_record["executable_sha256"] = sha256_file(
            args.external_ble_executable)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
            "checked_stack_frames": checked_stack_frames,
        },
    }
    write_json(args.output / "run.json", record)

    device: PassiveSerial | None = None
    fixture: PassiveSerial | None = None
    fixture_process: subprocess.Popen[str] | None = None
    try:
        if not args.reuse_exact_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(1.0)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        if args.fixture_port is not None:
            if args.fixture_port == args.port:
                raise RuntimeError("fixture and DUT ports must be different")
            fixture = PassiveSerial(
                args.fixture_port, 115200, timeout=0.25)
            fixture_states.append(fixture_mode(fixture, "off"))
        if args.external_ble_executable is not None:
            fixture_process = subprocess.Popen(
                [str(args.external_ble_executable.resolve()),
                 str(args.external_ble_label)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if fixture_process.stdout is None:
                raise RuntimeError("external BLE fixture has no stdout")
            readable, _, _ = select.select(
                [fixture_process.stdout], [], [], 10.0)
            if not readable:
                raise RuntimeError("external BLE fixture did not become ready")
            fixture_state = json.loads(fixture_process.stdout.readline())
            fixture_states.append(fixture_state)
            if (fixture_state.get("schema") !=
                    "leshy.hil.macos_ble_name_fixture.v1" or
                    fixture_state.get("state") != "advertising" or
                    fixture_state.get("label") != args.external_ble_label):
                raise RuntimeError(
                    f"external BLE fixture start failed: {fixture_state}")
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics, "candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        recovery = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery, "exact media", status="admitted",
                expected_fingerprint=EXPECTED_CID,
                observed_fingerprint=EXPECTED_CID,
                fingerprint_matched=True, mounted_read_only=True,
                read_only_guaranteed=True, blocked_write_attempts=0,
                cleanup_complete=True, physical_write_calls=0)

        latest_generation = int(recovery["generation"])
        selected: dict[str, Any] | None = None
        scans: list[dict[str, Any]] = []
        for attempt in range(MAX_FRESH_SURVEY_CYCLES + 1):
            listed = open_targets(device)
            selected = find_proposal(device, listed)
            if selected is not None:
                states["proposal_selected"] = selected
                break
            close_targets(device)
            if attempt == MAX_FRESH_SURVEY_CYCLES:
                break
            if fixture is not None:
                fixture_states.append(fixture_mode(
                    fixture, "wifi" if not scans else "ble"))
            committed = run_survey_cycle(device, latest_generation, trace)
            latest_generation = int(committed["survey_generation"])
            scans.append({
                "generation": latest_generation,
                "observations": int(committed["survey_observations"]),
                "scan_cycles": int(committed["survey_product_scan_cycles"]),
            })
        if selected is None:
            raise RuntimeError(
                "no unambiguous real correlation proposal after bounded scans")
        validate_proposal(selected)
        proposal_id = str(selected["correlation_proposal_id"])
        candidate_identity = str(
            selected["correlation_candidate_identity_hex"])
        target_id = str(selected["selected_target_id"])
        target_count_before = int(selected["target_count"])
        identities_before = int(selected["source_identity_count"])
        generation_before = int(selected["target_state_generation"])
        decisions_before = int(selected["correlation_decision_count"])

        action(device, "right")
        action(device, "right")
        for _ in range(4):
            action(device, "down")
        action(device, "right")
        proposal_list = query(device, b"targets.state",
                              "leshy.targets.product.v1", "state")
        require(proposal_list, "proposal list", view="correlation_list",
                selected_target_id=target_id,
                correlation_proposal_id=proposal_id,
                correlation_selection=0, lease_mask=13)
        validate_proposal(proposal_list)
        states["proposal_list"] = proposal_list
        screens["proposal_list"] = capture(
            device, frames, "targets-correlation-list")

        action(device, "right")
        review = query(device, b"targets.state",
                       "leshy.targets.product.v1", "state")
        require(review, "proposal review", view="correlation_review",
                correlation_review_selection=0,
                correlation_proposal_id=proposal_id, write_enabled=False)
        validate_proposal(review)
        states["review"] = review
        screens["review"] = capture(
            device, frames, "targets-correlation-review")

        action(device, "right")
        known = query(device, b"targets.state",
                      "leshy.targets.product.v1", "state")
        require(known, "known evidence", view="correlation_evidence",
                correlation_evidence_candidate=False,
                correlation_proposal_id=proposal_id)
        states["known_evidence"] = known
        screens["known_evidence"] = capture(
            device, frames, "targets-correlation-known-evidence")
        action(device, "left")
        action(device, "down")
        action(device, "right")
        candidate_state = query(device, b"targets.state",
                                 "leshy.targets.product.v1", "state")
        require(candidate_state, "candidate evidence",
                view="correlation_evidence",
                correlation_evidence_candidate=True,
                correlation_candidate_identity_hex=candidate_identity,
                correlation_proposal_id=proposal_id)
        states["candidate_evidence"] = candidate_state
        screens["candidate_evidence"] = capture(
            device, frames, "targets-correlation-candidate-evidence")

        action(device, "left")
        action(device, "down")
        accept = query(device, b"targets.state",
                       "leshy.targets.product.v1", "state")
        require(accept, "accept selected", view="correlation_review",
                correlation_review_selection=2, write_enabled=True,
                correlation_proposal_id=proposal_id)
        screens["accept_selected"] = capture(
            device, frames, "targets-correlation-accept-selected")
        action(device, "right")
        saved = wait_mutation(device)
        generation_after = generation_before + 1
        decisions_after = decisions_before + 1
        check_atomic_accept(saved, generation_after, decisions_after)
        require(saved, "accepted ownership", status="ready", view="actions",
                selected_target_id=target_id,
                correlation_count=0,
                correlation_proposal_present=False,
                target_count=target_count_before,
                source_identity_count=identities_before + 1)
        states["accepted"] = saved
        screens["accepted"] = capture(
            device, frames, "targets-correlation-accepted")
        released_before_reset = close_targets(device)
        device.close()
        device = None

        ready, _, reset = reset_capture(
            args.port, args.output, "targets-correlation-cold-reopen", 20.0)
        require(ready, "cold candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        reopened = open_targets(device)
        require(reopened, "cold decision log", status="ready", view="list",
                target_state_generation=generation_after,
                correlation_decision_count=decisions_after,
                target_count=target_count_before,
                source_identity_count=identities_before + 1)
        states["reopened"] = reopened
        screens["reopened"] = capture(
            device, frames, "targets-correlation-cold-reopened")
        released = close_targets(device)
        if int(released.get("heap_free_after_release", 0)) + 512 < int(
                released.get("heap_free_before", 0)):
            raise RuntimeError(f"Targets workspace heap did not recover: {released}")
        cleanup = best_effort_cleanup(device)
        if not cleanup.get("complete"):
            raise RuntimeError(f"final cleanup failed: {cleanup}")
        if fixture is not None:
            fixture_states.append(fixture_mode(fixture, "off"))

        record.update({
            "status": "pass",
            "exact_cid": EXPECTED_CID,
            "session_generation_before": int(recovery["generation"]),
            "fresh_surveys": scans,
            "proposal_id": proposal_id,
            "target_id": target_id,
            "candidate_identity_hex": candidate_identity,
            "decision": "accept",
            "target_state_generation_before": generation_before,
            "target_state_generation_after": generation_after,
            "decision_count_before": decisions_before,
            "decision_count_after": decisions_after,
            "states": states,
            "screens": screens,
            "trace": trace,
            "reset": reset,
            "released_before_reset": released_before_reset,
            "released": released,
            "cleanup": cleanup,
            "flash_count": 0 if args.reuse_exact_flash else 1,
            "radio_tx_commands": 0,
            "external_fixture": fixture_record,
        })
    except Exception as error:
        if device is not None:
            cleanup = best_effort_cleanup(device)
        record.update({
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "states": states,
            "screens": screens,
            "trace": trace,
            "cleanup": cleanup,
            "external_fixture": fixture_record,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        raise
    finally:
        if fixture is not None:
            try:
                fixture_mode(fixture, "off")
            except Exception:
                pass
            fixture.close()
        if device is not None:
            device.close()
        if fixture_process is not None:
            fixture_process.terminate()
            try:
                fixture_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                fixture_process.kill()
                fixture_process.wait(timeout=5.0)

    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(json.dumps({"schema": SCHEMA, "status": "pass",
                      "run": str(args.output / "run.json")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
