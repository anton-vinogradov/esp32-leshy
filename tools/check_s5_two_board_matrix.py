#!/usr/bin/env python3
"""Independently verify a completed S5 two-board matrix checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_s5_two_board_hil import MATRIX, verify_completed_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path,
                        help="path to the parent S5 matrix run.json")
    args = parser.parse_args()
    try:
        summary = verify_completed_matrix(args.run)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps({
        "schema": summary["schema"],
        "status": "pass",
        "source_commit": summary["source_commit"],
        "scenarios": list(MATRIX),
        "candidate_firmware_sha256": summary["product_firmware_sha256"],
        "fixture_firmware_sha256": summary["fixture_firmware_sha256"],
        "fixture_id": summary["fixture_id"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
