#!/usr/bin/env python3
"""Fail closed on incomplete real-Capture Protocol Workbench evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "leshy.protocol_workbench_persistence_hil.run.v1"
HEX64 = set("0123456789abcdef")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run_path = args.run.resolve()
    root = run_path.parent
    value: dict[str, Any] = json.loads(
        run_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    need(value.get("schema") == SCHEMA, "schema mismatch")
    need(value.get("status") == "pass" and value.get("passed") is True,
         "run did not pass")
    need(value.get("gate_eligible") is True, "run is not gate eligible")
    need(value.get("failures") == [], "run retained failures")
    need(value.get("exact_port") == "/dev/cu.usbmodem2101",
         "run is not bound to original board-01")
    candidate = value.get("candidate", {})
    need(candidate.get("fresh_flash") is True,
         "candidate was not freshly flashed")
    for key in ("firmware_sha256", "app_elf_sha256"):
        item = candidate.get(key)
        need(isinstance(item, str) and len(item) == 64 and set(item) <= HEX64,
             f"candidate.{key} invalid")

    policy = value.get("policy", {})
    for key in ("mac_wifi_controlled", "clone_port_touched",
                "cardputer_touched"):
        need(policy.get(key) is False, f"policy.{key} is not false")
    need(policy.get("radio_tx_commands") == 0 and
         policy.get("ir_transmit_commands") == 0,
         "a transmit command was used")
    need(policy.get("manual_action") == "one_owned_remote_button_press",
         "physical signal source is not explicit")
    need(policy.get("cold_recovery_read_only") is True,
         "cold recovery was not read-only")

    proof = value.get("proof", {})
    need(proof.get("real_physical_ir_capture") is True,
         "real IR signal was not captured")
    for key in ("capture_generation", "annotation_store_generation",
                "decode_store_generation"):
        need(isinstance(proof.get(key), int) and proof[key] > 0,
             f"proof.{key} invalid")
    fingerprint = proof.get("source_fingerprint")
    need(isinstance(fingerprint, str) and len(fingerprint) == 16,
         "source fingerprint invalid")
    need(proof.get("cold_reopen") is True,
         "cold reopen was not proven")
    need(proof.get("raw_capture_mutated") is False,
         "raw Capture was mutated")

    records = value.get("records", {})
    complete = records.get("ir_complete", {})
    need(complete.get("state") == "complete" and
         complete.get("pulses", 0) >= 4 and
         complete.get("application_tx_calls") == 0,
         "real IR Capture contract failed")
    saved = records.get("ir_saved", {})
    need(saved.get("persist_state") == "saved" and
         saved.get("persist_generation") == proof.get("capture_generation"),
         "IR Capture was not durably saved")
    open_state = records.get("workbench_open", {})
    need(open_state.get("source_kind") == "immutable_capture" and
         open_state.get("capture_generation") == proof.get(
             "capture_generation") and
         open_state.get("source_fingerprint") == fingerprint and
         open_state.get("annotation_status") == "empty" and
         open_state.get("decode_status") == "no_marks",
         "fresh immutable workbench state invalid")
    annotations = records.get("annotations_saved", {})
    need(annotations.get("annotations") == 1 and
         annotations.get("annotation_dirty") is False and
         annotations.get("annotation_status") == "saved" and
         annotations.get("annotation_store_generation") == proof.get(
             "annotation_store_generation"),
         "annotation commit was not proven")
    decoded = records.get("decode_saved", {})
    need(decoded.get("decode_valid") is True and
         decoded.get("decode_outcome") == "complete" and
         decoded.get("decode_fields") == 1 and
         decoded.get("decode_status") == "saved" and
         decoded.get("decode_store_generation") == proof.get(
             "decode_store_generation"),
         "derived decode commit was not proven")
    reopened = records.get("workbench_reopened", {})
    need(reopened.get("source_fingerprint") == fingerprint and
         reopened.get("capture_generation") == proof.get(
             "capture_generation") and
         reopened.get("annotation_status") == "recovered" and
         reopened.get("annotation_store_generation") == proof.get(
             "annotation_store_generation") and
         reopened.get("decode_status") == "recovered" and
         reopened.get("decode_store_generation") == proof.get(
             "decode_store_generation") and
         reopened.get("raw_capture_mutated") is False,
         "exact cold reopen continuity failed")
    recovery = records.get("recovery_after", {})
    need(recovery.get("generation") == proof.get("capture_generation") and
         recovery.get("mounted_read_only") is True and
         recovery.get("read_only_guaranteed") is True and
         recovery.get("physical_write_calls") == 0 and
         recovery.get("cleanup_complete") is True,
         "cold product recovery contract failed")
    final = records.get("final_ui", {})
    need(final.get("page") == "home" and
         final.get("runtime_owner") == "none" and
         final.get("lease_mask") == 0,
         "final clean Home missing")
    need(value.get("cleanup", {}).get("complete") is True,
         "terminal cleanup incomplete")

    for record_name, stem in {
        "ir_complete": "ir-capture-complete",
        "ir_saved": "ir-capture-saved",
        "workbench_open": "workbench-real-capture",
        "decode_saved": "workbench-decode-saved",
        "workbench_reopened": "workbench-cold-reopened",
    }.items():
        frame = value.get("captures", {}).get(record_name, {})
        raw = root / "frames" / f"{stem}.rgb565"
        png = root / "frames" / f"{stem}.png"
        need(frame.get("bytes") == 153600, f"{record_name} frame invalid")
        need(raw.is_file(), f"{raw.name} missing")
        if raw.is_file():
            need(digest(raw) == frame.get("sha256"),
                 f"{raw.name} hash mismatch")
        need(png.is_file(), f"{png.name} missing")

    checker = root / Path(__file__).name
    runner = root / "run_1x_protocol_workbench_persistence_hil.py"
    need(checker.is_file(), "retained checker missing")
    need(runner.is_file(), "retained runner missing")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("Protocol Workbench persistence HIL evidence passed: real owned IR "
          "Capture, protected exact-source marks and derived decode, "
          "read-only cold reopen, immutable raw identity, zero TX, clean Home")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
