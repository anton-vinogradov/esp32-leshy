#!/usr/bin/env python3
"""Fail closed if live spectrum/waterfall rendering can blank static UI."""

from __future__ import annotations

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
        nrf_start = function_body(source, "bool startNrf24Receiver(bool finder)")
        cc_start = function_body(source, "bool startCc1101Spectrum(")
        signal_card = function_body(source, "void renderRadioSignalCard(")
        wifi_radar = function_body(source, "void renderWifiNetworkRadar(")
        ble_radar = function_body(source, "void renderBleDeviceRadar(")
        wifi_device = function_body(
            source, "void renderWifiDeviceDetailLiveData(bool force)")
        selection_delta = function_body(source, "bool renderSelectionDelta()")
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

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print("PASS live renderer: static chrome/text retained; signal fields, "
          "spectrum columns and one waterfall row update incrementally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
