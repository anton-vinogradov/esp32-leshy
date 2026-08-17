#!/usr/bin/env python3
"""Machine-check retained 0.52 visual-system build and physical TFT evidence."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-visual-system-0.52.json"
THEME = ROOT / "firmware/leshy1/src/ui/VisualTheme.h"
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
PLATFORMIO = ROOT / "firmware/leshy1/platformio.ini"
SHA256 = re.compile(r"[0-9a-f]{64}")


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def exact(record: dict[str, Any], expected: dict[str, Any], prefix: str,
          failures: list[str]) -> None:
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(f"{prefix}{field}: {record.get(field)!r} != {value!r}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"{path}: invalid PNG signature")
    offset = 8
    width = height = 0
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if (depth, color_type, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError(f"{path}: unsupported PNG format")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    stride = 1 + width * 3
    if len(raw) != stride * height:
        raise ValueError(f"{path}: invalid decoded size")
    rows: list[list[tuple[int, int, int]]] = []
    for y in range(height):
        row = raw[y * stride:(y + 1) * stride]
        if row[0] != 0:
            raise ValueError(f"{path}: expected deterministic filter 0")
        rows.append([
            tuple(row[1 + x * 3:4 + x * 3])  # type: ignore[arg-type]
            for x in range(width)
        ])
    return width, height, rows


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    failures: list[str] = []
    exact(evidence, {
        "schema": "leshy.visual_system_acceptance.v1",
        "status": "pass_s2_candidate_not_stage_gate",
        "trust_status": "unsigned_local_result",
        "gate_eligible": False,
        "evidence_ids": ["E-BUILD-054", "E-HIL-076", "E-UX-003"],
        "board": "board-01", "profile": "esp32-div-v2-n16",
    }, "", failures)

    candidate = evidence.get("candidate", {})
    exact(candidate, {
        "version": "0.52.0-visual-system-measure",
        "firmware_sha256": "39fc2c923d56de9c495be998ea72b4aec6d6eea7eaac89e358dd9e668aa43ace",
        "factory_sha256": "56f90026c71a81734773e7a68f38b30f3aaed280ae016eafffab89094321569a",
        "app_elf_sha256": "d240d6aacbcb55baa91050c0c5bccd1714f3563f542e691cef7fe2b6adc9ada8",
        "linked_flash_bytes": 1063092, "static_ram_bytes": 125464,
        "app_image_bytes": 1063248, "factory_image_bytes": 1128784,
        "rtc_noinit_bytes": 20, "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate.", failures)

    hil = evidence.get("product_hil", {})
    exact(hil, {
        "run_id": "641a328b1437ac638f7186dd5457a9c4",
        "run_sha256": "703c8fed4d76fef52235927034c1e06cea9cd60a9ca6788cb83ef12f92e82018",
        "artifact_index_sha256": "33131ac807bac2e043a4cdb0a5c5739f0482a7c0d7836b965d8df44ec4282ecc",
        "passed": True, "gate_eligible": True,
        "exact_cid": "FE343253440000002000000055019CB7",
        "generation_before": 64, "generation_after": 65,
        "observations": 9, "scan_accepted": 9,
        "pipeline_forwarded": 9, "scan_dropped": 0,
        "pipeline_dropped": 0,
        "heap_total_bytes": 276040, "heap_free_bytes": 227588,
        "heap_min_free_bytes": 192128,
        "final_owner": "none", "final_lease_mask": 0,
    }, "product_hil.", failures)
    require(failures, 0 < hil.get("ready_before_ms", 0) < 2000,
            "product_hil.ready_before_ms: expected 0..2000")
    require(failures, 0 < hil.get("ready_after_ms", 0) < 2000,
            "product_hil.ready_after_ms: expected 0..2000")

    contract = evidence.get("visual_contract", {})
    exact(contract, {
        "source": "firmware/leshy1/src/ui/VisualTheme.h",
        "screen_width": 240, "screen_height": 320, "edge_px": 12,
        "content_width_px": 216, "header_height_px": 42,
        "row_height_px": 40, "row_gap_px": 7,
        "footer_divider_y": 236,
        "raw_tft_colors_remaining_in_renderer": 0,
        "footer_wrap_regression_fixed": True,
    }, "visual_contract.", failures)
    roles = contract.get("semantic_roles", [])
    require(failures, isinstance(roles, list) and len(roles) == 13 and
            len(set(roles)) == 13, "visual_contract.semantic_roles: require 13 roles")

    theme = THEME.read_text(encoding="utf-8")
    for token in ("struct Palette", "struct Layout", "ContentWidth = 216",
                  "FooterDividerY = 236", "static_assert"):
        require(failures, token in theme, f"VisualTheme.h: missing {token!r}")
    renderer = RENDERER.read_text(encoding="utf-8")
    require(failures, '#include "ui/VisualTheme.h"' in renderer,
            "renderer: VisualTheme include missing")
    for raw_color in ("TFT_BLACK", "TFT_YELLOW", "TFT_LIGHTGREY",
                      "TFT_GREEN", "TFT_DARKGREY", "TFT_RED", "color565("):
        require(failures, raw_color not in renderer,
                f"renderer: raw color remains: {raw_color}")
    require(failures, 'LESHY1_VERSION=\\"0.52.0-visual-system-measure\\"' in
            PLATFORMIO.read_text(encoding="utf-8"),
            "platformio.ini: wrong measurement version")

    expected_names = {"setup", "running", "committed", "export", "library", "home"}
    screens = evidence.get("retained_screens", {})
    require(failures, isinstance(screens, dict) and set(screens) == expected_names,
            "retained_screens: require six exact screens")
    decoded: dict[str, list[list[tuple[int, int, int]]]] = {}
    hashes: list[str] = []
    if isinstance(screens, dict):
        for name in sorted(expected_names):
            record = screens.get(name, {})
            relative = record.get("path")
            digest = record.get("png_sha256")
            require(failures, isinstance(relative, str), f"{name}.path: invalid")
            require(failures, isinstance(digest, str) and SHA256.fullmatch(digest) is not None,
                    f"{name}.png_sha256: invalid")
            if not isinstance(relative, str):
                continue
            path = ROOT / relative
            require(failures, path.is_file(), f"{name}: retained PNG missing")
            if not path.is_file():
                continue
            require(failures, sha256_file(path) == digest, f"{name}: PNG hash mismatch")
            hashes.append(str(digest))
            try:
                width, height, rows = decode_png(path)
            except ValueError as error:
                failures.append(str(error))
                continue
            require(failures, (width, height) == (240, 320),
                    f"{name}: expected 240x320")
            decoded[name] = rows
            header = (24, 56, 41)
            brand_x = [x for x, pixel in enumerate(rows[20]) if pixel != header]
            require(failures, bool(brand_x) and min(brand_x) <= 12 and max(brand_x) >= 120,
                    f"{name}: brand/header span incomplete")
            divider = (57, 73, 66)
            require(failures, all(rows[236][x] == divider for x in range(12, 228)),
                    f"{name}: footer divider incomplete")
            canvas = (0, 16, 8)
            input_pixels = [pixel for pixel in rows[258][16:132] if pixel != canvas]
            require(failures, len(input_pixels) >= 20,
                    f"{name}: INPUT RAW status not visible")
    require(failures, len(hashes) == 6 and len(set(hashes)) == 6,
            "retained_screens: screenshots must be six distinct frames")
    canvas = (0, 16, 8)
    for name in ("library", "home"):
        if name in decoded:
            require(failures,
                    all(pixel == canvas for row in decoded[name][310:320] for pixel in row),
                    f"{name}: footer copy wrapped into bottom guard rows")

    pixel_audit = evidence.get("pixel_audit", {})
    exact(pixel_audit, {
        "dimensions_match": True,
        "brand_spans_expected_header_width": True,
        "footer_divider_present": True,
        "input_status_present": True,
        "library_bottom_guard_rows_clear": True,
        "screens_distinct": True,
        "manual_visual_review": "pass",
    }, "pixel_audit.", failures)
    fixture = evidence.get("fixture_mismatch_diagnostic", {})
    exact(fixture, {
        "generic_suite_status": "failed_as_designed",
        "candidate_fault": False, "goldens_promoted": False,
        "correct_product_aware_runner_used": True,
    }, "fixture_mismatch_diagnostic.", failures)
    scope = evidence.get("scope", {})
    exact(scope, {
        "ux_03": "implemented_and_physically_evidenced",
        "ux_07": "partial", "demo_s2": "open",
    }, "scope.", failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("visual-system acceptance evidence: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
