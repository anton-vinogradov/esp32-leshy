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

    if failures:
        print("live-list rendering contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("live-list rendering contract passed: retained row diff + adaptive "
          "4-bpp/1-bpp atomic compositing, no live page clears")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
