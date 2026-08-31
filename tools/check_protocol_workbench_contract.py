#!/usr/bin/env python3
"""Static product guard for the receive-only Protocol Workbench slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolWorkbench.h"
SOURCE = ROOT / "firmware/leshy1/src/apps/protocol/ProtocolWorkbench.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"


def main() -> int:
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
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

    ui_required = (
        "selected->generation != sessionStoreWorkspace().generation",
        "openPersistedInfraredRawCapture(",
        "renderProtocolWorkbenchWaveform();",
        "ProtocolWorkbenchReadOnly",
        "kProtocolWorkbenchPage",
        "protocol_workbench_opened",
    )
    for marker in ui_required:
        if marker not in entry:
            failures.append(f"missing immutable UI path marker: {marker}")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("Protocol Workbench contract passed: bounded immutable IR analysis; "
          "no TX/replay/output API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
