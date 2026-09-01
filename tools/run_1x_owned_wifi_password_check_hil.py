#!/usr/bin/env python3
"""Physical export -> guided offline check for the exact owned Wi-Fi path."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import check_my_wifi_password as journey
import run_1x_wifi_authentication_capture_hil as authentication
import run_1x_wifi_authentication_persistence_hil as persistence
from run_1x_product_survey_hil import artifact_manifest, expect
from run_1x_prerelease_hil import sha256_file, write_json


RUN_SCHEMA = "leshy.owned_wifi_password_check_hil.run.v1"
ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CORPUS = b"not-the-fixture\nhashcat!\n"


def current_network_detail(
        device: Any, trace: list[dict[str, Any]], label: str,
        allowed_label_hash: str,
        mount_diagnostics: dict[str, Any] | None = None,
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Open a live network and traverse the current task-first intro.

    Wi-Fi Nearby intentionally stopped mounting product storage before a user
    asks to save anything.  The historical persistence runner still expects
    the old eager-remount telemetry and a direct technical-capture transition;
    this adapter preserves every radio/selection assertion while accepting the
    current zero-write boundary and explicit user-facing password-check step.
    """
    preparing = authentication.action(device, "right")
    trace.append(preparing)
    authentication.require_exact(preparing, {
        "page": "survey", "wifi_product_view": "networks",
        "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_selected_source_mask": 1,
    }, f"{label}_networks_preparing")
    network_list = authentication.wait_ui_state(
        device,
        lambda state: (
            state.get("wifi_product_view") == "networks" and
            state.get("survey_workflow_state") == "running" and
            state.get("survey_product_worker_ready") is True and
            state.get("wifi_networks_strongest_first") is True and
            int(state.get("wifi_networks_unique", 0)) >= 1 and
            int(state.get("survey_product_wifi_scan_cycles", 0)) >= 1
        ), 45.0, f"{label}: nearby Wi-Fi network did not appear")
    authentication.require_exact(network_list, {
        "runtime_owner": "wifi", "lease_mask": 15,
        "survey_product_worker_ready": True,
        "survey_product_status": "running",
        "survey_product_active_source_mask": 1,
        "survey_product_backend_open": False,
        "survey_product_storage_mounted": False,
        "survey_product_store_open_attempted": False,
        "survey_product_store_status": "permitted",
        "survey_product_admission_status": "permitted",
        "survey_product_filesystem_mount_stage": "idle",
        "survey_product_filesystem_bus_initialize_error": 0,
        "survey_product_filesystem_drive_available_before_vfs": False,
        "survey_product_filesystem_mount_attempts": 0,
        "survey_product_filesystem_mount_transient_retries": 0,
        "survey_product_filesystem_mount_error": 0,
        "survey_product_filesystem_mount_last_failure_error": 0,
        "survey_scan_status": "valid", "survey_scan_dropped": 0,
    }, f"{label}_networks_live")
    if mount_diagnostics is not None:
        mount_diagnostics[label] = {
            "completed": True,
            "policy": "volatile_list_mount_on_save_only",
            "storage_mounted": False,
            "physical_write_calls": 0,
        }
    network_list["authorized_selector"] = \
        authentication.select_authorized_network(
            device, allowed_label_hash, label)
    detail_ui = authentication.action(device, "right")
    trace.append(detail_ui)
    authentication.require_exact(detail_ui, {
        "wifi_product_view": "network_detail",
        # The live list keeps sorting after the user enters a card; only the
        # focus is user-owned.  Freezing the order here would resurrect the
        # navigation behaviour explicitly removed from the product contract.
        "wifi_network_navigation_locked": False,
        "wifi_network_focus_user_owned": True,
        "runtime_owner": "wifi", "lease_mask": 15,
    }, f"{label}_detail_ui")
    detail = authentication.read_only_query(
        device, b"wifi.network.detail",
        "leshy.wifi.network_detail.v1", "state")
    authentication.require_exact(detail, {
        "active": True, "passive": True,
        "active_probe_allowed": False,
    }, f"{label}_detail")
    if (not isinstance(detail.get("identity_hash"), int) or
            detail["identity_hash"] == 0 or
            not isinstance(detail.get("channel"), int) or
            not 1 <= detail["channel"] <= 13):
        raise RuntimeError(f"{label}: selected network has no fixed channel")
    intro_ui = authentication.action(device, "right")
    trace.append(intro_ui)
    authentication.require_exact(intro_ui, {
        "wifi_product_view": "password_check_intro",
        "runtime_event": "wifi_password_check_intro",
        "survey_workflow_state": "running",
        "runtime_owner": "wifi", "lease_mask": 15,
    }, f"{label}_password_check_intro")
    return network_list, detail_ui, detail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--allowed-ssid-fnv1a64", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--failed-precursor", type=Path)
    return parser


def child_arguments(args: argparse.Namespace, output: Path) -> list[str]:
    values = [
        "run_1x_wifi_authentication_persistence_hil.py",
        "--port", args.port,
        "--firmware", str(args.firmware),
        "--expected-version", args.expected_version,
        "--expected-cid", args.expected_cid,
        "--source-commit", args.source_commit,
        "--allowed-ssid-fnv1a64", args.allowed_ssid_fnv1a64,
        "--output", str(output),
    ]
    if args.reuse_exact_flash:
        values.append("--reuse-exact-flash")
    return values


def run_guided_check(payload: bytes) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="leshy-owned-wifi-") as directory:
        root = Path(directory)
        evidence = root / "exported-by-leshy.txt"
        corpus = root / "local-reviewed-list.txt"
        output = root / "result"
        evidence.write_bytes(payload)
        corpus.write_bytes(PUBLIC_CORPUS)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = journey.main([
                "--evidence", str(evidence),
                "--corpus", str(corpus),
                "--list-kind", "mixed",
                "--language", "en",
                "--max-candidates", "2",
                "--max-seconds", "10",
                "--output-directory", str(output),
                "--yes-i-am-authorized",
            ])
        reports = list(output.glob("wifi-password-check-*.json"))
        if status != 0 or stderr.getvalue() or len(reports) != 1:
            raise RuntimeError("guided offline check failed")
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        rendered = stdout.getvalue()
        if "hashcat!" in rendered or "WPA*" in rendered:
            raise RuntimeError("guided output disclosed a candidate or jargon")
        return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.reuse_exact_flash:
        raise SystemExit("this focused chain requires --reuse-exact-flash")
    if args.output.exists():
        raise SystemExit("--output must not exist")
    if not args.firmware.is_file():
        raise SystemExit("--firmware must be a regular file")
    child = args.output / "device"
    captured: dict[str, bytes] = {}
    original_detail = authentication.enter_network_detail
    original_reader = persistence.read_binary_artifact
    original_argv = sys.argv

    def intercept_reader(*reader_args: Any, **reader_kwargs: Any) \
            -> tuple[dict[str, Any], bytes, dict[str, Any]]:
        result = original_reader(*reader_args, **reader_kwargs)
        if len(reader_args) >= 3 and reader_args[2] == persistence.HC22000_SCHEMA:
            captured["hc22000"] = result[1]
        return result

    failures: list[str] = []
    child_status = 2
    verification: dict[str, Any] = {}
    try:
        authentication.enter_network_detail = current_network_detail
        persistence.read_binary_artifact = intercept_reader
        sys.argv = child_arguments(args, child)
        child_status = persistence.main()
        if child_status != 0:
            failures.append("device_export_chain_failed")
        elif "hc22000" not in captured:
            failures.append("device_export_not_observed")
        else:
            verification = run_guided_check(captured["hc22000"])
            if (verification.get("status") != "pass" or
                    verification.get("outcome") != "weak_password_match" or
                    verification.get("result", {}).get("matched_rank") != 2 or
                    verification.get("privacy", {}).get(
                        "plaintext_retained") is not False or
                    verification.get("side_effects") != {
                        "network_operations": 0,
                        "device_writes": 0,
                        "radio_operations": 0,
                    }):
                failures.append("guided_verification_contract_failed")
    except Exception:
        failures.append("coordinator_failed_closed")
    finally:
        sys.argv = original_argv
        authentication.enter_network_detail = original_detail
        persistence.read_binary_artifact = original_reader
        captured.clear()

    args.output.mkdir(parents=True, exist_ok=True)
    child_run = child / "run.json"
    child_value: dict[str, Any] = {}
    if child_run.is_file():
        child_value = json.loads(child_run.read_text(encoding="utf-8"))
    child_failures = expect(child_value, {
        "passed": True, "gate_eligible": True, "failures": [],
    }, "device") if child_status == 0 else []
    failures.extend(child_failures)
    precursor_sha = None
    if args.failed_precursor is not None:
        precursor_sha = sha256_file(args.failed_precursor)
    result = {
        "schema": RUN_SCHEMA,
        "passed": not failures,
        "failures": failures,
        "candidate": child_value.get("candidate", {}),
        "board": child_value.get("board", {}),
        "device_chain": {
            "run_sha256": sha256_file(child_run) if child_run.is_file() else None,
            "runner_sha256": sha256_file(
                Path(persistence.__file__).resolve()),
            "public_fixture_only": True,
            "fresh_flash": False,
            "atomic_save": child_value.get("fixture", {}).get(
                "persisted", {}).get("atomic_commit"),
            "cold_reopen": child_value.get("fixture", {}).get(
                "persisted", {}).get("reopen_verified"),
            "export": child_value.get("library", {}).get("hc22000", {}).get(
                "summary", {}),
            "final_cleanup": child_value.get("cleanup_after", {}).get(
                "complete"),
        },
        "computer_check": verification,
        "tooling": {
            "journey_sha256": sha256_file(
                ROOT / "tools/check_my_wifi_password.py"),
            "verifier_sha256": sha256_file(
                ROOT / "tools/owned_wifi_evidence_verifier.py"),
            "coordinator_sha256": sha256_file(Path(__file__).resolve()),
        },
        "precursor": {
            "reason": "obsolete_eager_mount_oracle_before_fixture",
            "run_sha256": precursor_sha,
            "device_write_started": False,
            "flash_started": False,
        } if precursor_sha is not None else None,
        "privacy": {
            "raw_export_retained": False,
            "candidate_plaintext_retained": False,
            "private_network_identity_retained": False,
            "corpus": "public_two-line_hil_only",
        },
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": result["passed"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
