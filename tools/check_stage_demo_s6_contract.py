#!/usr/bin/env python3
"""Fail closed unless DEMO-S6 stays one-flash, USB-only and dependency-honest."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_1x_stage_demo_s6_hil.py"
TARGETS_RUNNER = ROOT / "tools/run_1x_targets_evidence_hil.py"


def main() -> int:
    failures: list[str] = []
    spec = importlib.util.spec_from_file_location("stage_demo_s6", RUNNER)
    if spec is None or spec.loader is None:
        print("FAIL: cannot import DEMO-S6 runner", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = SimpleNamespace(
        port="/dev/cu.explicit-original-div",
        firmware=Path("firmware.bin"), elf=Path("firmware.elf"),
        map=Path("firmware.map"), expected_version="0.contract",
        expected_cid=module.EXPECTED_CID, source_commit="c" * 40,
        flash_baud=460800,
    )
    commands = [
        module.product_command(args, Path("baseline"), True),
        module.product_command(args, Path("repeat"), False),
        module.targets_command(args, Path("targets")),
        module.companion_command(args, Path("companion")),
    ]
    if sum("--flash" in command for command in commands) != 1:
        failures.append("exactly one child command must flash")
    if "--flash" in commands[1]:
        failures.append("repeat Survey must reuse the exact flashed candidate")
    if not (
        "--reuse-exact-flash" in commands[2]
        and "--open-every-evidence" in commands[2]
        and "--reuse-exact-flash" in commands[3]
    ):
        failures.append("Targets/companion exact reuse or every-evidence proof missing")
    flattened = "\n".join(" ".join(command) for command in commands)
    forbidden = (
        "networksetup", "airport", "scutil", "ifconfig", "route",
        "--exercise-device-web-lifecycle",
    )
    for token in forbidden:
        if token in flattened:
            failures.append(f"host-network or SoftAP command is forbidden: {token}")

    runner_source = RUNNER.read_text(encoding="utf-8")
    targets_source = TARGETS_RUNNER.read_text(encoding="utf-8")
    required_runner = (
        '"application_flash_count": 0 if args.reuse_exact_flash else 1',
        '"exact_flash_reused": args.reuse_exact_flash',
        "validate_reused_flash_lineage(",
        "validate_reused_survey_lineage(",
        '"reused_survey_lineage": survey_lineage',
        '"host_network_tools_invoked": False',
        '"active_mac_wifi_touched": False',
        '"wifi_softap_started": False',
        '"s6_exit_eligible": False',
        '"physical_http_parity_requires_dedicated_client"',
        '"s5_predecessor_physical_gate_requires_replacement_div"',
    )
    for token in required_runner:
        if token not in runner_source:
            failures.append(f"runner contract token missing: {token}")
    for token in ("--reuse-exact-flash", "--open-every-evidence",
                  '"evidence_details"'):
        if token not in targets_source:
            failures.append(f"Targets reuse/every-evidence token missing: {token}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "DEMO-S6 contract passed: one flash, contiguous baseline/repeat Surveys, "
        "every on-device conclusion opened, offline USB export, no Mac network, "
        "and S6 blockers retained"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
