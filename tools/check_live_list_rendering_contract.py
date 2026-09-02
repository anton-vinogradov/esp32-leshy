#!/usr/bin/env python3
"""Fail closed if a live discovery list regresses to page clearing."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"


def body(source: str, start: str, end: str) -> str:
    begin = source.find(start)
    finish = source.find(end, begin + len(start))
    if begin < 0 or finish < 0:
        raise ValueError(f"missing source boundary: {start!r} .. {end!r}")
    return source[begin:finish]


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    failures: list[str] = []
    required = (
        '#include "ui/LiveListRenderCache.h"',
        "TFT_eSprite liveListRowSprite(&display);",
        "liveListRowSprite.setColorDepth(4);",
        "releaseLiveListRowSprite();",
        "pushLiveListTextBand(",
        "pushLiveListRow(bounds",
        "pushLiveListDynamicFields(",
        "drawLiveListSelectionOverlay(bool selected)",
        "drawLiveListSelectionOverlay(const Rect& bounds, bool selected)",
        "wifiNetworkListRenderCache.classify",
        "wifiDeviceListRenderCache.classify",
        "bleDeviceListRenderCache.classify",
    )
    for marker in required:
        if marker not in source:
            failures.append(f"missing retained-list marker: {marker}")

    delta = body(source, "UiDeltaRenderResult renderSelectionDelta()",
                 "void renderInteractiveScreen")
    for view in ("WifiProductView::Networks", "WifiProductView::Devices",
                 "BleProductView::Devices"):
        anchor = delta.find(view)
        if anchor < 0:
            failures.append(f"missing delta branch: {view}")
            continue
        branch = delta[anchor:anchor + 2600]
        if "Layout::FooterDividerY - Layout::ContentTop" in branch:
            failures.append(f"{view} still clears the full content area")

    full_row = body(source, "bool pushLiveListRow(",
                    "bool pushLiveListDynamicFields(")
    full_text = full_row.rfind("drawLiveListRowText(")
    full_overlay = full_row.rfind("drawLiveListSelectionOverlay(selected);")
    full_push = full_row.rfind("liveListRowSprite.pushSprite(")
    if not (0 <= full_text < full_overlay < full_push):
        failures.append("full live-list row does not composite focus last")

    dynamic = body(source, "bool pushLiveListDynamicFields(",
                   "enum class NavigationKey")
    dynamic_bars = dynamic.rfind("drawLiveListSignalBars(rssiDbm);")
    dynamic_overlay = dynamic.rfind(
        "drawLiveListSelectionOverlay(selected);")
    dynamic_push = dynamic.rfind("liveListRowSprite.pushSprite(")
    if not (0 <= dynamic_bars < dynamic_overlay < dynamic_push):
        failures.append("dynamic live-list row does not composite focus last")

    if failures:
        print("live-list rendering contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("live-list rendering contract passed: retained row diff + adaptive "
          "4-bpp/1-bpp atomic compositing, focus overlay last, no live page "
          "clears")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
