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
COMPARISON = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolComparison.h"
COMPARISON_SOURCE = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolComparison.cpp"
DERIVED_DECODE = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolDerivedDecode.h"
DERIVED_DECODE_SOURCE = ROOT / \
    "firmware/leshy1/src/apps/protocol/ProtocolDerivedDecode.cpp"
DERIVED_DECODE_CODEC = ROOT / \
    "firmware/leshy1/src/storage/ProtocolDerivedDecodeCodec.cpp"
DERIVED_DECODE_STORE = ROOT / \
    "firmware/leshy1/src/storage/ProtocolDerivedDecodeStore.cpp"
TASK_CONTROLLER = ROOT / \
    "firmware/leshy1/src/apps/protocol/ProtocolWorkbenchTaskController.cpp"
CAPTURE_SNAPSHOT = ROOT / \
    "firmware/leshy1/src/apps/protocol/ProtocolCaptureSnapshot.cpp"
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
    comparison_source = COMPARISON.read_text(encoding="utf-8") + \
        COMPARISON_SOURCE.read_text(encoding="utf-8")
    derived_decode_source = DERIVED_DECODE.read_text(encoding="utf-8") + \
        DERIVED_DECODE_SOURCE.read_text(encoding="utf-8") + \
        DERIVED_DECODE_CODEC.read_text(encoding="utf-8") + \
        DERIVED_DECODE_STORE.read_text(encoding="utf-8")
    task_source = TASK_CONTROLLER.read_text(encoding="utf-8")
    snapshot_source = CAPTURE_SNAPSHOT.read_text(encoding="utf-8")
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

    comparison_required = (
        "ProtocolComparisonOutcome::Identical",
        "ProtocolComparisonOutcome::TimingVariation",
        "ProtocolComparisonOutcome::ValueChanged",
        "ProtocolComparisonOutcome::StructureChanged",
        "kMaximumRegions = 16U",
        "compareInfraredCaptures(",
        "identityMatchesAnalysis(",
        "valueChangedPulses",
        "omittedRegions",
    )
    for marker in comparison_required:
        if marker not in comparison_source:
            failures.append(f"missing bounded comparison marker: {marker}")
    for marker in forbidden:
        if marker in comparison_source:
            failures.append(
                f"derived comparison path contains output marker: {marker}")

    derived_decode_required = (
        "kDecoderVersion = 1U",
        "ProtocolAnnotationSet::kCapacity",
        "ProtocolDerivedFieldStatus::BitsObserved",
        "ProtocolDerivedFieldStatus::Inconclusive",
        "annotationStoreGeneration",
        "deriveProtocolDecode(",
        "No byte order is invented",
        "encodeProtocolDerivedDecode(",
        "decodeProtocolDerivedDecode(",
        "commitNextProtocolDerivedDecode(",
        "recoverProtocolDerivedDecode(",
        "protocol-derived-%08lu-%08lu-head-a.bin",
        "expectedAnnotationStoreGeneration",
        "commitGeneration(",
        "crc32c(",
    )
    for marker in derived_decode_required:
        if marker not in derived_decode_source:
            failures.append(f"missing bounded derived-decode marker: {marker}")
    for marker in forbidden:
        if marker in derived_decode_source:
            failures.append(
                f"derived decode path contains output marker: {marker}")

    task_required = (
        "ProtocolWorkbenchTaskView::Tasks",
        "ProtocolWorkbenchTaskView::Waveform",
        "ProtocolWorkbenchTaskView::Explain",
        "ProtocolWorkbenchTaskView::Annotate",
        "ProtocolWorkbenchTaskView::Comparison",
        "ProtocolWorkbenchTaskView::Decode",
        "ProtocolWorkbenchTaskActivation::CompareRequested",
        "ProtocolWorkbenchTaskActivation::DecodeRequested",
    )
    for marker in task_required:
        if marker not in task_source:
            failures.append(f"missing contextual task-tree marker: {marker}")
    for marker in forbidden:
        if marker in task_source or marker in snapshot_source:
            failures.append(
                f"task/snapshot path contains output marker: {marker}")

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
        "protocolWorkbenchTaskController.activate()",
        "prepareProtocolWorkbenchComparison()",
        "prepareProtocolWorkbenchDecode()",
        "ProtocolCaptureSnapshot currentSnapshot",
        "recoverSessionPair(",
        "pair.currentGeneration == currentIdentity.captureGeneration",
        "persistProtocolWorkbenchDecode()",
        "commitNextProtocolDerivedDecode(",
        "sameProtocolDerivedDecode(",
        "const auto decodeRecovered =",
        "decodeRecovered.storeGeneration",
        'protocolDerivedDecodeStorageStatus = "recovered"',
        "protocolDerivedDecodeStoreStatusName(",
        "openExistingReadOnly(permit)",
        "openExistingWritable(permit)",
        "void emitProtocolWorkbenchState(Stream& reply)",
        '"protocol.workbench.state"',
        "task_view",
        "selected_pulse",
        "annotation_view",
        '\\\"source_kind\\\":\\\"%s\\\",',
        '\\\"raw_capture_mutated\\\":false,',
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
          "task-first exact-source annotations; bounded two-Capture comparison; "
          "truthful annotation-derived fields; "
          "protected atomic save; "
          "no TX/replay/output API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
