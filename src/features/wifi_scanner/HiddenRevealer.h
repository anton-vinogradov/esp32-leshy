#pragma once

#include <Arduino.h>
#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

// HiddenRevealer — passively recovers the names of hidden Wi-Fi networks.
//
// A hidden AP leaves its SSID blank in beacons, but the name still travels in
// cleartext inside other 802.11 management frames: Probe Responses (the AP
// answering a client's directed probe) and (Re)Association Requests (a client
// joining). This class parks the radio on a channel in promiscuous mode, parses
// those frames, and caches BSSID -> SSID. Revealed names are persisted to NVS so
// they survive reboots, and can be listed / deleted by the UI.
//
// Reveal is passive: it only works while there is traffic to/from the network
// (a client probing or (re)connecting). Own-equipment / educational use only.
class HiddenRevealer {
public:
    void begin();                                   // mutex + load saved names from NVS
    void setTargets(uint8_t bssids[][6], int n);    // only reveal names for THESE (actually-hidden) BSSIDs
    void listen(uint8_t channel, uint32_t ms);      // promiscuous capture on one channel (scan task)

    bool lookup(const uint8_t bssid[6], String& out);   // revealed name for a BSSID, if known
    int  count();
    bool get(int i, uint8_t bssidOut[6], String& ssidOut);
    void remove(int i);                             // delete one entry + persist
    void clear();                                   // wipe all + persist

    void onFrame(const uint8_t* f, uint16_t len);   // internal (promiscuous callback)
    static HiddenRevealer* active;

private:
    struct Entry { uint8_t bssid[6]; char ssid[33]; };
    static const int MAX = 128;              // dense neighbourhoods have many hidden APs
    static const int MAXT = 24;              // hidden BSSIDs targeted in one reveal pass
    static const int SCHEMA = 2;             // bump to wipe stale NVS on semantics change
    Entry             ent_[MAX];
    int               n_ = 0;
    uint8_t           tgt_[MAXT][6];         // only store names for these (scan-confirmed hidden) BSSIDs
    int               tgtN_ = 0;
    volatile bool     dirty_ = false;               // new name captured, not yet persisted
    SemaphoreHandle_t mtx_ = nullptr;

    bool inTargets(const uint8_t b[6]) const;       // called under lock
    void storeLocked(const uint8_t bssid[6], const char* ssid, uint8_t slen);
    void persist();                                 // write whole table to NVS
    void load();
};
