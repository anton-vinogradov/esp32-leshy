#!/usr/bin/env python3
"""Host tests for the external-camera release subset contract."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from verify_1x_camera_subset import ContractError, REQUIRED_STAGES, verify


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def png(width: int, height: int, pixels: bytes) -> bytes:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(pixels[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def screen(stage: int) -> bytes:
    width, height = 240, 320
    result = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            color = (10, 14, 20)
            if y < 33:
                color = (22 + stage * 8, 80, 120 + stage * 12)
            if 16 <= x < 48 and 55 <= y < 102 + stage * 9:
                color = (235, 205 - stage * 20, 42 + stage * 22)
            if 64 <= x < 221 and 69 + stage * 11 <= y < 82 + stage * 11:
                color = (220, 225, 230)
            if 78 <= x < 190 - stage * 8 and 121 <= y < 131:
                color = (74, 190, 122)
            if 111 <= x < 222 and 178 + stage * 6 <= y < 193 + stage * 6:
                color = (176, 82, 208)
            if x > 196 and y > 268 - stage * 7:
                color = (240, 92, 52)
            offset = (y * width + x) * 3
            result[offset:offset + 3] = bytes(color)
    return bytes(result)


def camera_frame(panel: bytes, rotation: int = 0, blank: bool = False) -> bytes:
    frame_width, frame_height = 640, 480
    x0, y0, x1, y1 = 200, 80, 439, 399
    result = bytearray((18, 19, 20) * (frame_width * frame_height))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            u = (x - x0) / (x1 - x0)
            v = (y - y0) / (y1 - y0)
            if rotation == 180:
                u, v = 1.0 - u, 1.0 - v
            source_x = min(239, int(round(u * 239)))
            source_y = min(319, int(round(v * 319)))
            source = (source_y * 240 + source_x) * 3
            color = (25, 25, 25) if blank else panel[source:source + 3]
            target = (y * frame_width + x) * 3
            result[target:target + 3] = color
    return bytes(result)


class CameraSubsetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest = {
            "schema": "leshy.camera_subset.manifest.v1",
            "calibration": {
                "station_id": "board-01-bench",
                "camera_id": "synthetic-camera",
                "frame_width": 640,
                "frame_height": 480,
                "panel_quad_normalized": [
                    [200 / 639, 80 / 479], [439 / 639, 80 / 479],
                    [439 / 639, 399 / 479], [200 / 639, 399 / 479],
                ],
            },
            "thresholds": {
                "minimum_luma_contrast": 24,
                "minimum_reference_correlation": 0.45,
                "minimum_orientation_margin": 0.06,
            },
            "stages": [],
        }
        for index, stage in enumerate(REQUIRED_STAGES):
            gram = screen(index)
            gram_name = f"{stage}.gram.png"
            camera_name = f"{stage}.camera.png"
            (self.root / gram_name).write_bytes(png(240, 320, gram))
            (self.root / camera_name).write_bytes(
                png(640, 480, camera_frame(gram))
            )
            self.manifest["stages"].append({
                "id": stage, "camera_png": camera_name, "gram_png": gram_name,
            })
        self.path = self.root / "camera-manifest.json"
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self) -> None:
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_matching_physical_frames_pass(self) -> None:
        result = verify(self.path)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(len(result["stages"]), 4)
        self.assertTrue(all(stage["camera_png_sha256"] for stage in result["stages"]))
        self.assertGreater(
            min(stage["orientation_correlations"]["0"] for stage in result["stages"]),
            0.9,
        )

    def test_rotated_panel_fails_orientation(self) -> None:
        gram = screen(1)
        (self.root / "running.camera.png").write_bytes(
            png(640, 480, camera_frame(gram, rotation=180))
        )
        result = verify(self.path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("orientation margin" in item for item in result["failures"]))

    def test_blank_panel_fails_contrast_and_reference(self) -> None:
        gram = screen(2)
        (self.root / "committed.camera.png").write_bytes(
            png(640, 480, camera_frame(gram, blank=True))
        )
        result = verify(self.path)
        self.assertFalse(result["passed"])
        failures = "\n".join(result["failures"])
        self.assertIn("panel contrast", failures)
        self.assertIn("GRAM correlation", failures)

    def test_policy_thresholds_cannot_be_weakened(self) -> None:
        self.manifest["thresholds"]["minimum_reference_correlation"] = 0.01
        self.write_manifest()
        with self.assertRaisesRegex(ContractError, "weaker than release policy"):
            verify(self.path)

    def test_unsafe_evidence_path_is_rejected(self) -> None:
        self.manifest["stages"][0]["camera_png"] = "../outside.png"
        self.write_manifest()
        with self.assertRaisesRegex(ContractError, "unsafe path"):
            verify(self.path)

    def test_exact_stage_set_is_required(self) -> None:
        self.manifest["stages"].pop()
        self.write_manifest()
        with self.assertRaisesRegex(ContractError, "require exact order"):
            verify(self.path)


if __name__ == "__main__":
    unittest.main()
