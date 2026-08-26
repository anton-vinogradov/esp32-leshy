#!/usr/bin/env python3
"""Host checks for partition-safe local Web delta HIL."""

from __future__ import annotations

import hashlib
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
            'wifi_guard.capture()',
            'wifi_guard.connect(expected_ssid, expected_passphrase)',
            'wifi_guard.restore()',
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
