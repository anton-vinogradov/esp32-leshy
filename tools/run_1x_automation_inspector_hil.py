#!/usr/bin/env python3
"""One-flash physical Automation Inspector delta on board-01.

The runner writes only two bounded .lhau files below one exact
/leshy-hil/<run-id> directory on the explicitly selected SD card. It drives the
public Lab UI in EN and RU, proves stable TFT frames and zero Action/HID/resource
output, removes the fixture, restores the user's language and ends HIL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import action, artifact_manifest, capture, query
from run_1x_ui_typography_hil import normalize_home


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "leshy.automation_inspector_hil.run.v1"
STATE_SCHEMA = "leshy.automation.inspector.state.v1"
FIXTURE_SCHEMA = "leshy.automation.inspector.fixture.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
UI_SCHEMA = "leshy.ui.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_PORTS = {"/dev/cu.usbmodem1101"}


def require(state: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def wait_state(
    device: PassiveSerial, predicate: Callable[[dict[str, Any]], bool],
    label: str, timeout: float = 15.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, b"automation.inspector.state",
                     STATE_SCHEMA, "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{label}: {last!r}")


def set_language(device: PassiveSerial, language: str) -> dict[str, Any]:
    state = query(device, f"ui.language {language}".encode("ascii"),
                  UI_SCHEMA, "state")
    require(state, f"language {language}", language=language)
    return state


def enter_lab(device: PassiveSerial,
              trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(7):
        state = action(device, "down")
        trace.append(state)
    require(state, "focus Lab", page="home", selection=7,
            selected_id="lab", runtime_owner="none", lease_mask=0)
    state = action(device, "right")
    trace.append(state)
    require(state, "open Lab", page="lab", runtime_owner="lab",
            lease_mask=1)
    return state


def inspect_selected(
    device: PassiveSerial, expected_name: str, expected_parse: str,
    expected_policy: str, expected_trust: str,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    opened = action(device, "right")
    trace.append(opened)
    require(opened, f"open {expected_name}", page="automation_inspector",
            runtime_owner="lab", lease_mask=1)
    state = wait_state(
        device,
        lambda value: value.get("inspection_pending") is False and
        value.get("source_name") == expected_name,
        f"inspect {expected_name}")
    require(
        state, f"{expected_name} summary", status="valid",
        page="automation_inspector", source_status="inspected",
        source_name=expected_name, parse_status=expected_parse,
        policy_status=expected_policy, trust_status=expected_trust,
        execution_eligible=False, actions_invoked=0,
        hid_reports_emitted=0, resources_acquired=0,
        zero_action_hid_resource_output=True, fixture_active=True,
        fixture_cleanup_required=True, runtime_owner="lab", lease_mask=1,
        product_namespace_written=False, rf_transmit_attempts=0,
        response_complete=True)
    return state


def stable_capture_pair(
    device: PassiveSerial, frames: Path, stem: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    first = capture(device, frames, f"{stem}-a")
    time.sleep(0.25)
    second = capture(device, frames, f"{stem}-b")
    if first.get("rgb565_sha256") != second.get("rgb565_sha256"):
        raise RuntimeError(
            f"{stem}: static Inspector frame changed: "
            f"{first.get('rgb565_sha256')} != "
            f"{second.get('rgb565_sha256')}")
    if first.get("state", {}).get("revision") != \
            second.get("state", {}).get("revision"):
        raise RuntimeError(f"{stem}: UI revision changed between captures")
    return first, second


def return_home(device: PassiveSerial,
                trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = query(device, b"ui.state", UI_SCHEMA, "state")
    for _ in range(8):
        if (state.get("page") == "home" and
                state.get("runtime_owner") == "none" and
                state.get("lease_mask") == 0):
            return state
        state = action(device, "back")
        trace.append(state)
    raise RuntimeError(f"cannot return to clean Home: {state!r}")


def fixture_command(
    device: PassiveSerial, operation: str, expected_cid: str, run_id: str,
) -> dict[str, Any]:
    command = (
        f"automation.inspector-fixture {operation} disposable-write "
        f"{expected_cid} {run_id}"
    ).encode("ascii")
    return query(device, command, FIXTURE_SCHEMA, operation, timeout=25.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--skip-flash", action="store_true",
        help="reuse an already installed exact candidate after a runner-only failure")
    args = parser.parse_args()
    if args.port != BOARD_PORT or args.port in FORBIDDEN_PORTS:
        parser.error(f"exact board-01 port required: {BOARD_PORT}")
    if (len(args.expected_cid) != 32 or
            any(value not in "0123456789ABCDEF"
                for value in args.expected_cid)):
        parser.error("expected CID must be exactly 32 uppercase hex digits")
    if len(args.source_commit) != 40:
        parser.error("source commit must be a full hash")
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    runner_hash = sha256_file(Path(__file__))
    trace: list[dict[str, Any]] = []
    reports: dict[str, Any] = {}
    captures: dict[str, Any] = {}
    failures: list[str] = []
    cleanup: dict[str, Any] = {
        "attempted": False, "complete": False, "errors": []}
    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "passed": False,
        "failures": [],
        "checkpoint": "automation-inspector-physical-v1",
        "run_id": run_id,
        "board": "board-01",
        "port": args.port,
        "expected_cid": args.expected_cid,
        "source_commit": args.source_commit,
        "runner_source_sha256": runner_hash,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
        },
        "policy": {
            "fixture_scope": "/leshy-hil/<run-id>",
            "product_namespace_written": False,
            "radio_tx_commands": 0,
            "wifi_host_touched": False,
            "forbidden_ports_touched": [],
            "full_hil": False,
            "delta_only": True,
        },
    }
    write_json(args.output / "run.json", record)

    device: PassiveSerial | None = None
    initial_language = ""
    hil_begun = False
    fixture_may_exist = False
    try:
        if not args.skip_flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics, "candidate", version=args.expected_version,
                app_elf_sha256=app_identity)
        reports["metrics"] = metrics
        home = normalize_home(device)
        require(home, "initial Home", page="home", runtime_owner="none",
                lease_mask=0)
        initial_language = str(home["language"])

        begun = query(
            device, f"hil.begin {run_id} {app_identity}".encode("ascii"),
            HIL_SCHEMA, "begun")
        require(begun, "HIL begin", status="begun", active=True,
                session_id=run_id)
        reports["hil_begin"] = begun
        hil_begun = True

        fixture = fixture_command(
            device, "begin", args.expected_cid, run_id)
        fixture_may_exist = bool(
            fixture.get("cleanup_required") or fixture.get("fixture_active"))
        require(
            fixture, "fixture begin", status="complete", complete=True,
            fingerprint_matched=True, run_id=run_id,
            scratch_preexisting=False, fixture_active=True,
            cleanup_required=True, prepared=True, malformed_written=True,
            unsigned_written=True, file_barriers_complete=True,
            directory_barrier_complete=True, exact_entries=True,
            bytes_written=159, write_calls=2, file_syncs=2,
            directory_syncs=1, identity_cleanup=True,
            filesystem_cleanup=True, gpio21_stable_high=True,
            owned_after=0, product_namespace_written=False,
            format_allowed=False, rf_transmit_attempts=0,
            action_invocations=0, hid_reports=0)
        reports["fixture_begin"] = fixture

        set_language(device, "en")
        enter_lab(device, trace)
        catalog = wait_state(
            device,
            lambda value: value.get("catalog_status") == "ready" and
            value.get("catalog_size") == 2,
            "EN catalog")
        require(catalog, "EN catalog", selected_name="malformed.lhau",
                catalog_selection=0, catalog_omitted=0, fixture_active=True)
        reports["catalog_en"] = catalog

        malformed_en = inspect_selected(
            device, "malformed.lhau", "too_small", "invalid_step_count",
            "verifier_unavailable", trace)
        captures["malformed_en"] = stable_capture_pair(
            device, frames, "malformed-en")
        reports["malformed_en"] = malformed_en

        trace.append(action(device, "back"))
        trace.append(action(device, "down"))
        selected_unsigned = wait_state(
            device,
            lambda value: value.get("selected_name") == "unsigned.lhau" and
            value.get("catalog_selection") == 1,
            "select unsigned")
        reports["unsigned_selected_en"] = selected_unsigned
        unsigned_en = inspect_selected(
            device, "unsigned.lhau", "parsed", "ready",
            "missing_signature", trace)
        captures["unsigned_en"] = stable_capture_pair(
            device, frames, "unsigned-en")
        reports["unsigned_en"] = unsigned_en

        set_language(device, "ru")
        unsigned_ru = wait_state(
            device,
            lambda value: value.get("source_name") == "unsigned.lhau" and
            value.get("language") == "ru",
            "RU unsigned")
        captures["unsigned_ru"] = stable_capture_pair(
            device, frames, "unsigned-ru")
        reports["unsigned_ru"] = unsigned_ru

        trace.append(action(device, "back"))
        trace.append(action(device, "up"))
        malformed_ru = inspect_selected(
            device, "malformed.lhau", "too_small", "invalid_step_count",
            "verifier_unavailable", trace)
        require(malformed_ru, "RU malformed language", language="ru")
        captures["malformed_ru"] = stable_capture_pair(
            device, frames, "malformed-ru")
        reports["malformed_ru"] = malformed_ru

        reports["home_before_cleanup"] = return_home(device, trace)
        removed = fixture_command(
            device, "cleanup", args.expected_cid, run_id)
        fixture_may_exist = not bool(removed.get("cleanup_complete"))
        require(
            removed, "fixture cleanup", status="complete", complete=True,
            fingerprint_matched=True, run_id=run_id,
            fixture_active=False, cleanup_required=False,
            cleanup_complete=True, files_removed=2,
            identity_cleanup=True, filesystem_cleanup=True,
            gpio21_stable_high=True, owned_after=0,
            product_namespace_written=False, rf_transmit_attempts=0,
            action_invocations=0, hid_reports=0)
        reports["fixture_cleanup"] = removed

        final_inspector = query(
            device, b"automation.inspector.state", STATE_SCHEMA, "state")
        require(
            final_inspector, "fixture reset", fixture_active=False,
            fixture_cleanup_required=False,
            package_root="/leshy/automation/v1",
            zero_action_hid_resource_output=True,
            product_namespace_written=False, rf_transmit_attempts=0)
        reports["inspector_final"] = final_inspector

        if initial_language != "ru":
            set_language(device, initial_language)
        final = query(device, b"ui.state", UI_SCHEMA, "state")
        require(final, "final Home", page="home", language=initial_language,
                runtime_owner="none", lease_mask=0, safety_latched=False)
        reports["final"] = final
        safe = query(device, b"hardware.safe-outputs",
                     "leshy.hardware.safe-outputs.v1", "state")
        require(safe, "safe outputs", buzzer_inactive=True,
                nrf_ce_inactive=True, software_quiesce_complete=True)
        reports["safe_outputs"] = safe
        inputs = query(device, b"input.state",
                       "leshy.input.frontend.v1", "state")
        require(inputs, "inputs", status="ready", read_errors=0,
                queue_drops=0)
        reports["input"] = inputs
        ended = query(
            device, f"hil.end {run_id}".encode("ascii"),
            HIL_SCHEMA, "ended")
        require(ended, "HIL end", status="ended", active=False,
                session_id=run_id)
        reports["hil_end"] = ended
        hil_begun = False
        cleanup = {
            "attempted": True,
            "complete": True,
            "fixture_removed": True,
            "language_restored": True,
            "hil_ended": True,
            "final_home": True,
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
                if fixture_may_exist:
                    try:
                        removed = fixture_command(
                            device, "cleanup", args.expected_cid, run_id)
                        reports["fixture_cleanup_best_effort"] = removed
                        fixture_may_exist = not bool(
                            removed.get("cleanup_complete"))
                    except Exception as error:
                        cleanup["errors"].append(
                            f"fixture: {type(error).__name__}: {error}")
                if initial_language:
                    try:
                        set_language(device, initial_language)
                        cleanup["language_restored"] = True
                    except Exception as error:
                        cleanup["errors"].append(
                            f"language: {type(error).__name__}: {error}")
                if hil_begun and not fixture_may_exist:
                    try:
                        ended = query(
                            device, f"hil.end {run_id}".encode("ascii"),
                            HIL_SCHEMA, "ended")
                        reports["hil_end_best_effort"] = ended
                        hil_begun = False
                    except Exception as error:
                        cleanup["errors"].append(
                            f"hil: {type(error).__name__}: {error}")
                cleanup["fixture_removed"] = not fixture_may_exist
                cleanup["hil_ended"] = not hil_begun
                cleanup["complete"] = (
                    not fixture_may_exist and not hil_begun and
                    cleanup.get("language_restored") is True and
                    cleanup.get("final_home") is True and
                    cleanup["errors"] == [])
            device.close()

    record.update({
        "status": "pass" if not failures and cleanup.get("complete") else
                  "failed",
        "passed": not failures and cleanup.get("complete") is True,
        "failures": failures,
        "initial_language": initial_language,
        "reports": reports,
        "trace": trace,
        "captures": captures,
        "cleanup": cleanup,
        "flash_count": 0 if args.skip_flash else 1,
        "installed_candidate_reused": args.skip_flash,
        "hardware_reset_count": 0,
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
