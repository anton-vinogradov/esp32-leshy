#pragma once

#include <Arduino.h>
#include "esp_wifi.h"

// AirtimeMonitor — measures how BUSY each 2.4 GHz channel actually is, by summing
// the on-air time of the frames it hears in promiscuous mode (management + data +
// control), not by counting how many access points advertise on it. That is the
// honest answer to "which channel is loaded": a channel with one busy AP beats a
// channel crowded with idle ones.
//
// The percentage is a LOWER BOUND: only PPDUs the radio successfully receives and
// whose length/rate we can read are counted, and the rate is estimated, so real
// airtime is somewhat higher. Receive-only, fully legal. Needs the radio to
// itself (promiscuous) — pause the scan engine before begin(), like the deauth
// monitor.
class AirtimeMonitor {
public:
    bool begin(uint32_t dwellMs = 130);   // caller must pauseAndWait() the scan first
    void loop();                          // hop channels on schedule; call often
    void stop();
    bool isRunning() const { return running_; }
    uint8_t channel() const { return curChannel_; }

    // Copy the latest busy-permille (0..1000) for channels 1..13 into out[1..13].
    // Each channel's value is refreshed when the hop last visited it and held in
    // between (only one channel can be listened to at a time), so the graph shows
    // every channel while the radio sweeps.
    void read(uint16_t out[14]);

    void addBusyLocked(uint8_t ch, uint32_t us);   // called from the RX callback with s_mux held

private:
    static const uint8_t MAXCH = 13;
    void finalizeLocked(uint8_t ch, uint32_t now); // fold the finished dwell into last_[ch]

    volatile uint32_t busyUs_[14] = {0};    // summed frame airtime on the channel being listened to now
    volatile uint32_t obsUs_[14]  = {0};    // time listened on it since last finalize
    volatile uint16_t last_[14]   = {0};    // last computed busy-permille per channel (held between visits)
    uint8_t  curChannel_ = 1;
    uint32_t dwellMs_    = 130;
    uint32_t hopAt_      = 0;
    uint32_t landedAt_   = 0;               // millis when we tuned to curChannel_
    bool     running_    = false;
};
