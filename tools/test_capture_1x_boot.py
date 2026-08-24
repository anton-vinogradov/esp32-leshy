#!/usr/bin/env python3

from __future__ import annotations

import unittest

from capture_1x_boot import trigger_reset


class CaptureBootTests(unittest.TestCase):
    def test_hard_reset_never_asserts_rom_download_strap(self) -> None:
        events: list[tuple[str, object]] = []

        class FakePort:
            @property
            def dtr(self) -> bool:
                return False

            @dtr.setter
            def dtr(self, value: bool) -> None:
                events.append(("dtr", value))

            @property
            def rts(self) -> bool:
                return False

            @rts.setter
            def rts(self, value: bool) -> None:
                events.append(("rts", value))

        trigger_reset(
            FakePort(),
            sleep=lambda seconds: events.append(("sleep", seconds)),
        )

        self.assertEqual([
            ("dtr", False),
            ("rts", True),
            ("sleep", 0.2),
            ("rts", False),
            ("sleep", 0.2),
        ], events)
        self.assertNotIn(("dtr", True), events)


if __name__ == "__main__":
    unittest.main()
