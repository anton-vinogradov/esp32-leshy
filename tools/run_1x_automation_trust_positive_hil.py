#!/usr/bin/env python3
"""Positive physical HIL for Automation owner trust, isolated from product state."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from automation_trust_public_bundle import BUNDLE_BYTES, load_public_bundle
from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_automation_trust_ui_hil import (
    HIL_SCHEMA,
    TRUST_SCHEMA,
    UI_SCHEMA,
    enter_trust_page,
    focus_import,
    require,
    return_home,
    stable_capture_pair,
    trust_state,
    verify_passive,
)
from run_1x_device_lock_hil import LOCK_SCHEMA, device_lock_page, home_device
from run_1x_device_lock_persistence_hil import (
    enter_pin,
    ephemeral_pin,
    fixture_command as device_lock_fixture_command,
    wait_lock_state,
    wipe_pin,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    boot_ready_failures,
    capture,
    query,
    reset_capture,
)
from run_1x_ui_typography_hil import normalize_home


RUN_SCHEMA = "leshy.automation_trust_positive_hil.run.v1"
FIXTURE_SCHEMA = "leshy.automation.trust.fixture.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_PORTS = {"/dev/cu.usbmodem1101"}
def trust_fixture_command(device: PassiveSerial, operation: str, cid: str,
                          run_id: str, bundle_sha256: str) -> dict[str, Any]:
    if operation not in {"begin", "resume", "cleanup"}:
        raise ValueError("invalid trust fixture operation")
    command = (
        f"automation.trust-fixture {operation} disposable-write "
        f"{cid} {run_id} {bundle_sha256}"
    )
    return query(device, command.encode("ascii"), FIXTURE_SCHEMA, operation,
                 timeout=20.0)


def stage_public_bundle(device: PassiveSerial,
                        bundle: bytes) -> list[dict[str, Any]]:
    if len(bundle) != BUNDLE_BYTES:
        raise ValueError("invalid public bundle length")
    encoded = bundle.hex()
    reports = []
    for chunk in range(4):
        value = encoded[chunk * 64:(chunk + 1) * 64]
        report = query(
            device,
            f"automation.trust-fixture stage {chunk} {value}".encode("ascii"),
            FIXTURE_SCHEMA, "stage")
        require(
            report, f"stage {chunk}", status="staged", chunk=chunk,
            stage_mask=(1 << (chunk + 1)) - 1,
            staging_complete=chunk == 3, private_key_received=False,
            storage_written=False,
            product_namespace_written_or_erased=False,
            rf_transmit_attempts=0)
        reports.append(report)
    return reports


def verify_trust_state(record: dict[str, Any], label: str, *, count: int,
                       generation: int, active: bool,
                       cleanup_required: bool | None = None) -> None:
    if cleanup_required is None:
        cleanup_required = active
    require(
        record, label, ready=True, count=count, generation=generation,
        capacity=4, all_keys_p256_and_id_bound=True,
        fixture_active=active,
        fixture_cleanup_required=cleanup_required,
        fixture_namespace_selected=active, public_keys_only=True,
        private_key_stored=False, execution_connected=False,
        action_invocations=0, hid_reports=0, rf_transmit_attempts=0)


def verify_fixture(record: dict[str, Any], label: str, *, operation: str,
                   cid: str, run_id: str, bundle_sha256: str,
                   key_id: str) -> None:
    active = operation != "cleanup"
    require(
        record, label, status="complete", complete=True,
        expected_fingerprint=cid, cid_hex=cid, fingerprint_matched=True,
        run_id=run_id, expected_sha256=bundle_sha256,
        observed_sha256=bundle_sha256, bundle_valid=True, key_id=key_id,
        fixture_active=active, cleanup_required=active,
        fixture_namespace_selected=active,
        namespace_cleared=operation == "cleanup",
        product_restored=operation == "cleanup",
        exact_entries=True,
        bundle_read=True, bundle_matched=True,
        cleanup_complete=operation == "cleanup",
        identity_cleanup=True, filesystem_cleanup=True,
        gpio21_stable_high=True, owned_after=0,
        private_key_received=False,
        product_namespace_written_or_erased=False,
        whole_nvs_read_or_copied=False, format_allowed=False,
        rf_transmit_attempts=0, action_invocations=0, hid_reports=0)
    if operation == "begin":
        require(
            record, label + " write", scratch_preexisting=False,
            fixture_store_restored=True, namespace_prepared=True,
            prepared=True, bundle_written=True,
            file_barrier_complete=True, directory_barrier_complete=True,
            bytes_written=BUNDLE_BYTES, write_calls=1, file_syncs=1,
            directory_syncs=1)
    elif operation == "resume":
        require(record, label + " resume", fixture_store_restored=True)
    else:
        require(record, label + " cleanup", files_removed=1)


def begin_hil(device: PassiveSerial, run_id: str,
              app_identity: str) -> dict[str, Any]:
    report = query(
        device, f"hil.begin {run_id} {app_identity}".encode("ascii"),
        HIL_SCHEMA, "begun")
    require(report, "HIL begin", status="begun", active=True,
            session_id=run_id, app_elf_sha256=app_identity)
    return report


def reopen_after_reset(port: str, run_id: str,
                       app_identity: str) -> tuple[PassiveSerial, dict[str, Any]]:
    device = PassiveSerial(port, 115200, timeout=0.25)
    synchronize_console(device, 20.0)
    return device, begin_hil(device, run_id, app_identity)


def configure_isolated_lock(device: PassiveSerial, pin: bytearray,
                             trace: list[dict[str, Any]]) -> dict[str, Any]:
    home_device(device)
    device_lock_page(device)
    opened = action(device, "right")
    trace.append(opened)
    if opened.get("runtime_event") != "device_lock_editor_opened":
        raise RuntimeError("isolated Device Lock editor did not open")
    enter_pin(device, pin)
    enter_pin(device, pin)
    unlocked = wait_lock_state(
        device, lambda value: value.get("status") == "unlocked",
        "isolated trust mutation unlock")
    require(unlocked, "isolated lock configured", status="unlocked",
            protected_access=True, persistence_fixture_active=True)
    return unlocked


def unlock_isolated_lock(device: PassiveSerial, pin: bytearray,
                         trace: list[dict[str, Any]]) -> dict[str, Any]:
    home_device(device)
    device_lock_page(device)
    opened = action(device, "right")
    trace.append(opened)
    enter_pin(device, pin)
    unlocked = wait_lock_state(
        device, lambda value: value.get("status") == "unlocked",
        "restored isolated trust mutation unlock")
    require(unlocked, "isolated lock restored", status="unlocked",
            protected_access=True, persistence_fixture_active=True)
    return unlocked


def product_state_matches(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(after.get(field) == before.get(field) for field in (
        "ready", "load_status", "generation", "count",
        "all_keys_p256_and_id_bound"))


def best_effort_revoke_isolated_trust(
        device: PassiveSerial, pin: bytearray, trace: list[dict[str, Any]],
        cid: str, run_id: str, bundle_sha256: str,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Make the isolated store empty so the exact cleanup may proceed."""
    recovery: list[dict[str, Any]] = []
    current = trust_state(device)
    if (current.get("fixture_active") is False and
            current.get("fixture_cleanup_required") is True):
        resumed = trust_fixture_command(
            device, "resume", cid, run_id, bundle_sha256)
        recovery.append(resumed)
        current = trust_state(device)
    count = current.get("count")
    if count == 0:
        return current, recovery
    if count != 1 or current.get("fixture_active") is not True:
        raise RuntimeError(f"isolated trust store is not safely revocable: {current!r}")
    lock = query(device, b"device-lock.state", LOCK_SCHEMA, "state")
    if lock.get("persistence_fixture_active") is not True:
        resumed_lock = device_lock_fixture_command(device, "resume")
        recovery.append(resumed_lock)
        lock = query(device, b"device-lock.state", LOCK_SCHEMA, "state")
    if lock.get("status") != "unlocked":
        recovery.append(unlock_isolated_lock(device, pin, trace))
        return_home(device, trace)
    enter_trust_page(device, trace)
    review_action = action(device, "right")
    trace.append(review_action)
    review = trust_state(device)
    recovery.append(review)
    if review.get("ui_view") != "revoke_review":
        raise RuntimeError(f"cleanup revoke review did not open: {review!r}")
    apply_action = action(device, "right")
    trace.append(apply_action)
    revoked = trust_state(device)
    recovery.append(revoked)
    if revoked.get("count") != 0 or revoked.get("ui_result") != "applied":
        raise RuntimeError(f"cleanup revoke did not apply: {revoked!r}")
    return_home(device, trace)
    return revoked, recovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--bundle-metadata", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--skip-flash", action="store_true")
    args = parser.parse_args()
    if args.port != BOARD_PORT or args.port in FORBIDDEN_PORTS:
        parser.error(f"exact board-01 port required: {BOARD_PORT}")
    if len(args.source_commit) != 40:
        parser.error("source commit must be a full hash")
    if (len(args.expected_cid) != 32 or args.expected_cid.upper() !=
            args.expected_cid or any(character not in "0123456789ABCDEF"
                                     for character in args.expected_cid)):
        parser.error("expected CID must be 32 uppercase hexadecimal characters")
    for path in (args.firmware, args.elf, args.map, args.bundle,
                 args.bundle_metadata):
        if not path.is_file():
            parser.error(f"required artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    try:
        bundle, bundle_metadata = load_public_bundle(
            args.bundle, args.bundle_metadata)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    public_bundle = args.output / "automation-owner.lhak"
    public_metadata = args.output / "automation-owner.json"
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.bundle, public_bundle)
    shutil.copyfile(args.bundle_metadata, public_metadata)
    app_identity = app_elf_sha256(candidate)
    bundle_sha256 = hashlib.sha256(bundle).hexdigest()
    key_id = str(bundle_metadata["key_id"])
    run_id = secrets.token_hex(16)
    lock_pin = ephemeral_pin()
    reports: dict[str, Any] = {}
    captures: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    failures: list[str] = []
    cleanup: dict[str, Any] = {
        "attempted": False, "complete": False, "errors": []}
    device: PassiveSerial | None = None
    initial_language = ""
    product_trust_before: dict[str, Any] = {}
    product_lock_before: dict[str, Any] = {}
    hil_begun = False
    trust_fixture_active = False
    lock_fixture_active = False
    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "passed": False,
        "run_id": run_id,
        "board": "board-01",
        "port": args.port,
        "source_commit": args.source_commit,
        "runner_sha256": sha256_file(Path(__file__)),
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
        },
        "public_bundle": {
            **bundle_metadata,
            "retained_bundle_sha256": sha256_file(public_bundle),
            "retained_metadata_sha256": sha256_file(public_metadata),
        },
        "policy": {
            "delta_only": True,
            "full_hil": False,
            "trust_mutation_confirmed": True,
            "trust_namespace": "leshy1-auto-hil",
            "product_trust_namespace_written_or_erased": False,
            "sd_scope": f"/leshy-hil/{run_id}",
            "sd_files_written": 1,
            "sd_file_bytes": BUNDLE_BYTES,
            "private_key_used_or_stored": False,
            "radio_tx_commands": 0,
            "wifi_host_touched": False,
            "forbidden_ports_touched": [],
        },
    }
    write_json(args.output / "run.json", record)

    try:
        if not args.skip_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.6)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics, "candidate", version=args.expected_version,
                app_elf_sha256=app_identity, buzzer_inactive=True,
                input_detected=True)
        reports["metrics_before"] = metrics
        home = normalize_home(device)
        require(home, "initial Home", page="home", runtime_owner="none",
                lease_mask=0)
        initial_language = str(home["language"])
        sessions.append(begin_hil(device, run_id, app_identity))
        hil_begun = True

        product_trust_before = trust_state(device)
        product_count = int(product_trust_before.get("count", -1))
        product_generation = int(product_trust_before.get("generation", -1))
        if product_count < 0 or product_count > 4 or product_generation < 0:
            raise RuntimeError("invalid product trust baseline")
        verify_trust_state(
            product_trust_before, "product trust before", count=product_count,
            generation=product_generation, active=False,
            cleanup_required=False)
        reports["product_trust_before"] = product_trust_before
        product_lock_before = query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["product_lock_before"] = product_lock_before

        lock_begin = device_lock_fixture_command(device, "begin")
        require(lock_begin, "lock fixture begin", status="begun", active=True,
                product_namespace_written_or_erased=False)
        reports["device_lock_fixture_begin"] = lock_begin
        lock_fixture_active = True
        reports["device_lock_configured"] = configure_isolated_lock(
            device, lock_pin, trace)
        reports["home_after_lock"] = return_home(device, trace)

        reports["bundle_stages"] = stage_public_bundle(device, bundle)
        fixture_begin = trust_fixture_command(
            device, "begin", args.expected_cid, run_id, bundle_sha256)
        trust_fixture_active = bool(
            fixture_begin.get("fixture_active") or
            fixture_begin.get("cleanup_required"))
        verify_fixture(
            fixture_begin, "trust fixture begin", operation="begin",
            cid=args.expected_cid, run_id=run_id,
            bundle_sha256=bundle_sha256, key_id=key_id)
        reports["trust_fixture_begin"] = fixture_begin
        trust_fixture_active = True

        isolated_empty = trust_state(device)
        verify_trust_state(
            isolated_empty, "isolated empty", count=0, generation=0,
            active=True)
        require(isolated_empty, "isolated bundle root",
                bundle_root=f"/leshy-hil/{run_id}")
        reports["isolated_empty"] = isolated_empty

        enter_trust_page(device, trace)
        focus_import(device, trace)
        trace.append(action(device, "right"))
        review = trust_state(device)
        verify_passive(review, "positive import review")
        require(review, "positive import review view",
                ui_view="import_review", ui_result="none",
                confirmation_open=True, confirmation_fresh=True,
                fixture_active=True, fixture_namespace_selected=True)
        reports["import_review"] = review
        captures["import_review"] = stable_capture_pair(
            device, frames, "automation-trust-import-review")[0]

        trace.append(action(device, "right"))
        enrolled = trust_state(device)
        verify_trust_state(
            enrolled, "isolated enrolled", count=1, generation=1,
            active=True)
        require(enrolled, "isolated enroll result", ui_view="result",
                ui_result="applied", confirmation_open=False,
                device_unlocked=True)
        reports["enrolled"] = enrolled
        captures["enrolled"] = capture(
            device, frames, "automation-trust-enrolled")
        reports["home_before_reset"] = return_home(device, trace)

        device.close()
        device = None
        boot_restore, recovery_restore, reset_restore = reset_capture(
            args.port, args.output, "automation-trust-cold-restore", 25.0, 2)
        reports["cold_restore_boot"] = boot_restore
        reports["cold_restore_recovery"] = recovery_restore
        reports["cold_restore_reset"] = reset_restore
        reset_failures = boot_ready_failures(
            boot_restore, args.expected_version, app_identity)
        if reset_failures:
            raise RuntimeError("cold restore boot: " + "; ".join(reset_failures))
        device, resumed_session = reopen_after_reset(
            args.port, run_id, app_identity)
        sessions.append(resumed_session)
        hil_begun = True

        product_after_reset = trust_state(device)
        verify_trust_state(
            product_after_reset, "product after reset", count=product_count,
            generation=product_generation, active=False,
            cleanup_required=True)
        reports["product_trust_after_reset"] = product_after_reset
        if not product_state_matches(product_trust_before, product_after_reset):
            raise RuntimeError("product trust state changed across isolated enroll")

        fixture_resume = trust_fixture_command(
            device, "resume", args.expected_cid, run_id, bundle_sha256)
        reports["trust_fixture_resume"] = fixture_resume
        verify_fixture(
            fixture_resume, "trust fixture resume", operation="resume",
            cid=args.expected_cid, run_id=run_id,
            bundle_sha256=bundle_sha256, key_id=key_id)
        restored = trust_state(device)
        verify_trust_state(
            restored, "isolated restored", count=1, generation=1,
            active=True)
        reports["restored"] = restored

        lock_resume = device_lock_fixture_command(device, "resume")
        require(lock_resume, "lock fixture resume", status="resumed",
                active=True, product_namespace_written_or_erased=False)
        reports["device_lock_fixture_resume"] = lock_resume
        reports["device_lock_unlocked_after_reset"] = unlock_isolated_lock(
            device, lock_pin, trace)
        reports["home_before_revoke"] = return_home(device, trace)

        enter_trust_page(device, trace)
        trace.append(action(device, "right"))
        revoke_review = trust_state(device)
        verify_trust_state(
            revoke_review, "revoke review", count=1, generation=1,
            active=True)
        require(revoke_review, "revoke review view", ui_view="revoke_review",
                ui_result="none", confirmation_open=True,
                confirmation_fresh=True, device_unlocked=True)
        reports["revoke_review"] = revoke_review
        captures["revoke_review"] = stable_capture_pair(
            device, frames, "automation-trust-revoke-review")[0]

        trace.append(action(device, "right"))
        revoked = trust_state(device)
        verify_trust_state(
            revoked, "isolated revoked", count=0, generation=2,
            active=True)
        require(revoked, "isolated revoke result", ui_view="result",
                ui_result="applied", confirmation_open=False,
                device_unlocked=True)
        reports["revoked"] = revoked
        captures["revoked"] = capture(
            device, frames, "automation-trust-revoked")
        reports["home_before_cleanup"] = return_home(device, trace)

        fixture_cleanup = trust_fixture_command(
            device, "cleanup", args.expected_cid, run_id, bundle_sha256)
        verify_fixture(
            fixture_cleanup, "trust fixture cleanup", operation="cleanup",
            cid=args.expected_cid, run_id=run_id,
            bundle_sha256=bundle_sha256, key_id=key_id)
        reports["trust_fixture_cleanup"] = fixture_cleanup
        trust_fixture_active = False
        product_after_cleanup = trust_state(device)
        verify_trust_state(
            product_after_cleanup, "product after cleanup", count=product_count,
            generation=product_generation, active=False,
            cleanup_required=False)
        reports["product_trust_after_cleanup"] = product_after_cleanup
        if not product_state_matches(product_trust_before, product_after_cleanup):
            raise RuntimeError("product trust state changed after cleanup")

        lock_cleanup = device_lock_fixture_command(device, "cleanup")
        require(lock_cleanup, "lock fixture cleanup", status="cleaned",
                active=False, product_restored=True,
                product_namespace_written_or_erased=False)
        reports["device_lock_fixture_cleanup"] = lock_cleanup
        lock_fixture_active = False
        product_lock_after = query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        reports["product_lock_after_cleanup"] = product_lock_after
        for field in ("status", "failure", "failed_attempts",
                      "credential_generation"):
            if product_lock_after.get(field) != product_lock_before.get(field):
                raise RuntimeError(f"product Device Lock changed: {field}")

        final_home = query(device, b"ui.state", UI_SCHEMA, "state")
        require(final_home, "final Home", page="home", runtime_owner="none",
                lease_mask=0, safety_latched=False)
        reports["final_home"] = final_home
        safe = query(device, b"hardware.safe-outputs",
                     "leshy.hardware.safe-outputs.v1", "state")
        require(safe, "safe outputs", buzzer_inactive=True,
                nrf_ce_inactive=True, software_quiesce_complete=True)
        reports["safe_outputs"] = safe
        ended = query(
            device, f"hil.end {run_id}".encode("ascii"), HIL_SCHEMA, "ended")
        require(ended, "HIL end", status="ended", active=False,
                session_id=run_id)
        reports["hil_end"] = ended
        hil_begun = False
        device.close()
        device = None

        final_boot, final_recovery, final_reset = reset_capture(
            args.port, args.output, "automation-trust-final-clean", 25.0, 2)
        reports["final_boot"] = final_boot
        reports["final_recovery"] = final_recovery
        reports["final_reset"] = final_reset
        final_failures = boot_ready_failures(
            final_boot, args.expected_version, app_identity)
        if final_failures:
            raise RuntimeError("final clean boot: " + "; ".join(final_failures))
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        final_trust = trust_state(device)
        verify_trust_state(
            final_trust, "final product trust", count=product_count,
            generation=product_generation, active=False,
            cleanup_required=False)
        reports["final_product_trust"] = final_trust
        if not product_state_matches(product_trust_before, final_trust):
            raise RuntimeError("product trust changed after final cold boot")
        final_state = normalize_home(device)
        require(final_state, "final cold Home", page="home",
                runtime_owner="none", lease_mask=0)
        reports["final_cold_home"] = final_state
        cleanup = {
            "attempted": True,
            "complete": True,
            "trust_fixture_removed": True,
            "device_lock_fixture_removed": True,
            "scratch_removed": True,
            "product_trust_restored": True,
            "product_lock_restored": True,
            "final_cold_boot_clean": True,
            "hil_ended": True,
            "errors": [],
        }
    except Exception as error:
        failures.append(f"workflow: {type(error).__name__}: {error}")
    finally:
        if device is not None and device.is_open:
            if failures:
                cleanup["attempted"] = True
                try:
                    return_home(device, trace)
                    cleanup["final_home"] = True
                except Exception as error:
                    cleanup["errors"].append(
                        f"home: {type(error).__name__}: {error}")
                if trust_fixture_active:
                    try:
                        current, trust_recovery = \
                            best_effort_revoke_isolated_trust(
                                device, lock_pin, trace, args.expected_cid,
                                run_id, bundle_sha256)
                        reports["trust_revoke_best_effort"] = trust_recovery
                        if current.get("count") == 0:
                            removed = trust_fixture_command(
                                device, "cleanup", args.expected_cid, run_id,
                                bundle_sha256)
                            reports["trust_cleanup_best_effort"] = removed
                            trust_fixture_active = not bool(
                                removed.get("product_restored"))
                    except Exception as error:
                        cleanup["errors"].append(
                            f"trust: {type(error).__name__}: {error}")
                if lock_fixture_active:
                    try:
                        removed = device_lock_fixture_command(device, "cleanup")
                        reports["lock_cleanup_best_effort"] = removed
                        lock_fixture_active = not bool(
                            removed.get("product_restored"))
                    except Exception as error:
                        cleanup["errors"].append(
                            f"lock: {type(error).__name__}: {error}")
                if hil_begun and not trust_fixture_active and not lock_fixture_active:
                    try:
                        reports["hil_end_best_effort"] = query(
                            device, f"hil.end {run_id}".encode("ascii"),
                            HIL_SCHEMA, "ended")
                        hil_begun = False
                    except Exception as error:
                        cleanup["errors"].append(
                            f"hil: {type(error).__name__}: {error}")
                cleanup.update({
                    "trust_fixture_removed": not trust_fixture_active,
                    "device_lock_fixture_removed": not lock_fixture_active,
                    "hil_ended": not hil_begun,
                })
                cleanup["complete"] = (
                    not trust_fixture_active and not lock_fixture_active and
                    not hil_begun and cleanup["errors"] == [])
            device.close()
    wipe_pin(lock_pin)

    record.update({
        "status": "pass" if not failures and cleanup.get("complete")
                  else "failed",
        "passed": not failures and cleanup.get("complete") is True,
        "failures": failures,
        "initial_language": initial_language,
        "reports": reports,
        "captures": captures,
        "trace": trace,
        "sessions": sessions,
        "cleanup": cleanup,
        "flash_count": 0 if args.skip_flash else 1,
        "installed_candidate_reused": args.skip_flash,
        "hardware_reset_count": 2,
        "radio_tx_commands": 0,
    })
    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "status": record["status"],
        "passed": record["passed"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
