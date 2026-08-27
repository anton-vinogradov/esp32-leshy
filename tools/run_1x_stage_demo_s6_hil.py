#!/usr/bin/env python3
"""One-flash DEMO-S6 path: two Surveys, every diff evidence, offline USB export."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_RUNNER = ROOT / "tools/run_1x_product_survey_hil.py"
TARGETS_RUNNER = ROOT / "tools/run_1x_targets_evidence_hil.py"
COMPANION_RUNNER = ROOT / "tools/run_1x_companion_usb_delta_hil.py"
SCHEMA = "leshy.stage_demo_s6.run.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def artifact_manifest(output: Path) -> None:
    lines: list[str] = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "artifacts.sha256":
            lines.append(f"{digest(path)}  {path.relative_to(output)}")
    (output / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def expected_candidate(args: argparse.Namespace | SimpleNamespace) -> dict[str, Any]:
    return {
        "version": args.expected_version,
        "firmware_sha256": digest(args.firmware),
        "app_elf_sha256": app_elf_sha256(args.firmware),
    }


def product_command(args: argparse.Namespace | SimpleNamespace, output: Path,
                    flash: bool) -> list[str]:
    command = [
        sys.executable, str(PRODUCT_RUNNER),
        "--port", args.port,
        "--firmware", str(args.firmware),
        "--expected-version", args.expected_version,
        "--expected-cid", args.expected_cid,
        "--output", str(output),
        "--release-cycle",
        "--flash-baud", str(args.flash_baud),
    ]
    if flash:
        command.append("--flash")
    return command


def targets_command(args: argparse.Namespace | SimpleNamespace,
                    output: Path) -> list[str]:
    return [
        sys.executable, str(TARGETS_RUNNER),
        "--port", args.port,
        "--firmware", str(args.firmware),
        "--elf", str(args.elf),
        "--map", str(args.map),
        "--expected-version", args.expected_version,
        "--source-commit", args.source_commit,
        "--output", str(output),
        "--flash-baud", str(args.flash_baud),
        "--reuse-exact-flash",
        "--open-every-evidence",
    ]


def companion_command(args: argparse.Namespace | SimpleNamespace,
                      output: Path) -> list[str]:
    return [
        sys.executable, str(COMPANION_RUNNER),
        "--port", args.port,
        "--firmware", str(args.firmware),
        "--elf", str(args.elf),
        "--map", str(args.map),
        "--expected-version", args.expected_version,
        "--source-commit", args.source_commit,
        "--output", str(output),
        "--flash-baud", str(args.flash_baud),
        "--reuse-exact-flash",
    ]


def run_child(command: list[str], log_path: Path) -> int:
    process = subprocess.run(
        command, cwd=ROOT, check=False, capture_output=True, text=True
    )
    log_path.write_text(process.stdout + process.stderr, encoding="utf-8")
    return process.returncode


def _product_failures(run: dict[str, Any], expected: dict[str, Any],
                      expected_cid: str, *, flashed: bool,
                      label: str) -> list[str]:
    failures: list[str] = []
    candidate = run.get("candidate", {})
    if not (
        run.get("schema") == "leshy.product_survey_hil.run.v1"
        and run.get("passed") is True
        and run.get("failures") == []
        and run.get("expected_cid") == expected_cid
        and candidate.get("version") == expected["version"]
        and candidate.get("firmware_sha256") == expected["firmware_sha256"]
        and candidate.get("app_elf_sha256") == expected["app_elf_sha256"]
        and candidate.get("flashed") is flashed
        and run.get("gate_eligible") is flashed
    ):
        failures.append(f"{label}: candidate/status/CID mismatch")
    committed = run.get("committed", {})
    before = run.get("boot_before", {}).get("recovery", {})
    if not (
        isinstance(before.get("generation"), int)
        and isinstance(committed.get("survey_generation"), int)
        and committed.get("survey_generation") == before.get("generation") + 1
        and isinstance(committed.get("survey_observations"), int)
        and committed.get("survey_observations") > 0
        and run.get("release_cycle") is True
    ):
        failures.append(f"{label}: one-cycle Survey publication mismatch")
    final = run.get("final_state", {})
    if not (
        final.get("page") == "home"
        and final.get("runtime_owner") == "none"
        and final.get("lease_mask") == 0
        and run.get("cleanup_before_reboot", {}).get("complete") is True
        and run.get("cleanup_final", {}).get("complete") is True
    ):
        failures.append(f"{label}: final cleanup mismatch")
    return failures


def validate_reused_flash_lineage(
        lineage: Path, expected: dict[str, Any], port: str
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    root = lineage if lineage.is_dir() else lineage.parent
    parent_path = root / "run.json" if lineage.is_dir() else lineage
    baseline_path = root / "baseline-survey/run.json"
    if not parent_path.is_file() or not baseline_path.is_file():
        return {}, ["reused flash lineage run/baseline record missing"]
    parent = load_json(parent_path)
    baseline = load_json(baseline_path)
    candidate = parent.get("candidate", {})
    child_candidate = baseline.get("candidate", {})
    ready = baseline.get("boot_before", {}).get("ready", {})
    if not (
        parent.get("schema") == SCHEMA
        and parent.get("status") == "failed"
        and parent.get("installation", {}).get("application_flash_count") == 1
        and parent.get("target", {}).get("port") == port
        and candidate == expected
        and child_candidate.get("flashed") is True
        and child_candidate.get("version") == expected["version"]
        and child_candidate.get("firmware_sha256") == expected["firmware_sha256"]
        and child_candidate.get("app_elf_sha256") == expected["app_elf_sha256"]
        and ready.get("version") == expected["version"]
        and ready.get("app_elf_sha256") == expected["app_elf_sha256"]
        and baseline.get("committed") == {}
        and baseline.get("cleanup_before_reboot", {}).get("complete") is True
    ):
        failures.append("reused exact-flash lineage mismatch")
    retained = {
        "path": str(root),
        "run_sha256": digest(parent_path),
        "baseline_run_sha256": digest(baseline_path),
        "source_commit": parent.get("source_commit"),
        "failure_stage": "baseline-survey-pre-workflow",
    }
    return retained, failures


def validate_children(baseline: dict[str, Any], repeat: dict[str, Any],
                      targets: dict[str, Any], companion: dict[str, Any],
                      expected: dict[str, Any], expected_cid: str,
                      source_commit: str, *,
                      baseline_flashed: bool = True
                      ) -> tuple[dict[str, Any], list[str]]:
    failures = _product_failures(
        baseline, expected, expected_cid, flashed=baseline_flashed,
        label="baseline"
    )
    failures.extend(_product_failures(
        repeat, expected, expected_cid, flashed=False, label="repeat"
    ))
    baseline_generation = baseline.get("committed", {}).get("survey_generation")
    repeat_before = repeat.get("boot_before", {}).get("recovery", {}).get(
        "generation")
    repeat_generation = repeat.get("committed", {}).get("survey_generation")
    if not (
        isinstance(baseline_generation, int)
        and repeat_before == baseline_generation
        and repeat_generation == baseline_generation + 1
    ):
        failures.append("Survey generations are not one contiguous baseline/repeat pair")

    target_candidate = targets.get("candidate", {})
    target_rows = targets.get("targets", {}).get("rows", [])
    target_details = targets.get("targets", {}).get("evidence_details", [])
    comparison_count = targets.get("targets", {}).get("list", {}).get(
        "comparison_count")
    if not (
        targets.get("schema") == "leshy.targets_evidence_hil.run.v1"
        and targets.get("status") == "pass"
        and targets.get("source_commit") == source_commit
        and targets.get("exact_cid") == expected_cid
        and target_candidate.get("version") == expected["version"]
        and target_candidate.get("firmware_sha256") == expected["firmware_sha256"]
        and target_candidate.get("app_elf_sha256") == expected["app_elf_sha256"]
        and targets.get("flash_count") == 0
        and targets.get("exact_flash_reused") is True
        and targets.get("generations") == [baseline_generation, repeat_generation]
        and isinstance(comparison_count, int)
        and comparison_count > 0
        and len(target_rows) == comparison_count
        and len(target_details) == comparison_count
        and targets.get("storage_write_calls") == 0
        and targets.get("radio_tx_commands") == 0
        and targets.get("cleanup", {}).get("complete") is True
    ):
        failures.append("Targets every-conclusion evidence path mismatch")

    companion_candidate = companion.get("candidate", {})
    sessions = companion.get("sessions", {}).get("details", [])
    session_generations = [item.get("generation") for item in sessions]
    snapshot = companion.get("offline_snapshot", {})
    companion_compare_count = companion.get("targets", {}).get("compare_count")
    if not (
        companion.get("schema") == "leshy.companion_usb_delta_hil.run.v1"
        and companion.get("status") == "pass"
        and companion.get("source_commit") == source_commit
        and companion.get("exact_cid") == expected_cid
        and companion_candidate.get("version") == expected["version"]
        and companion_candidate.get("firmware_sha256") == expected["firmware_sha256"]
        and companion_candidate.get("app_elf_sha256") == expected["app_elf_sha256"]
        and companion.get("flash_count") == 0
        and companion.get("exact_flash_reused") is True
        and session_generations == [baseline_generation, repeat_generation]
        and companion_compare_count == comparison_count
        and snapshot.get("canonical_round_trip") is True
        and snapshot.get("counts", {}).get("sessions") == 2
        and snapshot.get("counts", {}).get("comparison_items") == comparison_count
        and isinstance(snapshot.get("snapshot_id"), str)
        and len(snapshot.get("snapshot_id")) == 64
        and companion.get("host_network_tools_invoked") is False
        and companion.get("active_mac_wifi_touched") is False
        and companion.get("wifi_softap_started") is False
        and companion.get("raw_radio_tx_commands") == 0
        and companion.get("storage_write_commands") == 0
        and companion.get("cleanup", {}).get("complete") is True
    ):
        failures.append("offline USB companion pair/export/network-isolation mismatch")

    summary = {
        "baseline_generation": baseline_generation,
        "repeat_generation": repeat_generation,
        "comparison_items": comparison_count,
        "evidence_views_opened": len(target_details),
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_bytes": snapshot.get("bytes"),
        "targets": snapshot.get("counts", {}).get("targets"),
    }
    return summary, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", default=EXPECTED_CID)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--reuse-exact-flash", action="store_true",
        help="reuse the exact image from a retained pre-workflow flash lineage",
    )
    parser.add_argument(
        "--reused-flash-lineage", type=Path,
        help="failed DEMO-S6 output whose exact flash and clean cleanup are retained",
    )
    args = parser.parse_args()
    args.firmware = args.firmware.resolve()
    args.elf = args.elf.resolve()
    args.map = args.map.resolve()
    args.output = args.output.resolve()
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if args.expected_cid != EXPECTED_CID:
        parser.error("DEMO-S6 is bound to the enrolled original-DIV CID")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    if args.reuse_exact_flash != (args.reused_flash_lineage is not None):
        parser.error(
            "--reuse-exact-flash and --reused-flash-lineage are required together"
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != args.source_commit or status:
        parser.error("exact DEMO-S6 requires clean committed HEAD")

    expected = expected_candidate(args)
    flash_lineage: dict[str, Any] = {}
    failures: list[str] = []
    if args.reuse_exact_flash:
        flash_lineage, lineage_failures = validate_reused_flash_lineage(
            args.reused_flash_lineage.resolve(), expected, args.port
        )
        failures.extend(lineage_failures)

    args.output.mkdir(parents=True)
    child_specs = [
        ("baseline-survey", product_command(
            args, args.output / "baseline-survey", not args.reuse_exact_flash)),
        ("repeat-survey", product_command(
            args, args.output / "repeat-survey", False)),
        ("targets-evidence", targets_command(
            args, args.output / "targets-evidence")),
        ("companion-offline", companion_command(
            args, args.output / "companion-offline")),
    ]
    child_exits: dict[str, int] = {}
    if not failures:
        for name, command in child_specs:
            exit_code = run_child(command, args.output / f"{name}.log")
            child_exits[name] = exit_code
            if exit_code != 0:
                failures.append(f"{name}: child exit {exit_code}")
                break

    runs: dict[str, dict[str, Any]] = {}
    for name, _ in child_specs:
        run_path = args.output / name / "run.json"
        if run_path.is_file():
            runs[name] = load_json(run_path)
        elif name not in child_exits:
            continue
        else:
            failures.append(f"{name}: run.json missing")

    summary: dict[str, Any] = {}
    if not failures and len(runs) == len(child_specs):
        summary, validation_failures = validate_children(
            runs["baseline-survey"], runs["repeat-survey"],
            runs["targets-evidence"], runs["companion-offline"],
            expected, args.expected_cid, args.source_commit,
            baseline_flashed=not args.reuse_exact_flash,
        )
        failures.extend(validation_failures)

    result = {
        "schema": SCHEMA,
        "status": "pass_demo_path" if not failures else "failed",
        "passed": not failures,
        "demo_path_eligible": not failures,
        "s6_exit_eligible": False,
        "s6_exit_blockers": [
            "physical_http_parity_requires_dedicated_client",
            "s5_predecessor_physical_gate_requires_replacement_div",
        ],
        "failures": failures,
        "candidate": expected,
        "source_commit": args.source_commit,
        "runner_sha256": digest(Path(__file__).resolve()),
        "child_runner_sha256": {
            "product": digest(PRODUCT_RUNNER),
            "targets": digest(TARGETS_RUNNER),
            "companion": digest(COMPANION_RUNNER),
        },
        "installation": {
            "application_flash_count": 0 if args.reuse_exact_flash else 1,
            "exact_flash_reused": args.reuse_exact_flash,
            "reused_flash_lineage": flash_lineage,
        },
        "target": {
            "port": args.port,
            "serial_port_discovery_calls": 0,
            "ports_opened": [args.port],
            "cardputer_ports_opened": 0,
        },
        "transport": {
            "host_network_tools_invoked": False,
            "active_mac_wifi_touched": False,
            "wifi_softap_started": False,
        },
        "summary": summary,
        "children": {
            name: {
                "exit_code": child_exits.get(name),
                "run_sha256": (
                    digest(args.output / name / "run.json")
                    if (args.output / name / "run.json").is_file() else ""
                ),
            }
            for name, _ in child_specs
        },
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": SCHEMA,
        "status": result["status"],
        "output": str(args.output),
        "summary": summary,
        "failures": failures,
    }, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
