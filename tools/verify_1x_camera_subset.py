#!/usr/bin/env python3
"""Verify external-camera views of the same UI states captured from TFT GRAM.

The verifier deliberately uses only the Python standard library.  Camera and
GRAM inputs are 8-bit, non-interlaced RGB/RGBA PNG files.  A station-specific
quadrilateral rectifies the physical panel before its luminance pattern is
compared with the exact GRAM frame.  Exposure changes are tolerated; a blank,
rotated, substituted, or badly registered panel is not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Iterable, Sequence


MANIFEST_SCHEMA = "leshy.camera_subset.manifest.v1"
RESULT_SCHEMA = "leshy.camera_subset.result.v1"
REQUIRED_STAGES = ("setup", "running", "committed", "export")
GRID_WIDTH = 24
GRID_HEIGHT = 32
POLICY_MIN_CONTRAST = 12.0
POLICY_MIN_CORRELATION = 0.25
POLICY_MIN_ORIENTATION_MARGIN = 0.025
MAX_PIXELS = 16_000_000


class ContractError(ValueError):
    """A fail-closed camera evidence contract violation."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"expected JSON object: {path}")
    return value


def safe_child(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label}: expected a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ContractError(f"{label}: unsafe path {value!r}")
    root_resolved = root.resolve()
    path = (root / relative).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ContractError(f"{label}: path escapes evidence root")
    if not path.is_file():
        raise ContractError(f"{label}: file not found: {value}")
    return path


def paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def decode_png(path: Path) -> tuple[int, int, bytes]:
    """Decode bounded 8-bit RGB/RGBA PNG to packed RGB bytes."""
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError(f"{path.name}: not a PNG")
    position = 8
    header: tuple[int, int, int, int, int, int, int] | None = None
    compressed = bytearray()
    saw_end = False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        end = position + 12 + length
        if end > len(data):
            raise ContractError(f"{path.name}: truncated PNG chunk")
        payload = data[position + 8:position + 8 + length]
        expected_crc = struct.unpack(">I", data[position + 8 + length:end])[0]
        actual_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ContractError(f"{path.name}: invalid PNG chunk CRC")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ContractError(f"{path.name}: invalid IHDR")
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            saw_end = True
            break
        position = end
    if header is None or not compressed or not saw_end:
        raise ContractError(f"{path.name}: incomplete PNG")
    width, height, depth, color_type, compression, filtering, interlace = header
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise ContractError(f"{path.name}: unsafe PNG dimensions {width}x{height}")
    if depth != 8 or color_type not in (2, 6) or compression or filtering or interlace:
        raise ContractError(
            f"{path.name}: require non-interlaced 8-bit RGB/RGBA PNG"
        )
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ContractError(f"{path.name}: invalid PNG deflate stream") from error
    if len(raw) != height * (stride + 1):
        raise ContractError(f"{path.name}: unexpected decoded PNG length")
    rows: list[bytearray] = []
    offset = 0
    for row_index in range(height):
        filter_kind = raw[offset]
        offset += 1
        encoded = raw[offset:offset + stride]
        offset += stride
        if filter_kind > 4:
            raise ContractError(f"{path.name}: unsupported PNG filter {filter_kind}")
        decoded = bytearray(stride)
        previous = rows[row_index - 1] if row_index else None
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index] if previous is not None else 0
            upper_left = (
                previous[index - channels]
                if previous is not None and index >= channels else 0
            )
            if filter_kind == 0:
                predictor = 0
            elif filter_kind == 1:
                predictor = left
            elif filter_kind == 2:
                predictor = above
            elif filter_kind == 3:
                predictor = (left + above) // 2
            else:
                predictor = paeth(left, above, upper_left)
            decoded[index] = (value + predictor) & 0xFF
        rows.append(decoded)
    rgb = bytearray(width * height * 3)
    target = 0
    for row in rows:
        for source in range(0, len(row), channels):
            rgb[target:target + 3] = row[source:source + 3]
            target += 3
    return width, height, bytes(rgb)


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label}: expected a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{label}: expected a finite number")
    return result


def calibration(manifest: dict[str, Any]) -> dict[str, Any]:
    value = manifest.get("calibration")
    if not isinstance(value, dict):
        raise ContractError("calibration: expected object")
    for field in ("station_id", "camera_id"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ContractError(f"calibration.{field}: required")
    width = value.get("frame_width")
    height = value.get("frame_height")
    if not isinstance(width, int) or isinstance(width, bool) or width < 320:
        raise ContractError("calibration.frame_width: must be an integer >= 320")
    if not isinstance(height, int) or isinstance(height, bool) or height < 240:
        raise ContractError("calibration.frame_height: must be an integer >= 240")
    raw_quad = value.get("panel_quad_normalized")
    if not isinstance(raw_quad, list) or len(raw_quad) != 4:
        raise ContractError("calibration.panel_quad_normalized: require TL/TR/BR/BL")
    quad: list[tuple[float, float]] = []
    for index, point in enumerate(raw_quad):
        if not isinstance(point, list) or len(point) != 2:
            raise ContractError(f"calibration.panel_quad_normalized[{index}]: invalid")
        x = number(point[0], f"panel_quad[{index}].x")
        y = number(point[1], f"panel_quad[{index}].y")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ContractError(f"calibration.panel_quad_normalized[{index}]: out of bounds")
        quad.append((x, y))
    tl, tr, br, bl = quad
    top = math.dist(tl, tr)
    bottom = math.dist(bl, br)
    left = math.dist(tl, bl)
    right = math.dist(tr, br)
    if min(top, bottom, left, right) < 0.12:
        raise ContractError("calibration.panel_quad_normalized: panel is too small")
    cross_values = []
    for first, second, third in zip(quad, quad[1:] + quad[:1], quad[2:] + quad[:2]):
        cross_values.append(
            (second[0] - first[0]) * (third[1] - second[1])
            - (second[1] - first[1]) * (third[0] - second[0])
        )
    if not (all(value > 0.0 for value in cross_values)
            or all(value < 0.0 for value in cross_values)):
        raise ContractError("calibration.panel_quad_normalized: require a convex ordered quad")
    aspect = ((top + bottom) / 2.0 * width) / ((left + right) / 2.0 * height)
    if not 0.55 <= aspect <= 0.95:
        raise ContractError(
            f"calibration.panel_quad_normalized: implausible portrait aspect {aspect:.3f}"
        )
    return {**value, "quad": quad, "panel_aspect": aspect}


def thresholds(manifest: dict[str, Any]) -> dict[str, float]:
    raw = manifest.get("thresholds", {})
    if not isinstance(raw, dict):
        raise ContractError("thresholds: expected object")
    values = {
        "minimum_luma_contrast": number(raw.get("minimum_luma_contrast", 24.0),
                                         "minimum_luma_contrast"),
        "minimum_reference_correlation": number(
            raw.get("minimum_reference_correlation", 0.45),
            "minimum_reference_correlation",
        ),
        "minimum_orientation_margin": number(
            raw.get("minimum_orientation_margin", 0.06),
            "minimum_orientation_margin",
        ),
    }
    if values["minimum_luma_contrast"] < POLICY_MIN_CONTRAST:
        raise ContractError("minimum_luma_contrast is weaker than release policy")
    if values["minimum_reference_correlation"] < POLICY_MIN_CORRELATION:
        raise ContractError("minimum_reference_correlation is weaker than release policy")
    if values["minimum_orientation_margin"] < POLICY_MIN_ORIENTATION_MARGIN:
        raise ContractError("minimum_orientation_margin is weaker than release policy")
    if values["minimum_reference_correlation"] > 1.0:
        raise ContractError("minimum_reference_correlation cannot exceed 1")
    if values["minimum_orientation_margin"] > 1.0:
        raise ContractError("minimum_orientation_margin cannot exceed 1")
    return values


def pixel(rgb: bytes, width: int, height: int, x: float, y: float) -> tuple[float, float, float]:
    x = min(max(x, 0.0), width - 1.0)
    y = min(max(y, 0.0), height - 1.0)
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    x1, y1 = min(x0 + 1, width - 1), min(y0 + 1, height - 1)
    fx, fy = x - x0, y - y0
    samples = []
    for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        offset = (py * width + px) * 3
        samples.append(rgb[offset:offset + 3])
    return tuple(
        samples[0][channel] * (1.0 - fx) * (1.0 - fy)
        + samples[1][channel] * fx * (1.0 - fy)
        + samples[2][channel] * (1.0 - fx) * fy
        + samples[3][channel] * fx * fy
        for channel in range(3)
    )


def luma(color: Sequence[float]) -> float:
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def square_to_quad(quad: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    """Return a projective transform from unit-square coordinates to a quad."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    dx1, dx2 = x1 - x2, x3 - x2
    dy1, dy2 = y1 - y2, y3 - y2
    dx3, dy3 = x0 - x1 + x2 - x3, y0 - y1 + y2 - y3
    if abs(dx3) < 1e-12 and abs(dy3) < 1e-12:
        projective_x = projective_y = 0.0
    else:
        determinant = dx1 * dy2 - dx2 * dy1
        if abs(determinant) < 1e-12:
            raise ContractError("calibration.panel_quad_normalized: singular transform")
        projective_x = (dx3 * dy2 - dx2 * dy3) / determinant
        projective_y = (dx1 * dy3 - dx3 * dy1) / determinant
    return (
        x1 - x0 + projective_x * x1,
        x3 - x0 + projective_y * x3,
        x0,
        y1 - y0 + projective_x * y1,
        y3 - y0 + projective_y * y3,
        y0,
        projective_x,
        projective_y,
    )


def rectified_luma(width: int, height: int, rgb: bytes,
                   quad: Sequence[tuple[float, float]],
                   rotation: int = 0) -> list[float]:
    transform = square_to_quad(quad)
    result: list[float] = []
    inset = 0.025
    for row in range(GRID_HEIGHT):
        v = inset + (1.0 - inset * 2.0) * (row + 0.5) / GRID_HEIGHT
        for column in range(GRID_WIDTH):
            u = inset + (1.0 - inset * 2.0) * (column + 0.5) / GRID_WIDTH
            if rotation == 90:
                source_u, source_v = v, 1.0 - u
            elif rotation == 180:
                source_u, source_v = 1.0 - u, 1.0 - v
            elif rotation == 270:
                source_u, source_v = 1.0 - v, u
            else:
                source_u, source_v = u, v
            denominator = (
                transform[6] * source_u + transform[7] * source_v + 1.0
            )
            if abs(denominator) < 1e-12:
                raise ContractError("calibration panel transform crosses infinity")
            x = (
                transform[0] * source_u + transform[1] * source_v + transform[2]
            ) / denominator * (width - 1)
            y = (
                transform[3] * source_u + transform[4] * source_v + transform[5]
            ) / denominator * (height - 1)
            result.append(luma(pixel(rgb, width, height, x, y)))
    return result


def full_frame_luma(width: int, height: int, rgb: bytes,
                    rotation: int = 0) -> list[float]:
    quad = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    return rectified_luma(width, height, rgb, quad, rotation)


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * fraction))
    return ordered[index]


def correlation(first: Sequence[float], second: Sequence[float]) -> float:
    if len(first) != len(second) or not first:
        raise ContractError("internal comparison dimensions disagree")
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    numerator = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first, second)
    )
    first_energy = sum((value - first_mean) ** 2 for value in first)
    second_energy = sum((value - second_mean) ** 2 for value in second)
    denominator = math.sqrt(first_energy * second_energy)
    return numerator / denominator if denominator > 1e-9 else 0.0


def rounded(value: float) -> float:
    return round(value, 6)


def verify_stage(root: Path, item: dict[str, Any], cal: dict[str, Any],
                 limits: dict[str, float]) -> tuple[dict[str, Any], list[str]]:
    stage_id = item.get("id")
    camera_path = safe_child(root, item.get("camera_png"), f"{stage_id}.camera_png")
    gram_path = safe_child(root, item.get("gram_png"), f"{stage_id}.gram_png")
    camera_width, camera_height, camera_rgb = decode_png(camera_path)
    gram_width, gram_height, gram_rgb = decode_png(gram_path)
    failures: list[str] = []
    if (camera_width, camera_height) != (cal["frame_width"], cal["frame_height"]):
        failures.append(
            f"{stage_id}: camera dimensions {camera_width}x{camera_height} "
            f"!= calibrated {cal['frame_width']}x{cal['frame_height']}"
        )
    if gram_width * 4 != gram_height * 3 or gram_width < 120:
        failures.append(
            f"{stage_id}: GRAM frame must be portrait 3:4, got {gram_width}x{gram_height}"
        )
    camera_values = rectified_luma(
        camera_width, camera_height, camera_rgb, cal["quad"]
    )
    contrast = percentile(camera_values, 0.95) - percentile(camera_values, 0.05)
    correlations = {
        str(rotation): correlation(
            camera_values,
            full_frame_luma(gram_width, gram_height, gram_rgb, rotation),
        )
        for rotation in (0, 90, 180, 270)
    }
    expected = correlations["0"]
    competing = max(value for key, value in correlations.items() if key != "0")
    margin = expected - competing
    if contrast < limits["minimum_luma_contrast"]:
        failures.append(
            f"{stage_id}: panel contrast {contrast:.3f} below "
            f"{limits['minimum_luma_contrast']:.3f}"
        )
    if expected < limits["minimum_reference_correlation"]:
        failures.append(
            f"{stage_id}: GRAM correlation {expected:.3f} below "
            f"{limits['minimum_reference_correlation']:.3f}"
        )
    if margin < limits["minimum_orientation_margin"]:
        failures.append(
            f"{stage_id}: orientation margin {margin:.3f} below "
            f"{limits['minimum_orientation_margin']:.3f}"
        )
    return {
        "id": stage_id,
        "passed": not failures,
        "camera_png": str(camera_path.relative_to(root.resolve())),
        "camera_png_sha256": sha256_file(camera_path),
        "camera_dimensions": [camera_width, camera_height],
        "gram_png": str(gram_path.relative_to(root.resolve())),
        "gram_png_sha256": sha256_file(gram_path),
        "gram_dimensions": [gram_width, gram_height],
        "panel_luma_mean": rounded(sum(camera_values) / len(camera_values)),
        "panel_luma_p05": rounded(percentile(camera_values, 0.05)),
        "panel_luma_p95": rounded(percentile(camera_values, 0.95)),
        "panel_luma_contrast": rounded(contrast),
        "orientation_correlations": {
            key: rounded(value) for key, value in correlations.items()
        },
        "expected_orientation": 0,
        "expected_orientation_margin": rounded(margin),
        "failures": failures,
    }, failures


def verify(manifest_path: Path) -> dict[str, Any]:
    manifest = load_object(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ContractError(f"schema: expected {MANIFEST_SCHEMA}")
    cal = calibration(manifest)
    limits = thresholds(manifest)
    raw_stages = manifest.get("stages")
    if not isinstance(raw_stages, list):
        raise ContractError("stages: expected array")
    if any(not isinstance(item, dict) for item in raw_stages):
        raise ContractError("stages: every entry must be an object")
    ids = tuple(item.get("id") for item in raw_stages)
    if ids != REQUIRED_STAGES:
        raise ContractError(f"stages: require exact order {REQUIRED_STAGES!r}")
    root = manifest_path.parent.resolve()
    stage_results: list[dict[str, Any]] = []
    failures: list[str] = []
    for item in raw_stages:
        result, stage_failures = verify_stage(root, item, cal, limits)
        stage_results.append(result)
        failures.extend(stage_failures)
    return {
        "schema": RESULT_SCHEMA,
        "passed": not failures,
        "manifest": manifest_path.name,
        "manifest_sha256": sha256_file(manifest_path),
        "station_id": cal["station_id"],
        "camera_id": cal["camera_id"],
        "calibrated_frame_dimensions": [cal["frame_width"], cal["frame_height"]],
        "panel_quad_normalized": manifest["calibration"]["panel_quad_normalized"],
        "panel_aspect": rounded(cal["panel_aspect"]),
        "thresholds": limits,
        "stages": stage_results,
        "failures": failures,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    try:
        result = verify(args.manifest)
    except (ContractError, OSError) as error:
        print(f"camera subset: FAIL: {error}", file=sys.stderr)
        return 2
    write_json(args.output, result)
    if not result["passed"]:
        for failure in result["failures"]:
            print(f"camera subset: FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        f"camera subset: PASS: {len(result['stages'])} physical TFT states, "
        f"station={result['station_id']} camera={result['camera_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
