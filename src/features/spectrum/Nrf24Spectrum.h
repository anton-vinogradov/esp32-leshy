#pragma once

#include <Arduino.h>
#include "esp_wifi.h"

// Nrf24Spectrum — a "poor man's" 2.4 GHz spectrum sniffer on the NRF24L01+. The chip
// has no spectrum analyzer, but its RPD (Received Power Detector, reg 0x09) latches
// when it hears a carrier stronger than ~-64 dBm on the tuned channel. Hop all 126
// 1-MHz channels (2400..2525 MHz), read RPD on each → a coarse energy map.
//
// Uses EVERY populated NRF24 module at once: with N modules, N different channels are
// tuned and listened to in the SAME dwell (the ~200us listen is the cost, and it runs
// concurrently), then their RPD bits are read back — so a full sweep is ~N x faster /
// denser. Modules are auto-detected at begin(); on the ESP32-DIV v2 slots #2 (CE47/
// CSN48) and #3 (CE14/CSN21) answer, #1 (CSN4) is unpopulated / shared with PN532.
//
// Raw SPI register access, no library. Shared radio bus SCK=12/MISO=13/MOSI=11
// (separate from the TFT bus), per-module CE/CSN. Receive-only.
class Nrf24Spectrum {
public:
    static const int CHANNELS = 126;      // 2400 + ch MHz, ch = 0..125
    static const int SLOTS    = 3;

    bool begin();                         // init SPI + detect modules; false if none answer
    bool present() const { return active_ > 0; }
    int  modules() const { return active_; }   // how many NRF24s are in use (1..3)
    void sweep(uint8_t out[CHANNELS]);    // one pass across all modules: out[ch] = carrier detected?
    void end();
    void diag();                          // QA: probe every slot/orientation, print STATUS

    static int wifiCenterNrfCh(int wifiCh) { return wifiCh == 14 ? 84 : 12 + (wifiCh - 1) * 5; }

private:
    uint8_t readReg(int csn, uint8_t r);
    void    writeReg(int csn, uint8_t r, uint8_t v);
    void    configModule(int csn);

    int active_ = 0;
    int ce_[SLOTS] = {0};                  // CE pins of the active modules (0..active_-1)
    int csn_[SLOTS] = {0};                 // CSN pins of the active modules
};
