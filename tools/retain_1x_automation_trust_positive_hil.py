#!/usr/bin/env python3
"""Retain compact, source-bound positive Automation trust HIL evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT / "tests/hil/evidence/board-01-automation-trust-positive-1.0.0-dev.308")
DEFAULT_SUMMARY = Path(f"{DEFAULT_BUNDLE}.json")
DEFAULT_FAILURE = (
    ROOT / "tests/hil/evidence/board-01-automation-trust-positive-1.0.0-dev.307-failed.json")
EXPECTED_SOURCE = "c70ab42739faab639b65c2fb77905718921fa676"
EXPECTED_RUNNER_COMMIT = "ae2ecbf88cfb3d10fb03739fb8591a844dc1d134"
EXPECTED_RUNNER = "d5384fb30e80f6f38baec4ede93b61a034c63f86864274ae172ad8cef0d356c7"
EXPECTED_VERSION = "1.0.0-dev.308"
EXPECTED_FIRMWARE = "d68155a47d47181547843d1ab2f89056fd98a5ce5863a05846604fae2637e866"
EXPECTED_ELF = "66e29c6337fddf89a3fe554def643c3cc167843c5a88125f765c952951e9c4c0"
EXPECTED_MAP = "96f803134e9dc83f849cdc6856a252be1035cb329c36dc3f873859b7d87e0128"
EXPECTED_FACTORY = "658eb147d214ac8f0fdd0b8bfe40d9a15b6928167974b69efae0cb28e590522f"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_BUNDLE = "426eb188dd0ba3f4386435c8bb59f7f250d87e8fb8a1402e3f250fbbe5986408"
EXPECTED_METADATA = "713cf315d8741dac99305aba7b4d856feabb6962a7bcbb8ee0a88b661342879d"
EXPECTED_KEY_ID = "72b53a9dcfb4d96b"
EXPECTED_PUBLIC_KEY = "72b53a9dcfb4d96b9fabc1d0b80abc950be7649678d7c7d88f50bb0793d48407"
EXPECTED_FAILURE_SOURCE = "d08815a5e927c6f1098c8103c631dd279063de13"
FRAMES = (
    "automation-trust-import-review-a.png",
    "automation-trust-import-review-b.png",
    "automation-trust-enrolled.png",
    "automation-trust-revoke-review-a.png",
    "automation-trust-revoke-review-b.png",
    "automation-trust-revoked.png",
)
BOOTS = (
    "automation-trust-cold-restore.ndjson",
    "automation-trust-final-clean.ndjson",
)
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.cpp",
    "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.h",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.h",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustHilFixture.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustHilFixture.h",
    "firmware/leshy1/src/apps/automation/AutomationTrustBundle.cpp",
    "firmware/leshy1/src/apps/automation/AutomationTrustBundle.h",
    "firmware/leshy1/src/apps/automation/AutomationTrustStore.cpp",
    "firmware/leshy1/src/apps/automation/AutomationTrustStore.h",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def git_blob_digest(commit: str, path: str) -> str:
    return hashlib.sha256(git_blob(commit, path)).hexdigest()


def validate_candidate(candidate: dict[str, Any]) -> None:
    require(candidate == {
        "app_elf_sha256": EXPECTED_ELF,
        "elf_sha256": EXPECTED_ELF,
        "firmware_bytes": 3563504,
        "firmware_sha256": EXPECTED_FIRMWARE,
        "map_sha256": EXPECTED_MAP,
        "version": EXPECTED_VERSION,
    }, "exact candidate mismatch")


def zero_output(state: dict[str, Any], name: str) -> None:
    require(state.get("action_invocations") == 0 and
            state.get("hid_reports") == 0 and
            state.get("rf_transmit_attempts") == 0,
            f"unsafe output counter: {name}")


def validate(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.automation_trust_positive_hil.run.v1" and
            run.get("status") == "pass" and run.get("passed") is True and
            run.get("failures") == [], "passing positive trust run required")
    require(run.get("board") == "board-01" and
            run.get("port") == "/dev/cu.usbmodem2101", "board identity mismatch")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "firmware source mismatch")
    validate_candidate(run.get("candidate", {}))
    require(run.get("runner_sha256") == EXPECTED_RUNNER,
            "runner identity mismatch")
    require(run.get("flash_count") == 0 and
            run.get("installed_candidate_reused") is True and
            run.get("hardware_reset_count") == 2,
            "accepted no-flash/two-reset lineage mismatch")

    public = run.get("public_bundle", {})
    require(public == {
        "algorithm": "ecdsa_p256_sha256",
        "bundle_bytes": 128,
        "bundle_sha256": EXPECTED_BUNDLE,
        "contains_private_key": False,
        "key_id": EXPECTED_KEY_ID,
        "label": "GitHub owner key",
        "public_key_sha256": EXPECTED_PUBLIC_KEY,
        "retained_bundle_sha256": EXPECTED_BUNDLE,
        "retained_metadata_sha256": EXPECTED_METADATA,
        "schema": "leshy.automation.trust_bundle.v1",
    }, "public bundle identity mismatch")
    expected_scope = f"/leshy-hil/{run['run_id']}"
    require(run.get("policy") == {
        "delta_only": True,
        "forbidden_ports_touched": [],
        "full_hil": False,
        "private_key_used_or_stored": False,
        "product_trust_namespace_written_or_erased": False,
        "radio_tx_commands": 0,
        "sd_file_bytes": 128,
        "sd_files_written": 1,
        "sd_scope": expected_scope,
        "trust_mutation_confirmed": True,
        "trust_namespace": "leshy1-auto-hil",
        "wifi_host_touched": False,
    }, "delta safety policy mismatch")
    require(run.get("radio_tx_commands") == 0, "radio command issued")

    reports = run["reports"]
    for name in ("product_trust_before", "isolated_empty", "enrolled",
                 "restored", "revoked", "product_trust_after_cleanup",
                 "final_product_trust"):
        zero_output(reports[name], name)
        require(reports[name].get("private_key_stored") is False and
                reports[name].get("public_keys_only") is True,
                f"public-only trust boundary mismatch: {name}")
    for name, count, generation in (
            ("product_trust_before", 0, 0), ("isolated_empty", 0, 0),
            ("enrolled", 1, 1), ("restored", 1, 1), ("revoked", 0, 2),
            ("product_trust_after_cleanup", 0, 0),
            ("final_product_trust", 0, 0)):
        state = reports[name]
        require(state.get("count") == count and
                state.get("generation") == generation,
                f"trust transition mismatch: {name}")

    begin = reports["trust_fixture_begin"]
    resume = reports["trust_fixture_resume"]
    cleanup = reports["trust_fixture_cleanup"]
    for name, state in (("begin", begin), ("resume", resume),
                        ("cleanup", cleanup)):
        zero_output(state, f"trust_fixture_{name}")
        require(state.get("complete") is True and
                state.get("cid_hex") == EXPECTED_CID and
                state.get("fingerprint_matched") is True and
                state.get("expected_sha256") == EXPECTED_BUNDLE and
                state.get("observed_sha256") == EXPECTED_BUNDLE and
                state.get("bundle_valid") is True and
                state.get("bundle_matched") is True and
                state.get("key_id") == EXPECTED_KEY_ID and
                state.get("private_key_received") is False and
                state.get("product_namespace_written_or_erased") is False and
                state.get("whole_nvs_read_or_copied") is False and
                state.get("format_allowed") is False and
                state.get("scratch_path") == expected_scope,
                f"trust fixture mismatch: {name}")
    require(begin.get("bytes_written") == 128 and begin.get("write_calls") == 1 and
            begin.get("file_syncs") == 1 and begin.get("directory_syncs") == 1 and
            begin.get("file_barrier_complete") is True and
            begin.get("directory_barrier_complete") is True and
            begin.get("exact_entries") is True,
            "durable exact SD write mismatch")
    require(resume.get("bytes_written") == 0 and resume.get("write_calls") == 0 and
            resume.get("scratch_preexisting") is True,
            "cold resume rewrote scratch data")
    require(cleanup.get("cleanup_complete") is True and
            cleanup.get("namespace_cleared") is True and
            cleanup.get("files_removed") == 1 and
            cleanup.get("product_restored") is True and
            cleanup.get("owned_after") == 0,
            "scratch cleanup mismatch")

    for name in ("cold_restore_reset", "final_reset"):
        reset = reports[name]
        require(reset.get("attempt") == 1 and reset.get("capture_attempts") == 1 and
                reset.get("capture_transient_retries") == 0 and
                reset.get("ready_present") is True and
                len(reset.get("attempt_records", [])) == 1,
                f"single cold reset mismatch: {name}")
    lock_before = reports["product_lock_before"]
    lock_after = reports["product_lock_after_cleanup"]
    require(all(lock_before.get(key) == lock_after.get(key) for key in
                ("status", "failure", "credential_generation", "failed_attempts",
                 "protected_access", "radio_touched")),
            "Device Lock product state changed")
    require(reports["device_lock_fixture_cleanup"].get("product_restored") is True and
            reports["device_lock_fixture_cleanup"].get(
                "product_namespace_written_or_erased") is False,
            "isolated Device Lock fixture not restored")
    require(run.get("cleanup") == {
        "attempted": True,
        "complete": True,
        "device_lock_fixture_removed": True,
        "errors": [],
        "final_cold_boot_clean": True,
        "hil_ended": True,
        "product_lock_restored": True,
        "product_trust_restored": True,
        "scratch_removed": True,
        "trust_fixture_removed": True,
    }, "terminal cleanup mismatch")
    require(reports["final_cold_home"].get("page") == "home" and
            reports["final_cold_home"].get("runtime_owner") == "none" and
            reports["final_cold_home"].get("lease_mask") == 0 and
            reports["safe_outputs"].get("buzzer_inactive") is True and
            reports["safe_outputs"].get("nrf_ce_inactive") is True and
            reports["safe_outputs"].get("software_quiesce_complete") is True and
            reports["hil_end"].get("active") is False,
            "safe terminal state mismatch")


def retain_failure(run_path: Path, output: Path) -> dict[str, Any]:
    failed = json.loads(run_path.read_text(encoding="utf-8"))
    failures = failed.get("failures", [])
    require(failed.get("schema") == "leshy.automation_trust_positive_hil.run.v1" and
            failed.get("status") == "failed" and failed.get("passed") is False and
            failed.get("source_commit") == EXPECTED_FAILURE_SOURCE and
            len(failures) == 1 and "bundle_matched': False" in failures[0],
            "expected dev.307 negative evidence mismatch")
    require(failed.get("cleanup", {}).get("complete") is True and
            failed.get("cleanup", {}).get("hil_ended") is True and
            failed.get("policy", {}).get("radio_tx_commands") == 0 and
            failed.get("policy", {}).get("wifi_host_touched") is False,
            "failed predecessor did not clean up safely")
    compact = {
        "schema": "leshy.automation_trust_positive_hil.failure.v1",
        "status": "failed_as_expected_and_preserved",
        "firmware_source_commit": EXPECTED_FAILURE_SOURCE,
        "candidate": failed["candidate"],
        "failure_class": "cold_restore_bundle_match_telemetry_false_negative",
        "failure": failures[0],
        "cleanup_complete": True,
        "hil_ended": True,
        "radio_tx_commands": 0,
        "wifi_host_touched": False,
        "successor_firmware_source_commit": EXPECTED_SOURCE,
        "raw_run_sha256": digest(run_path),
    }
    write_json(output, compact)
    return compact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--predecessor-failure", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--failure-summary", type=Path, default=DEFAULT_FAILURE)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists() or args.failure_summary.exists():
        parser.error("retained destination already exists")
    try:
        run_dir = args.run.resolve()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        validate(run)
        require(digest(args.factory.resolve()) == EXPECTED_FACTORY,
                "factory image mismatch")
        require(hashlib.sha256(git_blob(
            EXPECTED_RUNNER_COMMIT,
            "tools/run_1x_automation_trust_positive_hil.py")).hexdigest() ==
            EXPECTED_RUNNER, "runner commit/blob mismatch")
        for name in BOOTS:
            require((run_dir / name).is_file(), f"missing boot capture: {name}")
        for name in FRAMES:
            require((run_dir / "frames" / name).is_file(),
                    f"missing frame: {name}")
        require(digest(run_dir / "automation-owner.lhak") == EXPECTED_BUNDLE and
                digest(run_dir / "automation-owner.json") == EXPECTED_METADATA,
                "retained public bundle input mismatch")
    except (KeyError, OSError, subprocess.CalledProcessError,
            TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_path, args.bundle / "run.json")
    for name in BOOTS:
        shutil.copyfile(run_dir / name, args.bundle / name)
    for name in ("automation-owner.lhak", "automation-owner.json"):
        shutil.copyfile(run_dir / name, args.bundle / name)
    frames = args.bundle / "frames"
    frames.mkdir()
    for name in FRAMES:
        shutil.copyfile(run_dir / "frames" / name, frames / name)

    predecessor = retain_failure(
        args.predecessor_failure.resolve() / "run.json", args.failure_summary)
    provenance = {
        "schema": "leshy.automation_trust_positive_hil.provenance.v1",
        "firmware_source_commit": EXPECTED_SOURCE,
        "runner_commit": EXPECTED_RUNNER_COMMIT,
        "runner_sha256": EXPECTED_RUNNER,
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "source_sha256": {
            path: git_blob_digest(EXPECTED_SOURCE, path) for path in SOURCE_PATHS
        },
        "accepted_raw_run_sha256": digest(run_path),
        "predecessor_failure_summary_sha256": digest(args.failure_summary),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)

    reports = run["reports"]
    stable_frames = {
        "import_review": {
            "png_sha256": run["captures"]["import_review"]["png_sha256"],
            "pair": ["frames/automation-trust-import-review-a.png",
                     "frames/automation-trust-import-review-b.png"],
        },
        "revoke_review": {
            "png_sha256": run["captures"]["revoke_review"]["png_sha256"],
            "pair": ["frames/automation-trust-revoke-review-a.png",
                     "frames/automation-trust-revoke-review-b.png"],
        },
    }
    summary = {
        "schema": "leshy.automation_trust_positive_hil.summary.v1",
        "status": "pass_with_retained_negative_predecessor",
        "evidence_ids": ["E-BUILD-210", "E-AUTO-185", "E-HIL-218",
                         "E-SEC-085", "E-STORAGE-068", "RB-M221"],
        "board": run["board"],
        "firmware_source_commit": EXPECTED_SOURCE,
        "runner_commit": EXPECTED_RUNNER_COMMIT,
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "lineage": {
            "candidate_flashes": 1,
            "accepted_run_flashes": 0,
            "accepted_run_reused_installed_candidate": True,
            "accepted_run_hardware_resets": 2,
            "reset_capture_attempts": 2,
            "reset_capture_transient_retries": 0,
        },
        "public_bundle": run["public_bundle"],
        "storage": {
            "cid": EXPECTED_CID,
            "scratch_path": reports["trust_fixture_begin"]["scratch_path"],
            "bytes_written": 128,
            "write_calls": 1,
            "file_syncs": 1,
            "directory_syncs": 1,
            "exact_entries": True,
            "files_removed": 1,
            "namespace_cleared": True,
        },
        "trust_transition": {
            "product_before": {"count": 0, "generation": 0},
            "isolated_before": {"count": 0, "generation": 0},
            "enrolled": {"count": 1, "generation": 1},
            "cold_restored": {"count": 1, "generation": 1},
            "revoked": {"count": 0, "generation": 2},
            "product_after": {"count": 0, "generation": 0},
            "final_cold_boot": {"count": 0, "generation": 0},
        },
        "stable_frames": stable_frames,
        "result_frames": {
            "enrolled": "frames/automation-trust-enrolled.png",
            "revoked": "frames/automation-trust-revoked.png",
        },
        "safe": {
            "action_invocations": 0,
            "hid_reports": 0,
            "rf_transmit_attempts": 0,
            "radio_tx_commands": 0,
            "private_key_used_or_stored": False,
            "product_trust_namespace_written_or_erased": False,
            "device_lock_product_restored": True,
            "wifi_host_touched": False,
            "forbidden_ports_touched": [],
        },
        "cleanup": run["cleanup"],
        "boot_captures": list(BOOTS),
        "predecessor_failure": {
            "path": str(args.failure_summary.relative_to(ROOT)),
            "sha256": digest(args.failure_summary),
            "failure_class": predecessor["failure_class"],
        },
        "raw_run_sha256": provenance["accepted_raw_run_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
