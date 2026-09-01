#!/usr/bin/env python3

from __future__ import annotations

import unittest

from screenshot_library_hil_policy import owner_protected_access_admitted


class ScreenshotLibraryHilPolicyTests(unittest.TestCase):
    def test_owner_authorized_states_are_admitted(self) -> None:
        for status in ("unlocked", "disabled"):
            with self.subTest(status=status):
                self.assertTrue(owner_protected_access_admitted({
                    "status": status,
                    "protected_access": True,
                    "worker_active": False,
                }))

    def test_unprotected_or_transitional_states_fail_closed(self) -> None:
        cases = (
            {"status": "locked", "protected_access": False,
             "worker_active": False},
            {"status": "unconfigured", "protected_access": False,
             "worker_active": False},
            {"status": "disabled", "protected_access": False,
             "worker_active": False},
            {"status": "unlocked", "protected_access": True,
             "worker_active": True},
        )
        for state in cases:
            with self.subTest(state=state):
                self.assertFalse(owner_protected_access_admitted(state))


if __name__ == "__main__":
    unittest.main()
