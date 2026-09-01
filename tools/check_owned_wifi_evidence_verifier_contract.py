#!/usr/bin/env python3
"""Fail closed if the owned Wi-Fi verifier loses its safety contract."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/owned_wifi_evidence_verifier.py"
JOURNEY = ROOT / "tools/check_my_wifi_password.py"
HIL_RUNNER = ROOT / "tools/run_1x_owned_wifi_password_check_hil.py"
PERSISTENCE_RUNNER = ROOT / \
    "tools/run_1x_wifi_authentication_persistence_hil.py"


def imported_modules(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    return imported


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    forbidden = (imported_modules(SOURCE) | imported_modules(JOURNEY)) & {
        "asyncio", "http", "requests", "socket", "subprocess", "urllib"
    }
    if forbidden:
        raise SystemExit(
            f"owned Wi-Fi verifier imports forbidden side-effect modules: "
            f"{sorted(forbidden)}")

    required = (
        'MAX_EVIDENCE_BYTES = 65_536',
        'MAX_RECORDS = 16',
        'MAX_CORPUS_BYTES = 64 * 1024 * 1024',
        'MAX_BUDGET_CANDIDATES = 1_000_000',
        'MAX_BUDGET_SECONDS = 3_600.0',
        '"plaintext_retained": False',
        '"raw_evidence_retained": False',
        '"identity_linked_leak_corpus_bundled": False',
        '"network_operations": 0',
        '"device_writes": 0',
        '"radio_operations": 0',
        'verification requires --owned-evidence-confirmed',
        'verification requires --checkpoint',
    )
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        raise SystemExit(
            "owned Wi-Fi verifier safety contract is incomplete: " +
            ", ".join(missing))
    journey = JOURNEY.read_text(encoding="utf-8")
    journey_required = (
        '--yes-i-am-authorized',
        '--preview-only',
        '--resume',
        'No match does not prove that the password is strong',
        'Отсутствие совпадения не доказывает надёжность пароля',
        'без сети, радио и записи на устройство',
        'checkpoint_path=checkpoint_path',
        'preview_only=True',
    )
    missing = [fragment for fragment in journey_required
               if fragment not in journey]
    if missing:
        raise SystemExit(
            "task-first Wi-Fi journey contract is incomplete: " +
            ", ".join(missing))
    hil = HIL_RUNNER.read_text(encoding="utf-8")
    hil_required = (
        'volatile_list_mount_on_save_only',
        '"wifi_network_navigation_locked": False',
        '"wifi_network_focus_user_owned": True',
        '"wifi_product_view": "password_check_intro"',
        '"runtime_event": "wifi_password_check_intro"',
        'report.get("outcome") == "complete_no_match"',
        'report.get("outcome") == "weak_password_match"',
        '"public_positive_control": positive_control',
        '"fresh_flash": False',
        '"raw_export_retained": False',
        '"candidate_plaintext_retained": False',
        '"private_network_identity_retained": False',
        'authentication.enter_network_detail = current_network_detail',
        'persistence.read_binary_artifact = intercept_reader',
    )
    missing = [fragment for fragment in hil_required if fragment not in hil]
    if missing:
        raise SystemExit(
            "owned Wi-Fi physical-chain contract is incomplete: " +
            ", ".join(missing))
    persistence = PERSISTENCE_RUNNER.read_text(encoding="utf-8")
    persistence_required = (
        'def open_library_export_ready(',
        '"export_ready": action(device, "right")',
        '"library_view": expected_views[stage]',
        'library_navigation = open_library_export_ready(',
        'def close_library_export_to_home(',
        '"home": action(device, "left")',
        'library_exit = close_library_export_to_home(',
    )
    missing = [fragment for fragment in persistence_required
               if fragment not in persistence]
    if missing:
        raise SystemExit(
            "owned Wi-Fi cold-export contract is incomplete: " +
            ", ".join(missing))
    print("owned Wi-Fi evidence verifier contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
