#!/usr/bin/env python3
"""Fail closed unless the compact exact 0.144 Full/Guided delta is intact."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-full-guided-s5-rx-delta-0.144"
SUMMARY = ROOT / "tests/hil/evidence/board-01-full-guided-s5-rx-delta-0.144.json"
VERSION = "0.144.0-full-guided-s5-rx"
CID = "FE343253440000002000000055019CB7"
SOURCE = "0f2ffdf554d81c80993ec08f9d5697462351fd76"
BASE = "a7601486b63954b546591be1665b75657d52d4c4"
RUN_SHA256 = "4d52407fbc4ad4d12602ff559ff99007070e9db38a6b5f9b7e02b0573df9674e"
RUNNER_SHA256 = "44e453f30c7f0ebd7a2856a3b906939fef8f4f1725532e1cfc0672d01fc698ba"
PROVENANCE_SHA256 = "f7aa0f3721f3c87374bbbea5fc46701ce8556de1b406701f3f375bcded7d8f46"
PRECURSORS_SHA256 = "f68115f00c0f8579a84d0e6e43b435c150a8f0854da9b19bf59d9ff80f1048a6"
INDEX_SHA256 = "7605cc4be6aa115752fb236c7e51543e799682fc7ffb9a129860c4ad8c67fb4e"
FIRMWARE_SHA256 = "a173b2afb53e2b2b537c7a3460ebfbded1229e443f42aa5b4ab3db8ccc6dded2"
ELF_SHA256 = "9fee1996de80316946fcdbebe07064be2ab3baac3bd88fd6300bf4df8ca66402"
CAPTURES = {
    "active_artifacts", "active_checks", "active_disposable", "full_result",
    "home", "modes", "preflight", "quick_result", "visual_degraded",
    "visual_dialog_confirm", "visual_error", "visual_running",
    "visual_unavailable",
}
FULL_STATUSES = [
    *(["pass"] * 16), "not_applicable", "not_applicable",
    *(["pass"] * 8), "not_applicable", *(["pass"] * 4), "blocked",
]
PRECURSOR_OUTCOMES = [
    "fail_closed_navigation_entered_library",
    "fail_closed_stale_heap_gate_and_fsk_overflow",
    "fail_closed_fsk_isr_window_unbounded_between_service_passes",
    "fail_closed_heap_floor_and_pcap_applicability_contract",
    "fail_closed_host_serial_permission_denied_before_flash",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def git_blob(commit: str, relative: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return completed.stdout if completed.returncode == 0 else None


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24] if path.is_file() else b""
    if (len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or
            data[12:16] != b"IHDR"):
        return None
    return struct.unpack(">II", data[16:24])


def verify_manifest(failures: list[str]) -> tuple[int, int]:
    manifest = BUNDLE / "artifacts.sha256"
    require(failures, manifest.is_file() and digest(manifest) == INDEX_SHA256,
            "compact artifact index identity mismatch")
    if not manifest.is_file():
        return 0, 0
    indexed: set[str] = set()
    for number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"malformed compact artifact line {number}")
            continue
        expected, relative = match.groups()
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in indexed:
            failures.append(f"unsafe or duplicate compact artifact: {relative}")
            continue
        artifact = BUNDLE / path
        require(failures, artifact.is_file() and digest(artifact) == expected,
                f"compact artifact mismatch: {relative}")
        indexed.add(relative)
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() and path != manifest
    }
    require(failures, indexed == actual,
            "compact artifact index does not exactly cover bundle")
    files = [path for path in BUNDLE.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def main() -> int:
    failures: list[str] = []
    require(failures, SUMMARY.is_file() and BUNDLE.is_dir(),
            "compact Full/Guided S5 RX delta evidence missing")
    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    run = load(BUNDLE / "run.json")
    precursors = load(BUNDLE / "precursors.json")
    evidence = summary.get("evidence", {})
    file_count, byte_count = verify_manifest(failures)

    require(failures,
            summary.get("schema") ==
                "leshy.full_guided_s5_rx_delta.acceptance.v1" and
            summary.get("status") ==
                "pass_delta_full_guided_receivers_and_artifacts_positive_sources_open" and
            summary.get("board") == "board-01" and
            summary.get("evidence_ids") == [
                "E-BUILD-144", "E-AUTO-102", "E-HIL-162",
                "E-RADIO-020", "E-STORAGE-033",
            ], "acceptance summary contract mismatch")
    require(failures, summary.get("cadence") == {
        "accepted_delta_ordinal": 2,
        "anchor_evidence":
            "tests/hil/evidence/board-01-s5-runtime-completeness-0.139.json",
        "flash_policy": "one_exact_candidate_flash_for_delta_matrix",
        "full_after_accepted_deltas": 15,
        "full_matrix_run": False,
        "scope": "delta",
    }, "HIL cadence claim mismatch")
    require(failures,
            file_count == evidence.get("compact_files") == 18 and
            byte_count == evidence.get("compact_bytes") == 549917 and
            evidence.get("compact_artifact_manifest_sha256") == INDEX_SHA256 and
            evidence.get("compact_provenance_sha256") == PROVENANCE_SHA256 and
            evidence.get("run_sha256") == RUN_SHA256 and
            evidence.get("runner_sha256") == RUNNER_SHA256 and
            evidence.get("precursors_sha256") == PRECURSORS_SHA256 and
            evidence.get("tft_png_frames") == 13,
            "compact evidence identity or size mismatch")
    require(failures,
            digest(BUNDLE / "run.json") == RUN_SHA256 and
            digest(BUNDLE / "runner.py") == RUNNER_SHA256 and
            digest(BUNDLE / "provenance.json") == PROVENANCE_SHA256 and
            digest(BUNDLE / "precursors.json") == PRECURSORS_SHA256,
            "retained run/runner/provenance/precursor identity mismatch")

    candidate = run.get("candidate", {})
    require(failures,
            run.get("schema") ==
                "leshy.full_guided_disposable_self_test_hil.run.v4" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("expected_cid") == CID and
            candidate == {
                "app_elf_sha256": ELF_SHA256,
                "firmware_sha256": FIRMWARE_SHA256,
                "flashed": True,
                "source_commit": SOURCE,
                "version": VERSION,
            }, "exact Full/Guided delta run identity mismatch")
    require(failures,
            provenance.get("schema") ==
                "leshy.compact_delta_hil.provenance.v1" and
            provenance.get("base_commit") == BASE and
            provenance.get("candidate") == candidate and
            provenance.get("run_sha256") == RUN_SHA256 and
            provenance.get("runner_sha256") == RUNNER_SHA256 and
            provenance.get("runner_source") ==
                "tools/run_1x_full_guided_rf_hil.py" and
            provenance.get("cadence", {}).get("accepted_delta_ordinal") == 2 and
            provenance.get("cadence", {}).get("full_matrix_run") is False and
            provenance.get("retention", {}).get("png_frames") == 13 and
            provenance.get("build") == {
                "factory_sha256":
                    "4575b4706cea89b1b28f3973ae764117503a2e37e5a9e052373c08bfaf662add",
                "linked_flash_bytes": 3087248,
                "map_sha256":
                    "d324d1d33734eb15badf444c025e99dfd690f92a554b87223b611ac19b079e46",
                "static_ram_bytes": 211208,
            }, "compact provenance mismatch")
    for relative, expected in provenance.get("source_sha256", {}).items():
        blob = git_blob(SOURCE, relative)
        require(failures, blob is not None and
                hashlib.sha256(blob).hexdigest() == expected,
                f"candidate source binding mismatch: {relative}")
    require(failures,
            git_blob(SOURCE, "tools/run_1x_full_guided_rf_hil.py") ==
                (BUNDLE / "runner.py").read_bytes(),
            "executed runner is not bound to the candidate source")

    quick = run.get("quick_report", {})
    full = run.get("full_report", {})
    full_checks = full.get("checks", [])
    require(failures,
            quick.get("status") == "pass" and quick.get("passed") == 9 and
            quick.get("failed") == 0 and quick.get("blocked") == 0 and
            len(quick.get("checks", [])) == 9 and
            full.get("status") == "blocked" and full.get("passed") == 28 and
            full.get("failed") == 0 and full.get("blocked") == 1 and
            full.get("not_applicable") == 3 and len(full_checks) == 32 and
            [item.get("status") for item in full_checks] == FULL_STATUSES and
            full_checks[-1] == {
                "id": "full.capability.coverage", "status": "blocked"},
            "Quick/Full result contract mismatch")
    facts = full.get("facts", {})
    require(failures,
            facts.get("heap_free") == 96880 and
            facts.get("heap_free_floor") == 81920 and
            facts.get("heap_minimum") == 63848 and
            facts.get("heap_minimum_floor") == 49152 and
            facts.get("capture_pcap_audit_complete") is True and
            facts.get("capture_pcap_audit_applicable") is False and
            facts.get("capture_pcap_audit_passed") is False and
            facts.get("resource_scope_clean") is True,
            "Full heap/PCAP/resource facts mismatch")

    rf = run.get("active_rf", {})
    nrf = rf.get("nrf24", {})
    cc = rf.get("cc1101", {})
    fsk = rf.get("subghz_fsk", {})
    ook = rf.get("subghz_ook", {})
    infrared = rf.get("infrared", {})
    require(failures,
            rf.get("step") == "complete" and rf.get("rx_only") is True and
            rf.get("resource_released") is True and
            rf.get("cleanup_complete") is True and
            nrf.get("passed") is True and nrf.get("modules") == 3 and
            nrf.get("channels") == 83 and nrf.get("wire") == {
                "receive_ce_high_events": 83, "register_reads": 98,
                "register_writes": 101, "spi_bytes_clocked": 398,
            } and cc.get("passed") is True and cc.get("bins") == 64 and
            cc.get("wire", {}).get("register_reads") == 4270 and
            cc.get("wire", {}).get("register_writes") == 208 and
            cc.get("wire", {}).get("spi_bytes_clocked") == 9022 and
            ook.get("passed") is True and ook.get("samples") == 32 and
            fsk.get("passed") is True and fsk.get("samples") == 32 and
            fsk.get("edges") == 72 and fsk.get("overflow") is False and
            infrared.get("passed") is True and
            infrared.get("samples") == 64 and
            infrared.get("transitions") == 0 and
            rf.get("side_effects") == {
                "cc_fifo_writes": 0, "cc_pa_table_writes": 0,
                "cc_rejected_strobes": 0, "cc_tx_strobes": 0,
                "nrf_tx_mode_entries": 0, "nrf_tx_payload_commands": 0,
                "radio_tx_commands": 0, "storage_write_commands": 0,
            }, "active passive receiver contract mismatch")

    artifact = run.get("active_artifact", {})
    disposable = artifact.get("disposable", {})
    capture = artifact.get("capture", {})
    continuity = artifact.get("product_continuity", {})
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(failures,
            artifact.get("step") == "complete" and
            artifact.get("cleanup_complete") is True and
            capture == {
                "applicable": False, "complete": True, "passed": False,
                "pcap_bytes": 0, "pcap_fnv1a": 2166136261,
                "pcap_frames": 0,
            } and disposable.get("run_id") == "full-guided-v10" and
            disposable.get("write_calls") == 3 and
            disposable.get("write_bytes") == 505 and
            disposable.get("scratch_removed") is True and
            disposable.get("cleanup_passed") is True and
            continuity == {
                "complete": True, "generation_final": 110,
                "observations_final": 0, "passed": True,
            } and artifact.get("side_effects") == {
                "blocked_write_attempts": 0,
                "disposable_storage_write_bytes": 505,
                "disposable_storage_write_commands": 3,
                "product_storage_write_commands": 0,
                "radio_tx_commands": 0,
            }, "active artifact/disposable contract mismatch")
    require(failures,
            before.get("generation") == after.get("generation") == 110 and
            before.get("observations") == after.get("observations") == 0 and
            before.get("observed_fingerprint") ==
                after.get("observed_fingerprint") == CID and
            before.get("physical_write_calls") ==
                after.get("physical_write_calls") == 0 and
            before.get("cleanup_complete") is True and
            after.get("cleanup_complete") is True,
            "product artifact continuity mismatch")

    shield = run.get("shield_receiver_probe", {})
    require(failures,
            shield.get("status") == "pass" and
            shield.get("detected_receivers") == 3 and
            shield.get("gpio21_stable_high") is True and
            shield.get("resource_released") is True and
            shield.get("cleanup_complete") is True and
            shield.get("side_effects") == {
                "cc_command_strobes": 0, "nrf_ce_high_events": 0,
                "radio_tx_commands": 0,
            }, "shield receiver probe mismatch")
    final = run.get("final", {})
    cleanup = run.get("cleanup_after", {})
    require(failures,
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("safe_outputs", {}).get("nrf_ce_inactive") is True and
            cleanup.get("complete") is True and cleanup.get("errors") == [] and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "input/output/final cleanup mismatch")

    captures = run.get("captures", {})
    require(failures, set(captures) == CAPTURES,
            "automatic TFT capture inventory mismatch")
    for name in CAPTURES:
        png = BUNDLE / "frames" / f"{name}.png"
        require(failures,
                png_size(png) == (240, 320) and
                digest(png) == captures.get(name, {}).get("png_sha256"),
                f"automatic TFT frame mismatch: {name}")

    precursor_runs = precursors.get("runs", [])
    require(failures,
            precursors.get("schema") ==
                "leshy.full_guided_s5_rx_delta.precursors.v1" and
            len(precursor_runs) == 5 and
            [item.get("outcome") for item in precursor_runs] ==
                PRECURSOR_OUTCOMES and
            [item.get("failure_count") for item in precursor_runs] ==
                [206, 99, 84, 16, 1] and
            all(item.get("raw_run_sha256") for item in precursor_runs) and
            precursor_runs[-1].get("board_touched") is False,
            "fail-closed precursor chain mismatch")
    limits = summary.get("limits", {})
    require(failures,
            limits.get("full_capability_coverage_blocked") is True and
            limits.get("s5_exit_gate_closed") is True and
            limits.get("radio_transmit_authorized") is False and
            not any(limits.get(name) for name in (
                "physical_ir_positive_source_used",
                "physical_subghz_fsk_positive_source_used",
                "physical_subghz_ook_positive_source_used",
            )), "acceptance boundary mismatch")

    if failures:
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1
    print(
        "Full/Guided S5 RX compact delta acceptance: PASS; "
        "positive-source S5 exit remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
