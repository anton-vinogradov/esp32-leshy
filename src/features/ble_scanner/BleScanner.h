#pragma once

#include <Arduino.h>

// A best-effort guess at what a BLE device IS, from its advertising data (GAP
// Appearance, service UUIDs, name). Heuristic — meant to label the anonymous MAC
// list ("часы", "наушники", "мышь"), not to be authoritative.
enum BleKind : uint8_t {
    BK_NONE = 0, BK_PHONE, BK_PC, BK_WATCH, BK_AUDIO, BK_KBD, BK_MOUSE,
    BK_HID, BK_HEART, BK_THERMO, BK_TAG, BK_TV, BK_FITNESS
};
const char* bleKindLabel(BleKind k, bool ru);   // short localized tag; "" for BK_NONE

// BleScanner — passive BLE discovery over the built-in radio (Bluedroid). Lists
// nearby devices and flags known trackers (Apple Find My, Tile, Samsung
// SmartTag) so you can spot an unwanted tracker or find your own. Receive-only.
struct BleDev {
    String  mac;
    String  name;
    int     rssi;
    String  tracker;     // "" if not a recognized tracker
    BleKind kind;        // guessed device category (BK_NONE if unknown)
    String  vendor;      // brand from the manufacturer company-ID ("Apple"/"Samsung"/…), "" if unknown — shown when kind is unknown
};

class BleScanner {
public:
    bool begin();                              // false if the stack can't come up (RAM released for OTA → reboot needed)
    int  scan(uint32_t seconds = 5);           // blocks for `seconds`
    bool releaseForOta();                      // free BLE RAM for the OTA download; one-way (reboot to use BLE again)
    int  count() const { return count_; }
    const BleDev& at(int i) const { return devs_[i]; }

private:
    static const int MAX = 48;
    BleDev devs_[MAX];
    int    count_ = 0;
    bool   inited_ = false;
};
