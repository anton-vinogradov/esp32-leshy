#!/usr/bin/env python3
"""Fail closed unless the exact dev.285 Serial Console HIL evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT / "tests/hil/evidence/"
    "board-01-serial-console-stock-conflict-1.0.0-dev.285.json"
)


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        if not (
            value["schema"] ==
            "leshy.serial_console_stock_conflict.acceptance.v1"
            and value["status"] == "pass_stock_profile_product_negative"
            and value["evidence_ids"] == [
                "E-BUILD-200", "E-AUTO-175", "E-HIL-211", "E-UX-066"
            ]
            and value["exact_cid"] == "FE343253440000002000000055019CB7"
        ):
            failures.append("summary identity/status mismatch")

        if value["board"] != {
            "id": "board-01",
            "port": "/dev/cu.usbmodem2101",
            "mac": "1c:db:d4:87:90:d4",
        }:
            failures.append("original-board USB isolation mismatch")

        if value["candidate"] != {
            "version": "1.0.0-dev.285",
            "source_commit": "8a5799aca03f96ae518ae0c7c7391b43828d6f4f",
            "flash_mode": "exact_reuse_after_one_fresh_flash",
            "firmware_sha256":
                "9119f8c86e2ca9822fc18b754e58d25536e4ff1f11d15b412e01be3b5e02d993",
            "factory_sha256":
                "5ea9f9e43733a538718650b05f3ec9f5a6add31e5b2f839a12bdbb3aad94e63d",
            "app_elf_sha256":
                "f662101891a7857435e576374ff2a250558b0487ee4c306829499473dfe93348",
            "elf_sha256":
                "f662101891a7857435e576374ff2a250558b0487ee4c306829499473dfe93348",
            "map_sha256":
                "37d38edcafce37bcf2423b6fcacc4a76f475fb7162687c9006ef49114ea30428",
            "firmware_bytes": 3523472,
            "factory_bytes": 3589008,
        }:
            failures.append("candidate identity/build budget mismatch")

        evidence = value["evidence"]
        expected_evidence = {
            "run_id": "80f43a12e29fe4271a2d4c8fc1e0728f",
            "run_sha256":
                "ba25d3d2bcff059018b02de7e367c8836c16c20caf305c84312aadf5ce7bcf9b",
            "runner_sha256":
                "de2b942029e3446dc6ea254f3f59995ab8e94d07fbd3611715311a49ffc721df",
            "artifacts_sha256":
                "5ff09ad1a3d1834a86a8257af46af2453151e5b5d3afbf83cf4ae6d1386954b1",
            "product_checker_sha256":
                "27d4f74a7b7cd1a10ac85ab271d83351592daa8d858004a4ace24ea2deb672a4",
            "screen_png_sha256":
                "d28dd8c9a79280d051d75208f3b8623643c3542d01353dd3dd6d586fa5408568",
            "screen_rgb565_sha256":
                "b30e2c54b8014f437a5bf59aa6ab7b295ef19b08be499f9df8f1e72227adc1a6",
            "oracle_precursor_run_sha256":
                "61d05350f43ace9daa0d440d6fccdb78677b0e2213fc54c7c450f73ded4dc58b",
            "oracle_precursor_runner_sha256":
                "4acf259a71f495117923521dcef4e4a2c6423ec4bb5c897e6e96699d787c794f",
        }
        if evidence != expected_evidence:
            failures.append("retained run/artifact lineage mismatch")

        verified = value["verified"]
        expected_verified = {
            "preflight": "mux_conflict",
            "product_page": "serial_console",
            "stock_ui_action_changed": False,
            "action_resources_after_preview": 0,
            "action_resources_after_run": 0,
            "product_page_console_or_mux56_lease": False,
            "pins_touched": False,
            "uart_configure_calls_expected": 0,
            "uart_start_calls_expected": 0,
            "action_buffer_high_water": 0,
            "action_dropped_bytes": 0,
            "heap_free_before": 72576,
            "heap_free_after": 72576,
            "safe_outputs_unchanged": True,
            "cleanup_complete": True,
            "cli_raw_gpio_rejected": True,
            "final_page": "home",
            "final_runtime_owner": "none",
            "final_lease_mask": 0,
            "final_safety_state": "armed",
            "application_raw_tx_calls": 0,
            "radio_connect_calls": 0,
            "manual_button_presses": 0,
            "mac_wifi_touched": False,
            "clone_touched": False,
            "cardputer_touched": False,
        }
        if verified != expected_verified:
            failures.append("stock-conflict safety/cleanup assertions mismatch")

        expected_open = [
            "positive receive-only traffic on an explicitly reviewed no-RF "
            "mux56-3v3 fixture",
            "positive Bridge traffic and explicit serial.write permission",
            "timeout, endpoint-failure and safety-stop cleanup on the positive "
            "fixture",
            "explicit encrypted transcript Save and cold reopen/export",
        ]
        if value["open"] != expected_open:
            failures.append("open positive-fixture claims are no longer explicit")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Serial Console HIL acceptance passed: exact original board, stock "
        "mux conflict, zero pin/UART/radio side effects, invariant heap, "
        "zero leaked leases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
