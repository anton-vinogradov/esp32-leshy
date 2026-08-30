#!/usr/bin/env python3
"""Focused physical delta for the public-only Automation trust UI.

The runner never confirms an enrollment or revocation. It proves the exact
candidate, owner-visible EN/RU list, read-only fixed-path import review/failure,
touch selection, zero outputs and unchanged trust-store generation/count. A
temporary Device Lock credential lives only in the existing isolated HIL NVS
namespace and is scrubbed before completion.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_device_lock_hil import LOCK_SCHEMA, device_lock_page, home_device
from run_1x_device_lock_persistence_hil import (
    enter_pin,
    ephemeral_pin,
    fixture_command as device_lock_fixture_command,
    wait_lock_state,
    wipe_pin,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import action, artifact_manifest, capture, query
from run_1x_ui_typography_hil import normalize_home


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = "leshy.automation_trust_ui_hil.run.v1"
TRUST_SCHEMA = "leshy.automation.trust.state.v1"
HIL_SCHEMA = "leshy.hil.session.v1"
UI_SCHEMA = "leshy.ui.v1"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_PORTS = {"/dev/cu.usbmodem1101"}
HOME_ROW_Y = (89, 140, 191, 242)


def require(record: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: record.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def trust_state(device: PassiveSerial) -> dict[str, Any]:
    return query(device, b"automation.trust.state", TRUST_SCHEMA, "state")


def set_language(device: PassiveSerial, language: str) -> dict[str, Any]:
    state = query(device, f"ui.language {language}".encode("ascii"),
                  UI_SCHEMA, "state")
    require(state, f"language {language}", language=language)
    return state


def return_home(device: PassiveSerial,
                trace: list[dict[str, Any]]) -> dict[str, Any]:
    current = query(device, b"ui.state", UI_SCHEMA, "state")
    for _ in range(12):
        if (current.get("page") == "home" and
                current.get("runtime_owner") == "none" and
                current.get("lease_mask") == 0):
            return current
        current = action(device, "left")
        trace.append(current)
    raise RuntimeError(f"cannot return clean Home: {current!r}")


def enter_trust_page(device: PassiveSerial,
                     trace: list[dict[str, Any]]) -> dict[str, Any]:
    current = home_device(device)
    current = action(device, "right")
    trace.append(current)
    require(current, "open Device", page="device", device_selection=0)
    for expected in range(1, 8):
        current = action(device, "down")
        trace.append(current)
        require(current, f"Device item {expected}", page="device",
                device_selection=expected)
    current = action(device, "right")
    trace.append(current)
    require(current, "open trust", page="automation_trust",
            device_selection=7, runtime_owner="device", lease_mask=0)
    return current


def focus_import(device: PassiveSerial,
                 trace: list[dict[str, Any]]) -> dict[str, Any]:
    current = trust_state(device)
    count = int(current.get("count", -1))
    if count < 0 or count > 4:
        raise RuntimeError(f"invalid trust count: {current!r}")
    selection = int(current.get("ui_selection", -1))
    if selection < 0 or selection > count:
        raise RuntimeError(f"invalid trust selection: {current!r}")
    for expected in range(selection + 1, count + 1):
        trace.append(action(device, "down"))
        current = trust_state(device)
        require(current, f"trust selection {expected}", ui_view="list",
                ui_selection=expected)
    require(current, "import focused", ui_view="list", ui_selection=count)
    return current


def stable_capture_pair(device: PassiveSerial, frames: Path,
                        stem: str) -> tuple[dict[str, Any], dict[str, Any]]:
    first = capture(device, frames, f"{stem}-a")
    time.sleep(0.2)
    second = capture(device, frames, f"{stem}-b")
    if first.get("rgb565_sha256") != second.get("rgb565_sha256"):
        raise RuntimeError(f"{stem}: static frame changed")
    first_state = first.get("state", {})
    second_state = second.get("state", {})
    if first_state.get("revision") != second_state.get("revision"):
        raise RuntimeError(f"{stem}: UI revision changed")
    return first, second


def verify_passive(state: dict[str, Any], label: str) -> None:
    require(
        state, label, ready=True, capacity=4,
        all_keys_p256_and_id_bound=True, public_keys_only=True,
        private_key_stored=False, execution_connected=False,
        action_invocations=0, hid_reports=0, rf_transmit_attempts=0,
        runtime_owner="device", lease_mask=0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--skip-flash", action="store_true")
    args = parser.parse_args()
    if args.port != BOARD_PORT or args.port in FORBIDDEN_PORTS:
        parser.error(f"exact board-01 port required: {BOARD_PORT}")
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
    lock_pin = ephemeral_pin()
    reports: dict[str, Any] = {}
    captures: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    failures: list[str] = []
    initial_language = ""
    hil_begun = False
    lock_fixture_started = False
    cleanup: dict[str, Any] = {
        "attempted": False, "complete": False, "errors": []}
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
        "policy": {
            "delta_only": True,
            "full_hil": False,
            "trust_mutation_confirmed": False,
            "trust_namespace_written": False,
            "sd_mount": "read_only",
            "sd_files_written": 0,
            "private_key_used_or_stored": False,
            "radio_tx_commands": 0,
            "wifi_host_touched": False,
            "forbidden_ports_touched": [],
        },
    }
    write_json(args.output / "run.json", record)

    device: PassiveSerial | None = None
    trust_before: dict[str, Any] = {}
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

        reports["device_lock_before"] = query(
            device, b"device-lock.state", LOCK_SCHEMA, "state")
        lock_fixture = device_lock_fixture_command(device, "begin")
        require(lock_fixture, "lock fixture begin", status="begun",
                active=True, product_namespace_written_or_erased=False)
        reports["device_lock_fixture_begin"] = lock_fixture
        lock_fixture_started = True
        home_device(device)
        device_lock_page(device)
        opened = action(device, "right")
        if opened.get("runtime_event") != "device_lock_editor_opened":
            raise RuntimeError("isolated Device Lock editor did not open")
        enter_pin(device, lock_pin)
        enter_pin(device, lock_pin)
        unlocked = wait_lock_state(
            device, lambda value: value.get("status") == "unlocked",
            "isolated trust UI unlock")
        require(unlocked, "lock fixture unlocked", protected_access=True,
                persistence_fixture_active=True)
        reports["device_lock_unlocked"] = unlocked
        return_home(device, trace)

        set_language(device, "en")
        enter_trust_page(device, trace)
        trust_before = focus_import(device, trace)
        verify_passive(trust_before, "trust list EN")
        require(trust_before, "trust list EN view", page="automation_trust",
                ui_view="list", ui_result="none",
                confirmation_open=False, confirmation_fresh=False)
        reports["trust_before"] = trust_before
        captures["list_en"] = stable_capture_pair(
            device, frames, "trust-list-en")

        set_language(device, "ru")
        captures["list_ru"] = stable_capture_pair(
            device, frames, "trust-list-ru")

        trace.append(action(device, "right"))
        first_import = trust_state(device)
        verify_passive(first_import, "first import")
        if first_import.get("ui_view") not in {"result", "import_review"}:
            raise RuntimeError(f"unexpected import terminal: {first_import!r}")
        if first_import.get("ui_view") == "result" and \
                first_import.get("ui_result") not in {
                    "bundle_read_failed", "bundle_invalid",
                    "storage_unavailable", "storage_busy"}:
            raise RuntimeError(f"unexpected import failure: {first_import!r}")
        reports["first_import"] = first_import
        captures["first_import_ru"] = stable_capture_pair(
            device, frames, "trust-import-ru")
        trace.append(action(device, "left"))
        focus_import(device, trace)

        count = int(trust_before["count"])
        first_visible = 0 if count < 4 else count - 3
        visible_row = count - first_visible
        touched = query(
            device, f"ui.touch 120 {HOME_ROW_Y[visible_row]}".encode("ascii"),
            "leshy.touch.frontend.v1", "state")
        require(touched, "touch import", last_changed=True,
                footer_interactive=False, touch_back_enabled=False)
        reports["touch_import"] = touched
        touch_import = trust_state(device)
        verify_passive(touch_import, "touch import state")
        if touch_import.get("ui_view") not in {"result", "import_review"}:
            raise RuntimeError(f"touch import did not open: {touch_import!r}")
        reports["touch_import_state"] = touch_import
        trace.append(action(device, "left"))

        trust_after = trust_state(device)
        verify_passive(trust_after, "trust after")
        require(trust_after, "trust unchanged", ui_view="list",
                count=trust_before["count"],
                generation=trust_before["generation"],
                confirmation_open=False, confirmation_fresh=False)
        reports["trust_after"] = trust_after
        reports["home_before_cleanup"] = return_home(device, trace)
        if initial_language != "ru":
            set_language(device, initial_language)

        lock_removed = device_lock_fixture_command(device, "cleanup")
        require(lock_removed, "lock fixture cleanup", status="cleaned",
                active=False, product_restored=True,
                product_namespace_written_or_erased=False)
        reports["device_lock_fixture_cleanup"] = lock_removed
        lock_fixture_started = False
        lock_after = query(device, b"device-lock.state", LOCK_SCHEMA, "state")
        for field in ("status", "failure", "failed_attempts",
                      "credential_generation"):
            if lock_after.get(field) != \
                    reports["device_lock_before"].get(field):
                raise RuntimeError(f"Device Lock product state changed: {field}")
        reports["device_lock_after"] = lock_after
        final = query(device, b"ui.state", UI_SCHEMA, "state")
        require(final, "final Home", page="home", language=initial_language,
                runtime_owner="none", lease_mask=0, safety_latched=False)
        reports["final"] = final
        safe = query(device, b"hardware.safe-outputs",
                     "leshy.hardware.safe-outputs.v1", "state")
        require(safe, "safe outputs", buzzer_inactive=True,
                nrf_ce_inactive=True, software_quiesce_complete=True)
        reports["safe_outputs"] = safe
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
            "device_lock_fixture_removed": True,
            "language_restored": True,
            "final_home": True,
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
                if initial_language:
                    try:
                        set_language(device, initial_language)
                        cleanup["language_restored"] = True
                    except Exception as error:
                        cleanup["errors"].append(
                            f"language: {type(error).__name__}: {error}")
                if lock_fixture_started:
                    try:
                        removed = device_lock_fixture_command(device, "cleanup")
                        reports["device_lock_cleanup_best_effort"] = removed
                        lock_fixture_started = not bool(
                            removed.get("product_restored"))
                    except Exception as error:
                        cleanup["errors"].append(
                            f"lock: {type(error).__name__}: {error}")
                if hil_begun and not lock_fixture_started:
                    try:
                        reports["hil_end_best_effort"] = query(
                            device, f"hil.end {run_id}".encode("ascii"),
                            HIL_SCHEMA, "ended")
                        hil_begun = False
                    except Exception as error:
                        cleanup["errors"].append(
                            f"hil: {type(error).__name__}: {error}")
                cleanup["device_lock_fixture_removed"] = \
                    not lock_fixture_started
                cleanup["hil_ended"] = not hil_begun
                cleanup["complete"] = (
                    not lock_fixture_started and not hil_begun and
                    cleanup.get("language_restored") is True and
                    cleanup.get("final_home") is True and
                    cleanup["errors"] == [])
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
