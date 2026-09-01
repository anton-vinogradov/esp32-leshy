#!/usr/bin/env python3
"""Static product guard for the receive-only Protocol Workbench slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolWorkbench.h"
SOURCE = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolWorkbench.cpp"
ANNOTATIONS = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolAnnotations.h"
ANNOTATIONS_SOURCE = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolAnnotations.cpp"
ANNOTATION_CONTROLLER = ROOT / \
    "firmware/leshy1/src/apps/protocol/ProtocolAnnotationController.cpp"
ANNOTATION_CODEC = ROOT / "firmware/leshy1/src/storage/ProtocolAnnotationCodec.cpp"
ANNOTATION_STORE = ROOT / "firmware/leshy1/src/storage/ProtocolAnnotationStore.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"


def main() -> int:
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    annotation_source = ANNOTATIONS.read_text(encoding="utf-8") + \
        ANNOTATIONS_SOURCE.read_text(encoding="utf-8") + \
        ANNOTATION_CONTROLLER.read_text(encoding="utf-8") + \
        ANNOTATION_CODEC.read_text(encoding="utf-8") + \
        ANNOTATION_STORE.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    combined = header + source
    failures: list[str] = []

    required = (
        "const domain::captures::InfraredRawSource& source",
        "ProtocolWorkbenchWorkspace& workspace",
        "sourceFingerprint",
        "kMaximumPulses = 512U",
        "analyzeInfraredCapture(",
        "protocolTimingBandFor(",
        "protocolNormalizedUnits(",
    )
    for marker in required:
        if marker not in combined:
            failures.append(f"missing bounded analysis marker: {marker}")

    forbidden = ("transmit", "replay", "writePulse", "digitalWrite",
                 "RadioSpi", "ResourceBroker")
    for marker in forbidden:
        if marker in combined:
            failures.append(f"receive-only analyzer contains output marker: {marker}")

    annotation_required = (
        "captureGeneration",
        "captureFingerprint",
        "kCapacity = 12U",
        "sameProtocolAnnotationSource",
        "ProtocolAnnotationStatus::SourceMismatch",
        "ProtocolAnnotationStatus::Overlap",
        "encodeProtocolAnnotations(",
        "decodeProtocolAnnotations(",
        "commitNextProtocolAnnotations(",
        "recoverProtocolAnnotations(",
        "commitGeneration(",
        "crc32c(",
        "protocol-annotations-%08lu-head-a.bin",
        "ProtocolAnnotationActivation::SaveRequested",
        "ProtocolAnnotationView::ChooseStart",
        "ProtocolAnnotationView::ChooseEnd",
        "ProtocolAnnotationView::ChooseKind",
    )
    for marker in annotation_required:
        if marker not in annotation_source:
            failures.append(f"missing immutable annotation marker: {marker}")

    for marker in forbidden:
        if marker in annotation_source:
            failures.append(
                f"derived annotation path contains output marker: {marker}")

    ui_required = (
        "selected->generation != sessionStoreWorkspace().generation",
        "openPersistedInfraredRawCapture(",
        "renderProtocolWorkbenchWaveform();",
        "ProtocolWorkbenchReadOnly",
        "kProtocolWorkbenchPage",
        "protocol_workbench_opened",
        "ProtocolWorkbenchHilSource",
        "protocolAnnotationController.activate()",
        "renderProtocolAnnotationActionRow(",
        "renderProtocolAnnotationRangeStatus(",
        "persistProtocolWorkbenchAnnotations()",
        "DeviceLockOperation::ProtectedEvidence",
        "identifyScreenshotProductMedia(",
        "ProductStoreOperation::CommitEvidence",
        "commitNextProtocolAnnotations(",
        "sameProtocolAnnotationSet(",
        "protocolAnnotationController.noteSaved(",
        "protocol.workbench.hil-fixture open-nec",
        "protocol.workbench.hil-fixture clear",
        "if (!hilSession.active())",
        "kProtocolWorkbenchPage);",
        '"\\\"radio_touched\\\":false,\\\"application_tx_calls\\\":0,"',
        '"\\\"storage_mounted\\\":false,\\\"storage_written\\\":false,"',
        "protocolWorkbenchHilSource.reset();",
    )
    for marker in ui_required:
        if marker not in entry:
            failures.append(f"missing immutable UI path marker: {marker}")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("Protocol Workbench contract passed: bounded immutable IR analysis; "
          "task-first exact-source annotations; protected atomic save; "
          "no TX/replay/output API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
