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
    String   mac;
    String   name;
    int      rssi;
    String   tracker;    // "" if not a recognized tracker
    BleKind  kind;       // guessed device category (BK_NONE if unknown)
    String   vendor;     // brand from the manufacturer company-ID ("Apple"/"Samsung"/…), "" if unknown — shown when kind is unknown
    bool     pub;        // true = public (fixed, trackable) MAC; false = random (privacy-rotating)
    String   subtype;    // specific decode ("AirPods"/"iBeacon"/"Eddystone"/…) — refines the tag
    uint16_t appearance; // GAP Appearance code (0 = not advertised)
    int      txpwr;      // advertised TX power in dBm (127 = not advertised)
    uint16_t company;    // manufacturer company-ID (0 = none)
    String   svc;        // first advertised service, decoded to a name or 0xUUID
};

class BLEAdvertisedDevice;   // fwd — radar callback needs it without pulling the BLE headers into every includer

class BleScanner {
public:
    bool begin();                              // false if the stack can't come up (RAM released for OTA → reboot needed)
    int  scan(uint32_t seconds = 5);           // blocks for `seconds`
    bool releaseForOta();                      // free BLE RAM for the OTA download; one-way (reboot to use BLE again)
    int  count() const { return count_; }
    const BleDev& at(int i) const { return devs_[i]; }

    // Radar (find-one-device) mode: lock onto a MAC and get its RSSI live, updated on
    // every advertisement rather than once per full scan.
    void     radarSetTarget(const String& mac) { radarMac_ = mac; radarSeenMs_ = 0; radarRssi_ = 0; }
    void     radarScan(uint32_t seconds);      // one live window; the callback keeps radarRssi()/radarLastSeen() fresh
    int      radarRssi() const { return radarRssi_; }
    uint32_t radarLastSeen() const { return radarSeenMs_; }
    void     radarOnAd(BLEAdvertisedDevice& d);   // called by the scan callback for each ad (public so the callback can reach it)

private:
    static const int MAX = 48;
    BleDev devs_[MAX];
    int    count_ = 0;
    bool   inited_ = false;

    String            radarMac_;
    volatile int      radarRssi_   = 0;
    volatile uint32_t radarSeenMs_ = 0;
};
