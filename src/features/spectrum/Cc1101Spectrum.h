#pragma once

#include <Arduino.h>

// Cc1101Spectrum — a sub-GHz spectrum sniffer on the CC1101. Unlike the NRF24 (1-bit
// carrier detect), the CC1101 reports a real RSSI per frequency, so the waterfall
// carries true signal strength. We tune across a window, strobe RX, read RSSI, and
// step — building a heat map of the 300-928 MHz sub-GHz band.
//
// Raw SPI register access (no library). Same ESP32-DIV v2 radio bus as the NRF24
// (SCK=12, MISO=13, MOSI=11), separate chip-select CS=5. Only one of NRF/CC1101 is
// active at a time (different screens), so they share the bus cleanly.
class Cc1101Spectrum {
public:
    // Display windows the RIGHT key cycles through: the whole tunable span, then
    // aimed technical bands (car/alarm remotes, LoRa mesh nodes, ...).
    struct Band { const char* en; const char* ru; uint32_t loKHz; uint32_t hiKHz; };
    static const int NBANDS = 6;
    static const Band BANDS[NBANDS];

    bool begin();                         // SPI + reset + probe; false if the chip doesn't answer
    bool present() const { return present_; }
    uint8_t version() const { return version_; }
    void end();

    void setBand(int idx);                // choose a display window (idx into BANDS)
    int  band() const { return band_; }
    const Band& bandInfo() const { return BANDS[band_]; }

    // One pass over the current window: out[i] = 0..255 relative energy for bin i of n.
    void sweep(uint8_t* out, int n);
    // Sample a single bin i of n across the current band (0..255). Lets the caller
    // spread a sweep over many loop iterations so buttons stay responsive.
    uint8_t sampleBin(int i, int n);

    void diag();                          // QA: reset + print PARTNUM/VERSION

private:
    uint8_t readReg(uint8_t addr);        // status/config register read
    void    writeReg(uint8_t addr, uint8_t val);
    void    strobe(uint8_t cmd);
    void    reset();
    void    configBaseRX();               // one-time RX/AGC/bandwidth setup
    void    tune(uint32_t freqKHz);       // set carrier frequency
    void    csLow();
    void    csHigh() ;

    bool    present_ = false;
    uint8_t version_ = 0;
    int     band_    = 0;
};
