#pragma once

#include <Arduino.h>

// BleScanner — passive BLE discovery over the built-in radio (Bluedroid). Lists
// nearby devices and flags known trackers (Apple Find My, Tile, Samsung
// SmartTag) so you can spot an unwanted tracker or find your own. Receive-only.
struct BleDev {
    String mac;
    String name;
    int    rssi;
    String tracker;      // "" if not a recognized tracker
};

class BleScanner {
public:
    bool begin();
    int  scan(uint32_t seconds = 5);           // blocks for `seconds`
    int  count() const { return count_; }
    const BleDev& at(int i) const { return devs_[i]; }

private:
    static const int MAX = 48;
    BleDev devs_[MAX];
    int    count_ = 0;
    bool   inited_ = false;
};
