#!/usr/bin/env python3
"""Host tests for the fail-closed physical power-cut runner contract."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


class Port:
    def __init__(self, device: str, serial_number: str = "SERIAL",
                 vid: int = 0x303A, pid: int = 0x1001,
                 location: str = "2-1") -> None:
        self.device = device
        self.serial_number = serial_number
        self.vid = vid
        self.pid = pid
        self.location = location


PORTS: list[Port] = []


def load_runner() -> Any:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    list_ports_stub.comports = lambda: list(PORTS)
    tools_stub.list_ports = list_ports_stub
    serial_stub.tools = tools_stub
    sys.modules.setdefault("serial", serial_stub)
    sys.modules.setdefault("serial.tools", tools_stub)
    sys.modules.setdefault("serial.tools.list_ports", list_ports_stub)

    capture_stub = types.ModuleType("capture_1x_ui")
    capture_stub.PassiveSerial = object
    capture_stub.read_json = lambda *_args, **_kwargs: None
    capture_stub.synchronize_console = lambda *_args, **_kwargs: None
    sys.modules.setdefault("capture_1x_ui", capture_stub)

    identity_stub = types.ModuleType("esp_app_identity")
    identity_stub.app_elf_sha256 = lambda _path: "app"
    sys.modules.setdefault("esp_app_identity", identity_stub)

    path = Path(__file__).with_name("run_1x_sd_power_cut_matrix.py")
    spec = importlib.util.spec_from_file_location("sd_power_cut_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()
RUN_ID = "power-cut-b4"
BOUNDARY = 4


def valid_arm() -> dict[str, Any]:
    return {
        "schema": RUNNER.SCHEMA,
        "kind": "armed",
        "status": "ready",
        "run_id": RUN_ID,
        "boundary": BOUNDARY,
        "fingerprint_matched": True,
        "initial_generation": 1,
        "initial_observations": 3,
        "format_allowed": False,
        "writes_bounded_to_scratch": True,
        "reset_injection": False,
        "physical_power_cut": True,
        "radio_tx_commands": 0,
    }


def valid_recovery() -> dict[str, Any]:
    return {
        "schema": RUNNER.SCHEMA,
        "kind": "result",
        "mode": "recovery",
        "status": "valid",
        "run_id": RUN_ID,
        "boundary": BOUNDARY,
        "reset_reason_code": 1,
        "software_reset": False,
        "power_on_reset": True,
        "fingerprint_matched": True,
        "read_permit_status": "permitted",
        "scratch_exists": True,
        "opened_read_only": True,
        "session_store_io_writable": False,
        "generation_allowed": True,
        "reopened_observations": 3,
        "prior_unchanged": True,
        "bytes_written": 0,
        "file_syncs": 0,
        "directory_syncs": 0,
        "owned_after": 0,
        "cleanup_complete": True,
        "format_allowed": False,
        "existing_paths_deleted": False,
        "reset_injection": False,
        "physical_power_cut": True,
        "radio_tx_commands": 0,
    }


def transient_recovery() -> dict[str, Any]:
    record = valid_recovery()
    record.update({
        "status": "failed",
        "fingerprint_matched": False,
        "read_permit_status": "missing_media",
    })
    return record


class PowerCutContractTests(unittest.TestCase):
    def tearDown(self) -> None:
        PORTS.clear()

    def test_same_usb_identity_survives_device_path_change(self) -> None:
        identity = {
            "serial_number": "SERIAL", "vid": 0x303A,
            "pid": 0x1001, "location": "2-1",
        }
        PORTS.append(Port("/dev/cu.usbmodem9999"))
        self.assertEqual("/dev/cu.usbmodem9999", RUNNER.matching_port(identity))

    def test_ambiguous_usb_identity_fails_closed(self) -> None:
        identity = {
            "serial_number": "SERIAL", "vid": 0x303A,
            "pid": 0x1001, "location": None,
        }
        PORTS.extend([Port("/dev/a"), Port("/dev/b", location="2-2")])
        self.assertIsNone(RUNNER.matching_port(identity))

    def test_arm_requires_physical_not_software_reset(self) -> None:
        self.assertFalse(RUNNER.arm_mismatches(valid_arm(), RUN_ID, BOUNDARY))
        for key, value in {
            "reset_injection": True,
            "physical_power_cut": False,
            "fingerprint_matched": False,
            "format_allowed": True,
        }.items():
            with self.subTest(key=key):
                record = valid_arm()
                record[key] = value
                self.assertIn(key, RUNNER.arm_mismatches(
                    record, RUN_ID, BOUNDARY))

    def test_recovery_requires_power_on_and_zero_writes(self) -> None:
        self.assertFalse(RUNNER.recovery_mismatches(
            valid_recovery(), RUN_ID, BOUNDARY))
        for key, value in {
            "reset_reason_code": 3,
            "software_reset": True,
            "power_on_reset": False,
            "bytes_written": 1,
            "file_syncs": 1,
            "directory_syncs": 1,
            "prior_unchanged": False,
            "owned_after": 12,
        }.items():
            with self.subTest(key=key):
                record = valid_recovery()
                record[key] = value
                self.assertIn(key, RUNNER.recovery_mismatches(
                    record, RUN_ID, BOUNDARY))

    def test_only_exact_zero_write_media_readiness_is_retryable(self) -> None:
        self.assertTrue(RUNNER.retryable_media_readiness(
            transient_recovery(), RUN_ID, BOUNDARY))
        for key, value in {
            "reset_reason_code": 3,
            "bytes_written": 1,
            "read_permit_status": "fingerprint_mismatch",
            "physical_power_cut": False,
            "cleanup_complete": False,
        }.items():
            with self.subTest(key=key):
                record = transient_recovery()
                record[key] = value
                self.assertFalse(RUNNER.retryable_media_readiness(
                    record, RUN_ID, BOUNDARY))

    def test_exact_boot_requires_expected_candidate_and_power_on(self) -> None:
        boot = {
            "version": "0.101", "app_elf_sha256": "app",
            "input_detected": True, "buzzer_inactive": True,
            "buzzer_safety_configured": True, "reset_reason_code": 1,
        }
        self.assertFalse(RUNNER.exact_boot_mismatches(
            boot, "0.101", "app", require_power_on=True))
        boot["reset_reason_code"] = 11
        self.assertIn("reset_reason_code", RUNNER.exact_boot_mismatches(
            boot, "0.101", "app", require_power_on=True))


if __name__ == "__main__":
    unittest.main()
