#!/usr/bin/env python3
"""Fail closed unless the retained outcome-first screen proof is intact."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-content-0.106"
SUMMARY = ROOT / "tests/hil/evidence/board-01-product-content-0.106.json"
VERSION = "0.106.0-product-content"
CID = "FE343253440000002000000055019CB7"
LABELS = ("main", "infrared", "subghz", "wifi_capture")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def png_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or \
            data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not SUMMARY.is_file() or not BUNDLE.is_dir():
        fail("product-content evidence missing")
    summary = load(SUMMARY)
    provenance = load(BUNDLE / "provenance.json")
    if summary.get("schema") != "leshy.product_content.acceptance.v1" or \
            summary.get("status") != "pass_outcome_first_product_content" or \
            summary.get("evidence_ids") != [
                "E-BUILD-106", "E-AUTO-070", "E-HIL-130", "E-UX-025"] or \
            provenance != summary.get("candidate") or \
            provenance.get("version") != VERSION or \
            provenance.get("cid") != CID:
        fail("summary/provenance identity mismatch")
    manifest = BUNDLE / "artifacts.sha256"
    if digest(manifest) != summary["evidence"]["artifact_index_sha256"]:
        fail("manifest hash mismatch")
    indexed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = BUNDLE / relative
        indexed.add(relative)
        if not path.is_file() or digest(path) != expected:
            fail(f"artifact mismatch: {relative}")
    actual = {str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
              if path.is_file() and path.name != "artifacts.sha256"}
    if indexed != actual:
        fail("manifest coverage mismatch")

    runs: dict[str, dict[str, Any]] = {}
    frame_total = 0
    firmware_sha = provenance.get("firmware_sha256")
    app_sha = provenance.get("app_elf_sha256")
    for label in LABELS:
        run_path = BUNDLE / label / "run.json"
        run = load(run_path)
        runs[label] = run
        candidate = run.get("candidate", {})
        if run.get("passed") is not True or run.get("failures") != [] or \
                run.get("expected_cid") != CID or \
                candidate.get("version") != VERSION or \
                candidate.get("firmware_sha256") != firmware_sha or \
                candidate.get("app_elf_sha256") != app_sha or \
                digest(run_path) != provenance["run_sha256"].get(label):
            fail(f"{label}: run binding mismatch")
        records = run.get("screens", run.get("captures", {}))
        pngs = sorted((BUNDLE / label / "frames").glob("*.png"))
        if len(pngs) != len(records):
            fail(f"{label}: screenshot count mismatch")
        hashes = [record.get("png_sha256") for record in records.values()]
        for png in pngs:
            if png_size(png) != (240, 320) or digest(png) not in hashes:
                fail(f"{label}: invalid or unbound screenshot {png.name}")
        frame_total += len(pngs)
    primary = runs["main"]
    if primary.get("gate_eligible") is not True or \
            primary["candidate"].get("flashed") is not True or \
            primary["candidate"].get("flash_mode") != "fresh" or \
            primary["cleanup_after"]["final_state"].get("lease_mask") != 0:
        fail("fresh main gate/cleanup mismatch")
    for label in ("infrared", "subghz", "wifi_capture"):
        if runs[label]["candidate"].get("exact_flash_reused") is not True:
            fail(f"{label}: exact flash reuse missing")
    if runs["infrared"]["reports"]["terminal"].get("state") != "timed_out" or \
            runs["subghz"]["reports"]["terminal"].get("state") != "timed_out":
        fail("honest no-signal result mismatch")
    wifi = runs["wifi_capture"]
    if wifi["privacy"].get("visual_only") is not True or \
            wifi["privacy"].get("pcap_exported_to_host") is not False or \
            wifi["complete"].get("storage_written") is not False or \
            wifi["scrubbed"].get("state") != "idle":
        fail("Wi-Fi privacy/scrub mismatch")
    expected = {
        "developer_telemetry_on_product_screens": False,
        "exact_flash_reuse_runs": 3,
        "final_lease_mask": 0,
        "manual_button_presses": 0,
        "one_fresh_flash": True,
        "pcap_exported_to_host": False,
        "storage_written": False,
    }
    if frame_total != 37 or summary["evidence"].get("tft_states") != 37 or \
            summary.get("verified") != expected:
        fail("retained claims mismatch")
    print(json.dumps({"status": "pass", "version": VERSION,
                      "tft_states": 37, "fresh_flashes": 1,
                      "exact_reuse_runs": 3,
                      "pcap_exported_to_host": False,
                      "final_lease_mask": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
