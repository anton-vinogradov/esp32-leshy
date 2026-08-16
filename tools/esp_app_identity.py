#!/usr/bin/env python3
"""Read the ESP-IDF application identity embedded in an app image."""

from __future__ import annotations

import struct
from pathlib import Path


ESP_IMAGE_MAGIC = 0xE9
ESP_IMAGE_HEADER_BYTES = 24
ESP_SEGMENT_HEADER_BYTES = 8
ESP_APP_DESC_MAGIC = 0xABCD5432
ESP_APP_DESC_BYTES = 256
ESP_APP_DESC_ELF_SHA256_OFFSET = 144


def app_elf_sha256_from_bytes(image: bytes) -> str:
    """Return the full ELF SHA-256 from the first segment app descriptor."""
    descriptor_offset = ESP_IMAGE_HEADER_BYTES + ESP_SEGMENT_HEADER_BYTES
    required = descriptor_offset + ESP_APP_DESC_BYTES
    if len(image) < required:
        raise ValueError(f"candidate is too short for ESP app descriptor: {len(image)}")
    if image[0] != ESP_IMAGE_MAGIC:
        raise ValueError(f"invalid ESP image magic: 0x{image[0]:02x}")
    descriptor_magic = struct.unpack_from("<I", image, descriptor_offset)[0]
    if descriptor_magic != ESP_APP_DESC_MAGIC:
        raise ValueError(
            f"invalid ESP app descriptor magic: 0x{descriptor_magic:08x}"
        )
    start = descriptor_offset + ESP_APP_DESC_ELF_SHA256_OFFSET
    digest = image[start:start + 32]
    if len(digest) != 32 or not any(digest):
        raise ValueError("missing ESP app ELF SHA-256")
    return digest.hex()


def app_elf_sha256(path: Path) -> str:
    with path.open("rb") as candidate:
        return app_elf_sha256_from_bytes(candidate.read(
            ESP_IMAGE_HEADER_BYTES + ESP_SEGMENT_HEADER_BYTES + ESP_APP_DESC_BYTES
        ))
