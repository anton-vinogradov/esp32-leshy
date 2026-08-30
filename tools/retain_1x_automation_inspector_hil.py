#!/usr/bin/env python3
"""Retain compact, source-bound physical Automation Inspector evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-automation-inspector-1.0.0-dev.303"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-automation-inspector-1.0.0-dev.303.json"
EXPECTED_SOURCE = "ca5bf300289b310dd39845a530aa3fe7a2acd9c2"
EXPECTED_VERSION = "1.0.0-dev.303"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_FIRMWARE = "0976943e76b5d03feefb9acda58d07301597175bc41e62183a1cbcff884e95a2"
EXPECTED_ELF = "28a67093c3bedf01cae20289fa7bc162f973f614dff43b549eacc82be6216125"
EXPECTED_MAP = "f81d234557e19250b9fe99c7118942f2640108e6e66e1d0788d9e5a03b74979d"
EXPECTED_FACTORY = "8fc16699e4383b6e31050671ac04e2774ac58dcc368065ef1e9f4727b3e2b9ce"
EXPECTED_RUNNER = "68dd61776b4aac29234fca74a174171d1ec5d1aa4422f74aed6a048b53610ed8"
SCENARIOS = ("malformed_en", "unsigned_en", "malformed_ru", "unsigned_ru")
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationPackageHilFixture.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationPackageHilFixture.h",
    "firmware/leshy1/src/platform/arduino/BoardAutomationPackageReader.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationPackageReader.h",
    "tests/hil/delta-scopes/automation-inspector-1.0.0-dev.303.json",
    "tools/check_automation_hid_foundation.py",
    "tools/run_1x_automation_inspector_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_candidate(candidate: dict[str, Any]) -> None:
    require(candidate == {
        "app_elf_sha256": EXPECTED_ELF,
        "elf_sha256": EXPECTED_ELF,
        "firmware_bytes": 3541952,
        "firmware_sha256": EXPECTED_FIRMWARE,
        "map_sha256": EXPECTED_MAP,
        "source_commit": EXPECTED_SOURCE,
        "version": EXPECTED_VERSION,
    }, "exact candidate mismatch")


def validate(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.automation_inspector_hil.run.v1" and
            run.get("status") == "pass" and run.get("passed") is True and
            run.get("failures") == [], "passing inspector run required")
    require(run.get("source_commit") == EXPECTED_SOURCE and
            run.get("expected_cid") == EXPECTED_CID,
            "source/media identity mismatch")
    validate_candidate(run.get("candidate", {}))
    require(run.get("runner_source_sha256") == EXPECTED_RUNNER,
            "runner identity mismatch")
    require(run.get("flash_count") == 0 and
            run.get("hardware_reset_count") == 0 and
            run.get("installed_candidate_reused") is True,
            "accepted run must reuse the singly flashed candidate")
    policy = run.get("policy", {})
    require(policy == {
        "delta_only": True,
        "fixture_scope": "/leshy-hil/<run-id>",
        "forbidden_ports_touched": [],
        "full_hil": False,
        "isolated_device_lock_fixture": True,
        "pin_or_digest_retained": False,
        "product_lock_namespace_written_or_erased": False,
        "product_namespace_written": False,
        "radio_tx_commands": 0,
        "wifi_host_touched": False,
    }, "delta safety policy mismatch")

    reports = run["reports"]
    fixture = reports["fixture_begin"]
    require(fixture.get("complete") is True and
            fixture.get("cid_hex") == EXPECTED_CID and
            fixture.get("fingerprint_matched") is True and
            fixture.get("scratch_path") == f"/leshy-hil/{run['run_id']}" and
            fixture.get("scratch_preexisting") is False and
            fixture.get("malformed_written") is True and
            fixture.get("unsigned_written") is True and
            fixture.get("exact_entries") is True and
            fixture.get("bytes_written") == 159 and
            fixture.get("write_calls") == 2 and
            fixture.get("file_syncs") == 2 and
            fixture.get("directory_syncs") == 1 and
            fixture.get("file_barriers_complete") is True and
            fixture.get("directory_barrier_complete") is True and
            fixture.get("product_namespace_written") is False,
            "physical scratch fixture mismatch")

    expected_states = {
        "malformed_en": ("en", "malformed.lhau", 12, "too_small",
                         "verifier_unavailable", 0),
        "malformed_ru": ("ru", "malformed.lhau", 12, "too_small",
                         "verifier_unavailable", 0),
        "unsigned_en": ("en", "unsigned.lhau", 147, "parsed",
                        "missing_signature", 1),
        "unsigned_ru": ("ru", "unsigned.lhau", 147, "parsed",
                        "missing_signature", 1),
    }
    for name, expected in expected_states.items():
        state = reports[name]
        language, source_name, source_size, parse, trust, steps = expected
        require(state.get("language") == language and
                state.get("source_name") == source_name and
                state.get("source_size") == source_size and
                state.get("parse_status") == parse and
                state.get("trust_status") == trust and
                state.get("observed_steps") == steps and
                state.get("execution_eligible") is False and
                state.get("zero_action_hid_resource_output") is True and
                state.get("actions_invoked") == 0 and
                state.get("hid_reports_emitted") == 0 and
                state.get("resources_acquired") == 0 and
                state.get("rf_transmit_attempts") == 0 and
                state.get("product_namespace_written") is False,
                f"inspection state mismatch: {name}")

    for name in SCENARIOS:
        captures = run["captures"][name]
        require(len(captures) == 2 and
                captures[0]["rgb565_sha256"] == captures[1]["rgb565_sha256"] and
                captures[0]["png_sha256"] == captures[1]["png_sha256"] and
                captures[0]["frame_begin"]["revision"] ==
                captures[1]["frame_begin"]["revision"],
                f"unstable rendered pair: {name}")

    lock_before = reports["device_lock_before"]
    lock_after = reports["device_lock_after"]
    lock_cleanup = reports["device_lock_fixture_cleanup"]
    require(all(lock_before.get(key) == lock_after.get(key) for key in
                ("status", "failure", "credential_generation", "failed_attempts")) and
            lock_cleanup.get("status") == "cleaned" and
            lock_cleanup.get("product_restored") is True and
            lock_cleanup.get("product_namespace_written_or_erased") is False and
            lock_cleanup.get("whole_nvs_read_or_copied") is False,
            "isolated Device Lock fixture did not restore product state")
    cleanup = reports["fixture_cleanup"]
    final = reports["final"]
    require(cleanup.get("cleanup_complete") is True and
            cleanup.get("files_removed") == 2 and
            cleanup.get("exact_entries") is True and
            cleanup.get("product_namespace_written") is False and
            run.get("cleanup", {}).get("complete") is True and
            final.get("page") == "home" and
            final.get("language") == run.get("initial_language") and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            run.get("radio_tx_commands") == 0,
            "terminal cleanup mismatch")


def validate_lineage(paths: list[Path], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    expected_failures = (
        "workflow: SerialException: Port is already open.",
        "invalid_session_id",
        "open Lab:",
    )
    require(len(paths) == 3, "three explicit precursor runs required")
    result = []
    total_flashes = 0
    for path, needle in zip(paths, expected_failures):
        run_path = path.resolve() / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        validate_candidate(run.get("candidate", {}))
        joined = "\n".join(run.get("failures", []))
        require(run.get("status") == "failed" and needle in joined,
                f"unexpected precursor failure: {path}")
        total_flashes += int(run.get("flash_count", 0))
        result.append({
            "run_json_sha256": digest(run_path),
            "failure": run["failures"][0],
            "flash_count": run.get("flash_count", 0),
            "cleanup_complete": run.get("cleanup", {}).get("complete", False),
        })
    require(total_flashes == 1 and candidate["firmware_sha256"] == EXPECTED_FIRMWARE,
            "lineage must contain exactly one candidate flash")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--precursor-run", action="append", required=True,
                        type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        run_dir = args.run.resolve()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        validate(run)
        lineage = validate_lineage(args.precursor_run, run["candidate"])
        require(digest(args.factory.resolve()) == EXPECTED_FACTORY,
                "factory image mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_path, args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for scenario in SCENARIOS:
        stem = scenario.replace("_", "-")
        for suffix in ("a", "b"):
            shutil.copyfile(run_dir / "frames" / f"{stem}-{suffix}.png",
                            frames / f"{stem}-{suffix}.png")

    provenance = {
        "schema": "leshy.automation_inspector_hil.provenance.v1",
        "firmware_source_commit": EXPECTED_SOURCE,
        "harness_commits": [
            "603e230170da545b0ef011ed512f8d34416dac3d",
            "b7b2e04849b2fd76a7992b5fc2ecf42bf18b73be",
            "36cd4bc57ab06e78efefe5cf82a5fe7f4734936e",
        ],
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "runner_source_sha256": EXPECTED_RUNNER,
        "accepted_raw_run_sha256": digest(run_path),
        "precursor_lineage": lineage,
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)

    fixture = run["reports"]["fixture_begin"]
    states = run["reports"]
    summary = {
        "schema": "leshy.automation_inspector_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-BUILD-206", "E-AUTO-181", "E-HIL-215",
                         "E-UX-068", "E-STORAGE-039", "RB-M217"],
        "board": run["board"],
        "firmware_source_commit": EXPECTED_SOURCE,
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "exact_cid": EXPECTED_CID,
        "lineage": {
            "candidate_flashes": 1,
            "accepted_run_flashes": 0,
            "accepted_run_reused_installed_candidate": True,
            "precursors": lineage,
        },
        "fixture": {key: fixture[key] for key in (
            "scratch_path", "bytes_written", "write_calls", "file_syncs",
            "directory_syncs", "exact_entries", "fingerprint_matched")},
        "inspection": {
            name: {key: states[name][key] for key in (
                "language", "source_name", "source_size", "parse_status",
                "trust_status", "observed_steps", "execution_eligible",
                "zero_action_hid_resource_output")}
            for name in SCENARIOS
        },
        "stable_screens": {
            name: {
                "revision": run["captures"][name][0]["frame_begin"]["revision"],
                "rgb565_sha256": run["captures"][name][0]["rgb565_sha256"],
                "png_sha256": run["captures"][name][0]["png_sha256"],
                "pair": [f"frames/{name.replace('_', '-')}-a.png",
                         f"frames/{name.replace('_', '-')}-b.png"],
            } for name in SCENARIOS
        },
        "safe": {
            "action_invocations": 0,
            "hid_reports": 0,
            "resources_acquired": 0,
            "rf_transmit_attempts": 0,
            "product_namespace_written": False,
            "pin_or_digest_retained": False,
            "wifi_host_touched": False,
        },
        "cleanup": {
            "scratch_files_removed": states["fixture_cleanup"]["files_removed"],
            "device_lock_product_restored":
                states["device_lock_fixture_cleanup"]["product_restored"],
            "language_restored": run["cleanup"]["language_restored"],
            "page": states["final"]["page"],
            "runtime_owner": states["final"]["runtime_owner"],
            "lease_mask": states["final"]["lease_mask"],
        },
        "raw_run_sha256": provenance["accepted_raw_run_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
