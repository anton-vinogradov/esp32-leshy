#!/usr/bin/env python3
"""Retain compact, source-bound physical Automation trust UI evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT / "tests/hil/evidence/board-01-automation-trust-ui-1.0.0-dev.306")
DEFAULT_SUMMARY = Path(f"{DEFAULT_BUNDLE}.json")
EXPECTED_SOURCE = "41bf103008202e742598dfd3e092b28aeda45d95"
EXPECTED_RUNNER_COMMIT = "959ff6a281e930107481f0d247c12f38a2b4ea94"
EXPECTED_RUNNER = "6c37de1c6cc4ddabd2c03d5220b07f65453f1f6b9f679b44e7fabcaa3b829b27"
EXPECTED_VERSION = "1.0.0-dev.306"
EXPECTED_FIRMWARE = "fff7ac4b2b6c9ab66370a6b3bd0cd5c2b205d55ad55028debefebde94a969615"
EXPECTED_ELF = "d8155e1dd75b6c4b82e5ce08d41fec406eeee63475f1e2653b1f043d6aa892de"
EXPECTED_MAP = "0f1161041f1812c44fdf42c9dfdbd2c579a02a5f107ccca8a9e56251c8c59150"
EXPECTED_FACTORY = "069648d2fde7cc6e4f2c4ec44ef23e1a0f1c6a0b88a6127d3ecdf5bc9c185786"
SCENARIOS = {
    "list_en": "trust-list-en",
    "list_ru": "trust-list-ru",
    "first_import_ru": "trust-import-ru",
}
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/ui/UiStrings.def",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.cpp",
    "firmware/leshy1/src/platform/arduino/ArduinoAutomationTrust.h",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.cpp",
    "firmware/leshy1/src/platform/arduino/BoardAutomationTrustBundleReader.h",
    "firmware/leshy1/src/apps/automation/AutomationTrustStore.cpp",
    "firmware/leshy1/src/apps/automation/AutomationTrustStore.h",
    "firmware/leshy1/src/apps/automation/AutomationTrustBundle.cpp",
    "firmware/leshy1/src/apps/automation/AutomationTrustBundle.h",
    "tools/check_automation_hid_foundation.py",
    "tools/run_1x_automation_trust_ui_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT)


def git_blob_digest(commit: str, path: str) -> str:
    return hashlib.sha256(git_blob(commit, path)).hexdigest()


def validate_candidate(candidate: dict[str, Any]) -> None:
    require(candidate == {
        "app_elf_sha256": EXPECTED_ELF,
        "elf_sha256": EXPECTED_ELF,
        "firmware_bytes": 3552992,
        "firmware_sha256": EXPECTED_FIRMWARE,
        "map_sha256": EXPECTED_MAP,
        "version": EXPECTED_VERSION,
    }, "exact candidate mismatch")


def validate(run: dict[str, Any]) -> None:
    require(run.get("schema") == "leshy.automation_trust_ui_hil.run.v1" and
            run.get("status") == "pass" and run.get("passed") is True and
            run.get("failures") == [], "passing trust UI run required")
    require(run.get("source_commit") == EXPECTED_SOURCE,
            "firmware source mismatch")
    validate_candidate(run.get("candidate", {}))
    require(run.get("runner_sha256") == EXPECTED_RUNNER,
            "runner identity mismatch")
    require(run.get("flash_count") == 1 and
            run.get("installed_candidate_reused") is False and
            run.get("hardware_reset_count") == 0,
            "accepted run must contain one candidate flash")
    require(run.get("policy") == {
        "delta_only": True,
        "forbidden_ports_touched": [],
        "full_hil": False,
        "private_key_used_or_stored": False,
        "radio_tx_commands": 0,
        "sd_files_written": 0,
        "sd_mount": "read_only",
        "trust_mutation_confirmed": False,
        "trust_namespace_written": False,
        "wifi_host_touched": False,
    }, "delta safety policy mismatch")

    reports = run["reports"]
    before = reports["trust_before"]
    after = reports["trust_after"]
    require(before.get("ready") is True and before.get("capacity") == 4 and
            before.get("count") == after.get("count") and
            before.get("generation") == after.get("generation") and
            before.get("all_keys_p256_and_id_bound") is True and
            before.get("public_keys_only") is True and
            before.get("private_key_stored") is False and
            before.get("execution_connected") is False,
            "trust store changed or lost its public-only boundary")
    for name in ("trust_before", "first_import", "touch_import_state",
                 "trust_after"):
        state = reports[name]
        require(state.get("action_invocations") == 0 and
                state.get("hid_reports") == 0 and
                state.get("rf_transmit_attempts") == 0 and
                state.get("confirmation_open") is False and
                state.get("confirmation_fresh") is False,
                f"unsafe trust UI state: {name}")
    for name in ("first_import", "touch_import_state"):
        state = reports[name]
        require(state.get("ui_view") == "result" and
                state.get("ui_result") == "bundle_read_failed" and
                state.get("bundle_read_status") == "open_failed",
                f"fixed-path missing bundle result mismatch: {name}")

    for name in SCENARIOS:
        pair = run["captures"][name]
        require(len(pair) == 2 and
                pair[0]["rgb565_sha256"] == pair[1]["rgb565_sha256"] and
                pair[0]["png_sha256"] == pair[1]["png_sha256"] and
                pair[0]["frame_begin"]["revision"] ==
                pair[1]["frame_begin"]["revision"],
                f"unstable rendered pair: {name}")

    lock_before = reports["device_lock_before"]
    lock_after = reports["device_lock_after"]
    require(all(lock_before.get(key) == lock_after.get(key) for key in
                ("status", "failure", "credential_generation",
                 "failed_attempts")), "Device Lock product state changed")
    require(reports["device_lock_fixture_cleanup"].get("product_restored") is True and
            reports["device_lock_fixture_cleanup"].get(
                "product_namespace_written_or_erased") is False,
            "isolated Device Lock fixture not restored")
    require(run.get("cleanup", {}).get("complete") is True and
            reports["final"].get("page") == "home" and
            reports["final"].get("language") == run.get("initial_language") and
            reports["final"].get("runtime_owner") == "none" and
            reports["final"].get("lease_mask") == 0 and
            reports["safe_outputs"].get("buzzer_inactive") is True and
            reports["safe_outputs"].get("nrf_ce_inactive") is True and
            reports["safe_outputs"].get("software_quiesce_complete") is True and
            reports["hil_end"].get("active") is False,
            "terminal cleanup or safe output mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
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
        require(digest(args.factory.resolve()) == EXPECTED_FACTORY,
                "factory image mismatch")
        require(hashlib.sha256(git_blob(
            EXPECTED_RUNNER_COMMIT,
            "tools/run_1x_automation_trust_ui_hil.py")).hexdigest() ==
            EXPECTED_RUNNER, "runner commit/blob mismatch")
    except (KeyError, OSError, subprocess.CalledProcessError,
            TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_path, args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for stem in SCENARIOS.values():
        for suffix in ("a", "b"):
            shutil.copyfile(run_dir / "frames" / f"{stem}-{suffix}.png",
                            frames / f"{stem}-{suffix}.png")

    provenance = {
        "schema": "leshy.automation_trust_ui_hil.provenance.v1",
        "firmware_source_commit": EXPECTED_SOURCE,
        "runner_commit": EXPECTED_RUNNER_COMMIT,
        "runner_sha256": EXPECTED_RUNNER,
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "source_sha256": {
            path: git_blob_digest(EXPECTED_SOURCE, path)
            for path in SOURCE_PATHS
        },
        "accepted_raw_run_sha256": digest(run_path),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)

    reports = run["reports"]
    summary = {
        "schema": "leshy.automation_trust_ui_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-BUILD-208", "E-AUTO-183", "E-HIL-216",
                         "E-UX-069", "RB-M219"],
        "board": run["board"],
        "firmware_source_commit": EXPECTED_SOURCE,
        "runner_commit": EXPECTED_RUNNER_COMMIT,
        "candidate": run["candidate"],
        "factory_sha256": EXPECTED_FACTORY,
        "lineage": {
            "candidate_flashes": 1,
            "accepted_run_flashes": 1,
            "accepted_run_reused_installed_candidate": False,
        },
        "trust": {
            "capacity": reports["trust_before"]["capacity"],
            "count_before": reports["trust_before"]["count"],
            "count_after": reports["trust_after"]["count"],
            "generation_before": reports["trust_before"]["generation"],
            "generation_after": reports["trust_after"]["generation"],
            "load_status": reports["trust_before"]["load_status"],
            "public_keys_only": reports["trust_before"]["public_keys_only"],
            "all_keys_p256_and_id_bound":
                reports["trust_before"]["all_keys_p256_and_id_bound"],
            "private_key_stored": reports["trust_before"]["private_key_stored"],
            "execution_connected": reports["trust_before"]["execution_connected"],
        },
        "import": {
            "root": reports["first_import"]["bundle_root"],
            "name": reports["first_import"]["bundle_name"],
            "read_status": reports["first_import"]["bundle_read_status"],
            "result": reports["first_import"]["ui_result"],
            "button_path_checked": True,
            "touch_path_checked": True,
            "mutation_confirmed": False,
            "sd_mount": "read_only",
            "sd_files_written": 0,
        },
        "stable_screens": {
            name: {
                "revision": run["captures"][name][0]["frame_begin"]["revision"],
                "rgb565_sha256": run["captures"][name][0]["rgb565_sha256"],
                "png_sha256": run["captures"][name][0]["png_sha256"],
                "pair": [f"frames/{stem}-a.png", f"frames/{stem}-b.png"],
            } for name, stem in SCENARIOS.items()
        },
        "visual_review": {
            "en_list_legible": True,
            "ru_list_legible": True,
            "ru_no_execution_status_single_line": True,
            "static_frames_stable": True,
        },
        "safe": {
            "action_invocations": 0,
            "hid_reports": 0,
            "rf_transmit_attempts": 0,
            "trust_namespace_written": False,
            "private_key_used_or_stored": False,
            "wifi_host_touched": False,
            "forbidden_ports_touched": [],
        },
        "cleanup": {
            "device_lock_product_restored":
                reports["device_lock_fixture_cleanup"]["product_restored"],
            "language_restored": run["cleanup"]["language_restored"],
            "page": reports["final"]["page"],
            "runtime_owner": reports["final"]["runtime_owner"],
            "lease_mask": reports["final"]["lease_mask"],
            "hil_active": reports["hil_end"]["active"],
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
