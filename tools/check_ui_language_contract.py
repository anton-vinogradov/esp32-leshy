#!/usr/bin/env python3
"""Fail-closed host verifier for the generated EN/RU UI language contract."""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
FONT = ROOT / "firmware/leshy1/src/ui/fonts/RobotoCondensedGfx.h"
TTF = ROOT / "firmware/leshy1/assets/fonts/roboto-condensed/RobotoCondensed-wght.ttf"
LICENSE = ROOT / "firmware/leshy1/assets/fonts/roboto-condensed/OFL.txt"
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
CATALOG = ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.cpp"
CATALOG_HEADER = ROOT / "firmware/leshy1/src/domain/apps/AppCatalog.h"
CONTROLLER = ROOT / "firmware/leshy1/src/ui/UiController.cpp"
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"
EXPECTED_TTF_SHA256 = "dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0"
FIRST = 0x20
LAST = 0x451


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_glyphs(source: str, name: str) -> list[tuple[int, int, int, int, int, int]]:
    match = re.search(
        rf"const GFXglyph {name}Glyphs\[\] PROGMEM = \{{(.*?)\n\}};",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"missing generated glyph table: {name}")
    glyphs = []
    for line in match.group(1).splitlines():
        metric = re.search(
            r"\{(\d+), (\d+), (\d+), (\d+), (-?\d+), (-?\d+)\}", line
        )
        if metric:
            glyphs.append(tuple(int(value) for value in metric.groups()))
    if len(glyphs) != LAST - FIRST + 1:
        raise ValueError(f"{name}: expected {LAST - FIRST + 1} glyphs, got {len(glyphs)}")
    return glyphs


def pixel_width(text: str, glyphs: list[tuple[int, int, int, int, int, int]]) -> int:
    pen = 0
    rightmost = 0
    for character in text:
        codepoint = ord(character)
        if codepoint < FIRST or codepoint > LAST:
            raise ValueError(f"unsupported U+{codepoint:04X} in {text!r}")
        _, width, _, advance, x_offset, _ = glyphs[codepoint - FIRST]
        rightmost = max(rightmost, pen + x_offset + width)
        pen += advance
    return max(pen, rightmost)


def parse_catalog() -> list[tuple[str, str, int, str, str]]:
    entries = []
    pattern = re.compile(
        r'^LESHY_UI_TEXT\((\w+), (Body|Meta), (\d+), ("(?:[^"\\]|\\.)*"), '
        r'u8("(?:[^"\\]|\\.)*")\)$'
    )
    for number, line in enumerate(DEFINITIONS.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("LESHY_UI_TEXT"):
            continue
        match = pattern.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid UiStrings.def line {number}: {line}")
        identifier, role, maximum, english, russian = match.groups()
        entries.append(
            (identifier, role, int(maximum), ast.literal_eval(english), ast.literal_eval(russian))
        )
    return entries


def main() -> int:
    failures: list[str] = []
    for path in (DEFINITIONS, FONT, TTF, LICENSE, RENDERER, CATALOG,
                 CATALOG_HEADER, CONTROLLER, PLATFORMIO):
        require(failures, path.is_file(), f"missing contract file: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    require(failures, digest(TTF) == EXPECTED_TTF_SHA256,
            "vendored Roboto Condensed TTF hash mismatch")
    license_text = LICENSE.read_text(encoding="utf-8")
    require(failures, "SIL OPEN FONT LICENSE Version 1.1" in license_text,
            "SIL OFL license text missing")

    try:
        entries = parse_catalog()
        font_source = FONT.read_text(encoding="utf-8")
        body = parse_glyphs(font_source, "RobotoCondensedBody")
        meta = parse_glyphs(font_source, "RobotoCondensedMeta")
    except ValueError as error:
        failures.append(str(error))
        entries = []
        body = []
        meta = []

    require(failures, len(entries) >= 100,
            "catalog does not cover all current S2 user-facing surfaces")
    identifiers = [entry[0] for entry in entries]
    require(failures, len(identifiers) == len(set(identifiers)),
            "duplicate UI text identifier")
    for identifier, role, maximum, english, russian in entries:
        require(failures, bool(english) and bool(russian),
                f"{identifier}: empty translation")
        require(failures, 0 < maximum <= 212,
                f"{identifier}: invalid fit budget")
        if body and meta:
            glyphs = body if role == "Body" else meta
            for language, value in (("en", english), ("ru", russian)):
                try:
                    width = pixel_width(value, glyphs)
                except ValueError as error:
                    failures.append(f"{identifier}/{language}: {error}")
                    continue
                require(failures, width <= maximum,
                        f"{identifier}/{language}: {width}px exceeds {maximum}px")

    renderer = RENDERER.read_text(encoding="utf-8")
    require(failures, renderer.count("tr(UiTextId::") >= 80,
            "renderer bypasses the single UI string catalog")
    literal_prints = re.findall(r'display\.print\("([^"]*)"\)', renderer)
    require(failures, literal_prints == [],
            f"uncatalogued display literals: {literal_prints}")
    for marker in ('"SD OK"', '"SD !"', '"SD --"', '"RF RX"', '"RF --"'):
        require(failures, marker in renderer,
                f"language-neutral status label missing: {marker}")
    for token in ("setFreeFont(&RobotoCondensedBody)",
                  "setFreeFont(&RobotoCondensedMeta)",
                  "languageController.restore(loadUiLanguage())",
                  "saveUiLanguage(requested)",
                  '"ui.language "',
                  '"language\\\":\\\"%s'):
        require(failures, token in renderer, f"renderer contract missing: {token}")

    catalog = CATALOG.read_text(encoding="utf-8")
    require(failures, "kCapacity = 7" in CATALOG_HEADER.read_text(encoding="utf-8"),
            "Home must expose seven implemented user tasks")
    require(failures,
            '"device", "DEVICE"' in catalog and
            '"language", "LANGUAGE"' not in catalog and
            '"self-test", "SELF-TEST"' not in catalog and
            "uiController.openChild" in renderer,
            "Language/Self-Test must live below the final Device domain")
    controller = CONTROLLER.read_text(encoding="utf-8")
    require(failures, 'case 5: return "language"' in controller and
            'case 6: return "self_test"' in controller and
            'case 9: return "device"' in controller,
            "Device/Language/Self-Test page mapping mismatch")
    platformio = PLATFORMIO.read_text(encoding="utf-8")
    require(failures, "-D LOAD_GFXFF=1" in platformio,
            "UTF-8 firmware font build contract missing")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"UI language contract passed: {len(entries)} EN/RU strings fit generated GFX fonts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
