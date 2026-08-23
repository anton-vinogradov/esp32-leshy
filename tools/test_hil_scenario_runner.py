#!/usr/bin/env python3
"""Host contracts for the declarative HIL scenario boundary."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_hil_scenario as hil  # noqa: E402


class HilScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = json.loads((
            ROOT / "tests/hil/scenarios/infrared-passive-no-signal.json"
        ).read_text(encoding="utf-8"))
        self.ports = {"candidate": "/dev/candidate"}

    def test_repository_scenario_is_valid_for_one_board(self) -> None:
        hil.validate_scenario(self.scenario, self.ports)

    def test_required_fixture_is_fail_closed_until_bound(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario["devices"]["fixture"] = {
            "required": True, "kind": "bounded_signal_fixture",
        }
        scenario["steps"].insert(1, {
            "id": "fixture-once", "op": "query", "target": "fixture",
            "command": "fixture.ir.nec.once ${session_id} nec-10-34",
            "response_schema": "leshy.hil.fixture.signal.v1", "kind": "result",
        })
        with self.assertRaisesRegex(ValueError, "fixture"):
            hil.validate_scenario(scenario, self.ports)
        hil.validate_scenario(
            scenario, {**self.ports, "fixture": "/dev/fixture"})

    def test_duplicate_and_missing_candidate_ports_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            hil.parse_ports(["candidate=/dev/a", "candidate=/dev/b"])
        with self.assertRaisesRegex(ValueError, "candidate"):
            hil.parse_ports(["fixture=/dev/b"])
        with self.assertRaisesRegex(ValueError, "distinct"):
            hil.parse_ports([
                "candidate=/dev/shared", "fixture=/dev/shared",
            ])

    def test_command_injection_and_path_escape_are_rejected(self) -> None:
        for replacement in (
            {"id": "bad-action", "op": "action", "name": "right\nmetrics"},
            {"id": "bad-query", "op": "query", "command": "metrics\nui.key right",
             "response_schema": "leshy.boot.v1"},
            {"id": "bad-capture", "op": "capture", "name": "../outside"},
        ):
            scenario = copy.deepcopy(self.scenario)
            scenario["steps"][0] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):
                    hil.validate_scenario(scenario, self.ports)

    def test_sleep_and_step_count_are_bounded(self) -> None:
        scenario = copy.deepcopy(self.scenario)
        scenario["steps"][0] = {
            "id": "too-long", "op": "sleep", "seconds": 60.001,
        }
        with self.assertRaisesRegex(ValueError, "0..60"):
            hil.validate_scenario(scenario, self.ports)
        scenario["steps"] = [
            {"id": f"step-{index}", "op": "sleep", "seconds": 0}
            for index in range(257)
        ]
        with self.assertRaisesRegex(ValueError, "1..256"):
            hil.validate_scenario(scenario, self.ports)

    def test_query_placeholders_are_allowlisted_and_fully_rendered(self) -> None:
        command = hil.render_query_command(
            "fixture.ir.nec.once ${session_id} nec-10-34",
            {"session_id": "a" * 32},
        )
        self.assertEqual(
            "fixture.ir.nec.once " + "a" * 32 + " nec-10-34", command)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            hil.render_query_command(
                "fixture.ir.nec.once ${arbitrary_payload}", {})
        with self.assertRaisesRegex(ValueError, "substitution"):
            hil.render_query_command(
                "fixture.ir.nec.once ${session_id}", {})

    def test_fixture_admission_is_exact_and_inactive(self) -> None:
        identity = {
            "version": "0.2.2-bounded-signals",
            "role": "bounded_signal_fixture",
            "fixture_id": "0011223344556677",
            "app_elf_sha256": "a" * 64,
            "identity_ready": True,
            "ir_tx_inactive": True, "nrf_ce_inactive": True,
            "nrf_powered_down": True,
            "buzzer_inactive": True, "fixed_vector_only": True,
            "auto_arm": False, "watchdog_armed": True,
            "maximum_ir_emission_us": 100000,
            "maximum_nrf_carrier_us": 2500000,
            "session_lifetime_ms": 5000,
        }
        self.assertEqual([], hil.fixture_admission_failures(
            identity, "0.2.2-bounded-signals",
            "0011223344556677", "a" * 64))
        identity["ir_tx_inactive"] = False
        self.assertEqual(1, len(hil.fixture_admission_failures(
            identity, "0.2.2-bounded-signals",
            "0011223344556677", "a" * 64)))

    def test_fixture_profile_requires_read_only_accepted_board(self) -> None:
        fixture_id = "0011223344556677"
        profile = {
            "schema": "leshy.hil.board_profile.v1",
            "status": "accepted",
            "accepted_for_fixture_flash": True,
            "port_at_profile": "/dev/fixture",
            "writes_performed": False,
            "flash_erases_performed": 0,
            "flash_bytes_written": 0,
            "ram_stub_uploaded": False,
            "chip": {
                "family": "esp32-s3", "fixture_id": fixture_id,
                "flash_size": "16MB",
            },
            "assembly": {
                "profile": "esp32-div-v2-n16",
                "extension_modules": "none", "antennas_attached": True,
            },
            "operations": [
                {"read_only": True, "returncode": 0} for _ in range(4)
            ],
        }
        hil.validate_fixture_profile(profile, fixture_id, "/dev/fixture")
        with self.assertRaisesRegex(ValueError, "port"):
            hil.validate_fixture_profile(profile, fixture_id, "/dev/other")
        profile["writes_performed"] = True
        with self.assertRaisesRegex(ValueError, "writes_performed"):
            hil.validate_fixture_profile(profile, fixture_id)

    def test_raw_boot_requires_ready_but_recovery_is_query_only(self) -> None:
        ready = {
            "version": "0.129.0-pre-app-watchdog",
            "app_elf_sha256": "a" * 64,
            "buzzer_inactive": True,
            "input_detected": True,
            "input_probe_attempts": 2,
            "input_probe_transient_retries": 1,
        }
        self.assertEqual([], hil.boot_ready_failures(
            ready, "0.129.0-pre-app-watchdog", "a" * 64))
        ready["input_probe_transient_retries"] = 0
        self.assertEqual(1, len(hil.boot_ready_failures(
            ready, "0.129.0-pre-app-watchdog", "a" * 64)))

    def test_repository_positive_fixture_scenario_is_valid(self) -> None:
        scenario = json.loads((
            ROOT / "tests/hil/scenarios/infrared-nec-positive.json"
        ).read_text(encoding="utf-8"))
        hil.validate_scenario(scenario, {
            "candidate": "/dev/candidate", "fixture": "/dev/fixture",
        })

    def test_repository_nrf24_fixture_scenario_is_valid(self) -> None:
        scenario = json.loads((
            ROOT / "tests/hil/scenarios/nrf24-carrier-positive.json"
        ).read_text(encoding="utf-8"))
        hil.validate_scenario(scenario, {
            "candidate": "/dev/candidate", "fixture": "/dev/fixture",
        })

    def test_repository_nrf24_fixture_regression_is_valid(self) -> None:
        scenario = json.loads((
            ROOT / "tests/hil/scenarios/nrf24-fixture-regression.json"
        ).read_text(encoding="utf-8"))
        hil.validate_scenario(scenario, {
            "candidate": "/dev/candidate", "fixture": "/dev/fixture",
        })

    def test_numeric_checks_are_deterministic(self) -> None:
        record = {"samples": 345272, "nested": {"state": "timed_out"}}
        self.assertEqual([], hil.evaluate_checks(record, [
            {"path": "samples", "op": "gte", "value": 100000},
            {"path": "nested.state", "op": "eq", "value": "timed_out"},
        ], "terminal"))
        failures = hil.evaluate_checks(record, [
            {"path": "samples", "op": "lt", "value": 1},
        ], "terminal")
        self.assertEqual(1, len(failures))

    def test_nested_expectations_are_subset_checks(self) -> None:
        record = {
            "begin": {"schema": "fixture", "status": "valid", "extra": 1},
        }
        self.assertEqual([], hil.evaluate_expectations(
            record, {"begin": {"status": "valid"}}, "stream"))
        self.assertEqual(1, len(hil.evaluate_expectations(
            record, {"begin": {"status": "failed"}}, "stream")))

    def test_framed_ir_csv_is_retained_without_json_markers(self) -> None:
        payload = (
            b"pulse_index,level,duration_us\r\n"
            b"0,0,9000\r\n1,1,4500\r\n"
        )

        class Device:
            def __init__(self) -> None:
                self.lines = iter((
                    b'{"schema":"leshy.capture.infrared_raw.csv.v1",'
                    b'"kind":"csv_begin","pulses":2}\n',
                    payload.splitlines(keepends=True)[0],
                    payload.splitlines(keepends=True)[1],
                    payload.splitlines(keepends=True)[2],
                    b'{"schema":"leshy.capture.infrared_raw.csv.v1",'
                    b'"kind":"csv_end","status":"valid","bytes":56}\n',
                ))
                self.command = b""

            def reset_input_buffer(self) -> None:
                pass

            def write(self, value: bytes) -> None:
                self.command += value

            def flush(self) -> None:
                pass

            def readline(self) -> bytes:
                return next(self.lines, b"")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "live.csv"
            device = Device()
            record, retained = hil.read_framed_stream(
                device, "capture.ir.export.csv", output, 0.1)
            self.assertEqual(b"capture.ir.export.csv\n", device.command)
            self.assertEqual(payload, retained)
            self.assertEqual(payload, output.read_bytes())
            self.assertEqual(len(payload), record["bytes"])


if __name__ == "__main__":
    unittest.main()
