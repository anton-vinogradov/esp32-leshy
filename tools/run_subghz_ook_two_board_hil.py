#!/usr/bin/env python3
"""Run the bounded two-board CC1101 OOK capture/save scenario."""

from __future__ import annotations

import sys

from run_ir_two_board_hil import main


if __name__ == "__main__":
    sys.argv[1:1] = ["--scenario", "subghz-ook-positive"]
    raise SystemExit(main())
