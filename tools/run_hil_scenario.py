#!/usr/bin/env python3
"""Run a declarative one- or two-device Leshy HIL scenario fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shutil
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from capture_1x_boot import reset_and_capture_reconnecting
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    boot_ready_failures,
    capture,
    expect,
    parse_boot_records,
    query,
    valid_cid,
)
SCENARIO_SCHEMA = "leshy.hil.scenario.v1"
RUN_SCHEMA = "leshy.hil.scenario_run.v1"
SUPPORTED_OPERATIONS = {
    "action", "capture", "cleanup", "poll_query", "query",
    "reboot", "select_home_app", "sleep", "stream",
}
PUBLIC_ACTIONS = {"up", "down", "left", "right", "select", "back"}
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_CAPTURE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
UPPER_HEX_16 = re.compile(r"^[0-9A-F]{16}$")
PLACEHOLDER = re.compile(r"\$\{([a-z_]+)\}")
QUERY_PLACEHOLDERS = {
    "session_id": "0" * 32,
    "fixture_app_sha256": "0" * 64,
    "fixture_id": "0" * 16,
}
STREAM_CONTRACTS = {
    "capture.ir.export.csv": (
        "leshy.capture.infrared_raw.csv.v1", "csv_begin", "csv_end"),
    "capture.subghz.export.csv": (
        "leshy.capture.subghz_raw.csv.v1", "csv_begin", "csv_end"),
    "library.export.csv": ("leshy.library.csv.v1", "begin", "end"),
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("scenario must be a JSON object")
    return value


def parse_ports(values: list[str]) -> dict[str, str]:
    ports: dict[str, str] = {}
    for value in values:
        role, separator, port = value.partition("=")
        if not separator or not role or not port or role in ports:
            raise ValueError(f"invalid or duplicate --port binding: {value!r}")
        ports[role] = port
    if "candidate" not in ports:
        raise ValueError("--port candidate=<serial-device> is required")
    if len(set(ports.values())) != len(ports):
        raise ValueError("each device role requires a distinct serial port")
    return ports


def value_at(record: Any, path: str) -> Any:
    current = record
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            raise KeyError(path)
        current = current[component]
    return current


def evaluate_checks(record: dict[str, Any], checks: list[dict[str, Any]],
                    label: str) -> list[str]:
    failures: list[str] = []
    operations = {
        "eq": lambda actual, expected: actual == expected,
        "ne": lambda actual, expected: actual != expected,
        "gte": lambda actual, expected: actual >= expected,
        "lte": lambda actual, expected: actual <= expected,
        "gt": lambda actual, expected: actual > expected,
        "lt": lambda actual, expected: actual < expected,
        "in": lambda actual, expected: actual in expected,
    }
    for check in checks:
        path = check.get("path")
        operation = check.get("op")
        expected = check.get("value")
        if not isinstance(path, str) or operation not in operations:
            failures.append(f"{label}: invalid check {check!r}")
            continue
        try:
            actual = value_at(record, path)
            passed = operations[operation](actual, expected)
        except (KeyError, TypeError, ValueError) as error:
            failures.append(f"{label}.{path}: check error: {error}")
            continue
        if not passed:
            failures.append(
                f"{label}.{path}: {actual!r} does not satisfy "
                f"{operation} {expected!r}")
    return failures


def evaluate_expectations(record: dict[str, Any], expected: dict[str, Any],
                          label: str) -> list[str]:
    failures: list[str] = []
    for key, wanted in expected.items():
        actual = record.get(key)
        path = f"{label}.{key}"
        if isinstance(wanted, dict):
            if not isinstance(actual, dict):
                failures.append(f"{path}: {actual!r} is not an object")
            else:
                failures.extend(evaluate_expectations(actual, wanted, path))
        elif actual != wanted:
            failures.append(f"{path}: {actual!r} != {wanted!r}")
    return failures


def safe_console_token(value: object, maximum: int = 96) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum and
            value.isascii() and value.isprintable() and
            "\r" not in value and "\n" not in value)


def render_query_command(command: object,
                         values: dict[str, str]) -> str:
    if not isinstance(command, str):
        raise ValueError("query command must be a string")
    unknown = set(PLACEHOLDER.findall(command)) - set(QUERY_PLACEHOLDERS)
    if unknown:
        raise ValueError(
            f"unsupported query placeholder: {sorted(unknown)[0]}")
    rendered = PLACEHOLDER.sub(
        lambda match: values.get(match.group(1), match.group(0)), command)
    if PLACEHOLDER.search(rendered) or not safe_console_token(rendered, 192):
        raise ValueError("query command is unsafe after substitution")
    return rendered


def fixture_required(scenario: dict[str, Any]) -> bool:
    devices = scenario.get("devices", {})
    policy = devices.get("fixture", {}) if isinstance(devices, dict) else {}
    return isinstance(policy, dict) and policy.get("required") is True


def fixture_admission_failures(record: dict[str, Any], version: str,
                               fixture_id: str,
                               app_identity: str) -> list[str]:
    expected = {
        "version": version,
        "role": "bounded_signal_fixture",
        "fixture_id": fixture_id,
        "app_elf_sha256": app_identity,
        "identity_ready": True,
        "ir_tx_inactive": True,
        "nrf_ce_inactive": True,
        "nrf_powered_down": True,
        "cc_transmit_active": False,
        "cc_idle": True,
        "cc_power_cleared": True,
        "cc_tx_fifo_cleared": True,
        "buzzer_inactive": True,
        "fixed_vector_only": True,
        "auto_arm": False,
        "watchdog_armed": True,
        "maximum_ir_emission_us": 100000,
        "maximum_nrf_carrier_us": 2500000,
        "maximum_cc1101_emission_us": 250000,
        "session_lifetime_ms": 5000,
    }
    return expect(record, expected, "fixture_admission")


def validate_fixture_profile(profile: dict[str, Any], fixture_id: str,
                             fixture_port: str | None = None) -> None:
    chip = profile.get("chip", {})
    assembly = profile.get("assembly", {})
    expected = {
        "schema": "leshy.hil.board_profile.v1",
        "status": "accepted",
        "accepted_for_fixture_flash": True,
        "writes_performed": False,
        "flash_erases_performed": 0,
        "flash_bytes_written": 0,
        "ram_stub_uploaded": False,
    }
    failures = evaluate_expectations(profile, expected, "fixture_profile")
    failures.extend(evaluate_expectations(chip, {
        "family": "esp32-s3", "fixture_id": fixture_id,
        "flash_size": "16MB",
    }, "fixture_profile.chip"))
    failures.extend(evaluate_expectations(assembly, {
        "profile": "esp32-div-v2-n16", "extension_modules": "none",
        "antennas_attached": True,
    }, "fixture_profile.assembly"))
    operations = profile.get("operations")
    if (not isinstance(operations, list) or len(operations) != 4 or
            any(not isinstance(value, dict) or
                value.get("read_only") is not True or
                value.get("returncode") != 0 for value in operations)):
        failures.append("fixture_profile.operations: read-only proof missing")
    if (fixture_port is not None and
            profile.get("port_at_profile") != fixture_port):
        failures.append(
            "fixture_profile.port_at_profile: fixture port mismatch")
    if failures:
        raise ValueError("; ".join(failures))


def fixture_inactive_failures(record: dict[str, Any],
                              label: str) -> list[str]:
    return expect(record, {
        "ir_tx_inactive": True,
        "nrf_ce_inactive": True,
        "nrf_powered_down": True,
        "cc_transmit_active": False,
        "cc_idle": True,
        "cc_power_cleared": True,
        "cc_tx_fifo_cleared": True,
        "buzzer_inactive": True,
        "output_inactive": True,
    }, label)


def read_framed_stream(device: Any, command: str, output: Path,
                       timeout: float) -> tuple[dict[str, Any], bytes]:
    schema, begin_kind, end_kind = STREAM_CONTRACTS[command]
    device.reset_input_buffer()
    device.write(command.encode("ascii") + b"\n")
    device.flush()
    deadline = time.monotonic() + timeout
    begin: dict[str, Any] | None = None
    end: dict[str, Any] | None = None
    payload = bytearray()
    while time.monotonic() < deadline:
        line = device.readline()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("schema") == schema:
            if value.get("kind") == "error":
                raise RuntimeError(f"device rejected stream: {value}")
            if value.get("kind") == begin_kind:
                begin = value
                continue
            if value.get("kind") == end_kind and begin is not None:
                end = value
                break
        if begin is not None:
            payload.extend(line)
    if begin is None or end is None:
        raise TimeoutError(f"stream framing incomplete: {command}")
    body = bytes(payload)
    output.write_bytes(body)
    record = {
        "begin": begin,
        "end": end,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "artifact": str(output),
    }
    return record, body


def validate_scenario(scenario: dict[str, Any], ports: dict[str, str]) -> None:
    if scenario.get("schema") != SCENARIO_SCHEMA:
        raise ValueError("scenario schema mismatch")
    for key in ("id", "checkpoint", "steps", "limits"):
        if key not in scenario:
            raise ValueError(f"scenario field is missing: {key}")
    if not isinstance(scenario["id"], str) or not SAFE_ID.fullmatch(
            scenario["id"]):
        raise ValueError("scenario id is invalid")
    if not isinstance(scenario["checkpoint"], str) or not SAFE_ID.fullmatch(
            scenario["checkpoint"]):
        raise ValueError("scenario checkpoint is invalid")
    if not isinstance(scenario["limits"], dict):
        raise ValueError("scenario limits must be an object")
    devices = scenario.get("devices", {"candidate": {"required": True}})
    if not isinstance(devices, dict) or "candidate" not in devices:
        raise ValueError("scenario devices must declare candidate")
    for role, policy in devices.items():
        if not isinstance(role, str) or not SAFE_ID.fullmatch(role):
            raise ValueError(f"invalid device role: {role!r}")
        if not isinstance(policy, dict):
            raise ValueError(f"device role policy must be an object: {role}")
        required = isinstance(policy, dict) and policy.get("required") is True
        if required and role not in ports:
            raise ValueError(f"required device role is not bound: {role}")
        if role == "fixture" and required and policy.get("kind") != \
                "bounded_signal_fixture":
            raise ValueError(
                "required fixture must declare kind bounded_signal_fixture")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 256:
        raise ValueError("scenario must contain 1..256 steps")
    seen: set[str] = set()
    for step in steps:
        if (not isinstance(step, dict) or
                not isinstance(step.get("id"), str) or
                not SAFE_ID.fullmatch(step["id"])):
            raise ValueError("every step requires a safe string id")
        if step["id"] in seen:
            raise ValueError(f"duplicate step id: {step['id']}")
        seen.add(step["id"])
        operation = step.get("op")
        if operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"unsupported operation in {step['id']}")
        role = step.get("target", "candidate")
        if operation != "sleep" and role not in ports:
            raise ValueError(f"step {step['id']} targets unbound role {role}")
        if role == "fixture" and not fixture_required(scenario):
            raise ValueError(
                f"step {step['id']} targets a fixture that is not required")
        if role == "fixture" and operation not in ("poll_query", "query"):
            raise ValueError(
                f"step {step['id']} uses unsupported fixture operation")
        timeout = step.get("timeout", 15.0)
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or
                not 0 < timeout <= 60):
            raise ValueError(f"step {step['id']} timeout must be in (0, 60]")
        if operation == "sleep":
            seconds = step.get("seconds")
            if (isinstance(seconds, bool) or
                    not isinstance(seconds, (int, float)) or
                    not 0 <= seconds <= 60):
                raise ValueError(
                    f"step {step['id']} sleep must be 0..60 seconds")
        elif operation == "action" and step.get("name") not in PUBLIC_ACTIONS:
            raise ValueError(f"step {step['id']} has an invalid public action")
        elif operation in ("poll_query", "query"):
            try:
                render_query_command(step.get("command"), QUERY_PLACEHOLDERS)
            except ValueError as error:
                raise ValueError(
                    f"step {step['id']} has an unsafe query: {error}") from error
            if not safe_console_token(step.get("command"), 192):
                raise ValueError(f"step {step['id']} has an unsafe query")
            if (not safe_console_token(step.get("response_schema"), 80) or
                    not safe_console_token(step.get("kind", "state"), 32)):
                raise ValueError(
                    f"step {step['id']} has an invalid response contract")
            if operation == "poll_query":
                interval = step.get("interval", 0.1)
                if (isinstance(interval, bool) or
                        not isinstance(interval, (int, float)) or
                        not 0.05 <= interval <= 2.0):
                    raise ValueError(
                        f"step {step['id']} poll interval must be 0.05..2")
                if not isinstance(step.get("until"), dict):
                    raise ValueError(
                        f"step {step['id']} poll until must be an object")
        elif operation == "reboot":
            seconds = step.get("capture_seconds", 8.0)
            if role != "candidate":
                raise ValueError(
                    f"step {step['id']} can reboot only the candidate")
            if (isinstance(seconds, bool) or
                    not isinstance(seconds, (int, float)) or
                    not 2.0 <= seconds <= 45.0):
                raise ValueError(
                    f"step {step['id']} reboot capture must be 2..45 seconds")
        elif operation == "stream":
            name = step.get("name", step["id"])
            if role != "candidate" or step.get("command") not in \
                    STREAM_CONTRACTS:
                raise ValueError(
                    f"step {step['id']} has an unsupported stream contract")
            if (not isinstance(name, str) or
                    not SAFE_CAPTURE_NAME.fullmatch(name)):
                raise ValueError(
                    f"step {step['id']} has an unsafe stream name")
        elif operation == "capture":
            name = step.get("name", step["id"])
            if (not isinstance(name, str) or
                    not SAFE_CAPTURE_NAME.fullmatch(name)):
                raise ValueError(f"step {step['id']} has an unsafe capture name")
        elif operation == "select_home_app":
            app_id = step.get("app_id")
            if not isinstance(app_id, str) or not SAFE_ID.fullmatch(app_id):
                raise ValueError(f"step {step['id']} has an invalid app id")
        if "expect" in step and not isinstance(step["expect"], dict):
            raise ValueError(f"step {step['id']} expect must be an object")
        if "checks" in step and not isinstance(step["checks"], list):
            raise ValueError(f"step {step['id']} checks must be an array")
    if fixture_required(scenario) and not any(
            step.get("target", "candidate") == "fixture" and
            step.get("op") in ("poll_query", "query") for step in steps):
        raise ValueError("required fixture has no bounded query step")


def select_home_app(device: Any, app_id: str,
                    trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = query(device, b"ui.state", "leshy.ui.v1", "state")
    for _ in range(10):
        if state.get("selection") == 0:
            break
        state = action(device, "up")
        trace.append(state)
    for _ in range(10):
        if state.get("selected_id") == app_id:
            return state
        state = action(device, "down")
        trace.append(state)
    raise RuntimeError(f"Home app {app_id!r} is not reachable: {state!r}")


def main() -> int:
    from capture_1x_ui import PassiveSerial, synchronize_console

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--port", action="append", default=[],
                        help="role=/dev/...; candidate is required")
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-offset", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--fixture-firmware", type=Path)
    parser.add_argument("--fixture-profile", type=Path)
    parser.add_argument("--expected-fixture-version")
    parser.add_argument("--expected-fixture-id")
    parser.add_argument("--fixture-source-commit")
    parser.add_argument("--flash-fixture", action="store_true")
    parser.add_argument("--reuse-exact-fixture-flash", action="store_true")
    parser.add_argument("--fixture-flash-offset",
                        type=lambda value: int(value, 0), default=0x10000)
    args = parser.parse_args()
    try:
        ports = parse_ports(args.port)
        scenario = load_object(args.scenario)
        validate_scenario(scenario, ports)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be 32 uppercase hexadecimal characters")
    if not HEX_40.fullmatch(args.source_commit):
        parser.error("--source-commit must be a full lowercase commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    needs_fixture = fixture_required(scenario)
    fixture_arguments = (
        args.fixture_firmware, args.fixture_profile,
        args.expected_fixture_version,
        args.expected_fixture_id, args.fixture_source_commit,
        args.flash_fixture, args.reuse_exact_fixture_flash,
    )
    if needs_fixture:
        if args.fixture_firmware is None or not args.fixture_firmware.is_file():
            parser.error("required fixture firmware is missing")
        if args.fixture_profile is None or not args.fixture_profile.is_file():
            parser.error("accepted read-only fixture profile is missing")
        if not safe_console_token(args.expected_fixture_version, 48):
            parser.error("--expected-fixture-version is required and invalid")
        if (not isinstance(args.expected_fixture_id, str) or
                not UPPER_HEX_16.fullmatch(args.expected_fixture_id)):
            parser.error(
                "--expected-fixture-id must be 16 uppercase hexadecimal "
                "characters")
        if (not isinstance(args.fixture_source_commit, str) or
                not HEX_40.fullmatch(args.fixture_source_commit)):
            parser.error(
                "--fixture-source-commit must be a full lowercase commit ID")
        if args.flash_fixture == args.reuse_exact_fixture_flash:
            parser.error(
                "choose exactly one of --flash-fixture or "
                "--reuse-exact-fixture-flash")
        if sha256_file(args.fixture_firmware) == sha256_file(args.firmware):
            parser.error("candidate and fixture firmware must be distinct")
        try:
            validate_fixture_profile(
                load_object(args.fixture_profile), args.expected_fixture_id,
                ports["fixture"])
        except (OSError, ValueError, json.JSONDecodeError) as error:
            parser.error(str(error))
    elif any(fixture_arguments):
        parser.error(
            "fixture arguments require a scenario with a required fixture")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    streams = args.output / "streams"
    streams.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    fixture_image: Path | None = None
    fixture_profile_sha = ""
    fixture_sha = ""
    fixture_app_identity = ""
    if needs_fixture:
        fixture_image = args.output / "fixture.bin"
        shutil.copyfile(args.fixture_firmware, fixture_image)
        retained_profile = args.output / "fixture-profile.json"
        shutil.copyfile(args.fixture_profile, retained_profile)
        fixture_profile_sha = sha256_file(retained_profile)
        fixture_sha = sha256_file(fixture_image)
        fixture_app_identity = app_elf_sha256(fixture_image)
    scenario_sha = hashlib.sha256(args.scenario.read_bytes()).hexdigest()
    run_id = secrets.token_hex(16)
    failures: list[str] = []
    step_results: list[dict[str, Any]] = []
    reports: dict[str, Any] = {}
    captures: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    boot: dict[str, Any] = {}
    recovery_before: dict[str, Any] = {}
    recovery_after: dict[str, Any] = {}
    metrics_after: dict[str, Any] = {}
    input_state: dict[str, Any] = {}
    safe_outputs: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"attempted": False}
    fixture_identity: dict[str, Any] = {}
    fixture_admission: dict[str, Any] = {}
    fixture_cleanup: dict[str, Any] = {"attempted": False}
    stream_payloads: dict[str, bytes] = {}
    fixture_armed = False
    fixture_vector_executed = ""
    scenario_completed = False

    try:
        if args.flash:
            flash_candidate(ports["candidate"], candidate,
                            args.flash_offset, args.flash_baud)
            time.sleep(0.5)
        if needs_fixture and args.flash_fixture:
            assert fixture_image is not None
            flash_candidate(ports["fixture"], fixture_image,
                            args.fixture_flash_offset, args.flash_baud)
            time.sleep(0.5)
        with ExitStack() as stack:
            devices: dict[str, PassiveSerial] = {}
            active_ports = {"candidate": ports["candidate"]}
            if needs_fixture:
                active_ports["fixture"] = ports["fixture"]
            for role, port in active_ports.items():
                device = stack.enter_context(
                    PassiveSerial(port, 115200, timeout=0.5))
                synchronize_console(device, 30.0)
                devices[role] = device
            product = devices["candidate"]

            # Close whichever candidate connection is current only after the
            # safety callbacks.  A reboot replaces ``product`` without adding
            # the replacement to ExitStack: otherwise its context would close
            # before the callbacks registered earlier in this stack.
            def close_candidate() -> None:
                product.close()

            stack.callback(close_candidate)

            # Registered after the serial contexts and dynamic close callback
            # so cleanup runs while the current candidate port is still open,
            # including after a reboot or any failed scenario step.
            def cleanup_candidate() -> None:
                nonlocal cleanup
                cleanup = best_effort_cleanup(product)
                if not cleanup.get("complete"):
                    failures.append(
                        "cleanup: terminal zero-lease state unproven")

            stack.callback(cleanup_candidate)
            if needs_fixture:
                fixture = devices["fixture"]

                # This callback is registered after candidate cleanup so LIFO
                # ordering always quiesces the transmitter first.
                def cleanup_fixture() -> None:
                    nonlocal fixture_cleanup
                    command = (f"fixture.stop {run_id}" if scenario_completed
                               else "fixture.panic")
                    expected_state = ("stopped" if scenario_completed
                                      else "panicked")
                    try:
                        fixture_cleanup = query(
                            fixture, command.encode("ascii"),
                            "leshy.hil.fixture.signal.v1", "state", timeout=5.0)
                        fixture_cleanup["attempted"] = True
                        fixture_cleanup["command"] = command.split()[0]
                        failures.extend(fixture_inactive_failures(
                            fixture_cleanup, "fixture_cleanup"))
                        if fixture_cleanup.get("state") != expected_state:
                            failures.append(
                                "fixture_cleanup: unexpected terminal state")
                    except Exception as cleanup_error:
                        failures.append(
                            "fixture_cleanup: "
                            f"{type(cleanup_error).__name__}: {cleanup_error}")
                        try:
                            fixture_cleanup = query(
                                fixture, b"fixture.panic",
                                "leshy.hil.fixture.signal.v1", "state",
                                timeout=5.0)
                            fixture_cleanup["attempted"] = True
                            fixture_cleanup["command"] = "fixture.panic"
                            failures.extend(fixture_inactive_failures(
                                fixture_cleanup, "fixture_panic_fallback"))
                        except Exception as panic_error:
                            failures.append(
                                "fixture_panic_fallback: "
                                f"{type(panic_error).__name__}: {panic_error}")

                stack.callback(cleanup_fixture)

                fixture_identity = query(
                    fixture, b"fixture.identity",
                    "leshy.hil.fixture.signal.v1", "ready", timeout=5.0)
                failures.extend(fixture_admission_failures(
                    fixture_identity, args.expected_fixture_version,
                    args.expected_fixture_id, fixture_app_identity))
                failures.extend(evaluate_checks(fixture_identity, [{
                    "path": "state", "op": "in",
                    "value": ["idle", "complete", "stopped", "expired",
                              "panicked"],
                }], "fixture_identity"))
                if failures:
                    raise RuntimeError("fixture identity contract failed")
                fixture_reset = query(
                    fixture, b"fixture.panic",
                    "leshy.hil.fixture.signal.v1", "state", timeout=5.0)
                reset_failures = fixture_inactive_failures(
                    fixture_reset, "fixture_reset")
                reset_failures.extend(expect(
                    fixture_reset, {"state": "panicked"}, "fixture_reset"))
                failures.extend(reset_failures)
                if reset_failures:
                    raise RuntimeError("fixture pre-arm panic failed")
            boot = query(product, b"metrics", "leshy.boot.v1", "ready")
            recovery_before = query(
                product, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            failures.extend(boot_failures(
                boot, recovery_before, args.expected_version,
                app_identity, args.expected_cid))
            if failures:
                raise RuntimeError("candidate boot contract failed")
            cleanup_before = best_effort_cleanup(product)
            if not cleanup_before.get("complete"):
                raise RuntimeError("initial cleanup did not reach Home/lease 0")

            for step in scenario["steps"]:
                step_id = step["id"]
                operation = step["op"]
                role = step.get("target", "candidate")
                started = time.monotonic()
                record: dict[str, Any] = {}
                operation_failures: list[str] = []
                if operation == "sleep":
                    time.sleep(float(step["seconds"]))
                    record = {"slept_seconds": step["seconds"]}
                elif operation == "cleanup":
                    record = best_effort_cleanup(devices[role])
                elif operation == "select_home_app":
                    record = select_home_app(
                        devices[role], step["app_id"], trace)
                    reports[step_id] = record
                elif operation == "action":
                    record = action(devices[role], step["name"],
                                    timeout=float(step.get("timeout", 15.0)))
                    trace.append(record)
                    reports[step_id] = record
                elif operation == "reboot":
                    before_reboot = query(
                        product, b"ui.state", "leshy.ui.v1", "state")
                    operation_failures.extend(expect(before_reboot, {
                        "page": "home", "runtime_owner": "none",
                        "lease_mask": 0,
                    }, f"{step_id}.before"))
                    fixture_before_reboot: dict[str, Any] | None = None
                    if needs_fixture:
                        fixture_before_reboot = query(
                            devices["fixture"], b"fixture.state",
                            "leshy.hil.fixture.signal.v1", "state", timeout=5.0)
                        operation_failures.extend(fixture_inactive_failures(
                            fixture_before_reboot,
                            f"{step_id}.fixture"))
                        operation_failures.extend(expect(
                            fixture_before_reboot,
                            {"state": "complete", "session_id": run_id},
                            f"{step_id}.fixture"))
                    if operation_failures:
                        raise RuntimeError(
                            "pre-reboot zero-lease contract failed")
                    product.close()
                    reboot_raw, ready_ms, usb_disconnects, open_attempts = \
                        reset_and_capture_reconnecting(
                            ports["candidate"],
                            float(step.get("capture_seconds", 8.0)))
                    (args.output / f"{step_id}.ndjson").write_bytes(reboot_raw)
                    captured_ready, captured_recovery = parse_boot_records(
                        reboot_raw)
                    timing = {
                        "bytes": len(reboot_raw),
                        "sha256": hashlib.sha256(reboot_raw).hexdigest(),
                        "first_byte_ms": None,
                        "ready_marker_ms": ready_ms,
                        "usb_disconnects": usb_disconnects,
                        "usb_open_attempts": open_attempts,
                        "reconnecting_capture": True,
                    }
                    product = PassiveSerial(
                        ports["candidate"], 115200, timeout=0.5)
                    synchronize_console(product, 30.0)
                    devices["candidate"] = product
                    ready_after = query(
                        product, b"metrics", "leshy.boot.v1", "ready")
                    recovery_at_reboot = query(
                        product, b"storage.product.boot-recovery",
                        "leshy.storage.product_boot_recovery.v1", "state")
                    operation_failures.extend(boot_failures(
                        ready_after, recovery_at_reboot,
                        args.expected_version, app_identity,
                        args.expected_cid))
                    # The boot transcript guarantees the exact candidate and
                    # input readiness. Product recovery is a query contract,
                    # so it is verified in full on the reconnected console.
                    operation_failures.extend(boot_ready_failures(
                        captured_ready, args.expected_version, app_identity))
                    record = {
                        "before": before_reboot,
                        "fixture": fixture_before_reboot,
                        "captured_ready": captured_ready,
                        "captured_recovery": captured_recovery,
                        "recovery_observation": "post_reconnect_query",
                        "timing": timing,
                        "ready": ready_after,
                        "recovery": recovery_at_reboot,
                    }
                    reports[step_id] = record
                elif operation in ("poll_query", "query"):
                    if role == "fixture" and not fixture_armed:
                        admission_command = (
                            f"fixture.begin {run_id} "
                            f"{fixture_app_identity} "
                            f"{args.expected_fixture_id}")
                        fixture_admission = query(
                            devices[role], admission_command.encode("ascii"),
                            "leshy.hil.fixture.signal.v1", "armed", timeout=5.0)
                        admission_failures = fixture_admission_failures(
                            fixture_admission,
                            args.expected_fixture_version,
                            args.expected_fixture_id,
                            fixture_app_identity)
                        admission_failures.extend(expect(
                            fixture_admission, {
                                "state": "armed",
                                "session_id": run_id,
                                "armed": True,
                            }, "fixture_admission"))
                        failures.extend(admission_failures)
                        if admission_failures:
                            raise RuntimeError("fixture admission failed")
                        fixture_armed = True
                    command = render_query_command(step["command"], {
                        "session_id": run_id,
                        "fixture_app_sha256": fixture_app_identity,
                        "fixture_id": args.expected_fixture_id or "",
                    })
                    if operation == "query":
                        record = query(
                            devices[role], command.encode("ascii"),
                            step["response_schema"],
                            step.get("kind", "state"),
                            timeout=float(step.get("timeout", 15.0)))
                    else:
                        poll_deadline = time.monotonic() + float(
                            step.get("timeout", 15.0))
                        while True:
                            remaining = poll_deadline - time.monotonic()
                            if remaining <= 0:
                                raise TimeoutError(
                                    f"poll condition did not match: {step_id}")
                            record = query(
                                devices[role], command.encode("ascii"),
                                step["response_schema"],
                                step.get("kind", "state"),
                                timeout=min(5.0, remaining))
                            if not expect(record, step["until"], step_id):
                                break
                            time.sleep(min(
                                float(step.get("interval", 0.1)),
                                max(0.0, poll_deadline - time.monotonic())))
                    reports[step_id] = record
                elif operation == "stream":
                    stream_name = step.get("name", step_id)
                    record, payload = read_framed_stream(
                        devices[role], step["command"],
                        streams / f"{stream_name}.csv",
                        float(step.get("timeout", 15.0)))
                    stream_payloads[step_id] = payload
                    operation_failures.extend(expect(record["end"], {
                        "bytes": len(payload),
                    }, f"{step_id}.end"))
                    if (not payload.startswith(
                            b"pulse_index,level,duration_us\r\n") or
                            b"\n" in payload.replace(b"\r\n", b"") or
                            not payload.endswith(b"\r\n")):
                        operation_failures.append(
                            f"{step_id}: non-canonical pulse CSV framing")
                    reports[step_id] = record
                elif operation == "capture":
                    record = capture(devices[role], frames,
                                     step.get("name", step_id))
                    captures[step_id] = record
                step_failures = list(operation_failures)
                if role == "fixture":
                    nrf_start = command.startswith(
                        "fixture.nrf24.carrier.start ")
                    cc_ook_once = command.startswith(
                        "fixture.cc1101.ook.once ")
                    cc_fsk_once = command.startswith(
                        "fixture.cc1101.fsk.once ")
                    if not nrf_start:
                        step_failures.extend(fixture_inactive_failures(
                            record, step_id))
                    step_failures.extend(expect(
                        record, {"session_id": run_id}, step_id))
                    if command.startswith("fixture.ir.nec.once "):
                        step_failures.extend(expect(record, {
                            "state": "complete",
                            "vector_id": "nec-10-34",
                            "armed": False,
                            "start_count": int(
                                fixture_identity.get("start_count", 0)) + 1,
                            "stop_count": int(
                                fixture_identity.get("stop_count", 0)) + 1,
                            "emission_count": int(
                                fixture_identity.get("emission_count", 0)) + 1,
                        }, step_id))
                        step_failures.extend(evaluate_checks(record, [{
                            "path": "last_duration_us", "op": "gt",
                            "value": 0,
                        }, {
                            "path": "last_duration_us", "op": "lte",
                            "value": 100000,
                        }], step_id))
                        if fixture_vector_executed:
                            step_failures.append(
                                f"{step_id}: fixture vector repeated")
                        fixture_vector_executed = "infrared_nec"
                    elif cc_ook_once or cc_fsk_once:
                        signal = "cc1101_fsk" if cc_fsk_once else "cc1101_ook"
                        vector = ("cc1101-fsk-433920-min" if cc_fsk_once else
                                  "cc1101-ook-433920-min")
                        packet_count = 1 if cc_fsk_once else 4
                        step_failures.extend(expect(record, {
                            "state": "complete",
                            "signal": signal,
                            "vector_id": vector,
                            "armed": False,
                            "start_count": int(
                                fixture_identity.get("start_count", 0)) + 1,
                            "stop_count": int(
                                fixture_identity.get("stop_count", 0)) + 1,
                            "emission_count": int(
                                fixture_identity.get("emission_count", 0)) + 1,
                            "cc_frequency_khz": 433920,
                            "cc_power_dbm": -15,
                            "cc_patable": 29,
                            "cc_packet_length": 60,
                            "cc_hardware_auto_idle": True,
                            "cc_transmit_active": False,
                            "cc_idle": True,
                            "cc_power_cleared": True,
                            "cc_tx_fifo_cleared": True,
                            "cc_start_error": "none",
                            "cc_part_number": 0,
                            "cc_tx_strobes": packet_count,
                            "cc_patable_writes": 2,
                            "cc_tx_fifo_writes": packet_count,
                            "cc_tx_fifo_bytes": packet_count * 60,
                        }, step_id))
                        step_failures.extend(evaluate_checks(record, [{
                            "path": "last_duration_us", "op": "gt",
                            "value": 0,
                        }, {
                            "path": "last_duration_us", "op": "lte",
                            "value": 250000,
                        }, {
                            "path": "cc_version", "op": "ne",
                            "value": 0,
                        }, {
                            "path": "cc_version", "op": "ne",
                            "value": 255,
                        }], step_id))
                        if fixture_vector_executed:
                            step_failures.append(
                                f"{step_id}: fixture vector repeated")
                        fixture_vector_executed = signal
                    elif nrf_start:
                        step_failures.extend(expect(record, {
                            "state": "running",
                            "signal": "nrf24_carrier",
                            "vector_id": "nrf24-ch42-min-2s",
                            "armed": False,
                            "start_count": int(
                                fixture_identity.get("start_count", 0)) + 1,
                            "stop_count": int(
                                fixture_identity.get("stop_count", 0)),
                            "emission_count": int(
                                fixture_identity.get("emission_count", 0)),
                            "last_duration_us": 0,
                            "ir_tx_inactive": True,
                            "nrf_ce_inactive": False,
                            "nrf_powered_down": False,
                            "nrf_carrier_active": True,
                            "buzzer_inactive": True,
                            "nrf_channel": 42,
                            "nrf_frequency_mhz": 2442,
                            "nrf_power_dbm": -18,
                        }, step_id))
                        if fixture_vector_executed:
                            step_failures.append(
                                f"{step_id}: fixture vector repeated")
                        fixture_vector_executed = "nrf24_carrier"
                    elif (fixture_vector_executed == "nrf24_carrier" and
                          record.get("state") == "complete"):
                        step_failures.extend(expect(record, {
                            "signal": "nrf24_carrier",
                            "vector_id": "nrf24-ch42-min-2s",
                            "start_count": int(
                                fixture_identity.get("start_count", 0)) + 1,
                            "stop_count": int(
                                fixture_identity.get("stop_count", 0)) + 1,
                            "emission_count": int(
                                fixture_identity.get("emission_count", 0)) + 1,
                            "nrf_carrier_active": False,
                        }, step_id))
                        step_failures.extend(evaluate_checks(record, [{
                            "path": "last_duration_us", "op": "gte",
                            "value": 2000000,
                        }, {
                            "path": "last_duration_us", "op": "lte",
                            "value": 2500000,
                        }], step_id))
                if isinstance(step.get("expect"), dict):
                    step_failures.extend(evaluate_expectations(
                        record, step["expect"], step_id))
                if isinstance(step.get("checks"), list):
                    step_failures.extend(evaluate_checks(
                        record, step["checks"], step_id))
                failures.extend(step_failures)
                step_results.append({
                    "id": step_id, "op": operation, "target": role,
                    "elapsed_ms": round(
                        (time.monotonic() - started) * 1000.0, 3),
                    "passed": not step_failures,
                    "failures": step_failures,
                })
                if step_failures:
                    raise RuntimeError(f"scenario step failed: {step_id}")

            final = reports.get("final")
            if not isinstance(final, dict):
                final = query(product, b"ui.state", "leshy.ui.v1", "state")
            reports["final"] = final
            recovery_after = query(
                product, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            metrics_after = query(product, b"metrics", "leshy.boot.v1", "ready")
            input_state = query(
                product, b"input.state", "leshy.input.frontend.v1", "state")
            safe_outputs = query(
                product, b"hardware.safe-outputs",
                "leshy.hardware.safe-outputs.v1", "state")
            invariants = scenario.get("invariants", {})
            if invariants.get("final_home_zero_lease", True) and (
                    final.get("page") != "home" or
                    final.get("runtime_owner") != "none" or
                    final.get("lease_mask") != 0):
                failures.append("invariant: final Home/zero lease failed")
            if invariants.get("storage_unchanged", True) and (
                    recovery_after.get("generation") !=
                    recovery_before.get("generation") or
                    recovery_after.get("observations") !=
                    recovery_before.get("observations") or
                    recovery_after.get("physical_write_calls") != 0):
                failures.append("invariant: product storage changed")
            generation_report = invariants.get(
                "storage_generation_from_report")
            if generation_report is not None:
                saved = reports.get(generation_report, {})
                saved_generation = saved.get("persist_generation")
                before_generation = recovery_before.get("generation")
                if (not isinstance(saved_generation, int) or
                        not isinstance(before_generation, int) or
                        saved_generation != before_generation + 1 or
                        recovery_after.get("generation") != saved_generation or
                        recovery_after.get("physical_write_calls") != 0):
                    failures.append(
                        "invariant: persisted generation continuity failed")
            byte_exact_streams = invariants.get("byte_exact_streams")
            if byte_exact_streams is not None:
                if (not isinstance(byte_exact_streams, list) or
                        len(byte_exact_streams) != 2 or
                        any(not isinstance(value, str)
                            for value in byte_exact_streams) or
                        any(value not in stream_payloads
                            for value in byte_exact_streams) or
                        stream_payloads.get(byte_exact_streams[0]) !=
                        stream_payloads.get(byte_exact_streams[1])):
                    failures.append(
                        "invariant: byte-exact stream comparison failed")
            if invariants.get("heap_free_unchanged", True) and \
                    metrics_after.get("heap_free") != boot.get("heap_free"):
                failures.append("invariant: heap_free changed")
            if invariants.get("input_clean", True) and (
                    input_state.get("queue_drops") != 0 or
                    input_state.get("read_errors") != 0):
                failures.append("invariant: input errors/drops")
            if invariants.get("safe_outputs", True) and (
                    safe_outputs.get("buzzer_inactive") is not True or
                    safe_outputs.get("nrf_ce_inactive") is not True):
                failures.append("invariant: safe outputs inactive failed")
            scenario_completed = not failures
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "runner_source_sha256": sha256_file(Path(__file__).resolve()),
        "scenario": {
            "schema": scenario.get("schema"), "id": scenario.get("id"),
            "path": str(args.scenario), "sha256": scenario_sha,
        },
        "passed": bool(args.flash or args.reuse_exact_flash) and not failures,
        "gate_eligible": scenario.get("gate_eligible", False),
        "checkpoint": scenario.get("checkpoint"),
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "firmware_sha256": firmware_sha,
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "exact_flash_reused": args.reuse_exact_flash,
        },
        "fixture": ({
            "version": args.expected_fixture_version,
            "source_commit": args.fixture_source_commit,
            "firmware_sha256": fixture_sha,
            "app_elf_sha256": fixture_app_identity,
            "fixture_id": args.expected_fixture_id,
            "profile_sha256": fixture_profile_sha,
            "flashed": args.flash_fixture,
            "exact_flash_reused": args.reuse_exact_fixture_flash,
            "identity": fixture_identity,
            "admission": fixture_admission,
            "cleanup": fixture_cleanup,
        } if needs_fixture else None),
        "ports": ports,
        "expected_cid": args.expected_cid,
        "boot": boot,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "metrics_after": metrics_after,
        "reports": reports,
        "input": input_state,
        "safe_outputs": safe_outputs,
        "cleanup": cleanup,
        "captures": captures,
        "trace": trace,
        "steps": step_results,
        "invariants": scenario.get("invariants", {}),
        "limits": scenario.get("limits", {}),
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA, "scenario_id": scenario.get("id"),
        "passed": result["passed"], "steps": len(step_results),
        "failures": failures, "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
