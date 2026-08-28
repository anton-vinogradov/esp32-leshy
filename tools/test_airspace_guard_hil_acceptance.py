#!/usr/bin/env python3
"""Host tests for the fail-closed Airspace Guard HIL acceptance checker."""

from __future__ import annotations

import argparse
import binascii
import copy
import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any

def load_checker() -> Any:
    path = Path(__file__).with_name("check_airspace_guard_hil_acceptance.py")
    spec = importlib.util.spec_from_file_location("airspace_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()
SOURCE = "c" * 40
APP = "d" * 64


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RUNNER_SHA = digest(
    Path(__file__).with_name("run_1x_airspace_guard_hil.py").read_bytes())


def esp_image(app_sha256: str) -> bytes:
    image = bytearray(512)
    image[0] = 0xE9
    descriptor = 24 + 8
    struct.pack_into("<I", image, descriptor, 0xABCD5432)
    image[descriptor + 144:descriptor + 176] = bytes.fromhex(app_sha256)
    return bytes(image)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return (struct.pack(">I", len(payload)) + body +
            struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF))


def rgb565be_to_png(frame: bytes, width: int, height: int) -> bytes:
    rows = bytearray()
    offset = 0
    for _ in range(height):
        rows.append(0)
        for _ in range(width):
            value = (frame[offset] << 8) | frame[offset + 1]
            offset += 2
            red = (value >> 11) & 0x1F
            green = (value >> 5) & 0x3F
            blue = value & 0x1F
            rows.extend(((red << 3) | (red >> 2),
                         (green << 2) | (green >> 4),
                         (blue << 3) | (blue >> 2)))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) +
            png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9)) +
            png_chunk(b"IEND", b""))


def result(generation: int, capacity_drops: int = 0) -> dict[str, Any]:
    injected = capacity_drops > 0
    actual_drops = 199 if injected else 0
    retained = 1 if injected else 56
    available = 16 + retained
    return {
        "schema": CHECKER.STATE_SCHEMA,
        "kind": "state",
        "capture_state": "result",
        "generation": generation,
        "load_status": "ready",
        "elevated_noise_low_confidence": True,
        "noise_samples_dropped": 0,
        "noise_samples_malformed": 0,
        "noise_samples_observed": 0,
        "noise_samples_available": 0,
        "noise_samples_inspected": 0,
        "malformed_frames": 0,
        "source_read_failures": 0,
        "findings_dropped": 0,
        "inspection_truncated": False,
        "wifi_capture_state": "complete",
        "wifi_driver_error": 0,
        "wifi_cleanup_complete": True,
        "wifi_monitor_active": False,
        "wifi_disconnects_dropped": 0,
        "wifi_identity_dropped": 0,
        "wifi_noise_dropped": 0,
        "wifi_receive_invalid_frames": 0,
        "wifi_identity_malformed_envelope": 0,
        "wifi_identity_malformed_addressing": 0,
        "wifi_identity_malformed_elements": 0,
        "wifi_invalid_frames": 0,
        "source_frames_dropped": actual_drops,
        "wifi_identity_retention_complete": True,
        "wifi_noise_retention_complete": True,
        "evidence_incomplete": injected,
        "ble_worker_control": 0,
        "ble_worker_ready": True,
        "ble_worker_status": (
            "incomplete_evidence" if injected else "complete"
        ),
        "ble_worker_valid": True,
        "ble_worker_generation": generation,
        "ble_capacity_drop_requested": injected,
        "ble_capacity_drop_injected": injected,
        "ble_scan_status": "valid",
        "ble_scan_attempts": 1,
        "ble_scan_transient_retries": 0,
        "ble_cleanup_complete": True,
        "ble_scan_observed": 200,
        "ble_scan_reported": 200,
        "ble_scan_read": 200,
        "ble_scan_accepted": 200 - actual_drops,
        "ble_scan_rejected": 0,
        "ble_scan_dropped": actual_drops,
        "ble_retention_observed": 200,
        "ble_retention_valid": 200,
        "ble_retention_retained": retained,
        "ble_retention_dropped": actual_drops,
        "ble_retention_malformed": 0,
        "survey_queues_released": True,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
        "outcome": "finding",
        "view": "finding",
        "finding_selection": 0,
        "evidence_selection": 0,
        "source_frames_observed": 300,
        "frames_available": available,
        "frames_inspected": available,
        "ble_records": retained,
        "wifi_frames_reported": 100,
        "wifi_frames_retained": 16,
        "wifi_identity_retained": 16,
        "wifi_identity_projected": 16,
        "finding_mask": 16,
        "finding_count": 1,
    }


def running(stage: str, generation: int) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": CHECKER.STATE_SCHEMA,
        "kind": "state",
        "capture_state": stage,
        "generation": generation,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
        "ble_worker_ready": True,
        "survey_queues_released": True,
        "heap_free_before_queue_release": 100,
        "heap_free_after_queue_release": 200,
    }
    if stage == "wifi_running":
        value.update({
            "wifi_capture_state": "running",
            "wifi_monitor_active": True,
            "wifi_cleanup_complete": False,
            "wifi_driver_error": 0,
            "ble_worker_control": 0,
        })
    else:
        value.update({
            "wifi_capture_state": "complete",
            "wifi_monitor_active": False,
            "wifi_cleanup_complete": True,
            "wifi_driver_error": 0,
            "wifi_disconnects_dropped": 0,
            "wifi_identity_dropped": 0,
            "wifi_noise_dropped": 0,
            "wifi_receive_invalid_frames": 0,
            "ble_worker_control": 2,
        })
    return value


def stopped(generation: int) -> dict[str, Any]:
    return {
        "schema": CHECKER.STATE_SCHEMA,
        "kind": "state",
        "capture_state": "idle",
        "generation": generation,
        "wifi_capture_state": "idle",
        "wifi_monitor_active": False,
        "wifi_cleanup_complete": True,
        "ble_worker_control": 0,
        "survey_queues_released": False,
        "passive_only": True,
        "rx_only": True,
        "application_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "runtime_owner": "wifi",
        "lease_mask": 15,
    }


def cleanup() -> dict[str, Any]:
    return {
        "attempted": True,
        "complete": True,
        "errors": [],
        "final_state": {
            "schema": "leshy.ui.v1",
            "kind": "state",
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "safety_state": "armed",
            "safety_latched": False,
            "survey_product_backend_open": False,
            "survey_product_storage_mounted": False,
            "survey_product_source_active": False,
        },
    }


def recovery() -> dict[str, Any]:
    return {
        "expected_fingerprint": CHECKER.CID,
        "observed_fingerprint": CHECKER.CID,
        "fingerprint_matched": True,
        "integrity": "valid",
        "mounted_read_only": True,
        "read_only_guaranteed": True,
        "write_enabled": False,
        "blocked_write_attempts": 0,
        "physical_write_calls": 0,
        "cleanup_complete": True,
        "owned_after": 0,
        "generation": 10,
        "observations": 40,
    }


def boot(firmware: str) -> dict[str, Any]:
    del firmware
    return {
        "schema": "leshy.boot.v1",
        "kind": "ready",
        "version": CHECKER.VERSION,
        "app_elf_sha256": APP,
        "reset_reason_code": 1,
        "input_detected": True,
        "buzzer_safety_configured": True,
        "buzzer_inactive": True,
        "legacy_sources": False,
        "heap_total": 134116,
        "heap_free": 60548,
        "heap_min_free": 512,
    }


def negative(firmware: str) -> dict[str, Any]:
    return {
        "schema": CHECKER.NEGATIVE_SCHEMA,
        "status": "failed",
        "gate_eligible": False,
        "candidate_rejected": True,
        "board": CHECKER.BOARD,
        "port": CHECKER.PORT,
        "rom_mac": CHECKER.ROM_MAC,
        "expected_cid": CHECKER.CID,
        "candidate": {
            "version": CHECKER.FAILED_VERSION,
            "source_commit": CHECKER.FAILED_SOURCE,
            "firmware_sha256": CHECKER.FAILED_FIRMWARE,
            "app_elf_sha256": CHECKER.FAILED_APP,
            "fresh_delta_run_sha256": CHECKER.FAILED_DELTA_RUN,
            "failed_full_run_sha256": CHECKER.FAILED_FULL_RUN,
            "failed_full_artifact_index_sha256": CHECKER.FAILED_FULL_INDEX,
        },
        "failure": {
            "first_capture_state": "failed",
            "first_load_status": "invalid_report",
            "first_ble_worker_status": "complete",
            "first_ble_worker_valid": True,
            "first_ble_scan_status": "valid",
            "first_ble_retention_retained": 49,
            "first_ble_retention_dropped": 0,
            "first_findings_dropped": 0,
            "second_capture_state": "result",
            "second_load_status": "ready",
            "second_ble_records": 53,
            "second_findings_dropped": 0,
            "root_cause": CHECKER.ROOT_CAUSE,
        },
        "post_failure_cleanup": {
            "complete": True,
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "safety_state": "armed",
            "safety_latched": False,
        },
        "corrective_candidate": {
            "version": CHECKER.FAILED_241_VERSION,
            "source_commit": CHECKER.FAILED_241_SOURCE,
            "firmware_sha256": CHECKER.FAILED_241_FIRMWARE,
            "app_elf_sha256": CHECKER.FAILED_241_APP,
            "runner_source_sha256": CHECKER.FAILED_241_RUNNER,
            "inspection_budget_records": 128,
            "source_local_wifi_records": 64,
            "source_local_ble_records": 64,
        },
        "cadence": {"accepted_deltas_unchanged": "9/15"},
    }


def negative_dev241(firmware: str) -> dict[str, Any]:
    return {
        "schema": CHECKER.NEGATIVE_SCHEMA,
        "status": "failed",
        "gate_eligible": False,
        "candidate_rejected": True,
        "board": CHECKER.BOARD,
        "port": CHECKER.PORT,
        "rom_mac": CHECKER.ROM_MAC,
        "expected_cid": CHECKER.CID,
        "candidate": {
            "version": CHECKER.FAILED_241_VERSION,
            "source_commit": CHECKER.FAILED_241_SOURCE,
            "firmware_sha256": CHECKER.FAILED_241_FIRMWARE,
            "app_elf_sha256": CHECKER.FAILED_241_APP,
            "failed_full_run_sha256": CHECKER.FAILED_241_FULL_RUN,
            "failed_full_artifact_index_sha256": CHECKER.FAILED_241_FULL_INDEX,
        },
        "failure": {
            "first_capture_state": "result",
            "first_load_status": "ready",
            "first_ble_worker_status": "complete",
            "first_ble_worker_valid": True,
            "first_ble_scan_status": "valid",
            "first_ble_scan_dropped": 0,
            "first_ble_retention_retained": 54,
            "first_ble_retention_dropped": 0,
            "first_frames_available": 74,
            "first_findings_dropped": 0,
            "second_capture_state": "failed",
            "second_load_status": "ready",
            "second_ble_worker_status": "incomplete_evidence",
            "second_ble_worker_valid": False,
            "second_ble_scan_status": "valid",
            "second_ble_scan_observed": 1296,
            "second_ble_scan_reported": 1296,
            "second_ble_scan_read": 1296,
            "second_ble_scan_accepted": 1295,
            "second_ble_scan_rejected": 0,
            "second_ble_scan_dropped": 1,
            "second_ble_retention_observed": 1296,
            "second_ble_retention_valid": 1296,
            "second_ble_retention_retained": 64,
            "second_ble_retention_dropped": 1,
            "second_ble_retention_malformed": 0,
            "second_evidence_incomplete": True,
            "second_outcome": "inconclusive",
            "second_source_frames_observed": 0,
            "second_source_frames_dropped": 0,
            "second_frames_available": 0,
            "second_ble_records": 0,
            "second_findings_dropped": 0,
            "root_cause": CHECKER.ROOT_CAUSE_241,
        },
        "post_failure_cleanup": {
            "complete": True,
            "page": "home",
            "runtime_owner": "none",
            "lease_mask": 0,
            "safety_state": "armed",
            "safety_latched": False,
        },
        "corrective_candidate": {
            "version": CHECKER.VERSION,
            "source_commit": SOURCE,
            "firmware_sha256": firmware,
            "app_elf_sha256": APP,
            "runner_source_sha256": RUNNER_SHA,
            "inspection_budget_records": 128,
            "source_local_wifi_records": 64,
            "source_local_ble_records": 64,
        },
        "cadence": {"accepted_deltas_unchanged": "9/15"},
    }


def run_record(firmware: str) -> dict[str, Any]:
    ready = boot(firmware)
    first_result = result(5)
    second_result = result(7, 1)
    evidence_list = copy.deepcopy(first_result)
    evidence_list.update({"view": "evidence_list", "evidence_selection": 0})
    evidence_detail = copy.deepcopy(first_result)
    evidence_detail.update({"view": "evidence_detail", "evidence_selection": 0})
    fixture = {
        "kind": "macos_corebluetooth",
        "label": CHECKER.BLE_LABEL,
        "executable_sha256": CHECKER.BLE_FIXTURE_SHA256,
        "host_wifi_control_calls": 0,
        "terminated": True,
        "states": [{
            "schema": "leshy.hil.macos_ble_name_fixture.v1",
            "state": "advertising",
            "label": CHECKER.BLE_LABEL,
        }],
    }
    scope = {
        "single_flash": True,
        "manual_button_presses": 0,
        "screenshots_automatic": True,
        "passive_receive_only": True,
        "deterministic_ble_fixture": True,
        "host_wifi_control_calls": 0,
        "application_wifi_connect_calls": 0,
        "application_raw_tx_calls": 0,
        "wifi_cancel_cleanup_proved": True,
        "ble_cancel_cleanup_proved": True,
        "two_complete_guard_lifecycles": True,
        "conclusive_guard_lifecycles": 1,
        "static_pixels_unchanged_during_live_refresh": True,
        "zero_heap_drift_after_warmup": True,
        "storage_write_authorized": False,
        "elevated_noise_is_low_confidence_indicator": True,
        "absence_of_noise_finding_is_not_absence_of_interference": True,
    }
    return {
        "schema": CHECKER.RUN_SCHEMA,
        "run_id": "1" * 32,
        "runner_source_sha256": RUNNER_SHA,
        "passed": True,
        "gate_eligible": True,
        "failures": [],
        "candidate": {
            "version": CHECKER.VERSION,
            "source_commit": SOURCE,
            "firmware_sha256": firmware,
            "app_elf_sha256": APP,
            "flashed": True,
            "flash_mode": "fresh",
        },
        "expected_cid": CHECKER.CID,
        "boot": ready,
        "boot_metrics_samples": [copy.deepcopy(ready), copy.deepcopy(ready)],
        "recovery_before": recovery(),
        "recovery_after": recovery(),
        "wifi_running": running("wifi_running", 1),
        "ble_running": running("ble_running", 3),
        "wifi_cancelled": stopped(2),
        "ble_cancelled": stopped(4),
        "result_first": first_result,
        "result_second": second_result,
        "result_navigation": [evidence_list, evidence_detail],
        "metrics_after_first": {"heap_total": 134116, "heap_free": 60548},
        "metrics_after_second": {"heap_total": 134116, "heap_free": 60548},
        "input": {
            "schema": "leshy.input.frontend.v1", "kind": "state",
            "status": "ready", "task_started": True, "read_errors": 0,
            "queue_drops": 0, "hot_path_serial_writes": 0,
        },
        "safe_outputs": {
            "schema": "leshy.hardware.safe-outputs.v1", "kind": "state",
            "buzzer_inactive": True, "buzzer_level": "low",
            "nrf_ce_inactive": True, "software_quiesce_complete": True,
        },
        "hil_session": {
            "begin": {
                "schema": "leshy.hil.session.v1", "kind": "begun",
                "status": "begun", "session_id": "1" * 32,
                "active": True, "app_elf_sha256": APP,
                "firmware_version": CHECKER.VERSION, "ui_revision": 10,
                "host_begin_ack_received": True,
                "host_begin_action_writes": 1,
                "host_begin_action_replays": 0,
            },
            "end": {
                "schema": "leshy.hil.session.v1", "kind": "ended",
                "status": "ended", "session_id": "1" * 32,
                "active": False, "app_elf_sha256": APP,
                "ui_revision": 20,
                "host_end_ack_received": True,
                "host_end_action_writes": 1,
                "host_end_action_replays": 0,
                "host_end_requested_session_id": "1" * 32,
            },
        },
        "capacity_drop_injection": {
            "schema": "leshy.airspace_guard.capacity_drop_test.v1",
            "kind": "state", "status": "armed", "one_shot": True,
            "armed": True, "hil_active": True, "worker_idle": True,
            "ui_home": True, "runtime_owner": "none", "lease_mask": 0,
            "hardware_touched": False, "radio_started": False,
            "storage_mounted": False, "storage_written": False,
        },
        "capacity_drop_clear": {
            "schema": "leshy.airspace_guard.capacity_drop_test.v1",
            "kind": "state", "status": "cleared", "one_shot": True,
            "armed": False, "hil_active": True, "worker_idle": True,
            "ui_home": True, "runtime_owner": "none", "lease_mask": 0,
            "hardware_touched": False, "radio_started": False,
            "storage_mounted": False, "storage_written": False,
        },
        "pixel_proof": {
            "wifi": {"live_changed_pixels": 1, "static_changed_pixels": 0},
            "ble": {"live_changed_pixels": 1, "static_changed_pixels": 0},
        },
        "external_ble_fixture": fixture,
        "cleanup_before": cleanup(),
        "cleanup_after": cleanup(),
        "scope": scope,
        "screens": {},
    }


class AirspaceAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.expectations_path = self.root / "expectations.json"
        self.negative_dev239_path = self.root / "negative-dev239.json"
        self.negative_dev241_path = self.root / "negative-dev241.json"
        self.firmware_bytes = esp_image(APP)
        self.firmware = digest(self.firmware_bytes)
        self.run = run_record(self.firmware)
        self.negative_dev239 = negative(self.firmware)
        self.negative_dev241 = negative_dev241(self.firmware)
        self.screen_state_overrides: dict[str, dict[str, Any]] = {}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_bundle(self) -> None:
        files: dict[str, bytes] = {"firmware.bin": self.firmware_bytes}
        frames: dict[str, bytes] = {
            key: bytes(CHECKER.FRAME_BYTES) for key in CHECKER.SCREEN_FILES
        }
        for source, (top, _bottom, _before, after) in (
                CHECKER.LIVE_REGIONS.items()):
            del source
            changed = bytearray(frames[after])
            offset = (top * CHECKER.WIDTH + 1) * 2
            changed[offset:offset + 2] = b"\xff\xff"
            frames[after] = bytes(changed)
        for key, stem in CHECKER.SCREEN_FILES.items():
            rgb = frames[key]
            png = rgb565be_to_png(rgb, CHECKER.WIDTH, CHECKER.HEIGHT)
            state = {
                "schema": "leshy.ui.v1", "kind": "state",
                "page": "survey",
                "wifi_product_view": "airspace_guard",
                "runtime_owner": "wifi", "lease_mask": 15,
                "revision": 5,
            }
            state.update(self.screen_state_overrides.get(key, {}))
            screen = {
                "frame_begin": {
                    "schema": "leshy.ui.capture.v1", "kind": "frame_begin",
                    "format": "rgb565be", "width": 240, "height": 320,
                    "bytes": CHECKER.FRAME_BYTES, "revision": 5,
                },
                "frame_end": {
                    "schema": "leshy.ui.capture.v1", "kind": "frame_end",
                    "bytes": CHECKER.FRAME_BYTES, "revision": 5,
                },
                "png_sha256": digest(png),
                "rgb565_sha256": digest(rgb),
                "state": state,
                "transport_attempts": 1,
                "transport_transient_retries": 0,
                "transport_transient_errors": [],
            }
            self.run["screens"][key] = screen
            files[f"frames/{stem}.png"] = png
            files[f"frames/{stem}.rgb565"] = rgb
            files[f"frames/{stem}.json"] = (
                json.dumps(screen, sort_keys=True).encode()
            )
        files["run.json"] = json.dumps(self.run, sort_keys=True).encode()
        for name, data in files.items():
            path = self.bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest = "".join(
            f"{digest(data)}  {name}\n" for name, data in sorted(files.items())
        ).encode()
        (self.bundle / "artifacts.sha256").write_text(
            manifest.decode(), encoding="utf-8"
        )
        expectations = {
            "schema": CHECKER.EXPECTATIONS_SCHEMA,
            "version": CHECKER.VERSION,
            "expected_cid": CHECKER.CID,
            "run_id": self.run["run_id"],
            "source_commit": SOURCE,
            "firmware_sha256": self.firmware,
            "app_elf_sha256": APP,
            "runner_source_sha256": self.run["runner_source_sha256"],
            "positive_run_sha256": digest(files["run.json"]),
            "positive_artifact_index_sha256": digest(manifest),
        }
        self.expectations_path.write_text(
            json.dumps(expectations, sort_keys=True), encoding="utf-8")
        self.negative_dev239_path.write_text(
            json.dumps(self.negative_dev239, sort_keys=True), encoding="utf-8"
        )
        self.negative_dev241_path.write_text(
            json.dumps(self.negative_dev241, sort_keys=True), encoding="utf-8"
        )

    def args(self) -> argparse.Namespace:
        return CHECKER.parse_args([
            "--expectations", str(self.expectations_path),
            "--positive", str(self.bundle),
            "--negative-dev239", str(self.negative_dev239_path),
            "--negative-dev241", str(self.negative_dev241_path),
            "--expected-source-commit", SOURCE,
            "--expected-firmware-sha256", self.firmware,
            "--expected-app-elf-sha256", APP,
        ])

    def test_exact_full_bundle_and_retained_failure_pass(self) -> None:
        self.write_bundle()
        self.assertEqual([], CHECKER.check(self.args()))

    def test_transport_or_rejected_loss_fails_closed(self) -> None:
        self.run["result_second"]["ble_scan_rejected"] = 1
        self.run["result_second"]["ble_scan_status"] = "transport_error"
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_second.ble_scan_rejected", failures)
        self.assertIn("result_second.ble_scan_status", failures)

    def test_manifest_tamper_fails_closed(self) -> None:
        self.write_bundle()
        (self.bundle / "firmware.bin").write_bytes(b"tampered")
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("positive.firmware.bin: hash mismatch", failures)

    def test_negative_root_cause_tamper_fails_closed(self) -> None:
        self.negative_dev241["failure"]["root_cause"] = "unknown"
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("negative_dev241.failure.root_cause", failures)

    def test_missing_hil_session_fails_closed(self) -> None:
        del self.run["hil_session"]
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("positive.hil_session", failures)

    def test_mismatched_hil_session_fails_closed(self) -> None:
        self.run["hil_session"]["end"]["session_id"] = "f" * 32
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("positive.hil_session.end.session_id", failures)

    def test_missing_capacity_injection_fails_closed(self) -> None:
        del self.run["capacity_drop_injection"]
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("positive.capacity_drop_injection", failures)

    def test_missing_injected_result_flag_fails_closed(self) -> None:
        self.run["result_second"]["ble_capacity_drop_injected"] = False
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_second.ble_capacity_drop_injected", failures)

    def test_missing_requested_result_flag_fails_closed(self) -> None:
        self.run["result_second"]["ble_capacity_drop_requested"] = False
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_second.ble_capacity_drop_requested", failures)

    def test_old_natural_capacity_shape_cannot_prove_capacity_one(self) -> None:
        second = self.run["result_second"]
        second.update({
            "source_frames_dropped": 1,
            "ble_scan_accepted": 199,
            "ble_scan_dropped": 1,
            "ble_retention_retained": 56,
            "ble_retention_dropped": 1,
            "frames_available": 72,
            "frames_inspected": 72,
            "ble_records": 56,
        })
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_second.ble_scan_accepted", failures)
        self.assertIn("effective_capacity_one_accounting", failures)

    def test_baseline_requested_flag_fails_closed(self) -> None:
        self.run["result_first"]["ble_capacity_drop_requested"] = True
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_first.ble_capacity_drop_requested", failures)

    def test_capacity_drop_clear_mismatch_fails_closed(self) -> None:
        self.run["capacity_drop_clear"]["armed"] = True
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("capacity_drop_clear.armed", failures)

    def test_lost_ack_recovered_hil_session_is_accepted(self) -> None:
        begin = self.run["hil_session"]["begin"]
        begin.update({
            "kind": "state", "status": "active",
            "host_begin_ack_received": False,
            "host_begin_ack_error": "lost begin ACK",
        })
        end = self.run["hil_session"]["end"]
        end.update({
            "kind": "state", "status": "inactive", "session_id": "",
            "firmware_version": CHECKER.VERSION,
            "host_end_ack_received": False,
            "host_end_ack_error": "lost end ACK",
        })
        self.write_bundle()
        self.assertEqual([], CHECKER.check(self.args()))

    def test_hil_end_replay_accounting_fails_closed(self) -> None:
        self.run["hil_session"]["end"]["host_end_action_replays"] = 1
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("host_end_action_replays", failures)

    def test_firmware_embedded_identity_mismatch_fails_closed(self) -> None:
        self.firmware_bytes = esp_image("e" * 64)
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("embedded identity mismatch", failures)

    def test_forged_pixel_proof_fails_closed(self) -> None:
        self.run["pixel_proof"]["wifi"]["live_changed_pixels"] = 999
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("pixel_proof.wifi.live_changed_pixels", failures)

    def test_invalid_png_fails_closed(self) -> None:
        self.write_bundle()
        (self.bundle / "frames/guard-result.png").write_bytes(b"not a png")
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("invalid PNG signature/header", failures)

    def test_navigation_generation_mismatch_fails_closed(self) -> None:
        self.run["result_navigation"][1]["generation"] += 1
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("result_navigation[1].generation", failures)

    def test_lifecycle_generation_mismatch_fails_closed(self) -> None:
        self.run["result_second"]["generation"] += 1
        self.run["result_second"]["ble_worker_generation"] += 1
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("second result mismatch", failures)

    def test_incomplete_cleanup_fails_closed(self) -> None:
        self.run["cleanup_after"]["final_state"][
            "survey_product_storage_mounted"] = True
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("cleanup_after.final_state.survey_product_storage_mounted",
                      failures)

    def test_enabled_gate_requires_all_three_evidence_sets(self) -> None:
        self.write_bundle()
        self.negative_dev241_path.unlink()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("negative_dev241", failures)

    def test_exact_run_hash_pin_fails_closed(self) -> None:
        self.write_bundle()
        expectations = json.loads(self.expectations_path.read_text())
        expectations["positive_run_sha256"] = "0" * 64
        self.expectations_path.write_text(
            json.dumps(expectations, sort_keys=True), encoding="utf-8")
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("positive.run: expectation hash mismatch", failures)

    def test_stale_runner_hash_fails_closed(self) -> None:
        stale = "0" * 64
        self.run["runner_source_sha256"] = stale
        self.negative_dev241["corrective_candidate"][
            "runner_source_sha256"] = stale
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("current runner binding mismatch", failures)

    def test_missing_expectations_marker_fails_closed(self) -> None:
        self.write_bundle()
        self.expectations_path.unlink()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("expectations", failures)

    def test_screen_state_semantic_mismatch_fails_closed(self) -> None:
        self.screen_state_overrides["evidence_detail"] = {
            "wifi_product_view": "menu",
        }
        self.write_bundle()
        failures = "\n".join(CHECKER.check(self.args()))
        self.assertIn("screens.evidence_detail.state.wifi_product_view",
                      failures)


if __name__ == "__main__":
    unittest.main()
