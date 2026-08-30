"""Pure host validation for public Automation owner trust bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BUNDLE_SCHEMA = "leshy.automation.trust_bundle.v1"
BUNDLE_BYTES = 128


def load_public_bundle(bundle_path: Path,
                       metadata_path: Path) -> tuple[bytes, dict[str, Any]]:
    bundle = bundle_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("bundle metadata must be a JSON object")
    digest = hashlib.sha256(bundle).hexdigest()
    expected = {
        "schema": BUNDLE_SCHEMA,
        "algorithm": "ecdsa_p256_sha256",
        "bundle_bytes": BUNDLE_BYTES,
        "bundle_sha256": digest,
        "contains_private_key": False,
    }
    actual = {key: metadata.get(key) for key in expected}
    if actual != expected:
        raise ValueError(
            f"public bundle metadata mismatch: expected={expected}, actual={actual}")
    key_id = metadata.get("key_id")
    public_key_sha256 = metadata.get("public_key_sha256")
    label = metadata.get("label")
    if len(bundle) != BUNDLE_BYTES:
        raise ValueError(f"public bundle must be exactly {BUNDLE_BYTES} bytes")
    if (not isinstance(key_id, str) or len(key_id) != 16 or
            any(character not in "0123456789abcdef" for character in key_id)):
        raise ValueError("metadata key_id must be 16 lowercase hex characters")
    if (not isinstance(public_key_sha256, str) or
            len(public_key_sha256) != 64 or
            any(character not in "0123456789abcdef"
                for character in public_key_sha256) or
            not public_key_sha256.startswith(key_id)):
        raise ValueError("metadata public key digest/key id binding is invalid")
    if not isinstance(label, str) or not label or len(label.encode("utf-8")) > 31:
        raise ValueError("metadata label is missing or too long")
    return bundle, metadata
