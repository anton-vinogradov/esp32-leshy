#!/usr/bin/env python3
"""Cheap fail-closed HIL smoke for every user-facing Home entry.

This is deliberately a navigation/lifecycle delta, not a feature acceptance
test.  Each enabled Home entry must open, keep the expected page, runtime owner
and lease for a bounded dwell, and return cleanly to Home.  Merely observing the
first ``ui.key`` acknowledgement is insufficient: a deferred worker failure may
otherwise bounce back to Home immediately after that acknowledgement.

The runner never selects a nested action, so it cannot explicitly start an
nRF24/CC1101 receiver, capture, active probe, connection, or transmit path.
Bluetooth's existing top-level passive Product Survey lifecycle is eager and
may legitimately exercise product storage.  This smoke retains its available
store-byte telemetry but does not claim to measure or prohibit all SD writes.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ble_nearby_entry_gate import BLE_ENTRY_STABILITY_SECONDS
from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_airspace_guard_hil import (
    action,
    begin_hil_session,
    candidate_verification_succeeded,
    end_hil_session,
    read_only_query,
    robust_cleanup,
)
from run_1x_device_lock_hil import LOCK_SCHEMA, device_lock_page, home_device
from run_1x_device_lock_persistence_hil import (
    enter_pin,
    ephemeral_pin,
    fixture_command,
    wait_lock_state,
    wipe_pin,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    artifact_manifest,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)


RUN_SCHEMA = "leshy.top_level_menu_smoke_hil.run.v1"
UI_SCHEMA = "leshy.ui.v1"
TARGETS_SCHEMA = "leshy.targets.product.v1"
HIL_SESSION_SCHEMA = "leshy.hil.session.v1"
BOARD_ID = "board-01"
BOARD_PORT = "/dev/cu.usbmodem2101"
FORBIDDEN_FIXTURE_PORT = "/dev/cu.usbmodem1101"
DEFAULT_DWELL_SECONDS = 1.25
DEFAULT_SAMPLE_SECONDS = 0.20
HOME_SETTLE_SECONDS = 0.25
BLE_MINIMUM_DWELL_SECONDS = BLE_ENTRY_STABILITY_SECONDS
BLE_MINIMUM_FREE_HEAP_BEFORE_BEGIN = 73000
BLE_MINIMUM_LARGEST_HEAP_BEFORE_BEGIN = 28000


@dataclass(frozen=True)
class MenuCase:
    index: int
    item_id: str
    page: str
    runtime_owner: str
    lease_mask: int
    extra: tuple[tuple[str, Any], ...] = ()
    minimum_dwell_seconds: float = DEFAULT_DWELL_SECONDS

    def expected(self) -> dict[str, Any]:
        return {
            "schema": UI_SCHEMA,
            "kind": "state",
            "page": self.page,
            "parent_page": "home",
            "selected_id": self.item_id,
            "selected_enabled": True,
            "runtime_owner": self.runtime_owner,
            "lease_mask": self.lease_mask,
            "safety_latched": False,
            **dict(self.extra),
        }


# This order is the user-visible AppCatalog order, not an independently curated
# subset.  Adding/removing/reordering a Home entry must update this executable
# contract; an unnoticed tenth entry therefore fails closed at the final Home
# boundary instead of silently receiving no smoke coverage.
MENU_CASES = (
    MenuCase(0, "wifi", "survey", "wifi", 15,
             (("wifi_product_view", "menu"),)),
    MenuCase(1, "ble", "survey", "ble", 15,
             (("ble_product_view", "devices"),),
             BLE_MINIMUM_DWELL_SECONDS),
    MenuCase(2, "spectrum24", "survey", "spectrum24", 9),
    MenuCase(3, "subghz", "survey", "subghz", 9),
    MenuCase(4, "capture", "capture", "capture", 11),
    MenuCase(5, "targets", "targets", "targets", 13),
    MenuCase(6, "library", "library", "library", 5),
    MenuCase(7, "lab", "lab", "lab", 1),
    MenuCase(8, "device", "device", "device", 1),
)


def selected_menu_cases(requested: list[str] | None) -> tuple[MenuCase, ...]:
    """Resolve a catalog-ordered strict delta or the complete default set."""
    if not requested:
        return MENU_CASES
    if len(requested) != len(set(requested)):
        raise ValueError("--only menu ids must be unique")
    known = {case.item_id: case for case in MENU_CASES}
    unknown = [item_id for item_id in requested if item_id not in known]
    if unknown:
        raise ValueError(f"unknown --only menu ids: {', '.join(unknown)}")
    requested_set = set(requested)
    return tuple(case for case in MENU_CASES
                 if case.item_id in requested_set)


def state_failures(case: MenuCase, state: dict[str, Any],
                   label: str) -> list[str]:
    """Return every page/owner/lease invariant violation for one sample."""
    failures = expect(state, case.expected(), label)
    if state.get("page") == "home":
        failures.append(f"{label}: immediate/deferred bounce to Home")
    if state.get("runtime_owner") == "none" or state.get("lease_mask") == 0:
        failures.append(f"{label}: foreground runtime/lease disappeared")
    return failures


def collect_stable_dwell(
        device: PassiveSerial, case: MenuCase, first: dict[str, Any],
        dwell_seconds: float, sample_seconds: float, *,
        query_state: Callable[[PassiveSerial], dict[str, Any]] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Sample through the entire dwell, including its terminal boundary."""
    if dwell_seconds <= 0 or sample_seconds <= 0:
        raise ValueError("dwell and sample intervals must be positive")
    if query_state is None:
        query_state = lambda serial: read_only_query(
            serial, b"ui.state", UI_SCHEMA, "state")

    started = monotonic()
    samples: list[dict[str, Any]] = []
    failures: list[str] = []

    def retain(state: dict[str, Any]) -> None:
        sample = dict(state)
        sample["host_dwell_offset_ms"] = round(
            max(0.0, monotonic() - started) * 1000.0, 3)
        sample["host_read_only"] = state is not first
        samples.append(sample)
        failures.extend(state_failures(
            case, state, f"{case.item_id}.dwell[{len(samples) - 1}]"))

    retain(first)
    deadline = started + dwell_seconds
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            # A read at/after the boundary closes the delayed-bounce window.
            retain(query_state(device))
            break
        sleep(min(sample_seconds, remaining))
        retain(query_state(device))
    return samples, failures


def effective_dwell_seconds(case: MenuCase, requested_seconds: float) -> float:
    """Never shorten a lifecycle below its asynchronous failure horizon."""
    if requested_seconds <= 0:
        raise ValueError("requested dwell must be positive")
    return max(requested_seconds, case.minimum_dwell_seconds)


def ble_begin_evidence_failure(samples: list[dict[str, Any]]) -> str | None:
    ready = [sample for sample in samples
             if sample.get("ble_begin_stage") == "ready"]
    if not ready:
        return "bounded BLE initialization never reached ready"
    sample = ready[-1]
    required = {
        "ble_begin_heap_free_before": BLE_MINIMUM_FREE_HEAP_BEFORE_BEGIN,
        "ble_begin_heap_largest_before":
            BLE_MINIMUM_LARGEST_HEAP_BEFORE_BEGIN,
        "ble_begin_heap_free_after": 1,
        "ble_begin_heap_largest_after": 1,
    }
    for key, minimum in required.items():
        value = sample.get(key)
        if (not isinstance(value, int) or isinstance(value, bool) or
                value < minimum):
            return f"{key}={value!r} below {minimum}"
    return None


def focus_home_case(device: PassiveSerial, case: MenuCase,
                    trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = read_only_query(device, b"ui.state", UI_SCHEMA, "state")
    if not (state.get("page") == "home" and
            state.get("runtime_owner") == "none" and
            state.get("lease_mask") == 0):
        raise RuntimeError(f"Home/zero lease required before {case.item_id}: {state!r}")
    for _ in range(8):
        if int(state.get("selection", -1)) == case.index:
            break
        direction = "down" if int(state.get("selection", -1)) < case.index else "up"
        state = action(device, direction)
        trace.append(state)
    failures = expect(state, {
        "page": "home", "selection": case.index,
        "selected_id": case.item_id, "selected_enabled": True,
        "runtime_owner": "none", "lease_mask": 0,
    }, f"{case.item_id}.home_focus")
    if failures:
        raise RuntimeError("; ".join(failures))
    return state


def wait_clean_home(device: PassiveSerial, case: MenuCase,
                    timeout: float = 12.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Request one Back/Left and prove eventual plus settled cleanup."""
    actions = [action(device, "left")]
    deadline = time.monotonic() + timeout
    last = actions[-1]
    while time.monotonic() < deadline:
        if (last.get("page") == "home" and
                last.get("runtime_owner") == "none" and
                last.get("lease_mask") == 0):
            break
        time.sleep(0.05)
        last = read_only_query(device, b"ui.state", UI_SCHEMA, "state")
        actions.append(last)
    failures = expect(last, {
        "page": "home", "selected_id": case.item_id,
        "runtime_owner": "none", "lease_mask": 0,
    }, f"{case.item_id}.home_return")
    if failures:
        raise RuntimeError("; ".join(failures))
    time.sleep(HOME_SETTLE_SECONDS)
    settled = read_only_query(device, b"ui.state", UI_SCHEMA, "state")
    failures = expect(settled, {
        "page": "home", "selected_id": case.item_id,
        "runtime_owner": "none", "lease_mask": 0,
    }, f"{case.item_id}.home_settled")
    if failures:
        raise RuntimeError("; ".join(failures))
    return actions, settled


def capture_feature_state(device: PassiveSerial,
                          case: MenuCase) -> dict[str, Any] | None:
    """Retain a read-only product diagnostic while its page is still open."""
    if case.item_id == "targets":
        return read_only_query(
            device, b"targets.state", TARGETS_SCHEMA, "state")
    return None


def result_contract_failures(result: dict[str, Any]) -> list[str]:
    """Fail closed on incomplete/malleable retained menu-smoke evidence."""
    failures: list[str] = []
    if result.get("schema") != RUN_SCHEMA:
        failures.append("result.schema: invalid")
    candidate = result.get("candidate", {})
    if not isinstance(candidate, dict) or candidate.get("verified") is not True:
        failures.append("result.candidate: exact boot identity unproven")
    policy = result.get("policy", {})
    failures.extend(expect(policy if isinstance(policy, dict) else {}, {
        "board_id": BOARD_ID, "exact_port": BOARD_PORT,
        "top_level_only": True, "nested_actions_selected": 0,
        "dangerous_tx_started": False,
        "mac_wifi_or_ble_controlled": False,
        "manual_button_presses": 0,
        "product_storage_writes_measured": False,
        "isolated_device_lock_fixture": True,
        "pin_or_digest_retained": False,
        "product_lock_namespace_written_or_erased": False,
    }, "result.policy"))
    lock_fixture = result.get("device_lock_fixture", {})
    if not isinstance(lock_fixture, dict):
        lock_fixture = {}
    failures.extend(expect(lock_fixture.get("begin", {}), {
        "status": "begun", "active": True,
        "product_namespace_written_or_erased": False,
    }, "result.device_lock_fixture.begin"))
    failures.extend(expect(lock_fixture.get("unlocked", {}), {
        "status": "unlocked", "protected_access": True,
        "persistence_fixture_active": True,
    }, "result.device_lock_fixture.unlocked"))
    failures.extend(expect(lock_fixture.get("cleanup", {}), {
        "status": "cleaned", "active": False,
        "product_restored": True,
        "product_namespace_written_or_erased": False,
    }, "result.device_lock_fixture.cleanup"))
    before_lock = lock_fixture.get("product_before", {})
    after_lock = lock_fixture.get("product_after", {})
    if not isinstance(before_lock, dict) or not isinstance(after_lock, dict):
        failures.append("result.device_lock_fixture.product_continuity: missing")
    else:
        for key in ("status", "credential_generation", "failed_attempts"):
            if before_lock.get(key) != after_lock.get(key):
                failures.append(
                    f"result.device_lock_fixture.product_continuity.{key}: changed")
    all_ids = [case.item_id for case in MENU_CASES]
    coverage = policy.get("coverage")
    requested_ids = policy.get("requested_menu_ids")
    expected_cases: tuple[MenuCase, ...] = ()
    if coverage == "full":
        if requested_ids != all_ids:
            failures.append("result.policy: full coverage catalog mismatch")
        else:
            expected_cases = MENU_CASES
    elif coverage == "delta":
        if (not isinstance(requested_ids, list) or not requested_ids or
                requested_ids == all_ids or len(requested_ids) !=
                len(set(requested_ids))):
            failures.append("result.policy: invalid strict delta subset")
        else:
            try:
                expected_cases = selected_menu_cases(requested_ids)
            except ValueError as error:
                failures.append(f"result.policy: {error}")
            if [case.item_id for case in expected_cases] != requested_ids:
                failures.append(
                    "result.policy: delta ids must follow catalog order")
    else:
        failures.append("result.policy: coverage must be full or delta")

    records = result.get("menus")
    if not isinstance(records, list):
        return failures + ["result.menus: missing"]
    expected_ids = [case.item_id for case in expected_cases]
    actual_ids = [record.get("id") for record in records
                  if isinstance(record, dict)]
    if actual_ids != expected_ids:
        failures.append(
            f"result.menus: {actual_ids!r} != {expected_ids!r}")
    for case, record in zip(expected_cases, records):
        label = f"result.{case.item_id}"
        if not isinstance(record, dict):
            failures.append(f"{label}: invalid record")
            continue
        if record.get("passed") is not True or record.get("failures") != []:
            failures.append(f"{label}: not passed")
        samples = record.get("dwell_samples")
        effective_dwell = record.get("effective_dwell_seconds")
        if (not isinstance(effective_dwell, (int, float)) or
                isinstance(effective_dwell, bool) or
                effective_dwell < case.minimum_dwell_seconds):
            failures.append(f"{label}: effective dwell below case minimum")
        if not isinstance(samples, list) or len(samples) < 2:
            failures.append(f"{label}: bounded dwell unproven")
        else:
            for index, state in enumerate(samples):
                if not isinstance(state, dict):
                    failures.append(f"{label}.dwell[{index}]: invalid")
                else:
                    failures.extend(state_failures(
                        case, state, f"{label}.dwell[{index}]"))
            terminal_offset = samples[-1].get("host_dwell_offset_ms") \
                if isinstance(samples[-1], dict) else None
            if (not isinstance(terminal_offset, (int, float)) or
                    isinstance(terminal_offset, bool) or
                    not isinstance(effective_dwell, (int, float)) or
                    terminal_offset + 0.001 < effective_dwell * 1000.0):
                failures.append(f"{label}: terminal dwell boundary unproven")
        if case.item_id == "ble" and isinstance(samples, list):
            ble_failure = ble_begin_evidence_failure(samples)
            if ble_failure is not None:
                failures.append(f"{label}: {ble_failure}")
        feature_state = record.get("feature_state")
        if case.item_id == "targets":
            failures.extend(expect(
                feature_state if isinstance(feature_state, dict) else {}, {
                    "schema": TARGETS_SCHEMA, "kind": "state",
                    "page_open": True, "lease_mask": case.lease_mask,
                }, f"{label}.feature_state"))
        elif feature_state not in (None, {}):
            failures.append(f"{label}.feature_state: unexpected")
        settled = record.get("home_settled")
        failures.extend(expect(settled if isinstance(settled, dict) else {}, {
            "page": "home", "selected_id": case.item_id,
            "runtime_owner": "none", "lease_mask": 0,
        }, f"{label}.home_settled"))
    screens = result.get("screens", {})
    if policy.get("screenshots_requested") is True:
        if not isinstance(screens, dict) or list(screens) != expected_ids:
            failures.append("result.screens: complete catalog-order set missing")
        else:
            for case in expected_cases:
                screen = screens.get(case.item_id, {})
                label = f"result.screens.{case.item_id}"
                if not isinstance(screen, dict):
                    failures.append(f"{label}: invalid record")
                    continue
                begin = screen.get("frame_begin", {})
                if not isinstance(begin, dict) or (
                        begin.get("width"), begin.get("height"),
                        begin.get("bytes")) != (240, 320, 153600):
                    failures.append(f"{label}: invalid TFT geometry")
                failures.extend(state_failures(
                    case,
                    screen.get("state", {})
                    if isinstance(screen.get("state"), dict) else {},
                    label))
                for field in ("rgb565_sha256", "png_sha256"):
                    value = screen.get(field)
                    if (not isinstance(value, str) or len(value) != 64 or
                            any(character not in "0123456789abcdef"
                                for character in value)):
                        failures.append(f"{label}.{field}: invalid digest")
                attempts = screen.get("transport_attempts")
                retries = screen.get("transport_transient_retries")
                if (not isinstance(attempts, int) or isinstance(attempts, bool) or
                        not 1 <= attempts <= 2 or retries != attempts - 1):
                    failures.append(f"{label}: invalid transport attempts")
    elif screens not in ({}, None):
        failures.append("result.screens: unrequested screenshots retained")
    cleanup = result.get("cleanup_after", {})
    if not isinstance(cleanup, dict) or cleanup.get("complete") is not True:
        failures.append("result.cleanup_after: incomplete")
    safe = result.get("safe_outputs", {})
    failures.extend(expect(safe if isinstance(safe, dict) else {}, {
        "buzzer_inactive": True, "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "result.safe_outputs"))
    input_state = result.get("input", {})
    failures.extend(expect(
        input_state if isinstance(input_state, dict) else {}, {
            "status": "ready", "read_errors": 0, "queue_drops": 0,
        }, "result.input"))
    before = result.get("recovery_before", {})
    after = result.get("recovery_after", {})
    if not isinstance(before, dict) or not isinstance(after, dict):
        failures.append("result.recovery: missing")
    else:
        for key in ("generation", "observations"):
            if before.get(key) != after.get(key):
                failures.append(
                    f"result.boot_recovery_continuity.{key}: changed")
    if result.get("boot_recovery_continuity") is not True:
        failures.append("result.boot_recovery_continuity: unproven")
    hil = result.get("hil_session", {})
    if not isinstance(hil, dict):
        hil = {}
    failures.extend(expect(hil.get("begin", {}), {"active": True},
                           "result.hil_session.begin"))
    failures.extend(expect(hil.get("end", {}), {"active": False},
                           "result.hil_session.end"))
    post = result.get("post_hil_end", {})
    if not isinstance(post, dict):
        post = {}
    failures.extend(expect(post.get("hil", {}), {"active": False},
                           "result.post_hil_end.hil"))
    failures.extend(expect(post.get("ui", {}), {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, "result.post_hil_end.ui"))
    if coverage == "full":
        failures.extend(expect(result.get("catalog_boundary", {}), {
            "page": "home", "selection": MENU_CASES[-1].index,
            "selected_id": MENU_CASES[-1].item_id, "changed": False,
            "runtime_owner": "none", "lease_mask": 0,
        }, "result.catalog_boundary"))
    else:
        failures.extend(expect(result.get("catalog_boundary", {}), {
            "checked": False, "reason": "delta_subset",
        }, "result.catalog_boundary"))
    return failures


def validate_args(parser: argparse.ArgumentParser,
                  args: argparse.Namespace) -> None:
    if args.port == FORBIDDEN_FIXTURE_PORT:
        parser.error("board-02/clone fixture port is forbidden")
    if args.port != BOARD_PORT:
        parser.error(f"menu smoke is bound to {BOARD_ID} at {BOARD_PORT}")
    if not args.firmware.is_file():
        parser.error("--firmware must name an existing app image")
    if args.output.exists():
        parser.error("--output must not exist")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if (len(args.source_commit) != 40 or
            any(character not in "0123456789abcdefABCDEF"
                for character in args.source_commit)):
        parser.error("--source-commit must be a full hexadecimal Git commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    if args.dwell_seconds < 0.5:
        parser.error("--dwell-seconds must be at least 0.5")
    if not 0 < args.sample_seconds <= args.dwell_seconds:
        parser.error("--sample-seconds must be positive and no longer than dwell")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--dwell-seconds", type=float,
                        default=DEFAULT_DWELL_SECONDS)
    parser.add_argument("--sample-seconds", type=float,
                        default=DEFAULT_SAMPLE_SECONDS)
    parser.add_argument("--capture-screens", action="store_true")
    parser.add_argument(
        "--only", action="append", choices=[case.item_id for case in MENU_CASES],
        help="repeat for a strict catalog-ordered delta; default covers all menus")
    args = parser.parse_args()
    validate_args(parser, args)
    cases = selected_menu_cases(args.only)

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    trace: list[dict[str, Any]] = []
    menus: list[dict[str, Any]] = []
    screens: dict[str, dict[str, Any]] = {}
    boot: dict[str, Any] = {}
    boot_metrics_samples: list[dict[str, Any]] = []
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup_before: dict[str, Any] = {"attempted": False}
    cleanup_after: dict[str, Any] = {"attempted": False}
    hil_begin: dict[str, Any] = {}
    hil_end: dict[str, Any] = {}
    post_hil_end: dict[str, Any] = {}
    catalog_boundary: dict[str, Any] = {}
    device_lock_fixture: dict[str, Any] = {}
    flash_completed = False
    candidate_verified = False
    hil_started = False
    lock_fixture_started = False
    lock_pin = ephemeral_pin()
    frames_dir = args.output / "frames"
    if args.capture_screens:
        frames_dir.mkdir()

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            flash_completed = True
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            try:
                synchronize_console(device, 30.0)
                boot, boot_metrics_samples = stabilized_boot_metrics(device)
                recovery_before = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    boot, recovery_before, args.expected_version,
                    app_identity, args.expected_cid))
                if failures:
                    raise RuntimeError("boot contract failed")
                candidate_verified = candidate_verification_succeeded(
                    fresh_flash_requested=args.flash,
                    reuse_exact_requested=args.reuse_exact_flash,
                    flash_completed=flash_completed,
                    exact_boot_verified=True)
                if not candidate_verified:
                    raise RuntimeError("exact candidate verification failed")
                cleanup_before = robust_cleanup(device)
                if cleanup_before.get("complete") is not True:
                    raise RuntimeError("initial Home/zero-lease cleanup failed")
                hil_begin = begin_hil_session(
                    device, run_id, app_identity, args.expected_version)
                hil_started = True
                device_lock_fixture["product_before"] = read_only_query(
                    device, b"device-lock.state", LOCK_SCHEMA, "state")
                device_lock_fixture["begin"] = fixture_command(
                    device, "begin")
                lock_fixture_started = True
                if device_lock_fixture["begin"].get("status") != "begun":
                    raise RuntimeError("isolated Device Lock fixture unavailable")
                home_device(device)
                device_lock_page(device)
                opened = action(device, "right")
                if opened.get("runtime_event") != "device_lock_editor_opened":
                    raise RuntimeError("Device Lock fixture editor did not open")
                enter_pin(device, lock_pin)
                enter_pin(device, lock_pin)
                device_lock_fixture["unlocked"] = wait_lock_state(
                    device,
                    lambda state: state.get("status") == "unlocked",
                    "isolated menu-smoke unlock")
                if device_lock_fixture["unlocked"].get(
                        "protected_access") is not True:
                    raise RuntimeError("isolated Device Lock did not unlock")
                unlocked_cleanup = robust_cleanup(device)
                device_lock_fixture["unlocked_home"] = unlocked_cleanup
                if unlocked_cleanup.get("complete") is not True:
                    raise RuntimeError("unlocked fixture did not return Home")

                for case in cases:
                    record: dict[str, Any] = {
                        "id": case.item_id, "index": case.index,
                        "expected_page": case.page,
                        "expected_runtime_owner": case.runtime_owner,
                        "expected_lease_mask": case.lease_mask,
                        "minimum_dwell_seconds":
                            case.minimum_dwell_seconds,
                        "failures": [],
                    }
                    try:
                        record["home_focus"] = focus_home_case(
                            device, case, trace)
                        entered = action(device, "right")
                        trace.append(entered)
                        record["entered"] = entered
                        effective_dwell = effective_dwell_seconds(
                            case, args.dwell_seconds)
                        record["effective_dwell_seconds"] = effective_dwell
                        samples, dwell_failures = collect_stable_dwell(
                            device, case, entered, effective_dwell,
                            args.sample_seconds)
                        record["dwell_samples"] = samples
                        if case.item_id == "ble":
                            ble_failure = ble_begin_evidence_failure(samples)
                            if ble_failure is not None:
                                record["failures"].append(ble_failure)
                        record["survey_product_store_bytes_written_samples"] = [
                            sample.get("survey_product_store_bytes_written")
                            for sample in samples
                            if isinstance(
                                sample.get("survey_product_store_bytes_written"),
                                int)
                            and not isinstance(
                                sample.get("survey_product_store_bytes_written"),
                                bool)
                        ]
                        record["failures"].extend(dwell_failures)
                        feature_state = capture_feature_state(device, case)
                        if feature_state is not None:
                            record["feature_state"] = feature_state
                        if args.capture_screens:
                            screen = capture(
                                device, frames_dir,
                                f"{case.index:02d}-{case.item_id}")
                            screens[case.item_id] = screen
                            record["screen"] = screen
                        back_trace, settled = wait_clean_home(device, case)
                        trace.extend(back_trace)
                        trace.append(settled)
                        record["back_trace"] = back_trace
                        record["home_settled"] = settled
                    except Exception as error:
                        record["failures"].append(
                            f"{type(error).__name__}: {error}")
                        # Preserve subsequent coverage only if cleanup can prove
                        # the shared foreground is entirely released.
                        recovered = robust_cleanup(device)
                        record["recovery_cleanup"] = recovered
                        if recovered.get("complete") is not True:
                            raise
                    record["passed"] = not record["failures"]
                    menus.append(record)
                    failures.extend(
                        f"{case.item_id}: {failure}"
                        for failure in record["failures"])

                if cases == MENU_CASES:
                    # Full mode alone proves that the executable catalog has
                    # no untested tenth entry. Down on the last row is a no-op.
                    catalog_boundary = action(device, "down")
                    trace.append(catalog_boundary)
                    failures.extend(expect(catalog_boundary, {
                        "page": "home", "selection": MENU_CASES[-1].index,
                        "selected_id": MENU_CASES[-1].item_id,
                        "changed": False, "runtime_owner": "none",
                        "lease_mask": 0,
                    }, "catalog_boundary"))
                else:
                    catalog_boundary = {
                        "checked": False, "reason": "delta_subset"}

                input_state = read_only_query(
                    device, b"input.state",
                    "leshy.input.frontend.v1", "state")
                safe_outputs = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                recovery_after = read_only_query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(expect(input_state, {
                    "status": "ready", "read_errors": 0, "queue_drops": 0,
                }, "input"))
                failures.extend(expect(safe_outputs, {
                    "buzzer_inactive": True, "nrf_ce_inactive": True,
                    "software_quiesce_complete": True,
                }, "safe_outputs"))
                for key in ("generation", "observations"):
                    if recovery_after.get(key) != recovery_before.get(key):
                        failures.append(
                            f"boot_recovery_continuity.{key}: changed")
            except Exception as error:
                failures.append(f"workflow: {type(error).__name__}: {error}")
            finally:
                cleanup_after = robust_cleanup(device)
                if cleanup_after.get("complete") is not True:
                    failures.append("cleanup_after: Home/zero lease unproven")
                if lock_fixture_started:
                    try:
                        cleanup_hil_state = read_only_query(
                            device, b"hil.state", HIL_SESSION_SCHEMA,
                            "state")
                        device_lock_fixture["cleanup_hil_before"] = \
                            cleanup_hil_state
                        if cleanup_hil_state.get("active") is not True:
                            device_lock_fixture["cleanup_hil_rebegun"] = \
                                begin_hil_session(
                                    device, run_id, app_identity,
                                    args.expected_version)
                        else:
                            device_lock_fixture[
                                "cleanup_hil_rebegun"] = False
                        device_lock_fixture["cleanup"] = fixture_command(
                            device, "cleanup")
                        lock_fixture_started = False
                        device_lock_fixture["product_after"] = read_only_query(
                            device, b"device-lock.state", LOCK_SCHEMA,
                            "state")
                    except Exception as error:
                        failures.append(
                            "device_lock_fixture_cleanup: "
                            f"{type(error).__name__}: {error}")
                if hil_started:
                    try:
                        hil_end = end_hil_session(device, run_id, app_identity)
                        post_hil_end = {
                            "hil": read_only_query(
                                device, b"hil.state", HIL_SESSION_SCHEMA,
                                "state"),
                            "ui": read_only_query(
                                device, b"ui.state", UI_SCHEMA, "state"),
                        }
                        failures.extend(expect(post_hil_end["hil"], {
                            "active": False,
                        }, "post_hil_end.hil"))
                        failures.extend(expect(post_hil_end["ui"], {
                            "page": "home", "runtime_owner": "none",
                            "lease_mask": 0,
                        }, "post_hil_end.ui"))
                    except Exception as error:
                        failures.append(
                            f"hil_session_end: {type(error).__name__}: {error}")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")
    finally:
        wipe_pin(lock_pin)

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "passed": False,
        "gate_eligible": False,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "verified": candidate_verified,
            "flash_mode": "fresh" if args.flash else "reuse_exact",
        },
        "expected_cid": args.expected_cid,
        "policy": {
            "board_id": BOARD_ID, "exact_port": BOARD_PORT,
            "top_level_only": True, "nested_actions_selected": 0,
            "dangerous_tx_started": False,
            "mac_wifi_or_ble_controlled": False,
            "manual_button_presses": 0,
            "product_storage_writes_measured": False,
            "isolated_device_lock_fixture": True,
            "pin_or_digest_retained": False,
            "product_lock_namespace_written_or_erased": False,
            "screenshots_requested": args.capture_screens,
            "coverage": "full" if cases == MENU_CASES else "delta",
            "requested_menu_ids": [case.item_id for case in cases],
            "requested_dwell_seconds": args.dwell_seconds,
            "sample_seconds": args.sample_seconds,
        },
        "boot": boot,
        "boot_metrics_samples": boot_metrics_samples,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "boot_recovery_continuity": bool(recovery_before) and
            bool(recovery_after) and all(
                recovery_before.get(key) == recovery_after.get(key)
                for key in ("generation", "observations")),
        "input": input_state,
        "safe_outputs": safe_outputs,
        "menus": menus,
        "screens": screens,
        "device_lock_fixture": device_lock_fixture,
        "catalog_boundary": catalog_boundary,
        "trace": trace,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "hil_session": {"begin": hil_begin, "end": hil_end},
        "post_hil_end": post_hil_end,
    }
    contract_failures = result_contract_failures(result)
    failures.extend(f"contract: {failure}" for failure in contract_failures)
    result["failures"] = failures
    result["passed"] = candidate_verified and not failures
    result["gate_eligible"] = result["passed"]
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "status": "pass" if result["passed"] else "failed",
        "failures": failures,
        "menus": [record.get("id") for record in menus],
        "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
