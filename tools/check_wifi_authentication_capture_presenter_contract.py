#!/usr/bin/env python3
"""Fail closed if the CAP-049 presenter gains side effects or full redraws."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from check_ui_language_contract import parse_catalog, parse_glyphs, pixel_width


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.h"
SOURCE = ROOT / "firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.cpp"
TEST = ROOT / "tests/native/wifi_authentication_capture_presenter_tests.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
FONT = ROOT / "firmware/leshy1/src/ui/fonts/RobotoCondensedGfx.h"
ARDUINO = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
TEST_SH = ROOT / "tools/test.sh"

UINT32_MAX = 4_294_967_295
CAP049_ROW_WIDTH = 214
CAP049_TWO_UINT32_FORMAT_IDS = (
    "WifiAuthKeptLostFormat",
    "WifiAuthChannelCandidatesFormat",
    "WifiAuthPeersFormat",
    "WifiAuthPmkidEapolFormat",
    "WifiAuthEvidenceFormat",
    "WifiAuthLossFormat",
    "WifiAuthPeerPositionFormat",
)
CAP049_ONE_UINT32_FORMAT_IDS = (
    "WifiAuthTimeRemainingFormat",
    "WifiAuthPeerEvidenceFormat",
)
CAP049_RENDERER_FORMAT_IDS = ("WifiAuthSelectedTargetFormat",)


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        tests = TEST.read_text(encoding="utf-8")
        strings = STRINGS.read_text(encoding="utf-8")
        font = FONT.read_text(encoding="utf-8")
        arduino = ARDUINO.read_text(encoding="utf-8")
        test_sh = TEST_SH.read_text(encoding="utf-8")
    except OSError as error:
        print(f"CAP-049 presenter contract check failed: {error}",
              file=sys.stderr)
        return 1

    combined = header + source
    for marker in (
        "WifiAuthenticationCaptureUiView::Preparing",
        "WifiAuthenticationCaptureUiView::Cancelling",
        "WifiAuthenticationCaptureUiView::Running",
        "WifiAuthenticationCaptureUiView::Result",
        "WifiAuthenticationCaptureUiView::Inconclusive",
        "WifiAuthenticationCaptureUiView::Actions",
        "WifiAuthenticationCaptureUiView::PeerDetail",
        "WifiAuthenticationCaptureUiView::EvidenceList",
        "WifiAuthenticationCaptureUiView::EvidenceDetail",
        "WifiAuthenticationCaptureUiView::Failed",
        "CompleteAndPartialPeers",
        "PmkidsAndEapolFrames",
        "SelectedPeerMask",
        "TerminalAnalysisPending",
        "LossAndRejectedFrames",
        "ResultBeforeCleanup",
        "ReportRejected",
        "diffWifiAuthenticationCaptureUi",
        "fullScreenClear = false",
        "kVisibleRowCapacity = 4",
        "std::is_trivially_copyable_v",
        "row.text = metricText(metric, primary)",
        "model.reportOpenable = controller.reportOpenable()",
        "WifiAuthenticationCaptureExportEligibility::NotEvaluated",
    ):
        require(failures, marker in combined,
                f"missing CAP-049 presentation contract: {marker}")

    for marker in (
        "testPreparingAndCancellingAreHonest",
        "testRunningUsesHonestCandidateMetrics",
        "testRunningTimerRepaintsOnlyOneRowWithoutClearing",
        "testHeadlinePriorityAndIndependentCounts",
        "testInconclusiveShowsExactReason",
        "testResultActionsPeerAndEvidenceDrilldown",
        "testPeerToneChangeRepaintsColoredRegionsWithoutClearing",
        "testFailClosedInputs",
    ):
        require(failures, marker in tests,
                f"missing CAP-049 presenter native coverage: {marker}")

    for marker in (
        "WifiAuthPreparingTitle",
        "WifiAuthPreparingHeadline",
        "WifiAuthPreparingNote",
        "WifiAuthCancellingTitle",
        "WifiAuthCancellingHeadline",
        "WifiAuthCancellingNote",
        "WifiAuthTimeRemainingFormat",
        "WifiAuthChannelCandidatesFormat",
        "WifiAuthKeptLostFormat",
        "WifiAuthPeersFormat",
        "WifiAuthExactAfterStop",
        "WifiAuthPmkidEapolFormat",
        "WifiAuthPeerMaskFormat",
        "WifiAuthEvidenceFormat",
        "WifiAuthLossFormat",
        "WifiAuthReasonInvalid",
        "WifiAuthReasonInterrupted",
        "WifiAuthReasonLoss",
        "WifiAuthReasonSource",
        "WifiAuthReasonMalformed",
        "WifiAuthReasonLimit",
        "WifiAuthReasonNoData",
        "WifiAuthReasonUnsupported",
        "WifiAuthFailureInvalid",
        "WifiAuthFailureStart",
        "WifiAuthFailureRuntime",
        "WifiAuthFailureCleanup",
        "WifiAuthFailureReport",
        "WifiAuthFullHandshakeHeadline",
        "WifiAuthPartialHandshakeHeadline",
        "WifiAuthPmkidHeadline",
        "WifiAuthInconclusiveHeadline",
        "WifiAuthVolatileNote",
        "WifiAuthActionsHeadline",
        "WifiAuthActionDetails",
        "WifiAuthActionRepeat",
        "WifiAuthPeerTitle",
        "WifiAuthPeerHeadline",
        "WifiAuthPeerPositionFormat",
        "WifiAuthPeerEvidenceFormat",
        "WifiAuthEvidenceTitle",
        "WifiAuthEvidenceHeadline",
        "WifiAuthEvidenceListRowFormat",
        "WifiAuthEvidenceDetailTitle",
        "WifiAuthEvidenceDetailHeadline",
        "WifiAuthEvidenceFrameFormat",
        "WifiAuthEvidenceSignalFormat",
        "WifiAuthEvidenceReplayFormat",
        "WifiAuthEvidenceDescriptorFormat",
    ):
        require(failures, f"LESHY_UI_TEXT({marker}," in strings,
                f"missing CAP-049 localized UI string: {marker}")
        require(failures, f"UiTextId::{marker}" in combined,
                f"presenter does not register localized row text: {marker}")

    for marker in (
        "tests/native/wifi_authentication_capture_presenter_tests.cpp",
        "firmware/leshy1/src/ui/WifiAuthenticationCapturePresenter.cpp",
        "tools/check_wifi_authentication_capture_presenter_contract.py",
    ):
        require(failures, marker in test_sh,
                f"host suite does not register CAP-049 presenter: {marker}")

    for forbidden in (
        '#include "drivers/',
        '#include "platform/',
        '#include "kernel/',
        "ResourceBroker",
        "ArduinoEntry",
        "esp_wifi",
        "sendPacket",
        "injectFrame",
        "std::vector",
        "std::string",
        "unordered_",
        "new ",
        "delete ",
        "malloc(",
        "calloc(",
        "realloc(",
        "snprintf(",
        "fillScreen(",
        "clearScreen(",
    ):
        require(failures, forbidden not in combined,
                f"CAP-049 presenter crossed its pure-model boundary: {forbidden}")

    require(failures, "u8\"" not in combined,
            "CAP-049 presenter must use the shared localization catalog")
    try:
        meta = parse_glyphs(font, "RobotoCondensedMeta")
        catalog = {entry[0]: entry for entry in parse_catalog()}
    except ValueError as error:
        failures.append(f"cannot measure CAP-049 rendered rows: {error}")
        meta = []
        catalog = {}
    for identifier in CAP049_TWO_UINT32_FORMAT_IDS:
        entry = catalog.get(identifier)
        require(failures, entry is not None,
                f"missing CAP-049 format width contract: {identifier}")
        if entry is None or not meta:
            continue
        _, role, _, english, russian = entry
        require(failures, role == "Meta",
                f"{identifier}: numeric row must use Roboto Condensed Meta12")
        for language, template in (("en", english), ("ru", russian)):
            require(
                failures, template.count("%lu") == 2,
                f"{identifier}/{language}: expected exactly two uint32 fields")
            if template.count("%lu") != 2:
                continue
            try:
                rendered = template % (UINT32_MAX, UINT32_MAX)
                width = pixel_width(rendered, meta)
            except (TypeError, ValueError) as error:
                failures.append(
                    f"{identifier}/{language}: cannot render UINT32_MAX: {error}")
                continue
            require(
                failures, width <= CAP049_ROW_WIDTH,
                f"{identifier}/{language}: UINT32_MAX row is {width}px, "
                f"exceeds {CAP049_ROW_WIDTH}px")
    for identifier in CAP049_ONE_UINT32_FORMAT_IDS:
        entry = catalog.get(identifier)
        require(failures, entry is not None,
                f"missing CAP-049 format width contract: {identifier}")
        if entry is None or not meta:
            continue
        _, role, _, english, russian = entry
        require(failures, role == "Meta",
                f"{identifier}: numeric row must use Roboto Condensed Meta12")
        for language, template in (("en", english), ("ru", russian)):
            require(failures, template.count("%lu") == 1,
                    f"{identifier}/{language}: expected one uint32 field")
            if template.count("%lu") != 1:
                continue
            try:
                width = pixel_width(template % UINT32_MAX, meta)
            except (TypeError, ValueError) as error:
                failures.append(
                    f"{identifier}/{language}: cannot render UINT32_MAX: {error}")
                continue
            require(failures, width <= CAP049_ROW_WIDTH,
                    f"{identifier}/{language}: UINT32_MAX row is {width}px, "
                    f"exceeds {CAP049_ROW_WIDTH}px")
    for identifier in CAP049_RENDERER_FORMAT_IDS:
        entry = catalog.get(identifier)
        require(failures, entry is not None,
                f"missing CAP-049 renderer format width contract: {identifier}")
        if entry is None or not meta:
            continue
        _, role, _, english, russian = entry
        require(failures, role == "Meta",
                f"{identifier}: target row must use Roboto Condensed Meta12")
        for language, template in (("en", english), ("ru", russian)):
            require(failures, template.count("%u") == 1,
                    f"{identifier}/{language}: expected one channel field")
            if template.count("%u") != 1:
                continue
            try:
                width = pixel_width(template % 13, meta)
            except (TypeError, ValueError) as error:
                failures.append(
                    f"{identifier}/{language}: cannot render channel: {error}")
                continue
            require(failures, width <= CAP049_ROW_WIDTH,
                    f"{identifier}/{language}: target row is {width}px, "
                    f"exceeds {CAP049_ROW_WIDTH}px")

    capture_start = arduino.find("void renderWifiAuthenticationCapture(")
    capture_end = arduino.find("void renderInventoryPage(", capture_start)
    require(failures, capture_start >= 0 and capture_end > capture_start,
            "Arduino CAP-049 render function is missing")
    capture_renderer = (
        arduino[capture_start:capture_end]
        if capture_start >= 0 and capture_end > capture_start else ""
    )
    target_start = arduino.find("void renderWifiAuthenticationTarget(")
    target_end = arduino.find(
        "void renderWifiAuthenticationFixedRow(", target_start)
    target_renderer = (
        arduino[target_start:target_end]
        if target_start >= 0 and target_end > target_start else ""
    )
    require(
        failures,
        "LESHY_UI_TEXT(WifiAuthSelectedTargetFormat," in strings and
        "UiTextId::WifiAuthSelectedTargetFormat" in target_renderer,
        "Arduino CAP-049 generic target text is not localized",
    )
    require(
        failures,
        "kWifiAuthenticationTitleRegion" in capture_renderer and
        "renderWifiAuthenticationHeaderRegions(model)" in capture_renderer and
        "renderWifiAuthenticationTarget()" in capture_renderer,
        "Arduino CAP-049 renderer ignores lifecycle title or generic target",
    )
    require(
        failures,
        "formatWifiAuthenticationHeaderTarget" not in arduino and
        "target_bssid" not in arduino[capture_start:] and
        "%02X:%02X:%02X:%02X:%02X:%02X" not in capture_renderer,
        "Arduino CAP-049 renderer/diagnostic exposes a private target",
    )
    role_expression = re.compile(
        r"(?:leshy1::ui::)?uiTextSpec\(\s*"
        r"(?:model\.rows\[index\]|row)\.text\s*\)\.role")
    role_assignment = re.search(
        r"(?:const\s+)?(?:auto|UiTextRole)\s+(\w+)\s*=\s*"
        + role_expression.pattern,
        capture_renderer,
    )
    row_calls = re.findall(
        r"renderWifiAuthenticationFixedRow\(\s*displayRow\s*,\s*line\s*,"
        r"(.*?)\);",
        capture_renderer,
        re.DOTALL,
    )
    role_reaches_row = any(role_expression.search(call) for call in row_calls)
    if role_assignment is not None:
        role_name = role_assignment.group(1)
        role_reaches_row = role_reaches_row or any(
            re.search(rf"\b{re.escape(role_name)}\b", call)
            for call in row_calls
        )
    require(
        failures, role_reaches_row,
        "Arduino CAP-049 rows must pass uiTextSpec(row.text).role to their renderer")
    require(
        failures,
        re.search(r"renderMetric\(\s*displayRow\s*,\s*line\b",
                  capture_renderer) is None,
        "Arduino CAP-049 rows must not use the common Body metric renderer")
    row_renderer_start = arduino.find(
        "void renderWifiAuthenticationFixedRow(")
    row_renderer_end = arduino.find(
        "void renderWifiAuthenticationCapture(", row_renderer_start)
    row_renderer = (
        arduino[row_renderer_start:row_renderer_end]
        if row_renderer_start >= 0 and row_renderer_end > row_renderer_start
        else ""
    )
    require(
        failures,
        "UiTextRole role" in row_renderer and
        re.search(r"setUiCursor\(\s*\w*[Rr]ole\b", row_renderer) is not None,
        "Arduino CAP-049 row renderer must apply the supplied UI text role")

    if failures:
        print("CAP-049 presenter contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("CAP-049 presenter contract check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
