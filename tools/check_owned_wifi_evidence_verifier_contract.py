#!/usr/bin/env python3
"""Fail closed if the owned Wi-Fi verifier loses its safety contract."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/owned_wifi_evidence_verifier.py"


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(SOURCE))
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
    forbidden = imported & {
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
    print("owned Wi-Fi evidence verifier contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
