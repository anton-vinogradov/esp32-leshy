#pragma once

#include <Arduino.h>

// WifiScanner — a plain, synchronous Wi-Fi AP scan over the built-in radio.
// Passive discovery, fully legal. UI-agnostic: fills an array the caller renders.
struct WifiAp {
    String  ssid;
    uint8_t bssid[6];
    int8_t  rssi;
    uint8_t channel;
    uint8_t auth;        // wifi_auth_mode_t
};

class WifiScanner {
public:
    int scan(bool showHidden = true);          // returns count; blocks ~2 s
    int count() const { return count_; }
    const WifiAp& at(int i) const { return aps_[i]; }

    static const char* authName(uint8_t auth); // localized

private:
    static const int MAX = 48;
    WifiAp aps_[MAX];
    int    count_ = 0;
};
