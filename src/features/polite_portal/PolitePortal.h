#pragma once

#include <Arduino.h>
#include <DNSServer.h>
#include <WebServer.h>
#include "esp_wifi.h"

// PolitePortal — a captive portal that politely asks the operator of a nearby
// access point to lower its Wi-Fi TX power, and shuts itself down once it
// *estimates* (from beacon RSSI) that the power actually dropped.
//
// Unlike the classic "evil portal", it has NO input fields and logs NO
// credentials — just a message and a single button.
//
// Educational / own-equipment use only (see DISCLAIMER.md): the target AP must
// be one you own or are explicitly authorized to test. TX power cannot be read
// over the air, so it is inferred from beacon RSSI — which only tracks power if
// the device stays put. It is a rough estimate, not proof.
struct PolitePortalConfig {
    String   targetSsid;                      // AP whose TX power we watch (yours)
    String   portalSsid = "lower-your-wifi-power";
    int      rssiDropDb  = 6;                  // drop vs baseline that counts as "reduced"
    uint32_t baselineMs  = 8000;              // how long to measure the baseline
    uint32_t windowMs    = 5000;              // recent window used when verifying
    uint8_t  minSamples  = 8;                 // beacons needed before a verdict is trusted
};

class PolitePortal {
public:
    bool begin(const PolitePortalConfig& cfg);
    void loop();
    void stop();

    bool isRunning() const { return running_; }
    int  baselineRssi() const { return baseline_; }
    int  currentRssi();                       // median over the recent window
    int  sampleCount();                       // beacons within the recent window

    void pushSample(int8_t rssi);             // called from the sniffer callback

private:
    struct Sample { uint32_t t; int8_t rssi; };

    void handleRoot();
    void handleReduced();
    void handleResult();
    void redirectToPortal();
    void sendPage(const String& body, int refreshSec = -1, const char* refreshUrl = nullptr);
    int  medianWithin(uint32_t windowMs, int* countOut);

    PolitePortalConfig cfg_;
    DNSServer dns_;
    WebServer web_{80};
    IPAddress apIp_{192, 168, 4, 1};

    uint8_t targetBssid_[6]{};
    uint8_t channel_ = 1;
    int     baseline_ = 0;

    static const size_t CAP = 128;            // beacon RSSI ring buffer
    Sample  ring_[CAP]{};
    volatile size_t head_ = 0;

    bool     running_ = false;
    bool     shutdownArmed_ = false;
    uint32_t shutdownAt_ = 0;
};
