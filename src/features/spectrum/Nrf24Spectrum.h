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
    void sweep(uint8_t out[CHANNELS]);    // one pass: RX carrier map (out[ch] = detected?); also drives TX if armed
    void end();
    void diag();                          // QA: probe every slot/orientation, print STATUS

    // TX self-test — inject noise to prove the spectrum end-to-end. The rest of the
    // modules emit a constant carrier that hops across each selected Wi-Fi channel's
    // ~20 MHz span (reads as a band of white noise); with >=2 modules one keeps sweeping
    // (RX) so the injected signal shows on the waterfall, while a lone module is time-
    // sliced (LED indicates emission, but it can't catch its own carrier). Own-equipment
    // diagnostic; own the airtime.
    void    setTxWifiMask(uint16_t wifiMask);   // bit w (1..13) => transmit into Wi-Fi channel w; 0 => TX off
    bool    txActive() const { return txWifiMask_ != 0 && txHopN_ > 0 && active_ > 0; }
    uint8_t txSlotMask() const { return txSlotMask_; }   // physical NRF slots (bit 0..2) armed for TX → antenna LEDs

    // TX radiation power = the RF_PWR field of RF_SETUP: 0x06 = 0 dBm (max), then -6, -12,
    // 0x00 = -18 dBm. Set before arming; takes effect on the next setTxWifiMask().
    void    setTxPower(uint8_t rfPwrBits) { txPwr_ = rfPwrBits & 0x06; }
    uint8_t txPower() const { return txPwr_; }
    static int txPowerDbm(uint8_t bits) { return -18 + (int)(bits >> 1) * 6; }   // 00→-18 · 02→-12 · 04→-6 · 06→0

    static int wifiCenterNrfCh(int wifiCh) { return wifiCh == 14 ? 84 : 12 + (wifiCh - 1) * 5; }

private:
    static const int TX_SPAN = 9;         // ± NRF channels around a Wi-Fi centre (~19 MHz ≈ one 20 MHz channel)

    uint8_t readReg(int csn, uint8_t r);
    void    writeReg(int csn, uint8_t r, uint8_t v);
    void    configModule(int csn);        // put a module into RX (RPD) mode
    void    configTx(int csn, int ch);    // put a module into constant-carrier TX on channel ch

    int active_ = 0;
    int ce_[SLOTS]   = {0};                // CE pins of the active modules (0..active_-1)
    int csn_[SLOTS]  = {0};                // CSN pins of the active modules
    int slot_[SLOTS] = {0};                // physical slot index (0..2) of each active module — for the per-antenna LED

    uint16_t txWifiMask_ = 0;              // armed Wi-Fi channels (bit 1..13); 0 = TX off
    uint8_t  txPwr_      = 0x06;           // RF_PWR bits — default 0 dBm (max); user-tunable in Settings
    int      txCount_    = 0;              // modules dedicated to TX (rest sweep RX); 1 module → time-sliced
    uint8_t  txSlotMask_ = 0;             // physical slots emitting this sweep (for LEDs)
    uint8_t  txHop_[CHANNELS];             // distinct NRF channels the carrier hops through
    int      txHopN_ = 0;
    int      txHopI_ = 0;                  // hop cursor
    bool     txPhase_ = false;            // single-module case: alternate RX / TX per sweep
};
