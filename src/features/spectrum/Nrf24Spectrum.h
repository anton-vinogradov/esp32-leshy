#pragma once

#include <Arduino.h>

// Nrf24Spectrum — a "poor man's" 2.4 GHz spectrum sniffer built on a bare NRF24L01+.
// The chip has no real spectrum analyzer, but its RPD (Received Power Detector,
// register 0x09) latches when it hears a carrier stronger than about -64 dBm on
// the tuned channel. By hopping all 126 1-MHz channels (2400..2525 MHz) and reading
// RPD on each, we build a coarse energy map of the band — enough to see which
// Wi-Fi channels are lit and to spot non-Wi-Fi hoppers (BT, video, microwaves).
//
// Raw SPI register access (no RF24 library) for full control and zero deps. Uses
// the ESP32-DIV v2 radio SPI bus (shared with CC1101/SD) — separate from the TFT
// bus, so drawing never fights it. NRF24 slot #2: CE=47, CSN=48 (verified present
// on hardware; slot #1/CSN=4 is unpopulated here, slot #3 clashes with IR).
class Nrf24Spectrum {
public:
    static const int CHANNELS = 126;      // 2400 + ch MHz, ch = 0..125

    bool begin();                         // init SPI + NRF; returns false if the module doesn't answer
    bool present() const { return present_; }
    void sweep(uint8_t out[CHANNELS]);    // one pass: out[ch] = 1 if a carrier was detected on that channel
    void end();
    void diag();                          // QA: probe every NRF slot/bus-orientation, print STATUS to Serial

    // Wi-Fi channel N (1..14) centre maps to this NRF channel (freq-2400).
    static int wifiCenterNrfCh(int wifiCh) { return wifiCh == 14 ? 84 : 12 + (wifiCh - 1) * 5; }

private:
    uint8_t readReg(uint8_t r);
    void    writeReg(uint8_t r, uint8_t v);
    bool present_ = false;
};
