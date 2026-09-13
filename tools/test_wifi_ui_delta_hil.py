#!/usr/bin/env python3
"""Regression for the state-pass / stale-frame false positive found on dev.382."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from check_wifi_ui_delta_hil import PAGES, check


class WifiUiEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.frames = Path(self.directory.name)
        screens = {}
        for name, value in (("before-password-steps", 0), ("password-steps", 1),
                            ("password-steps-stable", 1)):
            raw = bytes([value]) * (240 * 320 * 2)
            png = b"fixture-only" + bytes([value])
            for ext, data in (("rgb565", raw), ("png", png)):
                (self.frames / f"{name}.{ext}").write_bytes(data)
            screens[name] = {"rgb565_sha256": hashlib.sha256(raw).hexdigest(),
                             "png_sha256": hashlib.sha256(png).hexdigest()}
        self.run = {
            "schema": "leshy.wifi_ui_delta.v1", "status": "passed", "failures": [],
            "cleanup_complete": True, "pages": {p: {"ui_page": p} for p in PAGES},
            "screens": screens, "channels": {"wifi_channel_measured_mask": 8191},
            "channel_pixels": {"static_changed_pixels": 0},
            "final": {"page": "home", "runtime_owner": "none", "lease_mask": 0,
                      "survey_scan_dropped": 0, "survey_dropped": 0,
                      "survey_timeline_overflow": 0, "survey_product_store_bytes_written": 0,
                      "survey_product_filesystem_mount_attempts": 0},
        }

    def test_valid(self):
        self.assertEqual(check(self.run, self.frames), [])

    def test_stale_preflight_despite_successful_state(self):
        self.frames.joinpath("password-steps.rgb565").write_bytes(
            self.frames.joinpath("before-password-steps.rgb565").read_bytes())
        self.assertIn("preflight must replace actions pixels", check(self.run, self.frames))

    def test_static_screen_changes(self):
        self.frames.joinpath("password-steps-stable.rgb565").write_bytes(b"bad")
        self.assertIn("preflight stable after non-start key", check(self.run, self.frames))

    def test_missing_frame(self):
        self.frames.joinpath("password-steps.png").unlink()
        self.assertTrue(check(self.run, self.frames))

    def test_bad_final_states(self):
        for key in self.run["final"]:
            with self.subTest(key=key):
                run = copy.deepcopy(self.run)
                run["final"][key] = None
                self.assertTrue(check(run, self.frames))

    def test_missing_page_and_changed_chrome(self):
        run = copy.deepcopy(self.run)
        del run["pages"]["identity"]
        run["channel_pixels"]["static_changed_pixels"] = 1
        self.assertIn("eight navigation pages", check(run, self.frames))
        self.assertIn("channel chrome immutable", check(run, self.frames))


if __name__ == "__main__":
    unittest.main()
