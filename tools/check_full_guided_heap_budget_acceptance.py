#!/usr/bin/env python3
"""Fail closed unless the exact 0.87 final-heap physical proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-full-guided-heap-budget-0.87.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-full-guided-heap-budget-0.87"
PREVIOUS = ROOT / "tests/hil/evidence/board-01-full-guided-disposable-0.86.json"
COMMIT = "a943f3c588e09e9e7fa8c604039247154cbf5d31"
CID = "FE343253440000002000000055019CB7"
CAPTURES = {
    "modes": "modes", "quick_result": "quick-result",
    "preflight": "preflight", "visual_dialog_confirm": "visual-dialog-confirm",
    "visual_unavailable": "visual-unavailable",
    "visual_degraded": "visual-degraded", "visual_error": "visual-error",
    "visual_running": "visual-running", "active_checks": "active-checks",
    "active_artifacts": "active-artifacts",
    "active_disposable": "active-disposable", "full_result": "full-result",
    "home": "home",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def verify_index(failures: list[str], index: Path) -> None:
    expected: dict[str, str] = {}
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or not parts[1]:
            failures.append(f"invalid artifact-index line {number}")
        else:
            expected[parts[1]] = parts[0]
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != "artifacts.sha256"
    }
    require(failures, set(expected) == actual, "artifact index is not exact")
    for relative, expected_hash in expected.items():
        path = BUNDLE / relative
        require(failures, path.is_file() and digest(path) == expected_hash,
                f"artifact mismatch: {relative}")


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file() and BUNDLE.is_dir(),
            "0.87 evidence is missing")
    require(failures, PREVIOUS.is_file(), "0.86 regression baseline is missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    evidence = load(EVIDENCE)
    candidate = evidence.get("candidate", {})
    retained = evidence.get("evidence", {})
    verified = evidence.get("verified", {})
    regression = evidence.get("regression", {})
    require(failures,
            evidence.get("schema") == "leshy.full_guided_heap_budget_acceptance.v1" and
            evidence.get("status") == "pass_final_heap_budget_checkpoint" and
            evidence.get("board") == "board-01" and
            candidate.get("version") == "0.87.0-full-guided-heap-budget" and
            candidate.get("source_commit") == COMMIT and
            candidate.get("runner_commit") == COMMIT,
            "acceptance identity mismatch")

    run_path = BUNDLE / "run.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures, digest(run_path) == retained.get("run_sha256"),
            "run binding mismatch")
    require(failures, digest(index_path) == retained.get("artifact_index_sha256"),
            "artifact index binding mismatch")
    require(failures, retained.get("files") == 45 and
            retained.get("tft_states") == 13, "inventory count mismatch")
    verify_index(failures, index_path)

    for key, filename in (
        ("firmware_sha256", "firmware.bin"),
        ("factory_sha256", "firmware.factory.bin"),
        ("app_elf_sha256", "firmware.elf"),
        ("map_sha256", "firmware.map"),
    ):
        require(failures, digest(BUNDLE / filename) == candidate.get(key),
                f"{filename} binding mismatch")
    require(failures,
            app_elf_sha256(BUNDLE / "firmware.bin") == candidate.get("app_elf_sha256") and
            (BUNDLE / "firmware.bin").stat().st_size == candidate.get("app_bytes") and
            (BUNDLE / "firmware.factory.bin").stat().st_size == candidate.get("factory_bytes"),
            "candidate identity/size mismatch")

    previous = load(PREVIOUS)
    require(failures,
            previous.get("evidence", {}).get("run_sha256") ==
                regression.get("previous_run_sha256") and
            previous.get("verified", {}).get("heap_minimum_after_full") == 129276 and
            regression.get("static_ram_delta_bytes") == -4608 and
            regression.get("heap_minimum_delta_bytes") == 4608,
            "0.86 regression baseline/delta mismatch")

    source = git_blob("firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
    controller = git_blob("firmware/leshy1/src/apps/self_test/SelfTestController.cpp")
    tests = git_blob("tests/native/clean_target_tests.cpp")
    runner = git_blob("tools/run_1x_full_guided_rf_hil.py")
    require(failures, source is not None and
            b"char diagnosticJson[5120]" not in source and
            b"char line[5120]" in source and
            b"auto& diagnosticJson = sdPhysicalEvidence.line" in source,
            "single shared diagnostic workspace contract mismatch")
    require(failures, controller is not None and
            b"report_.checks.fill({});" in controller and
            b"evaluateQuick(report_.facts);" in controller,
            "final Quick re-evaluation contract mismatch")
    require(failures, tests is not None and
            b"degradedHeap.heapMinimum = degradedHeap.heapFloor - 1U" in tests and
            b"heapFailure.failed == 1" in tests,
            "final-heap negative regression is missing")
    require(failures, runner is not None and
            hashlib.sha256(runner).hexdigest() == retained.get("runner_sha256"),
            "runner source binding mismatch")

    run = load(run_path)
    full = run.get("full_report", {})
    heap = verified.get("heap", {})
    heap_check = next(
        (item for item in full.get("checks", [])
         if item.get("id") == "quick.runtime.heap"), {})
    require(failures,
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            run.get("candidate", {}).get("source_commit") == COMMIT and
            run.get("candidate", {}).get("firmware_sha256") ==
                candidate.get("firmware_sha256") and
            run.get("candidate", {}).get("app_elf_sha256") ==
                candidate.get("app_elf_sha256"),
            "physical run identity mismatch")
    require(failures,
            [full.get("passed"), full.get("failed"), full.get("blocked"),
             full.get("not_applicable")] == [25, 0, 1, 3] and
            heap_check.get("status") == "pass" and
            full.get("facts", {}).get("heap_minimum") == heap.get("minimum") == 133884 and
            full.get("facts", {}).get("heap_floor") == heap.get("floor") == 131072 and
            heap.get("margin") == heap.get("minimum") - heap.get("floor") == 2812,
            "final Full/Guided heap result mismatch")

    disposable = run.get("active_artifact", {}).get("disposable", {})
    continuity = run.get("active_artifact", {}).get("product_continuity", {})
    final = run.get("cleanup_after", {}).get("final_state", {})
    require(failures,
            [disposable.get("write_calls"), disposable.get("write_bytes"),
             disposable.get("file_syncs"), disposable.get("directory_syncs"),
             disposable.get("files_removed")] == [3, 504, 3, 3, 3] and
            disposable.get("scratch_removed") is True and
            continuity.get("passed") is True and
            [continuity.get("generation_final"), continuity.get("observations_final")] == [83, 0] and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            [final.get("page"), final.get("runtime_owner"), final.get("lease_mask")] ==
                ["home", "none", 0],
            "functional continuity/cleanup mismatch")

    captures = run.get("captures", {})
    require(failures, set(captures) == set(CAPTURES),
            "exact 13 TFT states are required")
    for name, record in captures.items():
        basename = CAPTURES.get(name, "missing")
        png = BUNDLE / "frames" / f"{basename}.png"
        rgb = BUNDLE / "frames" / f"{basename}.rgb565"
        png_data = png.read_bytes() if png.is_file() else b""
        dims = struct.unpack(">II", png_data[16:24]) if len(png_data) >= 24 else None
        require(failures,
                dims == (240, 320) and rgb.is_file() and rgb.stat().st_size == 153600 and
                digest(png) == record.get("png_sha256") and
                digest(rgb) == record.get("rgb565_sha256"),
                "TFT capture binding mismatch")

    require(failures, evidence.get("limits") == {
        "controlled_power_cut_complete": False,
        "one_hour_endurance_complete": False,
        "demo_s4_complete": False,
        "release_gate_eligible": False,
    }, "remaining limits are not explicit")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print("PASS: exact 0.87 final heap budget and physical Full/Guided proof is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
