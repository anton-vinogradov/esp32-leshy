#pragma once

#include "../wifi_scanner/WifiScanner.h"

// WifiScreen — a live Wi-Fi scan rendered on the TFT: signal bars, SSID, RSSI
// and a lock marker per network. Call refresh() on a timer.
class WifiScreen {
public:
    void refresh();

private:
    WifiScanner scanner_;
    void drawBars(int x, int y, int rssi, uint16_t color);
};
