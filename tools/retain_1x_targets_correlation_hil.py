#!/usr/bin/env python3
"""Retain compact machine-checked exact 0.155 Targets correlation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-correlation-0.155"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-correlation-0.155.json"
EXPECTED_CID = "FE343253440000002000000055019CB7"
FIRMWARE_SOURCE = "7328220c641e25ca8ae34ea311500990108a1a18"
RECOVERY_SOURCE = "9ae9192803c96523ce0b76558494a8899fa88e4c"
VERSION = "0.155.7-targets-shared-codec"
FIRMWARE = "57cd9a4b2f84fbdd2ce7421f902497b1b57ea0a441adf64c20a6f37df93cdf2e"
ELF = "47f483e9a65ede473fa4c9b5a3541267fdf6ea6e04dd9fb66efe29e6772cb89a"
MAP = "17cdfbbfbe042a57c5b50eb31991015ca5a9b93ea72c49626c49132fe0020627"
TARGET_ID = "D232CBB7B4489ABAABFAFD7163BB1D51"
PROPOSAL_ID = "0BCA18AD1AC37BE67ED0E2936E3B1C8C"
CANDIDATE_IDENTITY = "E8F60A98CCBD"
FIXTURE_SERIAL = "E8:F6:0A:98:CC:BC"
FIXTURE_FIRMWARE = "faf515d51eb9c6f3128a3127949a171db099889a9eaafc8ce6627e564bab85b3"
FIXTURE_FACTORY = "1338ed9f37812a432793688e5be6676f9ec2660711376faac3ea9a1d19b61bfd"
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/apps/targets/TargetsController.cpp",
    "firmware/leshy1/src/apps/targets/TargetsController.h",
    "firmware/leshy1/src/domain/targets/Correlation.cpp",
    "firmware/leshy1/src/domain/targets/Correlation.h",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/services/targets/SessionCorrelationReview.cpp",
    "firmware/leshy1/src/services/targets/SessionCorrelationReview.h",
    "firmware/leshy1/src/storage/TargetStateStore.cpp",
    "firmware/leshy1/src/storage/TargetStateStore.h",
    "tools/check_targets_product_contract.py",
    "tools/check_targets_stack_elf_contract.py",
    "tools/run_1x_targets_correlation_hil.py",
    "tools/run_1x_targets_correlation_recovery_hil.py",
)
FRAMES = {
    "proposal-list": "targets-correlation-list",
    "proposal-review": "targets-correlation-review",
    "known-evidence": "targets-correlation-known-evidence",
    "candidate-evidence": "targets-correlation-candidate-evidence",
    "accept-selected": "targets-correlation-accept-selected",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def validate_candidate(candidate: dict[str, Any]) -> None:
    require(candidate.get("version") == VERSION and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("elf_sha256") == ELF and
            candidate.get("app_elf_sha256") == ELF and
            candidate.get("map_sha256") == MAP and
            candidate.get("firmware_bytes") == 3135296,
            "exact 0.155.7 candidate mismatch")
    frames = candidate.get("checked_stack_frames", {})
    require(frames.get("CorrelationService::propose(") == 416 and
            frames.get("buildSessionCorrelationReview(") == 816 and
            frames.get("TargetsController::loadBindings(") == 432 and
            frames.get("buildSide(") == 1104,
            "bounded stack preflight mismatch")


def validate_recovery(run: dict[str, Any]) -> None:
    require(run.get("schema") ==
            "leshy.targets_correlation_recovery_hil.run.v1" and
            run.get("status") == "pass" and
            run.get("source_commit") == RECOVERY_SOURCE,
            "passing exact recovery run required")
    validate_candidate(run.get("candidate", {}))
    transition = run.get("transition", {})
    require(transition == {
        "proposal_id": PROPOSAL_ID,
        "candidate_identity_hex": CANDIDATE_IDENTITY,
        "target_id": TARGET_ID,
        "target_revision_before": 3,
        "target_revision_after": 4,
        "target_state_generation_before": 8,
        "target_state_generation_after": 9,
        "decision_count_before": 0,
        "decision_count_after": 1,
        "source_identity_count_before": 69,
        "source_identity_count_after": 69,
    }, "cold accepted transition mismatch")
    accepted = run.get("accepted_target", {})
    require(run.get("exact_cid") == EXPECTED_CID and
            run.get("flash_count") == 0 and
            run.get("radio_tx_commands") == 0 and
            run.get("cardputer_ports_opened") == 0 and
            accepted.get("selected_target_id") == TARGET_ID and
            accepted.get("selected_revision") == 4 and
            accepted.get("target_state_generation") == 9 and
            accepted.get("correlation_decision_count") == 1 and
            accepted.get("source_identity_count") == 69 and
            accepted.get("correlation_count") == 0 and
            accepted.get("correlation_proposal_present") is False,
            "cold Target/decision state mismatch")
    released = run.get("released", {})
    final = run.get("cleanup", {}).get("final_state", {})
    require(released.get("status") == "not_loaded" and
            released.get("workspace_allocated") is False and
            released.get("cleanup_complete") is True and
            released.get("lease_mask") == 0 and
            run.get("cleanup", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "terminal cleanup mismatch")


def validate_correlation_precursor(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_correlation_hil.run.v1" and
            run.get("status") == "failed" and
            run.get("source_commit") == FIRMWARE_SOURCE,
            "exact correlation precursor required")
    validate_candidate(run.get("candidate", {}))
    selected = run.get("states", {}).get("proposal_selected", {})
    require(selected.get("selected_target_id") == TARGET_ID and
            selected.get("selected_revision") == 3 and
            selected.get("correlation_proposal_id") == PROPOSAL_ID and
            selected.get("correlation_candidate_identity_hex") ==
                CANDIDATE_IDENTITY and
            selected.get("correlation_confidence") == "medium" and
            selected.get("correlation_score_permille") == 463 and
            selected.get("correlation_feature_count") == 2 and
            selected.get("correlation_feature_kind") == "advertised_name" and
            selected.get("correlation_known_radio") == 1 and
            selected.get("correlation_candidate_radio") == 2 and
            selected.get("correlation_known_generation") == 154 and
            selected.get("correlation_candidate_generation") == 155 and
            selected.get("source_identity_count") == 69,
            "proposal/evidence mismatch")
    error = str(run.get("error", ""))
    require("accepted ownership:" in error and
            "'source_identity_count': 70" in error and
            "'source_identity_count': 69" in error and
            run.get("cleanup", {}).get("complete") is True,
            "precursor must stop only at the superseded harness assertion")


def validate_favorite(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.targets_favorite_hil.run.v1" and
            run.get("status") == "pass" and
            run.get("source_commit") == FIRMWARE_SOURCE and
            run.get("exact_cid") == EXPECTED_CID,
            "shared-codec mutation regression required")
    validate_candidate(run.get("candidate", {}))
    saved = run.get("states", {}).get("saved", {})
    require(saved.get("mutation_state") == "saved" and
            saved.get("mutation_status") == "saved" and
            saved.get("mutation_persisted") is True and
            saved.get("mutation_bytes_written") == 2079 and
            saved.get("mutation_write_calls") == 3 and
            saved.get("mutation_file_syncs") == 3 and
            saved.get("mutation_directory_syncs") == 3 and
            saved.get("mutation_heap_largest_before_mount") == 29684 and
            run.get("target_state_generation_before") == 7 and
            run.get("target_state_generation_after") == 8 and
            run.get("cleanup", {}).get("complete") is True,
            "shared codec atomic regression mismatch")


def validate_fixture_orchestration(orchestration: dict[str, Any]) -> None:
    state = orchestration.get("fixture_ready_state", {})
    require(
        orchestration.get("schema") ==
            "leshy.targets_correlation_fixture_orchestration.v1" and
        orchestration.get("status") == "failed" and
        orchestration.get("dut_port") == "/dev/cu.usbmodem2101" and
        orchestration.get("fixture_port") == "/dev/cu.usbmodem1101" and
        orchestration.get("fixture_openocd_serial") == FIXTURE_SERIAL and
        orchestration.get("fixture_firmware_sha256") == FIXTURE_FIRMWARE and
        orchestration.get("fixture_restore_attempted") is True and
        orchestration.get("fixture_restore_complete") is True and
        orchestration.get("fixture_restore_sha256") == FIXTURE_FACTORY and
        orchestration.get("fixture_ready_stable_replies") == 2 and
        state.get("schema") == "leshy.hil.correlation_fixture.v1" and
        state.get("mode") == "off" and
        state.get("ble_tx") is False and state.get("wifi_tx") is False,
        "bounded fixture restoration record mismatch",
    )


def validate_failures(stack: dict[str, Any], mount: dict[str, Any],
                      workspace: dict[str, Any]) -> None:
    require(stack.get("status") == "pass" and
            stack.get("source_commit") ==
                "f0ce2f5d977fec1da36ada579cb1cda6f4c2b0b2" and
            stack.get("exact_cid") == EXPECTED_CID,
            "stack-corrective regression mismatch")
    require(mount.get("status") == "failed" and
            mount.get("source_commit") ==
                "f0ce2f5d977fec1da36ada579cb1cda6f4c2b0b2" and
            "'mutation_status': 'mount_failed'" in str(mount.get("error")) and
            "'mutation_persisted': False" in str(mount.get("error")) and
            mount.get("cleanup", {}).get("complete") is True,
            "mount-starvation precursor mismatch")
    saved = workspace.get("states", {}).get("saved", {})
    require(workspace.get("status") == "failed" and
            workspace.get("source_commit") ==
                "aac7a4d336b246ce8742e7e5ec1e698dc8926de7" and
            saved.get("mutation_status") ==
                "workspace_unavailable_after_mount" and
            saved.get("mutation_persisted") is False and
            saved.get("mutation_bytes_written") == 0 and
            saved.get("mutation_write_calls") == 0 and
            workspace.get("cleanup", {}).get("complete") is True,
            "post-mount allocation precursor mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", required=True, type=Path)
    parser.add_argument("--correlation", required=True, type=Path)
    parser.add_argument("--favorite", required=True, type=Path)
    parser.add_argument("--stack", required=True, type=Path)
    parser.add_argument("--mount-failure", required=True, type=Path)
    parser.add_argument("--workspace-failure", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        directories = {name: getattr(args, name).resolve() for name in
                       ("recovery", "correlation", "favorite", "stack",
                        "mount_failure", "workspace_failure")}
        runs = {name: load(path / "run.json")
                for name, path in directories.items()}
        fixture_orchestration = load(
            directories["correlation"] / "fixture-orchestration.json")
        validate_recovery(runs["recovery"])
        validate_correlation_precursor(runs["correlation"])
        validate_favorite(runs["favorite"])
        validate_failures(runs["stack"], runs["mount_failure"],
                          runs["workspace_failure"])
        validate_fixture_orchestration(fixture_orchestration)
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(directories["recovery"] / "run.json",
                    args.bundle / "run.json")
    shutil.copyfile(directories["correlation"] /
                    "fixture-orchestration.json",
                    args.bundle / "fixture-orchestration.json")
    precursors = args.bundle / "precursors"
    precursors.mkdir()
    for name in ("correlation", "favorite", "stack", "mount_failure",
                 "workspace_failure"):
        shutil.copyfile(directories[name] / "run.json",
                        precursors / f"{name.replace('_', '-')}.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for retained, source in FRAMES.items():
        for suffix in (".json", ".png"):
            shutil.copyfile(directories["correlation"] / "frames" /
                            f"{source}{suffix}",
                            frames / f"{retained}{suffix}")
    for suffix in (".json", ".png"):
        shutil.copyfile(
            directories["recovery"] / "frames" /
            f"targets-correlation-recovered-target{suffix}",
            frames / f"recovered-target{suffix}")

    provenance = {
        "schema": "leshy.targets_correlation_hil.provenance.v1",
        "firmware_source_commit": FIRMWARE_SOURCE,
        "recovery_source_commit": RECOVERY_SOURCE,
        "candidate": runs["recovery"]["candidate"],
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "source_snapshot_commit": RECOVERY_SOURCE,
        "retention_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "retention_script_sha256": digest(Path(__file__).resolve()),
        "raw": {name: {
            "run_sha256": digest(path / "run.json"),
            "artifacts_manifest_sha256": digest(path / "artifacts.sha256"),
        } for name, path in directories.items()},
        "fixture_orchestration_sha256": digest(
            directories["correlation"] / "fixture-orchestration.json"),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {str(path.relative_to(args.bundle)): digest(path)
                for path in sorted(args.bundle.rglob("*")) if path.is_file()}
    write_json(args.bundle / "manifest.json", manifest)

    transition = runs["recovery"]["transition"]
    saved = runs["favorite"]["states"]["saved"]
    summary = {
        "schema": "leshy.targets_correlation_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-113", "E-HIL-173", "E-UX-050"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "fixture": {"id": "board-02", "rom_mac": "90:70:69:0d:15:e0",
                    "role": "bounded BLE name beacon",
                    "openocd_serial": FIXTURE_SERIAL,
                    "diagnostic_firmware_sha256": FIXTURE_FIRMWARE,
                    "factory_restore_sha256": FIXTURE_FACTORY,
                    "factory_restore_complete": True,
                    "terminal_mode": "off",
                    "terminal_stable_replies": 2,
                    "terminal_ble_tx": False,
                    "terminal_wifi_tx": False,
                    "orchestration": "fixture-orchestration.json"},
        "firmware_source_commit": FIRMWARE_SOURCE,
        "verification_source_commit": RECOVERY_SOURCE,
        "candidate": runs["recovery"]["candidate"],
        "exact_cid": EXPECTED_CID,
        "proposal": {
            "id": PROPOSAL_ID, "target_id": TARGET_ID,
            "candidate_identity_hex": CANDIDATE_IDENTITY,
            "confidence": "medium", "score_permille": 463,
            "features": ["advertised_name", "signal_trend"],
            "known": {"radio": "wifi", "generation": 154,
                      "rssi_dbm": -66, "channel": 8},
            "candidate": {"radio": "ble", "generation": 155,
                          "rssi_dbm": -63},
        },
        "accepted_transition": transition,
        "atomic_write_regression": {key: saved[key] for key in (
            "mutation_action_us", "mutation_elapsed_us",
            "mutation_bytes_written", "mutation_write_calls",
            "mutation_file_syncs", "mutation_directory_syncs",
            "mutation_heap_free_before_mount",
            "mutation_heap_largest_before_mount",
            "mutation_identity_attempts", "mutation_identity_transient_retries",
        )},
        "stack_frames": runs["recovery"]["candidate"]["checked_stack_frames"],
        "flash_count_recovery": 0,
        "radio_tx_commands_from_dut": 0,
        "cardputer_ports_opened": 0,
        "final": {"page": "home", "runtime_owner": "none", "lease_mask": 0},
        "screens": {name: {"png": f"frames/{name}.png",
                            "png_sha256": digest(frames / f"{name}.png")}
                    for name in (*FRAMES.keys(), "recovered-target")},
        "precursors": {
            "stack_frame_fixed": "precursors/stack.json",
            "mount_starvation_zero_write": "precursors/mount-failure.json",
            "post_mount_workspace_zero_write":
                "precursors/workspace-failure.json",
            "shared_codec_atomic_regression": "precursors/favorite.json",
            "accepted_then_harness_cardinality_abort":
                "precursors/correlation.json",
        },
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
