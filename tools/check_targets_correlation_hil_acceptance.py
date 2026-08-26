#!/usr/bin/env python3
"""Fail closed unless compact exact 0.155 Targets correlation HIL is intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-correlation-0.155.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_git_blob(commit: str, relative: str) -> str | None:
    try:
        blob = subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(blob).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    if not SUMMARY.is_file():
        print(f"FAIL: missing {SUMMARY}", file=sys.stderr)
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    bundle = ROOT / summary.get("bundle", "missing")
    manifest_path = bundle / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {})
    require(failures, manifest_path.is_file() and
            digest(manifest_path) == summary.get("manifest_sha256"),
            "manifest missing or hash mismatch")
    frame_names = (
        "proposal-list", "proposal-review", "known-evidence",
        "candidate-evidence", "accept-selected", "recovered-target",
    )
    expected = {"run.json", "provenance.json", "fixture-orchestration.json"}
    expected.update({f"frames/{name}{suffix}" for name in frame_names
                     for suffix in (".json", ".png")})
    expected.update({f"precursors/{name}.json" for name in (
        "correlation", "favorite", "mount-failure", "stack",
        "workspace-failure")})
    require(failures, set(manifest) == expected,
            "unexpected retained artifact set")
    for relative, expected_hash in manifest.items():
        path = bundle / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"retained artifact mismatch: {relative}")

    require(failures,
            summary.get("schema") ==
                "leshy.targets_correlation_hil.summary.v1" and
            summary.get("status") == "pass" and
            summary.get("evidence_ids") ==
                ["E-AUTO-113", "E-HIL-173", "E-UX-050"],
            "summary identity mismatch")
    require(failures,
            summary.get("firmware_source_commit") ==
                "7328220c641e25ca8ae34ea311500990108a1a18" and
            summary.get("verification_source_commit") ==
                "9ae9192803c96523ce0b76558494a8899fa88e4c",
            "source identity mismatch")
    candidate = summary.get("candidate", {})
    require(failures,
            candidate.get("version") ==
                "0.155.7-targets-shared-codec" and
            candidate.get("firmware_bytes") == 3135296 and
            candidate.get("firmware_sha256") ==
                "57cd9a4b2f84fbdd2ce7421f902497b1b57ea0a441adf64c20a6f37df93cdf2e" and
            candidate.get("app_elf_sha256") ==
                "47f483e9a65ede473fa4c9b5a3541267fdf6ea6e04dd9fb66efe29e6772cb89a" and
            candidate.get("map_sha256") ==
                "17cdfbbfbe042a57c5b50eb31991015ca5a9b93ea72c49626c49132fe0020627",
            "candidate identity mismatch")
    require(failures,
            summary.get("exact_cid") ==
                "FE343253440000002000000055019CB7" and
            summary.get("flash_count_recovery") == 0 and
            summary.get("radio_tx_commands_from_dut") == 0 and
            summary.get("cardputer_ports_opened") == 0,
            "media/passive/USB scope mismatch")
    fixture = summary.get("fixture", {})
    require(failures, fixture == {
        "id": "board-02",
        "rom_mac": "90:70:69:0d:15:e0",
        "role": "bounded BLE name beacon",
        "openocd_serial": "E8:F6:0A:98:CC:BC",
        "diagnostic_firmware_sha256":
            "faf515d51eb9c6f3128a3127949a171db099889a9eaafc8ce6627e564bab85b3",
        "factory_restore_sha256":
            "1338ed9f37812a432793688e5be6676f9ec2660711376faac3ea9a1d19b61bfd",
        "factory_restore_complete": True,
        "terminal_mode": "off",
        "terminal_stable_replies": 2,
        "terminal_ble_tx": False,
        "terminal_wifi_tx": False,
        "orchestration": "fixture-orchestration.json",
    }, "fixture restoration summary mismatch")
    fixture_path = bundle / "fixture-orchestration.json"
    if fixture_path.is_file():
        orchestration = json.loads(fixture_path.read_text(encoding="utf-8"))
        require(failures,
                orchestration.get("fixture_restore_complete") is True and
                orchestration.get("fixture_restore_sha256") ==
                    fixture.get("factory_restore_sha256") and
                orchestration.get("fixture_ready_stable_replies") == 2 and
                orchestration.get("fixture_ready_state", {}).get("mode") ==
                    "off" and
                orchestration.get("fixture_ready_state", {}).get("ble_tx")
                    is False and
                orchestration.get("fixture_ready_state", {}).get("wifi_tx")
                    is False,
                "fixture restoration artifact mismatch")
    require(failures, summary.get("proposal") == {
        "id": "0BCA18AD1AC37BE67ED0E2936E3B1C8C",
        "target_id": "D232CBB7B4489ABAABFAFD7163BB1D51",
        "candidate_identity_hex": "E8F60A98CCBD",
        "confidence": "medium", "score_permille": 463,
        "features": ["advertised_name", "signal_trend"],
        "known": {"radio": "wifi", "generation": 154,
                  "rssi_dbm": -66, "channel": 8},
        "candidate": {"radio": "ble", "generation": 155,
                      "rssi_dbm": -63},
    }, "proposal explanation mismatch")
    require(failures, summary.get("accepted_transition") == {
        "proposal_id": "0BCA18AD1AC37BE67ED0E2936E3B1C8C",
        "candidate_identity_hex": "E8F60A98CCBD",
        "target_id": "D232CBB7B4489ABAABFAFD7163BB1D51",
        "target_revision_before": 3, "target_revision_after": 4,
        "target_state_generation_before": 8,
        "target_state_generation_after": 9,
        "decision_count_before": 0, "decision_count_after": 1,
        "source_identity_count_before": 69,
        "source_identity_count_after": 69,
    }, "accepted cold-reopen transition mismatch")
    require(failures, summary.get("atomic_write_regression") == {
        "mutation_action_us": 212,
        "mutation_elapsed_us": 3320152,
        "mutation_bytes_written": 2079,
        "mutation_write_calls": 3,
        "mutation_file_syncs": 3,
        "mutation_directory_syncs": 3,
        "mutation_heap_free_before_mount": 61468,
        "mutation_heap_largest_before_mount": 29684,
        "mutation_identity_attempts": 1,
        "mutation_identity_transient_retries": 0,
    }, "bounded atomic-write regression mismatch")
    require(failures,
            summary.get("stack_frames", {}).get(
                "CorrelationService::propose(") == 416 and
            summary.get("stack_frames", {}).get(
                "buildSessionCorrelationReview(") == 816 and
            summary.get("stack_frames", {}).get(
                "TargetsController::loadBindings(") == 432,
            "bounded stack mismatch")
    require(failures, summary.get("final") == {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, "terminal cleanup mismatch")
    screen_hashes = {
        "accept-selected":
            "f37c60ed2ff6c2875b8d10c2a62bf2c09faf9c1670c7f2e2a6b76247a9da88e4",
        "candidate-evidence":
            "ac4ebd6d544143afd532139ed1146de8c0d31fc24db67ea23a2b7784df07f5a8",
        "known-evidence":
            "1e65add4962da9c12c95f7801b4f52d2d043755a11fcccd8ac1c9bca4401b177",
        "proposal-list":
            "8af71685a07dd7736997d4879d8eb912867c17cbff5bd5ec335d546260ddd4a1",
        "proposal-review":
            "ffcc9a54a05cce945a82eaeeba90cf2d861935038012314b69acc423f99cb27a",
        "recovered-target":
            "f31e197a16b4ba87e4889d57e9066b8219e339d179fb63a2c7dc48470d671caa",
    }
    require(failures, summary.get("screens") == {
        name: {"png": f"frames/{name}.png", "png_sha256": value}
        for name, value in screen_hashes.items()
    }, "screenshot set/hash mismatch")
    provenance_path = bundle / "provenance.json"
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        source_commit = str(provenance.get("source_snapshot_commit", ""))
        require(failures,
                source_commit ==
                    "9ae9192803c96523ce0b76558494a8899fa88e4c",
                "source snapshot commit mismatch")
        for relative, expected_hash in provenance.get(
                "source_sha256", {}).items():
            require(failures,
                    digest_git_blob(source_commit, relative) == expected_hash,
                    f"accepted source snapshot mismatch: {relative}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets correlation HIL acceptance passed: explainable proposal, "
          "bounded accept, exact cold recovery, immutable source population")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
