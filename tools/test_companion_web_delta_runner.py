#!/usr/bin/env python3
"""Host checks for partition-safe local Web delta HIL."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import partition_safety  # noqa: E402
import run_1x_companion_web_delta_hil as runner  # noqa: E402


def partition_table(
    entries: list[tuple[int, int, int, int, str]],
) -> bytes:
    payload = bytearray(b"\xff" * partition_safety.PARTITION_TABLE_SIZE)
    for index, (kind, subtype, offset, size, label) in enumerate(entries):
        payload[index * 32:(index + 1) * 32] = struct.pack(
            "<HBBLL16sL", partition_safety.PARTITION_MAGIC, kind, subtype,
            offset, size, label.encode("ascii").ljust(16, b"\0"), 0)
    md5_offset = len(entries) * 32
    payload[md5_offset:md5_offset + 32] = (
        struct.pack("<H", partition_safety.PARTITION_MD5_MAGIC) +
        b"\xff" * 14 + hashlib.md5(payload[:md5_offset]).digest())
    return bytes(payload)


class CompanionWebDeltaRunnerTests(unittest.TestCase):
    def test_credential_proof_is_exact_and_safe_to_retain(self) -> None:
        ssid = "Leshy-8790D4"
        password = "temporary123"
        expected = hashlib.sha256(
            b"leshy.companion.web.hil-proof.v1\0" + ssid.encode("ascii") +
            b"\0" + password.encode("ascii")).hexdigest()
        self.assertEqual(
            expected, runner.credential_proof_sha256(ssid, password))
        retained = runner.safe_credential_proof({
            "credential_sha256": expected,
            "ap_ipv4_ready": True,
            "dhcp_server_started": True,
            "associated_stations": 1,
            "credential_material_exposed": False,
            "proof_persisted": False,
        }, expected)
        self.assertTrue(retained["matched"])
        self.assertFalse(retained["proof_hash_recorded"])
        self.assertNotIn("credential_sha256", retained)

    def test_expected_error_is_returned_as_evidence(self) -> None:
        class Device:
            def __init__(self) -> None:
                self.writes: list[bytes] = []
                self.lines = [
                    b"not-json\n",
                    json.dumps({
                        "schema": "leshy.companion.web.seed.v1",
                        "kind": "error",
                        "status": "invalid",
                        "reason": "invalid_entropy",
                    }).encode("utf-8") + b"\n",
                ]

            def write(self, value: bytes) -> None:
                self.writes.append(value)

            def flush(self) -> None:
                pass

            def readline(self) -> bytes:
                return self.lines.pop(0) if self.lines else b""

        device = Device()
        response = runner.query_expected_error(
            device, b"companion.web.hil-seed 0000",
            "leshy.companion.web.seed.v1")
        self.assertEqual("invalid_entropy", response["reason"])
        self.assertEqual(
            [b"companion.web.hil-seed 0000\n"], device.writes)

    def test_failed_precursor_requires_exact_boot_and_safe_cleanup(self) -> None:
        candidate = {
            "version": "0.182.0-companion-web-http-parity",
            "app_elf_sha256": "app",
        }
        precursor = {
            "status": "failed",
            "metrics_before": dict(candidate),
            "cleanup": {
                "attempted": True,
                "complete": True,
                "errors": [],
                "final_state": {
                    "page": "home",
                    "runtime_owner": "none",
                    "lease_mask": 0,
                    "safety_state": "armed",
                    "safety_latched": False,
                },
            },
        }
        self.assertTrue(
            runner.failed_precursor_proves_safe_reuse(precursor, candidate))
        for path, unsafe in (
            (("metrics_before", "app_elf_sha256"), "other"),
            (("cleanup", "complete"), False),
            (("cleanup", "final_state", "lease_mask"), 1),
            (("cleanup", "final_state", "safety_latched"), True),
        ):
            changed = json.loads(json.dumps(precursor))
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = unsafe
            self.assertFalse(
                runner.failed_precursor_proves_safe_reuse(changed, candidate),
                path)

        changed = json.loads(json.dumps(precursor))
        changed["host_wifi"] = {
            "restore_attempted": True,
            "restored": False,
        }
        self.assertFalse(
            runner.failed_precursor_proves_safe_reuse(changed, candidate))

    def test_reviewed_layout_accepts_fitting_candidate(self) -> None:
        entries = [
            (1, 0x02, 0x9000, 0x5000, "nvs"),
            (1, 0x00, 0xE000, 0x2000, "otadata"),
            (0, 0x10, 0x10000, 0x400000, "app0"),
            (0, 0x11, 0x410000, 0x400000, "app1"),
            (1, 0x82, 0x810000, 0x7D0000, "spiffs"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partitions.bin"
            path.write_bytes(partition_table(entries)[:0xC00])
            layout = partition_safety.validated_partition_layout(
                path, 3_387_952)
            canonical = partition_safety.canonical_partition_table(path)
        self.assertEqual(0x400000, layout["app0"]["size"])
        self.assertEqual(0x1000, len(canonical))

    def test_factory_layout_rejected_before_flash(self) -> None:
        entries = [
            (0, 0x10, 0x10000, 0x330000, "app0"),
            (1, 0x82, 0x340000, 0x230000, "font"),
            (1, 0x82, 0x670000, 0x180000, "spiffs"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "factory-partitions.bin"
            path.write_bytes(partition_table(entries))
            with self.assertRaisesRegex(ValueError, "app0|app1"):
                partition_safety.validated_partition_layout(path, 3_387_952)

    def test_oversize_candidate_rejected(self) -> None:
        entries = [
            (0, 0x10, 0x10000, 0x400000, "app0"),
            (0, 0x11, 0x410000, 0x400000, "app1"),
            (1, 0x82, 0x810000, 0x7D0000, "spiffs"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partitions.bin"
            path.write_bytes(partition_table(entries))
            with self.assertRaisesRegex(ValueError, "does not fit"):
                partition_safety.validated_partition_layout(path, 0x400001)

    def test_legacy_precursor_requires_exact_application_identity(self) -> None:
        candidate = {
            "version": "0.174.0-companion-web-runtime",
            "firmware_sha256": "firmware",
            "firmware_bytes": 3_387_952,
            "elf_sha256": "elf",
            "map_sha256": "map",
            "app_elf_sha256": "app",
            "partitions_sha256": "partitions",
        }
        legacy = {key: value for key, value in candidate.items()
                  if key != "partitions_sha256"}
        self.assertTrue(runner.precursor_candidate_matches(legacy, candidate))
        legacy["firmware_sha256"] = "different"
        self.assertFalse(runner.precursor_candidate_matches(legacy, candidate))

    def test_only_quiesced_runtime_watchdog_latch_is_clearable(self) -> None:
        state = {
            "schema": "leshy.safety.v1",
            "kind": "state",
            "state": "latched",
            "reason": "runtime_watchdog",
            "armed": True,
            "latched": True,
            "clear_pending": False,
            "automatic_clear": False,
            "startup_guard_tripped": False,
            "buzzer_inactive": True,
            "nrf_ce_inactive": True,
            "runtime_owner": "none",
            "lease_mask": 0,
            "worker_active": "none",
            "worker_armed": False,
            "worker_expired": False,
            "worker_last_expired": "none",
            "worker_trip_count": 0,
            "trip_count": 2,
            "emergency_quiesce_count": 2,
        }
        self.assertTrue(runner.proven_clearable_runtime_watchdog(state))
        for field, unsafe in (
            ("reason", "output_invariant"),
            ("runtime_owner", "targets"),
            ("lease_mask", 1),
            ("worker_expired", True),
            ("startup_guard_tripped", True),
            ("nrf_ce_inactive", False),
        ):
            changed = dict(state)
            changed[field] = unsafe
            self.assertFalse(
                runner.proven_clearable_runtime_watchdog(changed), field)

    def test_target_id_requires_exact_uppercase_hex(self) -> None:
        self.assertTrue(
            runner.valid_target_id("D232CBB7B4489ABAABFAFD7163BB1D51"))
        for invalid in (
            "D232CBB7B4489ABAABFAFD7163BB1D5",
            "d232cbb7b4489abaabfafd7163bb1d51",
            "D232CBB7B4489ABAABFAFD7163BB1D5Z",
            None,
        ):
            self.assertFalse(runner.valid_target_id(invalid), invalid)

    def test_runner_has_no_discovery_or_partition_write(self) -> None:
        source = (ROOT / "tools/run_1x_companion_web_delta_hil.py").read_text()
        self.assertNotIn("serial.tools.list_ports", source)
        self.assertNotIn("write-flash", source)
        self.assertIn('parser.add_argument("--port", required=True)', source)
        self.assertIn(
            'parser.add_argument("--partitions", required=True, type=Path)',
            source)
        self.assertIn('"clear_action_replays": 0', source)
        self.assertIn(
            'action(device, "down")  # comparison is row 0;', source)
        self.assertIn('focused.get("selection") == 1', source)
        self.assertIn('detail.get("view") == "detail"', source)
        self.assertLess(
            source.index("read_flash_with_retry("),
            source.index("flash_candidate(args.port"))
        for marker in (
            '"--allow-host-wifi-change"',
            'parser.add_argument("--wifi-interface")',
            'parser.add_argument("--wifi-service")',
            'parser.add_argument("--softap-mac")',
            '"pending_guarded_host_wifi_exchange"',
            'f"companion.web.hil-seed {entropy.hex()}"',
            '"leshy.companion.web.seed.v1", "armed"',
            'b"companion.web.hil-proof"',
            '"leshy.companion.web.hil-proof.v1", "state"',
            'safe_credential_proof(',
            'wifi_guard.capture()',
            'wifi_guard.connect(',
            'wifi_guard.restore()',
            'host_wifi["dhcp_requests"] = wifi_guard.dhcp_requests',
            'normalized_pages(web_session_pages)',
            'normalized_pages(web_target_pages)',
            'normalized_pages(web_compare_pages)',
            '"target.mutation.preview", "web-first-preview"',
            '"target.mutation.confirm", "web-restore-confirm"',
            'assert_atomic_mutation_state(',
            '"transient_passphrase_recorded": False',
            '"credential_recorded": False',
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
