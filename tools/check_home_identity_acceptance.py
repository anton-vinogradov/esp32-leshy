#!/usr/bin/env python3
"""Fail closed unless the exact 0.94 localized Home proof remains intact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-home-identity-0.94.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-home-identity-0.94"
VERSION = "0.94.0-home-identity"
SOURCE = "569fd51dc62c7a10af62ff12e26354fb58f4a385"
CID = "FE343253440000002000000055019CB7"
FIRMWARE = "9eaa20de512baab2bd32bf23687ee84f68c6433804922fbee2e41594b39b7792"
FACTORY = "047b57c8a258a299d34dedfa0245952d2c13480db845af3c5806c6c76df32c2c"
APP = "94f936980e40833c2ec4814b5e9283ded05a9805ac073a5969f152cd70a59dc6"
MAP = "864ccd77459e2fe7261ee883fcce7cfc575d97d84096aed2950f06fd9b509c95"
RUNNER = "68a7c84066207cd1b5f860f0c8f3135dd589513ebb3297521ebc9ae86b3a1229"
CHECKER = "1724c45300acd7f36c00df214693d93dfa9a06a88bcedfd5452dac333a143b01"
GATE = "990f8deb3857ae0b700c0dee7b2fc7edbaeaf3a5ea239fcdcd1e0a3c1be86caa"
INDEX = "194d89ea5659dd0182d6a8f588d95f6502a8b904437dfff739f9cb38d3df203d"
PROVENANCE = "c24c6b7693ed821946071534e467ee645e240d6577276fa423e633e947901c26"
RUN = "64d85730ced64847482a8de6ff571c7cccaf7593987aa46346a107bceed59d8d"
OPAQUE = {"firmware.bin", "firmware.factory.bin", "firmware.elf", "firmware.map"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_manifest(failures: list[str], tracked_only: bool) -> None:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX,
            "artifact index mismatch")
    if not manifest.is_file():
        return
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        indexed.add(relative)
        path = BUNDLE / relative
        if tracked_only and relative in OPAQUE:
            continue
        require(failures, path.is_file(), f"retained artifact missing: {relative}")
        if path.is_file():
            require(failures, digest(path) == expected,
                    f"retained artifact mismatch: {relative}")
    require(failures, OPAQUE <= indexed, "opaque candidate bindings missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "0.94 Home identity evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    candidate = summary.get("candidate", {})
    evidence = summary.get("evidence", {})
    verified = summary.get("verified", {})
    require(failures,
            summary.get("schema") == "leshy.product_home_acceptance.v1" and
            summary.get("status") == "pass_home_identity_checkpoint" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") ==
                ["E-BUILD-095", "E-AUTO-059", "E-HIL-119", "E-UX-018"],
            "summary identity mismatch")
    require(failures,
            candidate.get("version") == VERSION and
            candidate.get("source_commit") == SOURCE and
            candidate.get("runner_commit") == SOURCE and
            candidate.get("firmware_sha256") == FIRMWARE and
            candidate.get("factory_sha256") == FACTORY and
            candidate.get("app_elf_sha256") == APP and
            candidate.get("map_sha256") == MAP and
            candidate.get("runner_sha256") == RUNNER and
            candidate.get("checker_sha256") == CHECKER and
            candidate.get("gate_sha256") == GATE and
            [candidate.get("firmware_bytes"), candidate.get("factory_bytes"),
             candidate.get("static_ram_bytes"), candidate.get("linked_flash_bytes")] ==
                [1506640, 1572176, 159856, 1506228],
            "candidate identity/size mismatch")
    require(failures, evidence == {
        "artifact_index_sha256": INDEX, "files": 52,
        "provenance_sha256": PROVENANCE, "run_sha256": RUN,
        "tft_states": 14,
    }, "evidence summary mismatch")
    require(failures,
            verified.get("home_identity") == {
                "english": "LESHY", "russian": "Леший",
                "displayed_semver": "v0.94.0", "full_version": VERSION,
                "nested_brand_mentions": 0,
            } and verified.get("languages") == ["en", "ru"] and
            verified.get("manual_button_presses") == 0 and
            verified.get("final_owner") == "none" and
            verified.get("final_lease_mask") == 0 and
            verified.get("heap") == [221852, 156892, 137540],
            "verified Home identity/runtime claims mismatch")

    verify_manifest(failures, args.tracked_only)
    for name, expected in (("provenance.json", PROVENANCE),
                           ("run.json", RUN), ("runner.py", RUNNER),
                           ("checker.py", CHECKER),
                           ("connected-candidate-gate.sh", GATE)):
        require(failures, (BUNDLE / name).is_file() and
                digest(BUNDLE / name) == expected, f"{name} binding mismatch")

    run = load(BUNDLE / "run.json")
    screens = run.get("screens", {})
    require(failures,
            run.get("passed") is True and not run.get("failures") and
            run.get("expected_cid") == CID and len(screens) == 14 and
            screens.get("home_en", {}).get("state", {}).get("language") == "en" and
            screens.get("home_top", {}).get("state", {}).get("language") == "ru" and
            screens.get("home_final", {}).get("state", {}).get("language") == "ru" and
            run.get("cleanup_after", {}).get("final_state", {}).get("lease_mask") == 0,
            "physical bilingual Home/final cleanup mismatch")

    strings = git_blob("firmware/leshy1/src/ui/UiStrings.def")
    renderer = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    platform = git_blob("firmware/leshy1/platformio.ini")
    runner = git_blob("tools/run_1x_product_home_hil.py")
    require(failures, strings is not None and
            strings.count(b'"LESHY"') == 1 and
            strings.count('u8"Леший"'.encode()) == 1 and
            b'ABOUT LESHY' not in strings and b'ESP32-LESHY' not in strings,
            "root-only localized brand source mismatch")
    require(failures, renderer is not None and all(token in renderer for token in (
        b"void formatHomeVersion(", b"const char* source = LESHY1_VERSION",
        b"*source != '-'", b"char version[24]", b"if (home)",
        b"setUiCursor(UiTextRole::Meta, 10, 18)")),
        "Home SemVer renderer source mismatch")
    require(failures, platform is not None and
            b'LESHY1_VERSION=\\"0.94.0-home-identity\\"' in platform,
            "exact build version source mismatch")
    require(failures, runner is not None and digest(BUNDLE / "runner.py") ==
            hashlib.sha256(runner).hexdigest() and
            b'query(device, b"ui.language en"' in runner and
            b'query(device, b"ui.language ru"' in runner,
            "bilingual physical runner source mismatch")

    if not args.tracked_only:
        for name, expected in (("firmware.bin", FIRMWARE),
                               ("firmware.factory.bin", FACTORY),
                               ("firmware.elf", APP), ("firmware.map", MAP)):
            require(failures, (BUNDLE / name).is_file() and
                    digest(BUNDLE / name) == expected,
                    f"opaque candidate mismatch: {name}")
        if (BUNDLE / "firmware.bin").is_file():
            require(failures, app_elf_sha256(BUNDLE / "firmware.bin") == APP,
                    "embedded ELF identity mismatch")
        check = subprocess.run(
            [str(BUNDLE / "checker.py"), "--run", str(BUNDLE),
             "--expected-version", VERSION, "--expected-cid", CID,
             "--source-commit", SOURCE], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "tools")})
        require(failures, check.returncode == 0,
                f"retained independent checker failed: {check.stdout}")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(json.dumps({
        "status": "pass", "version": VERSION, "tft_states": 14,
        "languages": ["en", "ru"], "brand": ["LESHY", "Леший"],
        "displayed_semver": "v0.94.0", "manual_button_presses": 0,
        "final_lease_mask": 0,
        "evidence_mode": "tracked" if args.tracked_only else "full",
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
