#pragma once

#include <Arduino.h>
#include "esp_wifi.h"

// StationSniffer — passively lists Wi-Fi CLIENT devices (stations), which a normal
// AP scan never sees. Promiscuous sniff of 802.11 data frames (extract the station
// side via the To/From-DS bits) and probe requests (a station searching for networks).
// Hops channels 1..13. Receive-only, passive observation — own-network / situational
// awareness, not a targeting tool.
struct StaRow {
    uint8_t  mac[6];
    uint8_t  bssid[6];   // AP the station talks to (zero = probe-only, not associated)
    int8_t   rssi;
    uint32_t last;
    uint16_t pkts;
    bool     assoc;      // true = seen in data frames (on an AP); false = probe-request only
};

class StationSniffer {
public:
    bool begin();
    void loop();                         // channel hop (call from the main loop)
    void stop();
    void seen(const uint8_t sta[6], const uint8_t bssid[6], bool assoc, int8_t rssi);  // from the RX callback, under s_mux
    int  count();
    bool row(int i, StaRow& out);        // i-th strongest (sorted by RSSI)
    uint8_t channel() const { return curChannel_; }
    bool    isRunning() const { return running_; }

private:
    static const int CAP = 48;
    StaRow   tbl_[CAP];
    int      n_ = 0;
    uint8_t  curChannel_ = 1;
    uint32_t nextHop_ = 0;
    bool     running_ = false;
};
