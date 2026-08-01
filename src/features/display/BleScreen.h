#pragma once

#include "../scan/ScanEngine.h"

// BleScreen — renders the BLE snapshot from ScanEngine (name/MAC, RSSI, tracker
// marker in amber). Same flicker-free draw()/rows() split as WifiScreen.
class BleScreen {
public:
    void draw(ScanEngine& e, int offset);
    void rows(ScanEngine& e, int offset);
};
