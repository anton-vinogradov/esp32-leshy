#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import inspect
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


def load_runner() -> Any:
    path = Path(__file__).with_name("run_1x_field_survey_hil.py")
    spec = importlib.util.spec_from_file_location("field_survey_hil_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


def result(status: str = "first_visit") -> dict[str, Any]:
    record = {
        "active": True,
        "previous_available": status == "compared",
        "compare_previous": status == "compared",
        "status": status,
        "build_status": "complete",
        "complete": True,
        "current_unique": 5,
        "baseline_unique": 0,
        "seen_again": 0,
        "new_this_visit": 5,
        "missing_this_visit": 0,
        "wifi_access_points": 2,
        "wifi_stations": 1,
        "ble_devices": 2,
        "session_id_exact": True,
        "session_stopped": True,
        "radio_touched": False,
        "storage_touched": False,
    }
    if status == "compared":
        record.update({
            "baseline_unique": 4,
            "seen_again": 3,
            "new_this_visit": 2,
            "missing_this_visit": 1,
        })
    return record


class FieldSurveyHilRunnerTests(unittest.TestCase):
    def test_library_oracle_accepts_coexisting_non_session_entries(self) -> None:
        library = {
            "page": "library", "library_view": "list",
            "library_entries": 2, "library_generation": 10,
            "library_persistent": True, "runtime_owner": "library",
            "lease_mask": 5, "library_selected_kind": "session",
        }
        self.assertEqual(
            [], RUNNER.field_survey_library_failures(library, 10))
        library["library_entries"] = 0
        self.assertTrue(
            RUNNER.field_survey_library_failures(library, 10))
        library["library_entries"] = 2
        library["library_selected_kind"] = "screenshot"
        self.assertTrue(
            RUNNER.field_survey_library_failures(library, 10))

    def test_export_validators_require_deduplicated_truthful_rows(self) -> None:
        native_payload = (
            ",".join(RUNNER.NATIVE_COLUMNS) + "\r\n" +
            "wifi_access_point,AA:BB:CC:DD:EE:FF,Cafe,1,2,3,2437000,"
            "6,-42,-51,wpa2_psk,ccmp,ccmp,\r\n" +
            "ble_device,11:22:33:44:55:66,Tag,3,4,1,0,0,-60,-60,,,,0x004C\r\n"
        ).encode("utf-8")
        native_begin = {
            "status": "valid", "generation": 172,
            "session_id": RUNNER.FIELD_SESSION_ID, "records": 2,
            "columns": 14, "line_endings": "crlf",
            "deduplicated": True, "persistent": True,
            "radio_touched": False,
        }
        native_end = {
            "status": "complete", "records": 2,
            "bytes": len(native_payload), "radio_touched": False,
        }
        failures, summary = RUNNER.native_export_failures(
            native_begin, native_payload, native_end,
            generation=172, records=2)
        self.assertEqual([], failures)
        self.assertEqual(4, summary["observations"])
        self.assertFalse(summary["ambient_identifiers_retained"])

        wigle_payload = (
            "WigleWifi-1.6,appRelease=ESP32-Leshy-test\r\n" +
            ",".join(RUNNER.WIGLE_COLUMNS) + "\r\n" +
            "AA:BB:CC:DD:EE:FF,Cafe,Auth,,6,2437,-42,,,,,,,WIFI\r\n" +
            "11:22:33:44:55:66,Tag,Misc [LE],,0,,-60,,,,,,0x004C,BLE\r\n"
        ).encode("utf-8")
        wigle_begin = {
            "status": "valid", "generation": 172,
            "session_id": RUNNER.FIELD_SESSION_ID,
            "format": "wigle_wifi_1.6", "records": 2,
            "skipped_wifi_stations": 0,
            "readiness": "untimed_unlocated", "trusted_utc": False,
            "trusted_location": False, "upload_ready": False,
            "persistent": True, "radio_touched": False,
        }
        wigle_end = {
            "status": "complete", "records": 2,
            "bytes": len(wigle_payload), "skipped_wifi_stations": 0,
            "readiness": "untimed_unlocated", "upload_ready": False,
            "radio_touched": False,
        }
        failures, summary = RUNNER.wigle_export_failures(
            wigle_begin, wigle_payload, wigle_end,
            generation=172, records=2)
        self.assertEqual([], failures)
        self.assertEqual({"WIFI": 1, "BLE": 1}, summary["entity_counts"])
        self.assertFalse(summary["upload_ready"])

    def test_export_validators_retain_station_only_in_native(self) -> None:
        native_payload = (
            ",".join(RUNNER.NATIVE_COLUMNS) + "\r\n" +
            "wifi_access_point,AA:BB:CC:DD:EE:FF,Cafe,1,2,3,2437000,"
            "6,-42,-51,wpa2_psk,ccmp,ccmp,\r\n" +
            "wifi_station,12:34:56:78:9A:BC,Phone,3,4,1,2437000,"
            "6,-60,-60,,,,\r\n"
        ).encode("utf-8")
        native_begin = {
            "status": "valid", "generation": 173,
            "session_id": RUNNER.FIELD_SESSION_ID, "records": 2,
            "columns": 14, "line_endings": "crlf",
            "deduplicated": True, "persistent": True,
            "radio_touched": False,
        }
        native_end = {
            "status": "complete", "records": 2,
            "bytes": len(native_payload), "radio_touched": False,
        }
        failures, summary = RUNNER.native_export_failures(
            native_begin, native_payload, native_end,
            generation=173, records=2, wifi_stations=1)
        self.assertEqual([], failures)
        self.assertEqual(1, summary["entity_counts"]["wifi_station"])

        wigle_payload = (
            "WigleWifi-1.6,appRelease=ESP32-Leshy-test\r\n" +
            ",".join(RUNNER.WIGLE_COLUMNS) + "\r\n" +
            "AA:BB:CC:DD:EE:FF,Cafe,Auth,,6,2437,-42,,,,,,,WIFI\r\n"
        ).encode("utf-8")
        wigle_begin = {
            "status": "valid", "generation": 173,
            "session_id": RUNNER.FIELD_SESSION_ID,
            "format": "wigle_wifi_1.6", "records": 1,
            "skipped_wifi_stations": 1,
            "readiness": "untimed_unlocated", "trusted_utc": False,
            "trusted_location": False, "upload_ready": False,
            "persistent": True, "radio_touched": False,
        }
        wigle_end = {
            "status": "complete", "records": 1,
            "bytes": len(wigle_payload), "skipped_wifi_stations": 1,
            "readiness": "untimed_unlocated", "upload_ready": False,
            "radio_touched": False,
        }
        failures, summary = RUNNER.wigle_export_failures(
            wigle_begin, wigle_payload, wigle_end,
            generation=173, records=2, wifi_stations=1)
        self.assertEqual([], failures)
        self.assertEqual({"WIFI": 1, "BLE": 0}, summary["entity_counts"])

    def test_first_visit_result_requires_exact_count_accounting(self) -> None:
        record = result()
        self.assertEqual(
            [], RUNNER.field_result_failures(record, "first_visit"))
        record["ble_devices"] = 1
        self.assertTrue(
            RUNNER.field_result_failures(record, "first_visit"))

    def test_station_delta_requires_live_station(self) -> None:
        record = result()
        self.assertEqual([], RUNNER.field_result_failures(
            record, "first_visit", require_wifi_station=True))
        record["wifi_access_points"] += record["wifi_stations"]
        record["wifi_stations"] = 0
        self.assertTrue(RUNNER.field_result_failures(
            record, "first_visit", require_wifi_station=True))

    def test_revisit_result_requires_set_arithmetic_and_exact_baseline(self) -> None:
        record = result("compared")
        self.assertEqual(
            [], RUNNER.field_result_failures(record, "compared", 4))
        record["missing_this_visit"] = 2
        self.assertTrue(
            RUNNER.field_result_failures(record, "compared", 4))

    def test_navigation_timeout_is_not_replayed(self) -> None:
        recovered = {"page": "survey"}
        with patch.object(RUNNER, "raw_action", side_effect=TimeoutError("lost")), \
             patch.object(RUNNER, "read_only_query", return_value=recovered):
            state = RUNNER.action(object(), "down")
        self.assertEqual(1, state["host_navigation_action_writes"])
        self.assertEqual(0, state["host_navigation_action_replays"])
        self.assertFalse(state["host_navigation_ack_received"])

    def test_hil_begin_timeout_recovers_read_only_without_replay(self) -> None:
        recovered = {
            "session_id": "1" * 32,
            "active": True,
            "app_elf_sha256": "a" * 64,
            "firmware_version": "test",
        }
        with patch.object(RUNNER, "query", side_effect=TimeoutError("lost")), \
             patch.object(RUNNER, "read_only_query", return_value=recovered):
            state = RUNNER.begin_hil(
                object(), "1" * 32, "a" * 64, "test")
        self.assertEqual(1, state["host_begin_action_writes"])
        self.assertEqual(0, state["host_begin_action_replays"])
        self.assertFalse(state["host_begin_ack_received"])

    def test_wait_aborts_and_retains_exact_safety_latch(self) -> None:
        ui = {
            "safety_latched": True,
            "survey_product_preparation_stage": "filesystem_mount",
        }
        safety = {
            "worker_last_expired": "product_survey_preparation",
            "worker_age_ms": 8001,
            "product_survey_preparation_stage": "filesystem_mount",
        }
        trace: list[dict[str, Any]] = []
        with patch.object(
                RUNNER, "read_only_query", side_effect=[ui, safety]):
            with self.assertRaisesRegex(
                    RuntimeError, "stage='filesystem_mount'"):
                RUNNER.wait_state(
                    object(), lambda _: False, 1.0, "waiting", trace)
        self.assertEqual("safety_latched", trace[0]["checkpoint"])
        self.assertEqual(safety, trace[0]["safety"])

    def test_runner_is_single_flash_and_contains_physical_negative(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        self.assertEqual(1, source.count("flash_candidate(args.port"))
        self.assertIn("--reuse-exact-flash", source)
        self.assertIn('b"storage.product.boot-recovery"', source)
        self.assertIn('maximum_attempts=1', source)
        self.assertLess(
            source.index('b"storage.product.boot-recovery"'),
            source.index("failures.extend(boot_failures("),
        )
        self.assertIn("survey.field-visit.test-incomplete once", source)
        self.assertIn('"survey_product_wifi_scan_cycles"', source)
        self.assertIn('"survey_product_ble_scan_cycles"', source)
        self.assertIn('"page": "home", "runtime_owner": "none", "lease_mask": 0',
                      source)

    def test_preflight_requires_both_sources_and_never_commits(self) -> None:
        source = inspect.getsource(RUNNER.run_preflight)
        self.assertIn('"survey_product_wifi_scan_cycles"', source)
        self.assertIn('"survey_product_ble_scan_cycles"', source)
        self.assertIn('"survey_product_status") == "paused"', source)
        self.assertNotIn('action(device, "up")', source)
        self.assertIn('"writes_committed": 0', source)
        self.assertNotIn("field_state(", source)
        self.assertNotIn("committed_failures(", source)

    def test_preflight_is_never_gate_eligible(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        self.assertIn("not args.preflight_only and", source)

    def test_post_commit_recovery_requires_exact_read_only_generation(self) -> None:
        record = {
            "status": "admitted",
            "catalog_admitted": True,
            "integrity": "valid",
            "expected_fingerprint": "A" * 32,
            "observed_fingerprint": "A" * 32,
            "fingerprint_matched": True,
            "generation": 172,
            "observations": 52,
            "mounted_read_only": True,
            "read_only_guaranteed": True,
            "write_enabled": False,
            "physical_write_calls": 0,
            "blocked_write_attempts": 0,
            "cleanup_complete": True,
            "owned_after": 0,
        }
        self.assertEqual([], RUNNER.post_commit_recovery_failures(
            record, "A" * 32, 172, "cold"))
        record["generation"] = 171
        self.assertTrue(RUNNER.post_commit_recovery_failures(
            record, "A" * 32, 172, "cold"))

    def test_full_mode_cold_reopens_after_revisit_and_recovery_only_is_delta(self) -> None:
        source = Path(RUNNER.__file__).read_text(encoding="utf-8")
        self.assertIn('"post-commit-cold"', source)
        self.assertLess(
            source.index('revisit = run_visit('),
            source.index('"post-commit-cold"'),
        )
        self.assertIn("--recovery-only", source)
        self.assertIn("--expected-generation", source)
        self.assertIn("not args.recovery_only and", source)
        self.assertIn("bool(post_commit_recovery) and", source)

    def test_export_mode_is_read_only_and_retains_no_ambient_ids(self) -> None:
        source = inspect.getsource(RUNNER.run_exports)
        self.assertIn('b"library.field-survey.export.native"', source)
        self.assertIn('b"library.field-survey.export.wigle"', source)
        self.assertNotIn("run_visit(", source)
        self.assertNotIn("write_bytes", source)
        self.assertIn("ambient_identifiers_retained", inspect.getsource(
            RUNNER.native_export_failures))
        self.assertIn('"runtime_owner": "library"', source)
        self.assertIn('"lease_mask": 5', source)


if __name__ == "__main__":
    unittest.main()
