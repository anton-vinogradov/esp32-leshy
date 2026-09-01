#!/usr/bin/env python3
"""Fail closed when product screens regress to developer-facing telemetry."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"


REQUIRED_OUTCOME_IDS = {
    "NoteWifiReady",
    "NoteBleReady",
    "NoteSpectrum24",
    "NoteSubGhz",
    "NoteCaptureReady",
    "NoteLibraryReady",
    "CaptureWifiPurpose",
    "CapturePacketsFormat",
    "IrAimDevice",
    "IrSignalDetected",
    "SubGhzPressButton",
    "SubGhzSignalRecorded",
    "SurveyFoundFormat",
    "SurveySearchWifi",
    "SurveySearchBle",
    "LibraryWifiScan",
    "LibraryBleScan",
    "LibraryWifiCapture",
    "LibrarySubGhzCapture",
    "LibraryInfraredCapture",
    "AutomationLibraryNoMediaHint",
    "AutomationLibraryEmptyHint",
    "AutomationLibraryFolderMissingHint",
    "AutomationLibraryReadOnly",
    "TargetsNoSessions",
    "TargetsNoSessionsHint",
    "TargetsLoadFailedHint",
}

# These remain valid in diagnostics/USB evidence, but they must not be rendered
# on product screens. Their catalog entries are retained for historical evidence
# compatibility until a later catalog compaction.
FORBIDDEN_RENDER_IDS = {
    "CaptureSource",
    "CaptureChannels",
    "CaptureLimit",
    "CaptureSnaplen",
    "CaptureBytesFormat",
    "CaptureDropsFormat",
    "CaptureScrubNote",
    "IrReceiver",
    "IrTimeout",
    "IrMode",
    "IrSafety",
    "IrPulsesFormat",
    "IrSamplingFormat",
    "IrCaptureNote",
    "IrNoSignalNote",
    "IrUnreliableNote",
    "SubGhzRawThresholdFormat",
    "SubGhzRawPulsesFormat",
    "SubGhzRawSamplesFormat",
    "SubGhzRawFskLater",
    "FifoNoRf",
    "FifoRxOnly",
    "FifoFormat",
    "PipelineFormat",
    "GenerationFormat",
    "FrequencyFormat",
    "LibraryRowFormat",
    "LibraryCaptureRowFormat",
    "LibraryRawRowFormat",
    "IntegrityFormat",
    "TimelineStoredFormat",
    "TimelineDutyFormat",
    "TransportSerial",
    "CaptureImmutable",
    "BleDeviceSeenFormat",
    "WifiNetworkSamplesFormat",
    "WifiDeviceFramesFormat",
}

REQUIRED_DENSE_DETAIL_IDS = {
    "RadioSignalLabel",
    "RadioSignalExcellent",
    "RadioSignalGood",
    "RadioSignalWeak",
    "RadioSignalVeryWeak",
    "RadioSignalDbmFormat",
    "RadioSignalScaleWeak",
    "RadioSignalScaleStrong",
    "WifiNetworkRadioFormat",
    "WifiNetworkSecurityFormat",
    "WifiNetworkVendorFormat",
}

# These strings are decisions or explanations on the normal user path. They
# must name the user's task or outcome, never the implementation that happens
# to provide it. Technical terminology remains valid in optional detail and
# export-format strings outside this set.
PRIMARY_TASK_IDS = {
    "AutomationInspectorTitle",
    "AutomationTrustDeviceItem",
    "AutomationTrustDeviceNote",
    "DeviceSerialConsole",
    "DeviceSerialConsoleReady",
    "DeviceSerialConsoleConflict",
    "CaptureWifiSource",
    "CaptureWifiSourceNote",
    "BleInspectorModesTitle",
    "BleInspectorRawMode",
    "BleInspectorRawModeNote",
    "BleInspectorGattMode",
    "BleInspectorGattModeNote",
    "BleInspectorReceiving",
    "BleInspectorFrozen",
    "BleInspectorCountFormat",
    "BleGattTitle",
    "BleGattPermissionScope",
    "BleGattPermissionNoData",
    "BleGattDiscovering",
    "BleGattReady",
    "BleGattFailed",
    "BleGattCountFormat",
    "BleGattActiveSafety",
    "SpectrumNrf24",
    "SpectrumCc1101",
    "Nrf24Modes",
    "Nrf24Overview",
    "Nrf24Finder",
    "SpectrumRunning",
    "SpectrumPaused",
    "SpectrumFault",
    "CcSpectrumBands",
    "CcSpectrumBandChoiceFormat",
    "CcSpectrumRunning",
    "CcSpectrumPaused",
    "SubGhzModes",
    "SubGhzSpectrum",
    "SubGhzRaw",
    "CcFinder",
    "SubGhzRawTypes",
    "SubGhzRawOok",
    "SubGhzRawFsk",
    "LibraryActionAnalyze",
    "LibraryActionAnalyzeNote",
    "LibraryActionExport",
    "LibraryActionExportNote",
    "LibraryActionsTitle",
    "ProtocolWorkbenchTitle",
    "WifiPasswordCheckTitle",
    "WifiPasswordCheckTask",
    "WifiPasswordCheckListen",
    "WifiPasswordCheckComputer",
    "WifiPasswordCheckNoPassword",
    "WifiPasswordCheckPermission",
    "WifiAuthFullHandshakeHeadline",
    "WifiAuthPartialHandshakeHeadline",
    "WifiAuthPmkidHeadline",
    "WifiAuthInconclusiveHeadline",
    "WifiAuthDataHeadline",
    "WifiAuthSavedStandardNote",
    "WifiAuthSavedPcapNote",
    "WifiAuthActionRepeat",
}

PRIMARY_JARGON = re.compile(
    r"\b(?:PMKID|EAPOL|ESB|EXTCAP|GATT|PCAP|HC22000|NRF24|CC1101|GPIO|UART|RAW)\b",
    re.IGNORECASE,
)


def parse_ui_strings(source: str) -> dict[str, tuple[str, str]]:
    pattern = re.compile(
        r'LESHY_UI_TEXT\(\s*([A-Za-z0-9_]+)\s*,\s*[^,]+\s*,\s*\d+\s*,'
        r'\s*"((?:[^"\\]|\\.)*)"\s*,\s*u8"((?:[^"\\]|\\.)*)"\s*\)'
    )
    return {match.group(1): (match.group(2), match.group(3))
            for match in pattern.finditer(source)}


def main() -> int:
    renderer = RENDERER.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    catalog = parse_ui_strings(strings)
    failures: list[str] = []

    for identifier in sorted(PRIMARY_TASK_IDS):
        localized = catalog.get(identifier)
        if localized is None:
            failures.append(f"missing primary task string: {identifier}")
            continue
        for language, value in zip(("en", "ru"), localized):
            jargon = PRIMARY_JARGON.search(value)
            if jargon is not None:
                failures.append(
                    f"primary task string {identifier}/{language} exposes "
                    f"implementation jargon: {jargon.group(0)}"
                )

    if "WifiProductView::PasswordCheckIntro" not in renderer:
        failures.append(
            "network detail must route through a password-check explanation"
        )
    network_detail_branch = re.search(
        r"wifiProductView == WifiProductView::NetworkDetail\).*?"
        r"wifiProductView == WifiProductView::PasswordCheckIntro",
        renderer,
        re.DOTALL,
    )
    if network_detail_branch is None:
        failures.append(
            "network detail does not expose the contextual password-check task"
        )
    elif "requestWifiAuthenticationCaptureFromDetail" in \
            network_detail_branch.group(0):
        failures.append(
            "network detail starts password evidence recording before its intro"
        )

    ble_detail_branch = re.search(
        r"} else if \(bleProductView == BleProductView::DeviceDetail\) \{.*?"
        r"} else if \(bleProductView == BleProductView::Devices\)",
        renderer,
        re.DOTALL,
    )
    if ble_detail_branch is None or \
            "bleProductView = BleProductView::InspectorMenu" not in \
            ble_detail_branch.group(0):
        failures.append(
            "Bluetooth detail must open contextual actions before a task"
        )
    elif "requestBleGattFromDetail" in ble_detail_branch.group(0):
        failures.append(
            "Bluetooth detail starts an active connection before task choice"
        )

    ble_actions_branch = re.search(
        r"} else if \(bleProductView == BleProductView::InspectorMenu\) \{.*?"
        r"} else if \(bleProductView == BleProductView::InspectorRaw\)",
        renderer,
        re.DOTALL,
    )
    if ble_actions_branch is None or \
            "bleProductView = BleProductView::DeviceDetail" not in \
            ble_actions_branch.group(0):
        failures.append(
            "Bluetooth contextual actions must return to the selected device"
        )

    for required in (
        "UiTextId::NavActions", "RfSpectrumView::Nrf24Menu",
        "RfSpectrumView::SubGhzMenu",
        "RfSpectrumView::SubGhzCaptureModeMenu",
    ):
        if required not in renderer:
            failures.append(f"missing contextual task-tree route: {required}")

    library_actions_call = renderer.find("libraryController.openActions()")
    library_detail_branch = renderer[
        max(0, library_actions_call - 420):library_actions_call + 80
    ] if library_actions_call >= 0 else ""
    if "LibraryView::SessionDetail" not in library_detail_branch:
        failures.append(
            "Library detail must open contextual actions before execution"
        )
    elif "requestExport" in library_detail_branch or \
            "openSelectedProtocolWorkbench" in library_detail_branch:
        failures.append(
            "Library detail executes a task before the contextual action node"
        )

    for identifier in sorted(REQUIRED_OUTCOME_IDS):
        if f"LESHY_UI_TEXT({identifier}," not in strings:
            failures.append(f"missing outcome-oriented string: {identifier}")
        if f"UiTextId::{identifier}" not in renderer:
            failures.append(f"outcome-oriented string is not rendered: {identifier}")

    for identifier in sorted(FORBIDDEN_RENDER_IDS):
        if re.search(rf"UiTextId::{re.escape(identifier)}\b", renderer):
            failures.append(f"developer-facing field rendered: {identifier}")

    for identifier in sorted(REQUIRED_DENSE_DETAIL_IDS):
        if f"LESHY_UI_TEXT({identifier}," not in strings:
            failures.append(f"missing dense detail string: {identifier}")
        if f"UiTextId::{identifier}" not in renderer:
            failures.append(f"dense detail string is not rendered: {identifier}")

    if renderer.count("void renderRadioSignalCard(") != 1 or \
            renderer.count("renderRadioSignalCard(") < 3 or \
            renderer.count("void renderRadioSignalCardDelta(") != 1 or \
            renderer.count("renderRadioSignalCardDelta(") < 2:
        failures.append(
            "radio details must share one full signal card and one bounded "
            "delta renderer"
        )

    for internal in (
        "capturePersistStatus",
        "infraredCapturePersistStatus",
        "subGhzCapturePersistStatus",
    ):
        display_path = re.search(
            rf"display\.print\([^;]*{re.escape(internal)}[^;]*\);", renderer,
            re.DOTALL,
        )
        if display_path:
            failures.append(f"internal persistence status rendered: {internal}")

    if "UiTextId::AutomationLibraryPath" in renderer:
        failures.append(
            "internal automation storage path rendered on the product screen"
        )

    automation_empty_state = re.search(
        r"BoardAutomationPackageStatus::DirectoryUnavailable.*?"
        r"UiTextId::AutomationLibraryEmpty.*?"
        r"UiTextId::AutomationLibraryFolderMissingHint.*?return;.*?"
        r"automationCatalogStatus != BoardAutomationPackageStatus::Ready.*?"
        r"UiTextId::AutomationLibraryNoMedia",
        renderer,
        re.DOTALL,
    )
    if automation_empty_state is None:
        failures.append(
            "Automation must distinguish a missing optional folder from an "
            "unavailable SD card"
        )

    targets_empty_state = re.search(
        r"targetsProductRuntime == nullptr.*?"
        r"targetsProductStatus, \"session_unavailable\".*?"
        r"UiTextId::TargetsNoSessions.*?UiTextId::TargetsNoSessionsHint"
        r".*?controller\.status\(\) == TargetsLoadStatus::SessionUnavailable"
        r".*?UiTextId::TargetsNoSessions.*?UiTextId::TargetsNoSessionsHint"
        r".*?controller\.status\(\) != TargetsLoadStatus::Ready"
        r".*?UiTextId::TargetsLoadFailed.*?UiTextId::TargetsLoadFailedHint",
        renderer,
        re.DOTALL,
    )
    if targets_empty_state is None:
        failures.append(
            "Targets must distinguish the no-session next step from a real "
            "storage/read failure"
        )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(
        "product UI content contract passed: outcomes/actions visible; "
        "primary tasks require no implementation jargon; developer telemetry "
        "stays off product screens; radio details use the shared user-facing "
        "signal card"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
