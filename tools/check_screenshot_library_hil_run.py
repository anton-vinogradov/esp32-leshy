#!/usr/bin/env python3
"""Fail closed on an incomplete screenshot/Library physical run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "leshy.screenshot_library_hil.run.v1"
HEX64 = set("0123456789abcdef")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run_path = args.run.resolve()
    root = run_path.parent
    value: dict[str, Any] = json.loads(run_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    need(value.get("schema") == SCHEMA, "schema mismatch")
    need(value.get("status") == "pass" and value.get("passed") is True,
         "run did not pass")
    need(value.get("failures") == [], "run retained failures")
    need(value.get("exact_port") == "/dev/cu.usbmodem2101",
         "run is not bound to original board-01")
    policy = value.get("policy", {})
    need(policy.get("mac_wifi_controlled") is False, "Mac Wi-Fi was controlled")
    need(policy.get("clone_port_touched") is False, "clone port was touched")
    need(policy.get("radio_tx_commands") == 0, "radio TX was requested")
    need(policy.get("temporary_device_lock_fixture") is False,
         "temporary encryption key invalidates persistence proof")
    candidate = value.get("candidate", {})
    for key in ("firmware_sha256", "app_elf_sha256"):
        item = candidate.get(key)
        need(isinstance(item, str) and len(item) == 64 and set(item) <= HEX64,
             f"candidate.{key} invalid")
    records = value.get("records", {})
    reference = records.get("reference", {})
    exported = records.get("export", {})
    need(reference.get("bytes") == 153600, "reference size invalid")
    need(exported.get("bytes") == 153600, "export size invalid")
    need(reference.get("sha256") == exported.get("sha256"),
         "stored screenshot differs from exact TFT reference")
    need(exported.get("frame_end", {}).get("status") == "valid",
         "export did not end validly after cleanup")
    export_begin = exported.get("frame_begin", {})
    identity_attempts = export_begin.get("identity_attempts")
    identity_retries = export_begin.get("identity_transient_retries")
    need(isinstance(identity_attempts, int) and
         1 <= identity_attempts <= 8,
         "export identity attempt count invalid")
    need(isinstance(identity_retries, int) and
         identity_retries == identity_attempts - 1,
         "export identity retry count invalid")
    generation = records.get("generation")
    need(isinstance(generation, int) and generation > 0, "generation invalid")
    cold = records.get("cold_recovery", {})
    need(cold.get("screenshot_admitted") is True,
         "cold boot did not admit Screenshot")
    need(cold.get("screenshot_generation") == generation,
         "cold boot recovered another generation")
    need(cold.get("mounted_read_only") is True and
         cold.get("read_only_guaranteed") is True and
         cold.get("physical_write_calls") == 0,
         "cold recovery was not strictly read-only")
    final_ui = records.get("final_ui", {})
    need(final_ui.get("page") == "home" and
         final_ui.get("runtime_owner") == "none" and
         final_ui.get("lease_mask") == 0,
         "final UI/resource state is not clean Home")
    for name in ("capture-reference.rgb565", "capture-reference.png",
                 "exported.rgb565", "exported.png", "firmware.bin",
                 "firmware.elf", "firmware.map", "artifacts.sha256"):
        need((root / name).is_file(), f"artifact missing: {name}")
    if (root / "capture-reference.rgb565").is_file():
        need(digest(root / "capture-reference.rgb565") ==
             reference.get("sha256"), "reference artifact hash mismatch")
    if (root / "exported.rgb565").is_file():
        need(digest(root / "exported.rgb565") == exported.get("sha256"),
             "export artifact hash mismatch")

    if failures:
        print(json.dumps({"passed": False, "failures": failures}, sort_keys=True))
        return 1
    print("screenshot/Library HIL run accepted: exact TFT bytes, protected export, cold recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
