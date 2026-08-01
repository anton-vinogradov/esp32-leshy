#pragma once

#include "../ble_scanner/BleScanner.h"

// BleScreen — renders a BLE scan on the TFT (name/MAC, RSSI, tracker marker).
// Same flicker-free draw()/rows() split as WifiScreen.
class BleScreen {
public:
    void scanCue();
    int  scan();                // ~4 s BLE scan; returns count
    void draw(int offset);
    void rows(int offset);
    int  count() const { return ble_.count(); }

private:
    BleScanner ble_;
};
