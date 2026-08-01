#pragma once

#include <Arduino.h>
#include "esp_wifi.h"

// SignalFinder — a "hot / cold" RSSI direction finder. First cut homes in on a
// Wi-Fi AP by SSID: it sniffs that AP's beacons on its channel, smooths the
// RSSI, and exposes a reading + a warmer/colder trend as you walk around.
// Designed to extend to BLE / NRF24 / CC1101 sources later.
//
// Own-equipment / authorized use only (see DISCLAIMER.md). Passive receive.
struct SignalFinderConfig {
    String   targetSsid;
    uint32_t updateMs   = 300;    // how often the reading/trend refreshes
    uint32_t windowMs   = 700;    // recent window for the reading (responsiveness vs noise)
    uint8_t  minSamples = 2;      // beacons needed before a reading is trusted
};

class SignalFinder {
public:
    bool begin(const SignalFinderConfig& cfg);
    void loop();
    void stop();

    bool isRunning() const { return running_; }
    int  reading() const { return hasReading_ ? last_ : -127; }  // -127 == no signal
    int  trend() const { return trend_; }     // dB vs previous reading (+ = warmer/closer)
    int  rssi();                              // live median over the window

    void pushSample(int8_t rssi);             // called from the sniffer callback

private:
    struct Sample { uint32_t t; int8_t rssi; };
    int medianWithin(uint32_t windowMs, int* countOut);

    SignalFinderConfig cfg_;
    uint8_t targetBssid_[6]{};
    uint8_t channel_ = 1;

    static const size_t CAP = 64;
    Sample  ring_[CAP]{};
    uint64_t head_ = 0;                       // guarded by portMUX; 64-bit never wraps in practice

    int      last_ = -127;
    bool     hasReading_ = false;             // distinguishes "no signal" from a real -127 dBm
    int      trend_ = 0;
    uint32_t nextUpdate_ = 0;
    bool     running_ = false;
};
