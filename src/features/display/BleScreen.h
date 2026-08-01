#pragma once

#include "../ble_scanner/BleScanner.h"

// BleScreen — renders a BLE scan on the TFT: signal bars, name/MAC, RSSI, and a
// highlighted marker for recognized trackers.
class BleScreen {
public:
    void scanCue();
    int  scan();                // ~4 s BLE scan; returns count
    void render(int offset);
    int  count() const { return ble_.count(); }

private:
    BleScanner ble_;
};
