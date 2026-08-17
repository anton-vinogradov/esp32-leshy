#!/usr/bin/env python3
"""Run product and isolated generic HIL once, restoring enrolled state.

This is a foreground orchestrator for the ephemeral GitHub Actions runner. It
never listens between releases: one invocation owns one attached board, tests
the exact candidate twice, and exits after read-only re-enrollment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from esp_app_identity import app_elf_sha256
from run_1x_product_survey_hil import parse_boot_records, reset_capture, valid_cid
from run_1x_prerelease_hil import sha256_file, write_json


RUN_SCHEMA = "leshy.release_hil.run.v1"


def execute(command: Sequence[str], log_prefix: Path) -> int:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    log_prefix.with_suffix(".stdout.log").write_text(
        result.stdout, encoding="utf-8"
    )
    log_prefix.with_suffix(".stderr.log").write_text(
        result.stderr, encoding="utf-8"
    )
    return result.returncode


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def send_command(port: str, command: str, schema: str,
                 kind: str = "result") -> dict[str, Any]:
    from capture_1x_ui import PassiveSerial, read_json, synchronize_console

    device = PassiveSerial(port, 115200, timeout=0.25)
    with device:
        synchronize_console(device)
        device.write(command.encode("ascii") + b"\n")
        device.flush()
        return read_json(device, schema, kind, timeout=20.0)


def query_final_state(port: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from capture_1x_ui import PassiveSerial, read_json, synchronize_console

    device = PassiveSerial(port, 115200, timeout=0.25)
    with device:
        synchronize_console(device)
        device.write(b"storage.product.boot-recovery\n")
        device.flush()
        recovery = read_json(
            device, "leshy.storage.product_boot_recovery.v1", "state",
            timeout=20.0,
        )
        device.write(b"ui.state\n")
        device.flush()
        state = read_json(device, "leshy.ui.v1", "state")
    return recovery, state


def unenroll_failures(record: dict[str, Any], cid: str) -> list[str]:
    expected = {
        "mode": "unenroll", "status": "valid", "was_enrolled": True,
        "cleared_fingerprint": cid, "nvs_key_removed": True,
        "sd_accessed": False, "sd_data_untouched": True,
        "active_catalog_unchanged": True, "reboot_required": True,
        "physical_write_calls": 0,
    }
    return [
        f"unenroll.{field}: {record.get(field)!r} != {wanted!r}"
        for field, wanted in expected.items() if record.get(field) != wanted
    ]


def unenroll_outcome(record: dict[str, Any], cid: str) -> tuple[bool, bool,
                                                                 list[str]]:
    failures = unenroll_failures(record, cid)
    enrollment_removed = record.get("nvs_key_removed") is True
    return enrollment_removed, not failures, failures


def reenroll_failures(record: dict[str, Any], cid: str,
                      generation: int, observations: int) -> list[str]:
    expected = {
        "mode": "enroll", "status": "valid",
        "expected_fingerprint": cid, "observed_fingerprint": cid,
        "fingerprint_matched": True, "mounted_read_only": True,
        "read_only_guaranteed": True, "write_enabled": False,
        "blocked_write_attempts": 0, "catalog_status": "admitted",
        "catalog_admitted": True, "generation": generation,
        "observations": observations, "enrollment_saved": True,
        "owned_after": 0, "cleanup_complete": True,
        "physical_write_calls": 0,
    }
    return [
        f"reenroll.{field}: {record.get(field)!r} != {wanted!r}"
        for field, wanted in expected.items() if record.get(field) != wanted
    ]


def final_failures(ready: dict[str, Any], recovery: dict[str, Any],
                   state: dict[str, Any], version: str, app_identity: str,
                   cid: str, generation: int,
                   observations: int) -> list[str]:
    failures: list[str] = []
    for field, wanted in {
        "version": version, "app_elf_sha256": app_identity,
        "buzzer_inactive": True, "input_detected": True,
    }.items():
        if ready.get(field) != wanted:
            failures.append(f"final_ready.{field}: {ready.get(field)!r} != {wanted!r}")
    for field, wanted in {
        "status": "admitted", "enrolled": True,
        "expected_fingerprint": cid, "observed_fingerprint": cid,
        "fingerprint_matched": True, "mounted_read_only": True,
        "read_only_guaranteed": True, "blocked_write_attempts": 0,
        "catalog_status": "admitted", "catalog_admitted": True,
        "generation": generation, "observations": observations,
        "integrity": "valid", "owned_after": 0,
        "cleanup_complete": True, "physical_write_calls": 0,
    }.items():
        if recovery.get(field) != wanted:
            failures.append(
                f"final_recovery.{field}: {recovery.get(field)!r} != {wanted!r}"
            )
    for field, wanted in {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "library_persistent": True, "library_simulated": False,
        "library_generation": generation,
    }.items():
        if state.get(field) != wanted:
            failures.append(f"final_state.{field}: {state.get(field)!r} != {wanted!r}")
    return failures


def finalize(output: Path, result: dict[str, Any]) -> None:
    write_json(output / "run.json", result)
    lines: list[str] = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {
            "artifacts.sha256", "runner-result.json"
        }:
            lines.append(f"{sha256_file(path)}  {path.relative_to(output)}")
    payload = "\n".join(lines) + "\n"
    (output / "artifacts.sha256").write_text(payload, encoding="utf-8")
    write_json(output / "runner-result.json", {
        "schema": "leshy.release_hil.runner_result.v1",
        "candidate_sha256": result.get("candidate_sha256"),
        "app_elf_sha256": result.get("candidate_app_elf_sha256"),
        "product_run_id": result.get("product", {}).get("run_id"),
        "generic_run_id": result.get("generic", {}).get("run_id"),
        "suite_id": result.get("generic", {}).get("suite_id"),
        "suite_revision": result.get("generic", {}).get("suite_revision"),
        "passed": result.get("passed", False),
        "gate_eligible": False,
        "bundle_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "trust_status": "unsigned_local_result",
        "reason": "release trust is established by GitHub Artifact Attestations",
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--flash-offset", default="0x10000")
    parser.add_argument("--flash-baud", default="460800")
    parser.add_argument("--boot-seconds", default="5.0")
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if not args.suite.is_file():
        parser.error(f"suite not found: {args.suite}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    args.output.mkdir(parents=True)

    candidate_hash = sha256_file(args.firmware)
    candidate_app = app_elf_sha256(args.firmware)
    failures: list[str] = []
    product_dir = args.output / "product"
    generic_dir = args.output / "generic"
    product_command = [
        sys.executable, str(Path(__file__).with_name("run_1x_product_survey_hil.py")),
        "--port", args.port, "--firmware", str(args.firmware),
        "--expected-version", args.expected_version,
        "--output", str(product_dir), "--flash-offset", args.flash_offset,
        "--flash-baud", args.flash_baud, "--boot-seconds", args.boot_seconds,
    ]
    if args.flash:
        product_command.append("--flash")
    product_return = execute(product_command, args.output / "product-runner")
    product = load_object(product_dir / "run.json") if (
        product_dir / "run.json"
    ).is_file() else {}
    if product_return != 0 or product.get("passed") is not True or product.get(
            "gate_eligible") is not bool(args.flash):
        failures.append(f"product HIL failed with exit code {product_return}")
    cid = product.get("expected_cid")
    committed = product.get("committed", {})
    generation = committed.get("survey_generation")
    observations = committed.get("survey_observations")
    if not valid_cid(cid):
        failures.append("product HIL did not bind an exact enrolled CID")
    if not isinstance(generation, int) or not isinstance(observations, int):
        failures.append("product HIL did not expose committed generation/accounting")

    isolation: dict[str, Any] = {}
    enrollment_removed = False
    generic_allowed = False
    if not failures:
        try:
            unenroll = send_command(
                args.port, "storage.product.unenroll confirm",
                "leshy.storage.product_enrollment.v1",
            )
            isolation["unenroll"] = unenroll
            enrollment_removed, generic_allowed, transition_failures = (
                unenroll_outcome(unenroll, cid)
            )
            failures.extend(transition_failures)
        except Exception as error:
            failures.append(f"unenroll: {type(error).__name__}: {error}")

    generic: dict[str, Any] = {}
    generic_return: int | None = None
    if generic_allowed:
        generic_command = [
            sys.executable, str(Path(__file__).with_name("run_1x_prerelease_hil.py")),
            "--port", args.port, "--suite", str(args.suite),
            "--firmware", str(args.firmware),
            "--expected-version", args.expected_version,
            "--output", str(generic_dir), "--flash-offset", args.flash_offset,
            "--flash-baud", args.flash_baud, "--boot-seconds", args.boot_seconds,
        ]
        if args.flash:
            generic_command.append("--flash")
        try:
            generic_return = execute(
                generic_command, args.output / "generic-runner"
            )
            if (generic_dir / "run.json").is_file():
                generic = load_object(generic_dir / "run.json")
            if (generic_return != 0 or generic.get("passed") is not True or
                    generic.get("gate_eligible") is not bool(args.flash)):
                failures.append(
                    f"generic HIL failed with exit code {generic_return}"
                )
        except Exception as error:
            failures.append(f"generic: {type(error).__name__}: {error}")

    if enrollment_removed:
        # A reset guarantees the enrollment command runs from idle Home even if
        # the generic lane failed part-way through a workflow.
        try:
            reset_capture(
                args.port, args.output, "pre-reenroll", float(args.boot_seconds)
            )
        except Exception as error:
            failures.append(f"pre_reenroll_reset: {type(error).__name__}: {error}")
        try:
            reenroll = send_command(
                args.port,
                f"storage.product.enroll disposable-read-only {cid}",
                "leshy.storage.product_enrollment.v1",
            )
            isolation["reenroll"] = reenroll
            failures.extend(reenroll_failures(
                reenroll, cid, generation, observations
            ))
        except Exception as error:
            failures.append(f"reenroll: {type(error).__name__}: {error}")

    final_ready: dict[str, Any] = {}
    final_recovery: dict[str, Any] = {}
    final_state: dict[str, Any] = {}
    if isolation.get("reenroll", {}).get("enrollment_saved") is True:
        try:
            final_ready, boot_recovery, final_timing = reset_capture(
                args.port, args.output, "final-enrolled-boot",
                float(args.boot_seconds),
            )
            # Querying after console synchronization is authoritative; boot output
            # can be opened after the recovery record has already been broadcast.
            final_recovery, final_state = query_final_state(args.port)
            isolation["final_boot"] = {
                "ready": final_ready, "broadcast_recovery": boot_recovery,
                "recovery": final_recovery, "state": final_state,
                "timing": final_timing,
            }
            failures.extend(final_failures(
                final_ready, final_recovery, final_state,
                args.expected_version, candidate_app, cid, generation,
                observations,
            ))
        except Exception as error:
            failures.append(f"final_boot: {type(error).__name__}: {error}")

    result = {
        "schema": RUN_SCHEMA,
        "candidate_sha256": candidate_hash,
        "candidate_app_elf_sha256": candidate_app,
        "expected_version": args.expected_version,
        "candidate_flashed": args.flash,
        "product": {
            "run_id": product.get("run_id"), "return_code": product_return,
            "passed": product.get("passed", False),
            "gate_eligible": product.get("gate_eligible", False),
            "expected_cid": cid, "generation": generation,
            "observations": observations,
        },
        "generic": {
            "run_id": generic.get("run_id"), "return_code": generic_return,
            "passed": generic.get("passed", False),
            "gate_eligible": generic.get("gate_eligible", False),
            "suite_id": generic.get("suite_id"),
            "suite_revision": generic.get("suite_revision"),
        },
        "state_isolation": isolation,
        "passed": not failures,
        "gate_eligible": bool(args.flash) and not failures,
        "failures": failures,
    }
    finalize(args.output.resolve(), result)
    print(json.dumps({
        "output": str(args.output.resolve()), "passed": result["passed"],
        "gate_eligible": result["gate_eligible"], "failures": failures,
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
