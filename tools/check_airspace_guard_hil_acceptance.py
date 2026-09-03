#!/usr/bin/env python3
"""Fail-closed acceptance check for the dev.242 Airspace Guard full HIL gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SOURCE_PATH = "tools/run_1x_airspace_guard_hil.py"
DEFAULT_POSITIVE = (
    ROOT / "tests/hil/evidence/board-01-airspace-guard-1.0.0-dev.242"
)
DEFAULT_NEGATIVE_DEV239 = (
    ROOT / "tests/hil/evidence/"
    "board-01-airspace-guard-1.0.0-dev.239-failed.json"
)
DEFAULT_NEGATIVE_DEV241 = (
    ROOT / "tests/hil/evidence/"
    "board-01-airspace-guard-1.0.0-dev.241-failed.json"
)
DEFAULT_EXPECTATIONS = (
    ROOT / "tests/hil/evidence/"
    "board-01-airspace-guard-1.0.0-dev.242-acceptance.json"
)
VERSION = "1.0.0-dev.242"
FAILED_VERSION = "1.0.0-dev.239"
FAILED_241_VERSION = "1.0.0-dev.241"
CID = "FE343253440000002000000055019CB7"
BOARD = "board-01"
PORT = "/dev/cu.usbmodem2101"
ROM_MAC = "1c:db:d4:87:90:d4"
BLE_LABEL = "Keenetic-5070"
BLE_FIXTURE_SHA256 = (
    "da3cec0a11116e563b8d34d7c3ef042b5aeba0978db069b2b7c89bce6d64106d"
)
FAILED_SOURCE = "88aa287f22b1311f5712dc81bbfef38350bf487e"
FAILED_FIRMWARE = (
    "64d9119237994b75f1827060d51e4fe2c3d2af76c8740adc3726764598d70e61"
)
FAILED_APP = (
    "ff7b5251b2dbff655487bcf99d0e93234bcf365422316109ca808185d56d7433"
)
FAILED_FULL_RUN = (
    "f5d6a69ee4f90173a163cb3e63c96a81067a0b973a4d4a0129d13be6e336be31"
)
FAILED_FULL_INDEX = (
    "11a0ce7d8b40bc4d52930e0d26b8201d4e735e8446cfef8e9b4459b4eeea18c5"
)
FAILED_DELTA_RUN = (
    "38f07bf1ebb12bcf2d4ef6ee3c7b8d94152bf5fdcc323e15c0ac35603cfb36ff"
)
ROOT_CAUSE = (
    "merged_complete_report_above_64_rejected_by_controller_inspection_budget"
)
FAILED_241_SOURCE = "9ccc4b1bf858619ede702145adc84ccab70a0c17"
FAILED_241_FIRMWARE = (
    "48a382c3fa754c133bac81f4e7de262a558cdc397b92c8f4180b3c1bd7141df1"
)
FAILED_241_APP = (
    "32d618dc780e8e56f114186fb2c27c9e7dd217f6eafa5e58a33310524c8a0f81"
)
FAILED_241_FULL_RUN = (
    "a65a28038632d3c044fcd53a533aa9569d2d48eec74a65fca229d894d04c3b93"
)
FAILED_241_FULL_INDEX = (
    "24cc316719c9734afe54bb853407b57ba22c76ad9a3f42fd3f296b35725445ee"
)
FAILED_241_RUNNER = (
    "d3876f198bb972a9faae6d3d5330360ccc6bc4e26eafd7f23297cb735b051e8a"
)
ROOT_CAUSE_241 = (
    "ble_capacity_loss_failed_whole_lifecycle_instead_of_retaining_"
    "inconclusive_result"
)
RUN_SCHEMA = "leshy.airspace_guard_hil.run.v1"
NEGATIVE_SCHEMA = "leshy.airspace_guard_hil.negative.v1"
EXPECTATIONS_SCHEMA = "leshy.airspace_guard_hil.acceptance_expectations.v1"
STATE_SCHEMA = "leshy.airspace_guard.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
SESSION_ID = re.compile(r"[0-9a-f]{32}")
ALLOWED_FINDING_MASK = 0x1F
ELEVATED_NOISE_MASK = 1 << 3
WIDTH = 240
HEIGHT = 320
FRAME_BYTES = WIDTH * HEIGHT * 2
LIVE_REGIONS = {
    "wifi": (67, 279, "wifi_first", "wifi_second"),
    "ble": (88, 132, "ble_first", "ble_second"),
}
SCREEN_FILES = {
    "wifi_first": "guard-wifi-first",
    "wifi_second": "guard-wifi-second",
    "ble_first": "guard-ble-first",
    "ble_second": "guard-ble-second",
    "result": "guard-result",
    "evidence_list": "guard-evidence-list",
    "evidence_detail": "guard-evidence-detail",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def committed_runner_sha256(commit: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{RUNNER_SOURCE_PATH}"], cwd=ROOT,
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(detail or "cannot read committed runner")
    return hashlib.sha256(result.stdout).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def integer(value: Any, minimum: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return minimum is None or value >= minimum


def load_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{label}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{label}: expected JSON object")
        return {}
    return value


def child(record: dict[str, Any], field: str, failures: list[str],
          prefix: str = "") -> dict[str, Any]:
    value = record.get(field)
    if not isinstance(value, dict):
        failures.append(f"{prefix}{field}: missing object")
        return {}
    return value


def exact(record: dict[str, Any], expected: dict[str, Any],
          failures: list[str], prefix: str) -> None:
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(
                f"{prefix}{field}: {record.get(field)!r} != {value!r}"
            )


def resolve_positive(path: Path, failures: list[str]) -> tuple[Path, Path]:
    if path.is_dir():
        return path, path / "run.json"
    if path.name == "run.json" and path.is_file():
        return path.parent, path
    failures.append(f"positive: expected bundle directory or run.json: {path}")
    return path.parent, path


def verify_expectations(value: dict[str, Any], failures: list[str]) -> None:
    expected_fields = {
        "schema", "version", "expected_cid", "run_id", "source_commit",
        "firmware_sha256", "app_elf_sha256", "runner_source_sha256",
        "positive_run_sha256", "positive_artifact_index_sha256",
    }
    require(failures, set(value) == expected_fields,
            "expectations: exact field inventory required")
    exact(value, {
        "schema": EXPECTATIONS_SCHEMA,
        "version": VERSION,
        "expected_cid": CID,
    }, failures, "expectations.")
    require(failures, isinstance(value.get("run_id"), str) and
            SESSION_ID.fullmatch(value["run_id"]) is not None,
            "expectations.run_id: lowercase 32-hex identifier expected")
    require(failures, isinstance(value.get("source_commit"), str) and
            COMMIT.fullmatch(value["source_commit"]) is not None,
            "expectations.source_commit: invalid")
    for field in (
            "firmware_sha256", "app_elf_sha256", "runner_source_sha256",
            "positive_run_sha256", "positive_artifact_index_sha256"):
        require(failures, isinstance(value.get(field), str) and
                SHA256.fullmatch(value[field]) is not None,
                f"expectations.{field}: invalid")


def verify_manifest(bundle: Path, failures: list[str]) -> dict[str, str]:
    manifest = bundle / "artifacts.sha256"
    if not manifest.is_file():
        failures.append("positive.artifacts.sha256: missing")
        return {}
    entries: dict[str, str] = {}
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        failures.append(f"positive.artifacts.sha256: {error}")
        return {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"positive.artifacts.sha256:{number}: malformed")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or
                name in entries or name == "artifacts.sha256"):
            failures.append(
                f"positive.artifacts.sha256:{number}: unsafe/duplicate {name!r}"
            )
            continue
        artifact = bundle / relative
        if not artifact.is_file():
            failures.append(f"positive.artifacts.sha256:{number}: missing {name}")
        else:
            try:
                actual = digest(artifact)
            except OSError as error:
                failures.append(f"positive.{name}: {error}")
            else:
                if actual != expected:
                    failures.append(f"positive.{name}: hash mismatch")
        entries[name] = expected
    try:
        actual_files = {
            str(item.relative_to(bundle))
            for item in bundle.rglob("*")
            if item.is_file() and item != manifest
        }
    except OSError as error:
        failures.append(f"positive.bundle inventory: {error}")
        actual_files = set()
    if set(entries) != actual_files:
        missing = sorted(set(entries) - actual_files)
        unindexed = sorted(actual_files - set(entries))
        failures.append(
            "positive.artifacts.sha256: inventory mismatch "
            f"missing={missing!r} unindexed={unindexed!r}"
        )
    require(failures, "run.json" in entries,
            "positive.artifacts.sha256: run.json not indexed")
    require(failures, "firmware.bin" in entries,
            "positive.artifacts.sha256: firmware.bin not indexed")
    return entries


def verify_candidate(run: dict[str, Any], bundle: Path,
                     entries: dict[str, str], failures: list[str],
                     expectations: dict[str, Any],
                     corrective: dict[str, Any]) -> dict[str, Any]:
    candidate = child(run, "candidate", failures, "positive.")
    exact(candidate, {
        "version": expectations.get("version"),
        "source_commit": expectations.get("source_commit"),
        "firmware_sha256": expectations.get("firmware_sha256"),
        "app_elf_sha256": expectations.get("app_elf_sha256"),
        "flashed": True,
    }, failures, "positive.candidate.")
    require(failures, candidate.get("flash_mode") in ("fresh", "reuse_exact"),
            "positive.candidate.flash_mode: fresh/reuse_exact expected")
    require(failures, isinstance(candidate.get("source_commit"), str) and
            COMMIT.fullmatch(candidate["source_commit"]) is not None,
            "positive.candidate.source_commit: invalid")
    for field in ("firmware_sha256", "app_elf_sha256"):
        require(failures, isinstance(candidate.get(field), str) and
                SHA256.fullmatch(candidate[field]) is not None,
                f"positive.candidate.{field}: invalid")
    require(failures,
            entries.get("firmware.bin") == candidate.get("firmware_sha256"),
            "positive.candidate.firmware_sha256: artifact binding mismatch")
    firmware_path = bundle / "firmware.bin"
    if firmware_path.is_file():
        try:
            embedded_app = app_elf_sha256(firmware_path)
        except (OSError, ValueError, struct.error) as error:
            failures.append(
                f"positive.candidate.app_elf_sha256: invalid ESP image: {error}")
        else:
            require(failures, embedded_app == candidate.get("app_elf_sha256"),
                    "positive.candidate.app_elf_sha256: embedded identity "
                    "mismatch")
    if corrective:
        for field in ("version", "source_commit", "firmware_sha256",
                      "app_elf_sha256"):
            require(failures, candidate.get(field) == corrective.get(field),
                    f"positive.candidate.{field}: corrective binding mismatch")
        exact(corrective, {
            "inspection_budget_records": 128,
            "source_local_wifi_records": 64,
            "source_local_ble_records": 64,
        }, failures, "negative.corrective_candidate.")
    return candidate


def verify_boot(run: dict[str, Any], candidate: dict[str, Any],
                failures: list[str]) -> None:
    boot = child(run, "boot", failures, "positive.")
    exact(boot, {
        "schema": "leshy.boot.v1",
        "kind": "ready",
        "version": candidate.get("version"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "reset_reason_code": 1,
        "input_detected": True,
        "buzzer_safety_configured": True,
        "buzzer_inactive": True,
        "legacy_sources": False,
    }, failures, "positive.boot.")
    for field in ("heap_total", "heap_free", "heap_min_free"):
        require(failures, integer(boot.get(field), 1),
                f"positive.boot.{field}: positive integer expected")
    samples = run.get("boot_metrics_samples")
    require(failures, isinstance(samples, list) and len(samples) >= 2,
            "positive.boot_metrics_samples: at least two expected")
    if isinstance(samples, list):
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                failures.append(f"positive.boot_metrics_samples[{index}]: object expected")
                continue
            exact(sample, {
                "version": candidate.get("version"),
                "app_elf_sha256": candidate.get("app_elf_sha256"),
                "heap_total": boot.get("heap_total"),
                "heap_free": boot.get("heap_free"),
            }, failures, f"positive.boot_metrics_samples[{index}].")


def verify_recovery(run: dict[str, Any], failures: list[str]) -> None:
    before = child(run, "recovery_before", failures, "positive.")
    after = child(run, "recovery_after", failures, "positive.")
    common = {
        "expected_fingerprint": CID,
        "observed_fingerprint": CID,
        "fingerprint_matched": True,
        "integrity": "valid",
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "blocked_write_attempts": 0,
        "physical_write_calls": 0,
        "cleanup_complete": True,
        "owned_after": 0,
    }
    exact(before, common, failures, "positive.recovery_before.")
    exact(after, common, failures, "positive.recovery_after.")
    for field in ("generation", "observations"):
        require(failures, integer(before.get(field), 0) and
                before.get(field) == after.get(field),
                f"positive.recovery.{field}: continuity mismatch")


def verify_running(state: dict[str, Any], stage: str,
                   failures: list[str]) -> None:
    prefix = f"positive.{stage}."
    exact(state, {
        "schema": STATE_SCHEMA,
        "kind": "state",
        "capture_state": stage,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
        "ble_worker_ready": True,
        "survey_queues_released": True,
    }, failures, prefix)
    if stage == "wifi_running":
        exact(state, {
            "wifi_capture_state": "running",
            "wifi_monitor_active": True,
            "wifi_cleanup_complete": False,
            "wifi_driver_error": 0,
            "ble_worker_control": 0,
        }, failures, prefix)
    else:
        exact(state, {
            "wifi_capture_state": "complete",
            "wifi_monitor_active": False,
            "wifi_cleanup_complete": True,
            "wifi_driver_error": 0,
            "wifi_disconnects_dropped": 0,
            "wifi_identity_dropped": 0,
            "wifi_noise_dropped": 0,
            "wifi_receive_invalid_frames": 0,
            "ble_worker_control": 2,
        }, failures, prefix)
    before = state.get("heap_free_before_queue_release")
    after = state.get("heap_free_after_queue_release")
    require(failures, integer(before, 0) and integer(after, 0) and
            after > before, f"{prefix}queue-release heap proof missing")


def verify_stopped(state: dict[str, Any], name: str,
                   failures: list[str]) -> None:
    exact(state, {
        "schema": STATE_SCHEMA,
        "kind": "state",
        "capture_state": "idle",
        "wifi_capture_state": "idle",
        "wifi_monitor_active": False,
        "wifi_cleanup_complete": True,
        "ble_worker_control": 0,
        "survey_queues_released": False,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
    }, failures, f"positive.{name}.")


def verify_result(state: dict[str, Any], name: str,
                  failures: list[str]) -> bool:
    prefix = f"positive.{name}."
    exact(state, {
        "schema": STATE_SCHEMA,
        "kind": "state",
        "capture_state": "result",
        "load_status": "ready",
        "elevated_noise_low_confidence": True,
        "noise_samples_dropped": 0,
        "noise_samples_malformed": 0,
        "malformed_frames": 0,
        "source_read_failures": 0,
        "findings_dropped": 0,
        "inspection_truncated": False,
        "wifi_capture_state": "complete",
        "wifi_driver_error": 0,
        "wifi_cleanup_complete": True,
        "wifi_monitor_active": False,
        "wifi_disconnects_dropped": 0,
        "wifi_identity_dropped": 0,
        "wifi_noise_dropped": 0,
        "wifi_receive_invalid_frames": 0,
        "ble_worker_control": 0,
        "ble_worker_ready": True,
        "ble_worker_valid": True,
        "ble_scan_status": "valid",
        "ble_cleanup_complete": True,
        "ble_scan_rejected": 0,
        "ble_retention_malformed": 0,
        "survey_queues_released": True,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
    }, failures, prefix)
    malformed_fields = (
        "wifi_identity_malformed_envelope",
        "wifi_identity_malformed_addressing",
        "wifi_identity_malformed_elements",
    )
    values = [state.get(field) for field in malformed_fields]
    malformed = sum(values) if all(integer(value, 0) for value in values) else -1
    scan_dropped = state.get("ble_scan_dropped")
    retention_dropped = state.get("ble_retention_dropped")
    capacity_drops = (
        scan_dropped if integer(scan_dropped, 0)
        else -1
    )
    capacity_loss = (
        malformed == 0 and integer(scan_dropped, 1) and
        scan_dropped > 0 and
        retention_dropped == scan_dropped
    )
    complete = (malformed == 0 and capacity_drops == 0 and
                retention_dropped == 0)
    expected_worker_status = "incomplete_evidence" if capacity_loss else "complete"
    exact(state, {
        "wifi_invalid_frames": malformed,
        "source_frames_dropped": malformed + capacity_drops,
        "wifi_identity_retention_complete": malformed == 0,
        "wifi_noise_retention_complete": malformed == 0,
        "evidence_incomplete": not complete,
        "ble_worker_status": expected_worker_status,
    }, failures, prefix)
    require(failures, integer(state.get("generation"), 1) and
            state.get("ble_worker_generation") == state.get("generation"),
            f"{prefix}worker generation mismatch")
    require(failures, complete or capacity_loss,
            f"{prefix}loss type: only exact BLE capacity loss is allowed")
    outcome = state.get("outcome")
    allowed = ("clear", "finding") if complete else ("inconclusive", "finding")
    require(failures, outcome in allowed, f"{prefix}outcome: invalid")
    observed = state.get("source_frames_observed")
    available = state.get("frames_available")
    inspected = state.get("frames_inspected")
    ble_records = state.get("ble_records")
    require(failures, all(integer(value, 1) for value in
                          (observed, available, inspected, ble_records)),
            f"{prefix}positive frame/BLE counts required")
    if all(integer(value, 0) for value in (observed, available, inspected)):
        require(failures, inspected <= available <= observed,
                f"{prefix}frame accounting invalid")
        require(failures, available <= 128,
                f"{prefix}inspection budget exceeded")
    exact(state, {
        "wifi_identity_projected": state.get("wifi_identity_retained"),
        "noise_samples_inspected": state.get("noise_samples_available"),
        "ble_records": state.get("ble_retention_retained"),
    }, failures, prefix)
    ble_accounting = tuple(state.get(field) for field in (
        "ble_scan_observed", "ble_scan_reported", "ble_scan_read",
        "ble_scan_accepted", "ble_scan_dropped", "ble_retention_observed",
        "ble_retention_valid",
    ))
    if all(integer(value, 0) for value in ble_accounting):
        (scan_observed, scan_reported, scan_read, scan_accepted,
         scan_lost, retention_observed, retention_valid) = ble_accounting
        require(failures,
                scan_observed == scan_reported == scan_read ==
                retention_observed == retention_valid,
                f"{prefix}BLE observation/retention accounting invalid")
        require(failures, scan_read == scan_accepted + scan_lost,
                f"{prefix}BLE accepted/drop accounting invalid")
    else:
        failures.append(f"{prefix}BLE accounting fields: integers expected")
    attempts = state.get("ble_scan_attempts")
    retries = state.get("ble_scan_transient_retries")
    require(failures, integer(attempts, 1) and attempts <= 2 and
            integer(retries, 0) and retries < attempts,
            f"{prefix}BLE scan attempt/retry accounting invalid")
    if all(integer(state.get(field), 0) for field in (
            "wifi_frames_reported", "ble_scan_observed",
            "source_frames_observed")):
        require(failures,
                state["source_frames_observed"] ==
                state["wifi_frames_reported"] + state["ble_scan_observed"],
                f"{prefix}source accounting invalid")
    if all(integer(state.get(field), 0) for field in
           ("wifi_frames_retained", "ble_records", "frames_available")):
        require(failures,
                state["frames_available"] ==
                state["wifi_frames_retained"] + state["ble_records"],
                f"{prefix}retained accounting invalid")
        require(failures, state["wifi_frames_retained"] <= 64 and
                state["ble_records"] <= 64,
                f"{prefix}source-local capacity exceeded")
    noise_observed = state.get("noise_samples_observed")
    noise_available = state.get("noise_samples_available")
    if integer(noise_observed, 0) and integer(noise_available, 0):
        require(failures, noise_observed >= noise_available,
                f"{prefix}noise accounting invalid")
    mask = state.get("finding_mask")
    count = state.get("finding_count")
    require(failures, integer(mask, 0) and
            not mask & ~ALLOWED_FINDING_MASK,
            f"{prefix}finding mask invalid")
    require(failures, integer(count, 0) and
            ((outcome == "finding") == (count > 0)),
            f"{prefix}finding count/outcome mismatch")
    if integer(mask, 0) and mask & ELEVATED_NOISE_MASK:
        require(failures, outcome == "finding" and
                integer(noise_available, 4),
                f"{prefix}elevated-noise evidence invalid")
    return capacity_loss


def verify_hil_session(run: dict[str, Any], candidate: dict[str, Any],
                       failures: list[str]) -> None:
    run_id = run.get("run_id")
    session = child(run, "hil_session", failures, "positive.")
    begin = child(session, "begin", failures, "positive.hil_session.")
    end = child(session, "end", failures, "positive.hil_session.")
    exact(begin, {
        "schema": "leshy.hil.session.v1",
        "session_id": run_id,
        "active": True,
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "firmware_version": candidate.get("version"),
    }, failures, "positive.hil_session.begin.")
    require(failures, integer(begin.get("host_begin_action_writes"), 1) and
            begin.get("host_begin_action_writes") == 1,
            "positive.hil_session.begin.host_begin_action_writes: 1 expected")
    require(failures, integer(begin.get("host_begin_action_replays"), 0) and
            begin.get("host_begin_action_replays") == 0,
            "positive.hil_session.begin.host_begin_action_replays: 0 expected")
    begin_ack = begin.get("host_begin_ack_received")
    if begin_ack is True:
        exact(begin, {"kind": "begun", "status": "begun"}, failures,
              "positive.hil_session.begin.")
    elif begin_ack is False:
        exact(begin, {"kind": "state", "status": "active"}, failures,
              "positive.hil_session.begin.")
        require(failures, isinstance(begin.get("host_begin_ack_error"), str) and
                bool(begin["host_begin_ack_error"]),
                "positive.hil_session.begin.host_begin_ack_error: "
                "lost-ACK evidence required")
    else:
        failures.append(
            "positive.hil_session.begin.host_begin_ack_received: bool expected")

    exact(end, {
        "schema": "leshy.hil.session.v1",
        "active": False,
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "host_end_requested_session_id": run_id,
    }, failures, "positive.hil_session.end.")
    end_ack = end.get("host_end_ack_received")
    writes = end.get("host_end_action_writes")
    replays = end.get("host_end_action_replays")
    require(failures, integer(writes, 1) and writes <= 2,
            "positive.hil_session.end.host_end_action_writes: 1..2 expected")
    require(failures, integer(replays, 0) and integer(writes, 1) and
            replays == writes - 1,
            "positive.hil_session.end.host_end_action_replays: "
            "write accounting mismatch")
    if end_ack is True:
        exact(end, {
            "kind": "ended", "status": "ended", "session_id": run_id,
        }, failures, "positive.hil_session.end.")
    elif end_ack is False:
        exact(end, {
            "kind": "state", "status": "inactive", "session_id": "",
            "firmware_version": candidate.get("version"),
        }, failures, "positive.hil_session.end.")
        require(failures, isinstance(end.get("host_end_ack_error"), str) and
                bool(end["host_end_ack_error"]),
                "positive.hil_session.end.host_end_ack_error: "
                "lost-ACK evidence required")
    else:
        failures.append(
            "positive.hil_session.end.host_end_ack_received: bool expected")
    begin_revision = begin.get("ui_revision")
    end_revision = end.get("ui_revision")
    require(failures, integer(begin_revision, 0) and
            integer(end_revision, 0) and end_revision >= begin_revision,
            "positive.hil_session: UI revision continuity invalid")


def verify_capacity_injection(run: dict[str, Any],
                              failures: list[str]) -> None:
    injection = child(run, "capacity_drop_injection", failures, "positive.")
    exact(injection, {
        "schema": "leshy.airspace_guard.capacity_drop_test.v1",
        "kind": "state",
        "status": "armed",
        "one_shot": True,
        "armed": True,
        "hil_active": True,
        "worker_idle": True,
        "ui_home": True,
        "runtime_owner": "none",
        "lease_mask": 0,
        "hardware_touched": False,
        "radio_started": False,
        "storage_mounted": False,
        "storage_written": False,
    }, failures, "positive.capacity_drop_injection.")
    cleared = child(run, "capacity_drop_clear", failures, "positive.")
    exact(cleared, {
        "schema": "leshy.airspace_guard.capacity_drop_test.v1",
        "kind": "state",
        "status": "cleared",
        "one_shot": True,
        "armed": False,
        "hil_active": True,
        "worker_idle": True,
        "ui_home": True,
        "runtime_owner": "none",
        "lease_mask": 0,
        "hardware_touched": False,
        "radio_started": False,
        "storage_mounted": False,
        "storage_written": False,
    }, failures, "positive.capacity_drop_clear.")


def verify_exact_capacity_one(state: dict[str, Any],
                              failures: list[str]) -> None:
    prefix = "positive.result_second."
    exact(state, {
        "ble_scan_accepted": 1,
        "ble_retention_retained": 1,
        "ble_records": 1,
    }, failures, prefix)
    scan_read = state.get("ble_scan_read")
    scan_dropped = state.get("ble_scan_dropped")
    retention_dropped = state.get("ble_retention_dropped")
    require(failures, integer(scan_read, 2),
            f"{prefix}ble_scan_read: expected >= 2")
    if integer(scan_read, 2):
        require(failures,
                scan_dropped == scan_read - 1 and
                retention_dropped == scan_read - 1,
                f"{prefix}effective_capacity_one_accounting: "
                "dropped must equal read - 1")


def verify_lifecycle_generations(run: dict[str, Any],
                                 failures: list[str]) -> None:
    names = (
        "wifi_running", "wifi_cancelled", "ble_running", "ble_cancelled",
        "result_first", "result_second",
    )
    generations = [
        run.get(name, {}).get("generation")
        if isinstance(run.get(name), dict) else None
        for name in names
    ]
    require(failures, all(integer(value, 1) for value in generations),
            "positive.lifecycle_generations: positive integers required")
    if all(integer(value, 1) for value in generations):
        wifi_running, wifi_cancelled, ble_running, ble_cancelled, first, second = (
            generations
        )
        require(failures, wifi_cancelled == wifi_running + 1,
                "positive.lifecycle_generations: Wi-Fi cancel mismatch")
        require(failures, ble_running == wifi_cancelled + 1,
                "positive.lifecycle_generations: BLE start mismatch")
        require(failures, ble_cancelled == ble_running + 1,
                "positive.lifecycle_generations: BLE cancel mismatch")
        require(failures, first == ble_cancelled + 1,
                "positive.lifecycle_generations: first result mismatch")
        require(failures, second == first + 2,
                "positive.lifecycle_generations: second result mismatch")


def verify_fixture(run: dict[str, Any], failures: list[str]) -> None:
    fixture = child(run, "external_ble_fixture", failures, "positive.")
    exact(fixture, {
        "kind": "macos_corebluetooth",
        "label": BLE_LABEL,
        "executable_sha256": BLE_FIXTURE_SHA256,
        "host_wifi_control_calls": 0,
        "terminated": True,
    }, failures, "positive.external_ble_fixture.")
    states = fixture.get("states")
    require(failures, isinstance(states, list) and len(states) == 1,
            "positive.external_ble_fixture.states: one state expected")
    if isinstance(states, list) and len(states) == 1 and isinstance(states[0], dict):
        exact(states[0], {
            "schema": "leshy.hil.macos_ble_name_fixture.v1",
            "state": "advertising",
            "label": BLE_LABEL,
        }, failures, "positive.external_ble_fixture.states[0].")


def verify_result_navigation(run: dict[str, Any],
                             failures: list[str]) -> None:
    navigation = run.get("result_navigation")
    require(failures, isinstance(navigation, list) and len(navigation) == 2,
            "positive.result_navigation: exact evidence list/detail proof "
            "required")
    first_result = run.get("result_first")
    if (not isinstance(navigation, list) or len(navigation) != 2 or
            not isinstance(first_result, dict)):
        return
    if not all(isinstance(item, dict) for item in navigation):
        failures.append("positive.result_navigation: state objects required")
        return
    immutable_fields = (
        "generation", "load_status", "outcome", "evidence_incomplete",
        "finding_count", "finding_mask", "finding_selection",
        "source_frames_observed", "frames_available", "frames_inspected",
        "ble_records", "ble_worker_generation", "ble_worker_status",
        "ble_worker_valid", "ble_capacity_drop_requested",
        "ble_capacity_drop_injected", "ble_scan_dropped",
        "ble_retention_dropped",
        "runtime_owner", "lease_mask",
    )
    for index, (state, view) in enumerate(zip(
            navigation, ("evidence_list", "evidence_detail"))):
        prefix = f"positive.result_navigation[{index}]."
        exact(state, {
            "schema": STATE_SCHEMA,
            "kind": "state",
            "capture_state": "result",
            "view": view,
        }, failures, prefix)
        for field in immutable_fields:
            require(failures, state.get(field) == first_result.get(field),
                    f"{prefix}{field}: first-result binding mismatch")
    evidence_selection = navigation[0].get("evidence_selection")
    require(failures, integer(evidence_selection, 0) and
            navigation[1].get("evidence_selection") == evidence_selection,
            "positive.result_navigation: evidence selection continuity "
            "invalid")


def verify_cleanup(run: dict[str, Any], failures: list[str]) -> None:
    for name in ("cleanup_before", "cleanup_after"):
        cleanup = child(run, name, failures, "positive.")
        exact(cleanup, {"attempted": True, "complete": True, "errors": []},
              failures, f"positive.{name}.")
        final = child(cleanup, "final_state", failures, f"positive.{name}.")
        exact(final, {
            "schema": "leshy.ui.v1",
            "kind": "state",
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "safety_state": "armed",
            "safety_latched": False,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_source_active": False,
        }, failures, f"positive.{name}.final_state.")


def validate_png(path: Path, failures: list[str], label: str) -> None:
    try:
        data = path.read_bytes()
    except OSError as error:
        failures.append(f"{label}: {error}")
        return
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        failures.append(f"{label}: invalid PNG signature/header")
        return
    try:
        chunk_size = struct.unpack_from(">I", data, 8)[0]
        chunk_type = data[12:16]
        width, height, depth, color, compression, filtering, interlace = (
            struct.unpack_from(">IIBBBBB", data, 16)
        )
    except struct.error as error:
        failures.append(f"{label}: invalid IHDR: {error}")
        return
    require(failures, chunk_size == 13 and chunk_type == b"IHDR",
            f"{label}: first chunk is not a canonical IHDR")
    require(failures, (width, height) == (WIDTH, HEIGHT),
            f"{label}: dimensions {width}x{height} != {WIDTH}x{HEIGHT}")
    require(failures,
            (depth, color, compression, filtering, interlace) ==
            (8, 2, 0, 0, 0),
            f"{label}: unsupported PNG encoding")
    require(failures, b"IEND" in data[29:], f"{label}: IEND missing")


def changed_pixels(before: bytes, after: bytes, live_top: int,
                   live_bottom: int) -> dict[str, int]:
    if len(before) != FRAME_BYTES or len(after) != FRAME_BYTES:
        raise ValueError("complete 240x320 RGB565 frames required")
    live = 0
    static = 0
    for y in range(HEIGHT):
        row = y * WIDTH * 2
        for offset in range(row, row + WIDTH * 2, 2):
            if before[offset:offset + 2] == after[offset:offset + 2]:
                continue
            if live_top <= y < live_bottom:
                live += 1
            else:
                static += 1
    return {"live_changed_pixels": live, "static_changed_pixels": static}


def verify_screens(run: dict[str, Any], bundle: Path,
                   entries: dict[str, str], failures: list[str]) -> None:
    screens = child(run, "screens", failures, "positive.")
    for key, stem in SCREEN_FILES.items():
        screen = child(screens, key, failures, "positive.screens.")
        begin = child(screen, "frame_begin", failures,
                      f"positive.screens.{key}.")
        end = child(screen, "frame_end", failures,
                    f"positive.screens.{key}.")
        exact(begin, {
            "schema": "leshy.ui.capture.v1", "kind": "frame_begin",
            "format": "rgb565be", "width": WIDTH, "height": HEIGHT,
            "bytes": FRAME_BYTES,
        }, failures, f"positive.screens.{key}.frame_begin.")
        exact(end, {
            "schema": "leshy.ui.capture.v1", "kind": "frame_end",
            "bytes": FRAME_BYTES, "revision": begin.get("revision"),
        }, failures, f"positive.screens.{key}.frame_end.")
        state = child(screen, "state", failures,
                      f"positive.screens.{key}.")
        exact(state, {
            "schema": "leshy.ui.v1", "kind": "state",
            "page": "survey", "wifi_product_view": "airspace_guard",
            "runtime_owner": "wifi", "lease_mask": 15,
            "revision": begin.get("revision"),
        }, failures, f"positive.screens.{key}.state.")
        attempts = screen.get("transport_attempts")
        retries = screen.get("transport_transient_retries")
        errors = screen.get("transport_transient_errors")
        require(failures, integer(attempts, 1) and attempts <= 2 and
                retries == attempts - 1 and isinstance(errors, list) and
                len(errors) == retries,
                f"positive.screens.{key}: transport accounting invalid")
        json_name = f"frames/{stem}.json"
        png_name = f"frames/{stem}.png"
        rgb_name = f"frames/{stem}.rgb565"
        require(failures, entries.get(png_name) == screen.get("png_sha256"),
                f"positive.screens.{key}: PNG binding mismatch")
        require(failures, entries.get(rgb_name) == screen.get("rgb565_sha256"),
                f"positive.screens.{key}: RGB565 binding mismatch")
        require(failures, json_name in entries,
                f"positive.screens.{key}: JSON artifact missing")
        rgb_path = bundle / rgb_name
        if rgb_path.is_file():
            require(failures, rgb_path.stat().st_size == FRAME_BYTES,
                    f"positive.screens.{key}: RGB565 size mismatch")
        png_path = bundle / png_name
        if png_path.is_file():
            validate_png(png_path, failures, f"positive.{png_name}")
        json_path = bundle / json_name
        if json_path.is_file():
            captured = load_json(json_path, failures, f"positive.{json_name}")
            require(failures, captured == screen,
                    f"positive.screens.{key}: JSON/run mismatch")


def verify_pixel_proof(run: dict[str, Any], bundle: Path,
                       failures: list[str]) -> None:
    pixel = child(run, "pixel_proof", failures, "positive.")
    for source, (top, bottom, before_key, after_key) in LIVE_REGIONS.items():
        proof = child(pixel, source, failures, "positive.pixel_proof.")
        before_stem = SCREEN_FILES[before_key]
        after_stem = SCREEN_FILES[after_key]
        try:
            before = (bundle / f"frames/{before_stem}.rgb565").read_bytes()
            after = (bundle / f"frames/{after_stem}.rgb565").read_bytes()
            computed = changed_pixels(before, after, top, bottom)
        except (OSError, ValueError) as error:
            failures.append(f"positive.pixel_proof.{source}: {error}")
            continue
        exact(proof, computed, failures, f"positive.pixel_proof.{source}.")
        require(failures, computed["live_changed_pixels"] > 0,
                f"positive.pixel_proof.{source}: no live change")
        require(failures, computed["static_changed_pixels"] == 0,
                f"positive.pixel_proof.{source}: static pixels changed")


def verify_positive(run: dict[str, Any], bundle: Path,
                    entries: dict[str, str], failures: list[str],
                    expectations: dict[str, Any],
                    corrective: dict[str, Any]) -> None:
    exact(run, {
        "schema": RUN_SCHEMA,
        "passed": True,
        "gate_eligible": True,
        "failures": [],
        "expected_cid": expectations.get("expected_cid"),
    }, failures, "positive.")
    exact(run, {
        "run_id": expectations.get("run_id"),
        "runner_source_sha256": expectations.get("runner_source_sha256"),
    }, failures, "positive.")
    require(failures, isinstance(run.get("run_id"), str) and
            SESSION_ID.fullmatch(run["run_id"]) is not None,
            "positive.run_id: lowercase 32-hex identifier expected")
    if corrective:
        require(failures,
                run.get("runner_source_sha256") ==
                corrective.get("runner_source_sha256"),
                "positive.runner_source_sha256: corrective binding mismatch")
    candidate = verify_candidate(
        run, bundle, entries, failures, expectations, corrective)
    verify_boot(run, candidate, failures)
    verify_hil_session(run, candidate, failures)
    verify_recovery(run, failures)
    for name in ("wifi_running", "ble_running"):
        state = child(run, name, failures, "positive.")
        verify_running(state, name, failures)
    for name in ("wifi_cancelled", "ble_cancelled"):
        state = child(run, name, failures, "positive.")
        verify_stopped(state, name, failures)
    results: list[dict[str, Any]] = []
    capacity_losses: list[bool] = []
    for name in ("result_first", "result_second"):
        state = child(run, name, failures, "positive.")
        capacity_losses.append(verify_result(state, name, failures))
        results.append(state)
    exact(results[0], {
        "ble_capacity_drop_requested": False,
        "ble_capacity_drop_injected": False,
    }, failures,
          "positive.result_first.")
    exact(results[1], {
        "ble_capacity_drop_requested": True,
        "ble_capacity_drop_injected": True,
    }, failures,
          "positive.result_second.")
    require(failures, capacity_losses == [False, True],
            "positive.results: exact baseline then injected-capacity-loss "
            "lifecycles required")
    verify_exact_capacity_one(results[1], failures)
    conclusive = sum(
        state.get("ble_worker_status") == "complete" and
        state.get("ble_scan_dropped") == 0 and
        state.get("ble_retention_dropped") == 0 and
        state.get("source_frames_dropped") == 0 and
        state.get("evidence_incomplete") is False
        for state in results
    )
    require(failures, conclusive >= 1,
            "positive.results: at least one conclusive zero-drop lifecycle required")
    require(failures, any(integer(state.get("frames_available"), 0) and
                          state["frames_available"] > 64 for state in results),
            "positive.results: no complete merged report above legacy 64-record budget")
    require(failures, results[0].get("outcome") == "finding" and
            results[0].get("view") == "finding",
            "positive.result_first: deterministic finding expected")
    verify_lifecycle_generations(run, failures)
    verify_result_navigation(run, failures)
    verify_capacity_injection(run, failures)
    verify_fixture(run, failures)
    input_state = child(run, "input", failures, "positive.")
    exact(input_state, {
        "schema": "leshy.input.frontend.v1", "kind": "state",
        "status": "ready", "task_started": True, "read_errors": 0,
        "queue_drops": 0, "hot_path_serial_writes": 0,
    }, failures, "positive.input.")
    safe = child(run, "safe_outputs", failures, "positive.")
    exact(safe, {
        "schema": "leshy.hardware.safe-outputs.v1", "kind": "state",
        "buzzer_inactive": True, "buzzer_level": "low",
        "nrf_ce_inactive": True, "software_quiesce_complete": True,
    }, failures, "positive.safe_outputs.")
    metrics_first = child(run, "metrics_after_first", failures, "positive.")
    metrics_second = child(run, "metrics_after_second", failures, "positive.")
    for field in ("heap_total", "heap_free"):
        require(failures, integer(metrics_first.get(field), 1) and
                metrics_first.get(field) == metrics_second.get(field),
                f"positive.metrics.{field}: post-warmup drift")
    scope = child(run, "scope", failures, "positive.")
    exact(scope, {
        "single_flash": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "passive_receive_only": True,
        "deterministic_ble_fixture": True,
        "host_wifi_control_calls": 0,
        "application_wifi_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "wifi_cancel_cleanup_proved": True,
        "ble_cancel_cleanup_proved": True,
        "two_complete_guard_lifecycles": True,
        "static_pixels_unchanged_during_live_refresh": True,
        "zero_heap_drift_after_warmup": True,
        "storage_write_authorized": False,
        "elevated_noise_is_low_confidence_indicator": True,
        "absence_of_noise_finding_is_not_absence_of_interference": True,
    }, failures, "positive.scope.")
    require(failures, scope.get("conclusive_guard_lifecycles") == conclusive,
            "positive.scope.conclusive_guard_lifecycles: result mismatch")
    verify_cleanup(run, failures)
    verify_screens(run, bundle, entries, failures)
    verify_pixel_proof(run, bundle, failures)


def verify_negative_dev239(value: dict[str, Any], failures: list[str]) -> None:
    exact(value, {
        "schema": NEGATIVE_SCHEMA,
        "status": "failed",
        "gate_eligible": False,
        "candidate_rejected": True,
        "board": BOARD,
        "port": PORT,
        "rom_mac": ROM_MAC,
        "expected_cid": CID,
    }, failures, "negative.")
    candidate = child(value, "candidate", failures, "negative.")
    exact(candidate, {
        "version": FAILED_VERSION,
        "source_commit": FAILED_SOURCE,
        "firmware_sha256": FAILED_FIRMWARE,
        "app_elf_sha256": FAILED_APP,
        "fresh_delta_run_sha256": FAILED_DELTA_RUN,
        "failed_full_run_sha256": FAILED_FULL_RUN,
        "failed_full_artifact_index_sha256": FAILED_FULL_INDEX,
    }, failures, "negative.candidate.")
    failure = child(value, "failure", failures, "negative.")
    exact(failure, {
        "first_capture_state": "failed",
        "first_load_status": "invalid_report",
        "first_ble_worker_status": "complete",
        "first_ble_worker_valid": True,
        "first_ble_scan_status": "valid",
        "first_ble_retention_retained": 49,
        "first_ble_retention_dropped": 0,
        "first_findings_dropped": 0,
        "second_capture_state": "result",
        "second_load_status": "ready",
        "second_ble_records": 53,
        "second_findings_dropped": 0,
        "root_cause": ROOT_CAUSE,
    }, failures, "negative.failure.")
    cleanup = child(value, "post_failure_cleanup", failures, "negative.")
    exact(cleanup, {
        "complete": True,
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "safety_state": "armed",
        "safety_latched": False,
    }, failures, "negative.post_failure_cleanup.")
    cadence = child(value, "cadence", failures, "negative.")
    exact(cadence, {"accepted_deltas_unchanged": "9/15"}, failures,
          "negative.cadence.")
    corrective = child(value, "corrective_candidate", failures, "negative.")
    exact(corrective, {
        "version": FAILED_241_VERSION,
        "source_commit": FAILED_241_SOURCE,
        "firmware_sha256": FAILED_241_FIRMWARE,
        "app_elf_sha256": FAILED_241_APP,
        "runner_source_sha256": FAILED_241_RUNNER,
        "inspection_budget_records": 128,
        "source_local_wifi_records": 64,
        "source_local_ble_records": 64,
    }, failures, "negative.corrective_candidate.")


def verify_negative_dev241(value: dict[str, Any],
                           failures: list[str]) -> dict[str, Any]:
    exact(value, {
        "schema": NEGATIVE_SCHEMA,
        "status": "failed",
        "gate_eligible": False,
        "candidate_rejected": True,
        "board": BOARD,
        "port": PORT,
        "rom_mac": ROM_MAC,
        "expected_cid": CID,
    }, failures, "negative_dev241.")
    candidate = child(value, "candidate", failures, "negative_dev241.")
    exact(candidate, {
        "version": FAILED_241_VERSION,
        "source_commit": FAILED_241_SOURCE,
        "firmware_sha256": FAILED_241_FIRMWARE,
        "app_elf_sha256": FAILED_241_APP,
        "failed_full_run_sha256": FAILED_241_FULL_RUN,
        "failed_full_artifact_index_sha256": FAILED_241_FULL_INDEX,
    }, failures, "negative_dev241.candidate.")
    failure = child(value, "failure", failures, "negative_dev241.")
    exact(failure, {
        "first_capture_state": "result",
        "first_load_status": "ready",
        "first_ble_worker_status": "complete",
        "first_ble_worker_valid": True,
        "first_ble_scan_status": "valid",
        "first_ble_scan_dropped": 0,
        "first_ble_retention_retained": 54,
        "first_ble_retention_dropped": 0,
        "first_frames_available": 74,
        "first_findings_dropped": 0,
        "second_capture_state": "failed",
        "second_load_status": "ready",
        "second_ble_worker_status": "incomplete_evidence",
        "second_ble_worker_valid": False,
        "second_ble_scan_status": "valid",
        "second_ble_scan_observed": 1296,
        "second_ble_scan_reported": 1296,
        "second_ble_scan_read": 1296,
        "second_ble_scan_accepted": 1295,
        "second_ble_scan_rejected": 0,
        "second_ble_scan_dropped": 1,
        "second_ble_retention_observed": 1296,
        "second_ble_retention_valid": 1296,
        "second_ble_retention_retained": 64,
        "second_ble_retention_dropped": 1,
        "second_ble_retention_malformed": 0,
        "second_evidence_incomplete": True,
        "second_outcome": "inconclusive",
        "second_source_frames_observed": 0,
        "second_source_frames_dropped": 0,
        "second_frames_available": 0,
        "second_ble_records": 0,
        "second_findings_dropped": 0,
        "root_cause": ROOT_CAUSE_241,
    }, failures, "negative_dev241.failure.")
    cleanup = child(value, "post_failure_cleanup", failures,
                    "negative_dev241.")
    exact(cleanup, {
        "complete": True,
        "page": "home",
        "runtime_owner": "none",
        "lease_mask": 0,
        "safety_state": "armed",
        "safety_latched": False,
    }, failures, "negative_dev241.post_failure_cleanup.")
    cadence = child(value, "cadence", failures, "negative_dev241.")
    exact(cadence, {"accepted_deltas_unchanged": "9/15"}, failures,
          "negative_dev241.cadence.")
    return child(value, "corrective_candidate", failures, "negative_dev241.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expectations", type=Path,
                        default=DEFAULT_EXPECTATIONS,
                        help="reviewed exact dev.242 acceptance hash pins")
    parser.add_argument("--positive", type=Path, default=DEFAULT_POSITIVE,
                        help="passing full-run bundle directory or run.json")
    parser.add_argument("--negative-dev239", type=Path,
                        default=DEFAULT_NEGATIVE_DEV239,
                        help="retained compact dev.239 negative evidence JSON")
    parser.add_argument("--negative-dev241", type=Path,
                        default=DEFAULT_NEGATIVE_DEV241,
                        help="retained compact dev.241 negative evidence JSON")
    parser.add_argument("--expected-version", default=VERSION)
    parser.add_argument("--expected-cid", default=CID)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-firmware-sha256")
    parser.add_argument("--expected-app-elf-sha256")
    return parser.parse_args(argv)


def check(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    expectations = load_json(args.expectations, failures, "expectations")
    if expectations:
        verify_expectations(expectations, failures)
        exact(expectations, {
            "version": args.expected_version,
            "expected_cid": args.expected_cid,
        }, failures, "expectations.")
        optional_pins = {
            "source_commit": args.expected_source_commit,
            "firmware_sha256": args.expected_firmware_sha256,
            "app_elf_sha256": args.expected_app_elf_sha256,
        }
        for field, value in optional_pins.items():
            if value is not None:
                require(failures, expectations.get(field) == value,
                        f"expectations.{field}: CLI pin mismatch")
        try:
            source_runner_sha256 = committed_runner_sha256(
                expectations["source_commit"]
            )
        except OSError as error:
            failures.append(f"source-commit runner: {error}")
        else:
            require(failures,
                    expectations.get("runner_source_sha256") ==
                    source_runner_sha256,
                    "expectations.runner_source_sha256: source-commit runner "
                    "binding mismatch")
    bundle, run_path = resolve_positive(args.positive, failures)
    entries = verify_manifest(bundle, failures) if bundle.is_dir() else {}
    run = load_json(run_path, failures, "positive.run")
    if expectations:
        if run_path.is_file():
            require(failures,
                    digest(run_path) == expectations.get("positive_run_sha256"),
                    "positive.run: expectation hash mismatch")
        manifest = bundle / "artifacts.sha256"
        if manifest.is_file():
            require(failures,
                    digest(manifest) == expectations.get(
                        "positive_artifact_index_sha256"),
                    "positive.artifacts.sha256: expectation hash mismatch")
    negative_dev239 = load_json(
        args.negative_dev239, failures, "negative_dev239")
    negative_dev241 = load_json(
        args.negative_dev241, failures, "negative_dev241")
    if negative_dev239:
        verify_negative_dev239(negative_dev239, failures)
    corrective = (
        verify_negative_dev241(negative_dev241, failures)
        if negative_dev241 else {}
    )
    if run and expectations:
        verify_positive(
            run, bundle, entries, failures, expectations, corrective)
    return failures


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = check(args)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": "leshy.airspace_guard_hil.acceptance.v1",
        "status": "pass",
        "expectations": str(args.expectations),
        "positive": str(args.positive),
        "negative_dev239": str(args.negative_dev239),
        "negative_dev241": str(args.negative_dev241),
        "expected_version": args.expected_version,
        "expected_cid": args.expected_cid,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
