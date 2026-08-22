#!/usr/bin/env python3
"""Run a declarative one- or two-device Leshy HIL scenario fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)
from run_1x_subghz_raw_hil import select_home_app


SCENARIO_SCHEMA = "leshy.hil.scenario.v1"
RUN_SCHEMA = "leshy.hil.scenario_run.v1"
SUPPORTED_OPERATIONS = {
    "action", "capture", "cleanup", "query", "select_home_app", "sleep",
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


def validate_scenario(scenario: dict[str, Any], ports: dict[str, str]) -> None:
    if scenario.get("schema") != SCENARIO_SCHEMA:
        raise ValueError("scenario schema mismatch")
    for key in ("id", "checkpoint", "steps", "limits"):
        if key not in scenario:
            raise ValueError(f"scenario field is missing: {key}")
    devices = scenario.get("devices", {"candidate": {"required": True}})
    if not isinstance(devices, dict) or "candidate" not in devices:
        raise ValueError("scenario devices must declare candidate")
    for role, policy in devices.items():
        required = isinstance(policy, dict) and policy.get("required") is True
        if required and role not in ports:
            raise ValueError(f"required device role is not bound: {role}")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("scenario steps must be a non-empty list")
    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str):
            raise ValueError("every step requires a string id")
        if step["id"] in seen:
            raise ValueError(f"duplicate step id: {step['id']}")
        seen.add(step["id"])
        if step.get("op") not in SUPPORTED_OPERATIONS:
            raise ValueError(f"unsupported operation in {step['id']}")
        role = step.get("target", "candidate")
        if step["op"] != "sleep" and role not in ports:
            raise ValueError(f"step {step['id']} targets unbound role {role}")
        if step["op"] == "sleep" and not 0 <= step.get("seconds", -1) <= 60:
            raise ValueError(f"step {step['id']} sleep must be 0..60 seconds")


def main() -> int:
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
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    firmware_sha = sha256_file(candidate)
    app_identity = app_elf_sha256(candidate)
    scenario_sha = hashlib.sha256(args.scenario.read_bytes()).hexdigest()
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

    try:
        if args.flash:
            flash_candidate(ports["candidate"], candidate,
                            args.flash_offset, args.flash_baud)
            time.sleep(0.5)
        with ExitStack() as stack:
            devices: dict[str, PassiveSerial] = {}
            for role, port in ports.items():
                device = stack.enter_context(
                    PassiveSerial(port, 115200, timeout=0.5))
                synchronize_console(device, 30.0)
                devices[role] = device
            product = devices["candidate"]
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
                elif operation == "query":
                    record = query(
                        devices[role], step["command"].encode("ascii"),
                        step["response_schema"], step.get("kind", "state"),
                        timeout=float(step.get("timeout", 15.0)))
                    reports[step_id] = record
                elif operation == "capture":
                    record = capture(devices[role], frames,
                                     step.get("name", step_id))
                    captures[step_id] = record
                step_failures = []
                if isinstance(step.get("expect"), dict):
                    step_failures.extend(expect(
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
            cleanup = best_effort_cleanup(product)
            if not cleanup.get("complete"):
                failures.append("cleanup: terminal zero-lease state unproven")
    except Exception as error:
        failures.append(f"runner: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "run_id": secrets.token_hex(16),
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
