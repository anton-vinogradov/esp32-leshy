#pragma once

#include "../wifi_scanner/WifiScanner.h"

// WifiScreen — renders a Wi-Fi scan on the TFT. draw() paints the full screen
// (header + rows + footer) after a scan; rows() repaints just the list from
// `offset` using an off-screen sprite, so scrolling is flicker-free.
class WifiScreen {
public:
    void scanCue();             // header "scanning" cue (shown during the scan)
    int  scan();                // perform the scan; returns count
    void draw(int offset);      // full screen after a scan / screen switch
    void rows(int offset);      // list only (on scroll) — no flicker
    int  count() const { return scanner_.count(); }

private:
    WifiScanner scanner_;
};
