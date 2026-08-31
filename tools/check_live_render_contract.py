#!/usr/bin/env python3
"""Fail closed if live spectrum/waterfall rendering can blank static UI."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise ValueError(f"missing function: {signature}")
    closing = source.find(") {", start)
    opening = closing + 2 if closing >= 0 else -1
    if opening < 0:
        raise ValueError(f"missing function body: {signature}")
    depth = 0
    for offset in range(opening, len(source)):
        token = source[offset]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:offset]
    raise ValueError(f"unterminated function body: {signature}")


def main() -> int:
    source = ENTRY.read_text(encoding="utf-8")
    failures: list[str] = []

    try:
        latest = function_body(source, "void renderLatestWaterfallRow()")
        bars = function_body(source, "void renderSpectrumBars(bool force")
        active = function_body(source, "void renderActiveSpectrumData()")
        nrf_service = function_body(source, "void serviceNrf24Spectrum()")
        cc_service = function_body(source, "void serviceCc1101Spectrum()")
        subghz_capture_service = function_body(
            source, "void serviceSubGhzRawCapture()")
        nrf_start = function_body(source, "bool startNrf24Receiver(bool finder)")
        cc_start = function_body(source, "bool startCc1101Spectrum(")
        signal_card = function_body(source, "void renderRadioSignalCard(")
        wifi_radar = function_body(source, "void renderWifiNetworkRadar(")
        ble_radar = function_body(source, "void renderBleDeviceRadar(")
        ble_list_row = function_body(source, "bool renderBleDeviceRow(")
        ble_refresh_service = function_body(
            source, "void serviceBleDeviceUiRefresh()")
        wifi_device = function_body(
            source, "void renderWifiDeviceDetailLiveData(bool force)")
        selection_delta = function_body(
            source, "UiDeltaRenderResult renderSelectionDelta()")
        interactive = function_body(
            source, "void renderInteractiveScreen(bool clearContent) {")
        header = function_body(source, "void renderHeader(const char* title")
        protocol_selection = function_body(
            source, "void renderProtocolWorkbenchSelection()")
        protocol_page = function_body(
            source, "void renderProtocolWorkbenchPage(bool clearContent)")
    except ValueError as error:
        failures.append(str(error))
    else:
        if "renderWaterfallSlot(spectrumViewport.latestRow());" not in latest:
            failures.append("latest waterfall update does not draw its one data row")
        if any(token in latest for token in ("fillRect(", "drawFastHLine(")):
            failures.append("latest waterfall update repaints outside its data row")
        if "renderWaterfallCursor" in source:
            failures.append("moving waterfall cursor reintroduced")

        full_guard = bars.find("if (fullRender) {")
        full_fill = bars.find(
            "display.fillRect(0, kSpectrumGraphY, Layout::ScreenWidth")
        column_loop = bars.find(
            "for (std::int16_t x = 0; x < Layout::ScreenWidth; ++x)")
        if not (0 <= full_guard < full_fill < column_loop):
            failures.append("spectrum background clear is not full-render-only")
        for token in (
            "spectrumRenderedIntensity[column]",
            "if (previous == intensity) continue;",
            "previousHeight - height",
        ):
            if token not in bars:
                failures.append(f"incremental spectrum marker missing: {token}")
        if "renderSpectrumBars(true);" not in active:
            failures.append("full spectrum page does not initialize its graph")
        for label, body in (("nRF24", nrf_service), ("CC1101", cc_service)):
            if "renderSpectrumBars();" not in body:
                failures.append(f"{label} live service is not column-incremental")
            if "renderSpectrumBars(true);" in body:
                failures.append(f"{label} live service forces a graph blank/redraw")
        if "finalState == SubGhzRawCaptureState::Waiting" in \
                subghz_capture_service:
            failures.append(
                "unchanged Sub-GHz waiting screen is still repainted on cadence")
        if "if (terminal)" not in subghz_capture_service or \
                "renderInteractiveScreen(true);" not in subghz_capture_service:
            failures.append(
                "Sub-GHz capture must repaint exactly at its terminal transition")
        reset = "spectrumRenderedIntensity.fill(kSpectrumRenderedIntensityInvalid);"
        if reset not in nrf_start:
            failures.append("nRF24 spectrum render cache is not reset at start")
        if reset not in cc_start:
            failures.append("CC1101 spectrum render cache is not reset at start")
        for label, body in (
            ("shared signal card", signal_card),
            ("Wi-Fi network radar", wifi_radar),
            ("BLE device radar", ble_radar),
            ("Wi-Fi device detail", wifi_device),
        ):
            if "if (force" not in body:
                failures.append(f"{label} has no static/dynamic render boundary")
        for marker in (
            "renderBleDeviceRadar(live, signal, false);",
            "renderWifiNetworkRadar(live, signal, false);",
            "renderWifiDeviceDetailLiveData(false);",
        ):
            if marker not in selection_delta:
                failures.append(f"live text/radar delta marker missing: {marker}")
        for marker in (
            "UiDeltaRenderResult::RequiresFull",
            "UiDeltaRenderResult::NoChange",
            "UiDeltaRenderResult::Rendered",
        ):
            if marker not in selection_delta:
                failures.append(f"tri-state repaint result missing: {marker}")
        for marker in (
            "deltaResult = renderSelectionDelta();",
            "deltaResult != UiDeltaRenderResult::RequiresFull",
            "++uiNoChangeRepaintsSuppressed;",
        ):
            if marker not in interactive:
                failures.append(
                    f"generic no-change suppression missing: {marker}")
        if "&& renderSelectionDelta()" in interactive:
            failures.append(
                "boolean delta fallback can still turn a no-op into a full repaint")
        if "void renderInteractiveScreen(bool clearContent =" in source:
            failures.append(
                "full-scene repaint still has a dangerous default argument")
        if re.search(r"\brenderInteractiveScreen\(\s*\);", source):
            failures.append(
                "render caller did not explicitly choose full or dirty-only scope")
        for marker in (
            "staticFieldsEqual(visual)",
            "renderBleDeviceRowNote(visual, bounds, background);",
            "++bleDeviceListSignalDeltaRepaints;",
        ):
            if marker not in ble_list_row:
                failures.append(
                    f"BLE list signal-only dirty repaint missing: {marker}")
        if "fillRoundRect" in ble_list_row[
                ble_list_row.find("if (canRenderSignalDelta)"):
                ble_list_row.find("++bleDeviceListRowFullRepaints")]:
            failures.append(
                "BLE signal delta still erases the complete menu row")
        for marker in (
            "bleDeviceListUiRefreshPending = true;",
            "++bleDeviceListRefreshesDeferred;",
            "nowUs < nextBleDeviceListUiRefreshUs",
            "navigationChanged || stateChanged",
        ):
            if marker not in selection_delta:
                failures.append(
                    f"BLE list scanner-rate coalescing missing: {marker}")
        for marker in (
            "bleDeviceListUiRefreshPending",
            "bleDeviceUiRefreshPending",
            "renderInteractiveScreen(false);",
        ):
            if marker not in ble_refresh_service:
                failures.append(
                    f"BLE deadline refresh service missing: {marker}")
        if "renderInteractiveScreen(true);" in ble_refresh_service:
            failures.append(
                "BLE deadline refresh service can force a full-scene repaint")
        worker_then_visual = re.search(
            r"serviceProductSurveyWorker\(\);\s*"
            r"serviceBleDeviceUiRefresh\(\);", source)
        if worker_then_visual is None:
            failures.append(
                "BLE pending visual refresh is not serviced after scanner work")
        if "renderProtocolWorkbenchSelection();" not in selection_delta:
            failures.append(
                "Protocol Workbench selection is not dirty-region rendered")
        if "renderProtocolWorkbenchWaveform();" in protocol_selection:
            failures.append(
                "Protocol Workbench pulse movement redraws the waveform")
        for marker in (
            "kProtocolWorkbenchCursorY",
            "pushLiveMetaTextRow(",
        ):
            if marker not in protocol_selection:
                failures.append(
                    f"Protocol Workbench dirty marker missing: {marker}")
        if "renderProtocolWorkbenchWaveform();" not in protocol_page:
            failures.append(
                "Protocol Workbench full scene does not draw its waveform")
        header_guard = header.find("if (!clearContent) return;")
        header_clear = header.find("display.fillRect(header.x")
        if not (0 <= header_guard < header_clear):
            failures.append(
                "in-place render can still clear and repaint static header chrome")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("PASS live renderer: static chrome/text retained; no-change ticks "
          "are suppressed; scanner-rate BLE changes are coalesced with a "
          "deadline flush; signal fields, spectrum columns, one waterfall "
          "row and Protocol Workbench cursor update incrementally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
