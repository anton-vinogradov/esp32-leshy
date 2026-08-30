#!/usr/bin/env python3
"""Fail closed if the CAP-051 foundation gains an unreviewed active surface."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/services/ble/BleInspector.h"
SOURCE = ROOT / "firmware/leshy1/src/services/ble/BleInspector.cpp"
EXPORT = ROOT / "firmware/leshy1/src/services/ble/BleInspectorExport.cpp"
PASSIVE = ROOT / "firmware/leshy1/src/platform/arduino/BoardBlePassiveScanner.cpp"
PRODUCT = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
HIL = ROOT / "tools/run_1x_ble_inspector_hil.py"


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise SystemExit(f"BLE Inspector contract missing {label}: {marker}")


header = HEADER.read_text(encoding="utf-8")
source = SOURCE.read_text(encoding="utf-8")
passive = PASSIVE.read_text(encoding="utf-8")
export = EXPORT.read_text(encoding="utf-8")
product = PRODUCT.read_text(encoding="utf-8")
hil = HIL.read_text(encoding="utf-8")

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

for marker, label in (
    ('"leshy.ble.inspector.capture.v1"', "versioned raw export schema"),
    ("BleInspectorCaptureState::Frozen", "immutable export boundary"),
    ('"\\\"complete\\\":false', "fail-closed incomplete stream header"),
    ('\\"payload_hex\\"', "exact payload export"),
):
    require(export, marker, label)

for marker, label in (
    ("BleProductView::InspectorRaw", "visible product view"),
    ("beginBleInspectorCapture(*liveBleDeviceDetail())", "selected detail entry"),
    ("bleInspectorCapture->ingest(record, monotonicUs)", "scanner capture handoff"),
    ("bleInspectorCapture->size() == BleInspectorCapture::kRecordCapacity", "zero-drop automatic freeze"),
    ("union BleProductSharedWorkspace", "mutually exclusive BLE workspace"),
    ("sizeof(BleInspectorCapture) <=", "shared workspace size bound"),
    ("activateBleInspectorWorkspace()", "explicit Inspector workspace lifetime"),
    ("releaseBleInspectorWorkspace()", "explicit Inspector workspace release"),
    ("bleInspectorWorkspaceActive()", "shared workspace ownership guard"),
    ("workspace_owned_by_ble_inspector", "Airspace state inactive-member guard"),
    ('"ble_workspace_busy"', "Airspace worker exclusion at BLE entry"),
    ('"ble.inspector.export.raw"', "local raw export action"),
    ("renderBleInspectorRawData(false)", "incremental inspector repaint"),
    ("nowUs + kBleDeviceUiRefreshPeriodUs", "bounded inspector refresh cadence"),
    ('\\"atomic_row_allocation_failures\\"', "atomic repaint failure telemetry"),
    ('\\"direct_row_fallbacks\\"', "direct repaint fallback telemetry"),
):
    require(product, marker, label)

for marker, label in (
    ("performed_before_application_flash", "pre-flash identity proof"),
    ("expected_fingerprint", "expected CID preflight"),
    ("observed_fingerprint", "observed CID preflight"),
    ("mounted_read_only", "read-only storage preflight"),
    ("wait_stable_ble_entry(device)", "bounded Bluetooth entry stability"),
    ("cardputer_touched\": False", "Cardputer isolation evidence"),
):
    require(hil, marker, label)

print(
    "BLE Inspector contract passed: exact selected raw capture/export, incremental "
    "product UI, explicit enumeration-only permission, exact peer binding and "
    "fail-closed disconnect"
)
