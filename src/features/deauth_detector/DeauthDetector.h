#pragma once

#include <Arduino.h>
#include "esp_wifi.h"

// DeauthDetector — passively watches the air for Wi-Fi deauth/disassoc frames
// and raises an alert when they burst. Receive-only, fully legal; a defensive
// counterpart to the (out-of-scope) deauth attack. Own-network use recommended:
// pin fixedChannel to your AP's channel, or leave 0 to hop and catch any.
struct DeauthDetectorConfig {
    uint8_t  fixedChannel  = 0;     // 0 = hop channels 1..13
    uint32_t hopMs         = 300;
    uint32_t windowMs      = 3000;  // window for the rate/alert
    uint16_t alertThreshold = 5;    // frames within windowMs to raise an alert
};

struct DeauthEvent {
    uint32_t t;
    uint8_t  subtype;               // 0xC0 deauth, 0xA0 disassoc
    int8_t   rssi;
    uint8_t  channel;
    uint8_t  src[6];
    uint8_t  dst[6];
};

class DeauthDetector {
public:
    bool begin(const DeauthDetectorConfig& cfg = DeauthDetectorConfig());
    void loop();
    void stop();

    void writeLocked(const DeauthEvent& e); // called from the callback WITH s_mux already held

    uint32_t total();
    int      recentCount();                 // events within windowMs
    bool     alerting() { return recentCount() >= cfg_.alertThreshold; }
    bool     lastEvent(DeauthEvent& out);
    uint8_t  channel() const { return curChannel_; }
    uint32_t windowMs() const { return cfg_.windowMs; }
    bool     isRunning() const { return running_; }

private:
    DeauthDetectorConfig cfg_;

    static const size_t CAP = 64;
    DeauthEvent ring_[CAP]{};
    uint64_t head_ = 0;                      // all access guarded by portMUX
    uint32_t total_ = 0;

    uint8_t  curChannel_ = 1;
    uint32_t nextHop_ = 0;
    bool     running_ = false;
};
