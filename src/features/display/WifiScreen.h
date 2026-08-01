#pragma once

#include "../wifi_scanner/WifiScanner.h"

// WifiScreen — renders a Wi-Fi scan on the TFT. scan() collects, render(offset)
// draws a scrollable list (signal bars, SSID, RSSI, lock marker).
class WifiScreen {
public:
    void scanCue();             // header with a "scanning" hint (shown during scan)
    int  scan();                // perform the scan; returns count
    void render(int offset);    // draw the list starting at `offset`
    int  count() const { return scanner_.count(); }

private:
    WifiScanner scanner_;
};
