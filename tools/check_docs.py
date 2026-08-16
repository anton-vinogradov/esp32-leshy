#!/usr/bin/env python3
"""Validate the ESP32-Leshy documentation source-of-truth invariants."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "docs" / "v1"


def ids(path: Path, pattern: str) -> set[str]:
    return set(re.findall(pattern, path.read_text(encoding="utf-8")))


def main() -> int:
    errors: list[str] = []

    markdown_files = [ROOT / "README.md", ROOT / "README.ru.md"]
    markdown_files.extend(sorted((ROOT / "docs").rglob("*.md")))
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")

    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        for raw_link in link_pattern.findall(text):
            link = raw_link.strip()
            if link.startswith("<") and link.endswith(">"):
                link = link[1:-1]
            link = re.sub(r"\s+[\"'].*$", "", link)
            if not link or link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = unquote(link.split("#", 1)[0])
            target = (path.parent / relative).resolve()
            if not target.exists():
                errors.append(f"broken local link: {path.relative_to(ROOT)} -> {link}")

    paired_ids = [
        ("stage", V1 / "DELIVERY_PLAN.md", V1 / "DELIVERY_PLAN.ru.md", r"^## (S\d+)\b"),
        ("job", V1 / "PRODUCT_REQUIREMENTS.md", V1 / "PRODUCT_REQUIREMENTS.ru.md", r"\bJ-\d{2}\b"),
        (
            "requirement",
            V1 / "PRODUCT_REQUIREMENTS.md",
            V1 / "PRODUCT_REQUIREMENTS.ru.md",
            r"\b(?:PR|NFR)-\d{3}\b",
        ),
        (
            "capability",
            V1 / "CAPABILITY_CATALOG.md",
            V1 / "CAPABILITY_CATALOG.ru.md",
            r"\bCAP-\d{3}\b",
        ),
        (
            "UX baseline artifact",
            V1 / "UX_UI_BASELINE.md",
            V1 / "UX_UI_BASELINE.ru.md",
            r"\bUX-\d{2}\b",
        ),
        (
            "UX screen",
            V1 / "UX_SCREEN_MAP.md",
            V1 / "UX_SCREEN_MAP.ru.md",
            r"\bUX-S\d{2}\b",
        ),
        (
            "catalog review finding",
            V1 / "CAPABILITY_REVIEW.md",
            V1 / "CAPABILITY_REVIEW.ru.md",
            r"\bCRV-\d{2}\b",
        ),
        (
            "stage demo",
            V1 / "STAGE_DEMO.md",
            V1 / "STAGE_DEMO.ru.md",
            r"\bDEMO-S\d+\b",
        ),
        ("goal", V1 / "TRACEABILITY.md", V1 / "TRACEABILITY.ru.md", r"\bG-\d{3}\b"),
        (
            "hardware unknown",
            V1 / "HARDWARE_ENVELOPE.md",
            V1 / "HARDWARE_ENVELOPE.ru.md",
            r"\bHW-U\d{2}\b",
        ),
        (
            "hardware test",
            V1 / "HARDWARE_ENVELOPE.md",
            V1 / "HARDWARE_ENVELOPE.ru.md",
            r"\bHW-T\d{2}\b",
        ),
    ]
    for label, english, russian, pattern in paired_ids:
        flags = re.MULTILINE if pattern.startswith("^") else 0
        en_ids = set(re.findall(pattern, english.read_text(encoding="utf-8"), flags))
        ru_ids = set(re.findall(pattern, russian.read_text(encoding="utf-8"), flags))
        if en_ids != ru_ids:
            errors.append(
                f"EN/RU {label} IDs differ: EN-only={sorted(en_ids - ru_ids)}, "
                f"RU-only={sorted(ru_ids - en_ids)}"
            )

    active_pattern = re.compile(r"^\| (S\d+) \| `active` \|", re.MULTILINE)
    active_by_language: dict[str, list[str]] = {}
    for language, path in (("EN", V1 / "STATUS.md"), ("RU", V1 / "STATUS.ru.md")):
        active = active_pattern.findall(path.read_text(encoding="utf-8"))
        active_by_language[language] = active
        if len(active) != 1:
            errors.append(f"{language} STATUS must contain exactly one active stage, found {active}")
    if active_by_language["EN"] != active_by_language["RU"]:
        errors.append(f"EN/RU active stages differ: {active_by_language}")

    checkbox_pattern = re.compile(r"^\s*- \[[ xX]\]", re.MULTILINE)
    for path in sorted(V1.rglob("*.md")):
        if checkbox_pattern.search(path.read_text(encoding="utf-8")):
            errors.append(
                f"live checklist outside canonical STATUS is forbidden: {path.relative_to(ROOT)}"
            )

    manifest_path = ROOT / "docs" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "0.x" not in str(manifest.get("name", "")):
        errors.append("docs/manifest.json must explicitly label the installed line as 0.x")

    installer = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    if "ESP32-Leshy 0.x" not in installer:
        errors.append("docs/index.html must explicitly label the installer as ESP32-Leshy 0.x")

    if errors:
        print("documentation checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "documentation checks passed: links, EN/RU IDs, active stage, "
        "status discipline, and 0.x installer label"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
