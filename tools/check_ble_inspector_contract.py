#!/usr/bin/env python3
"""Fail closed if the CAP-051 foundation gains an unreviewed active surface."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/services/ble/BleInspector.h"
SOURCE = ROOT / "firmware/leshy1/src/services/ble/BleInspector.cpp"
PASSIVE = ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp"


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise SystemExit(f"BLE Inspector contract missing {label}: {marker}")


header = HEADER.read_text(encoding="utf-8")
source = SOURCE.read_text(encoding="utf-8")
passive = PASSIVE.read_text(encoding="utf-8")

transport_match = re.search(
    r"class BleGattInspectorTransport \{(?P<body>.*?)\n\};",
    header,
    flags=re.DOTALL,
)
if transport_match is None:
    raise SystemExit("BLE Inspector transport boundary is missing")
operations = re.findall(
    r"virtual\s+(?:bool|BleGattDisconnectStatus)\s+(\w+)\s*\(",
    transport_match.group("body"),
)
expected = [
    "startConnect",
    "startServiceDiscovery",
    "requestDisconnect",
    "pollDisconnect",
]
if operations != expected:
    raise SystemExit(
        f"BLE Inspector transport surface changed: {operations!r} != {expected!r}"
    )

for marker, label in (
    ("record.payload.begin()", "raw payload storage"),
    ("record.payloadLength = source.payloadLength", "raw payload length handoff"),
    ("record.eventType = source.eventType", "event type handoff"),
):
    require(passive, marker, label)

for marker, label in (
    ("target.address == record.address", "exact passive target match"),
    ("address != target_.address", "exact connected target match"),
    ("EnumerateServicesAndCharacteristics", "enumeration-only permission"),
    ("Resource::EspRf", "separate radio lease"),
    ("CleanupPending", "truthful pending cleanup"),
    ("broker_.releaseAll(owner_)", "terminal lease release"),
    ("DisconnectFailed", "fail-closed disconnect failure"),
):
    require(source + header, marker, label)

print(
    "BLE Inspector contract passed: exact selected raw advertisements, explicit "
    "enumeration-only permission, exact peer binding and fail-closed disconnect"
)
