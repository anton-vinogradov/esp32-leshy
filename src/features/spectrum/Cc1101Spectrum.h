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

    // Tune to one frequency and read its RSSI in dBm (for the frequency hunter). Pure RX.
    int rssiAt(uint32_t freqKHz);

    // One pass over the current window: out[i] = 0..255 relative energy for bin i of n.
    void sweep(uint8_t* out, int n);
    // Sample a single bin i of n across the current band (0..255). Lets the caller
    // spread a sweep over many loop iterations so buttons stay responsive.
    uint8_t sampleBin(int i, int n);

    // TX test signal (own-equipment). One CC1101 → pure transmitter: it can't watch its
    // own signal (verify with an external receiver). beginTx tunes + configures TX,
    // txBurst sends one packet-load (call repeatedly for a stream), endTx returns to idle.
    void beginTx(uint32_t freqKHz);
    void txBurst();
    void endTx();
    void    setTxPower(uint8_t patable) { txPwr_ = patable; }   // PATABLE[0] value; default max
    uint8_t txPower() const { return txPwr_; }
    static uint32_t bandCenterKHz(const Band& b) { return (b.loKHz + b.hiKHz) / 2; }

    // RAW OOK record / replay (own-equipment: your own remotes/sensors on a bench). One
    // CC1101, so record and replay are separate steps. captureRaw blocks up to a few
    // seconds waiting for a burst on GDO0, storing on/off pulse durations (us); replayRaw
    // bit-bangs them back out. Verify on your own receiver.
    void beginCapture(uint32_t freqKHz);              // OOK: RSSI-envelope RX; FSK: GDO0 async demod
    int  captureRaw(uint16_t* durs, int maxN, uint32_t timeoutMs);   // returns pulse count (0 = nothing heard)
    void replayRaw(const uint16_t* durs, int n, uint32_t freqKHz);
    void diagRssi(uint32_t freqKHz);                       // QA: print live RSSI (find the capture threshold)
    void setCaptureThreshold(int dbm) { capThr_ = dbm; }   // carrier-sense floor (tune to reject noise)
    void setModulation(bool fsk) { fsk_ = fsk; }           // false = OOK (remotes), true = 2-FSK (sensors)
    void setInvert(bool inv) { inv_ = inv; }               // flip replay polarity
    bool modulation() const { return fsk_; }               // current capture/replay modulation (for persisting a slot)
    bool inverted() const { return inv_; }
    int  startLevel() const { return capStartLevel_; }     // captured start polarity — persist it per recording
    void setStartLevel(int lvl) { capStartLevel_ = lvl; }  // restore it before replaying a saved slot

    void diag();                          // QA: reset + print PARTNUM/VERSION

private:
    uint8_t readReg(uint8_t addr);        // status/config register read
    int     rssiDbm();                    // current RX RSSI in dBm (for the OOK envelope capture)
    void    writeReg(uint8_t addr, uint8_t val);
    void    writeBurst(uint8_t addr, const uint8_t* data, int len);
    void    strobe(uint8_t cmd);
    void    reset();
    void    configBaseRX();               // one-time RX/AGC/bandwidth setup
    void    tune(uint32_t freqKHz);       // set carrier frequency
    void    csLow();
    void    csHigh() ;

    bool    present_ = false;
    uint8_t version_ = 0;
    int     band_    = 0;
    uint8_t txByte_  = 0;                 // rolling payload byte → noise-like modulated TX
    uint8_t txPwr_   = 0xC0;              // PATABLE[0] — default ~max (~+10 dBm / 10 mW)
    int     capStartLevel_ = 1;           // GDO0 level of the captured burst's first pulse (for replay polarity)
    int     capThr_  = -72;               // carrier-sense RSSI floor (dBm) for captureRaw
    bool    fsk_     = false;             // TX/capture modulation: false OOK, true 2-FSK
    bool    inv_     = false;             // invert replay polarity
};
