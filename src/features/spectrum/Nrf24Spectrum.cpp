#include "Nrf24Spectrum.h"

#include <SPI.h>
#include <WiFi.h>
#include <string.h>

// ESP32-DIV v2 radio SPI bus + the three NRF24 slots (CiferTech BoardConfig).
static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11;
static const int SLOT_CE[3]  = { 15, 47, 14 };   // slot #1, #2, #3
static const int SLOT_CSN[3] = {  4, 48, 21 };

static SPIClass    nrfSpi(FSPI);
static SPISettings nrfSet(8000000, MSBFIRST, SPI_MODE0);

static const uint8_t R_CONFIG = 0x00, R_EN_AA = 0x01, R_EN_RXADDR = 0x02,
                     R_RF_CH = 0x05, R_RF_SETUP = 0x06, R_RPD = 0x09, CMD_W = 0x20;

uint8_t Nrf24Spectrum::readReg(int csn, uint8_t r) {
    nrfSpi.beginTransaction(nrfSet);
    digitalWrite(csn, LOW);
    nrfSpi.transfer(r & 0x1F);
    uint8_t v = nrfSpi.transfer(0xFF);
    digitalWrite(csn, HIGH);
    nrfSpi.endTransaction();
    return v;
}

void Nrf24Spectrum::writeReg(int csn, uint8_t r, uint8_t v) {
    nrfSpi.beginTransaction(nrfSet);
    digitalWrite(csn, LOW);
    nrfSpi.transfer(CMD_W | (r & 0x1F));
    nrfSpi.transfer(v);
    digitalWrite(csn, HIGH);
    nrfSpi.endTransaction();
}

void Nrf24Spectrum::configModule(int csn) {
    writeReg(csn, R_CONFIG,    0x00);   // power down while configuring
    writeReg(csn, R_EN_AA,     0x00);   // no auto-ack
    writeReg(csn, R_EN_RXADDR, 0x00);   // RPD needs no data pipes
    writeReg(csn, R_RF_SETUP,  0x06);   // 1 Mbps
    writeReg(csn, R_CONFIG,    0x03);   // PWR_UP | PRIM_RX → receiver
}

bool Nrf24Spectrum::begin() {
    for (int i = 0; i < SLOTS; i++) { pinMode(SLOT_CE[i], OUTPUT); digitalWrite(SLOT_CE[i], LOW);
                                      pinMode(SLOT_CSN[i], OUTPUT); digitalWrite(SLOT_CSN[i], HIGH); }
    nrfSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
    delay(5);

    active_ = 0;
    txWifiMask_ = 0; txHopN_ = 0; txHopI_ = 0; txSlotMask_ = 0; txPhase_ = false;
    for (int i = 0; i < SLOTS; i++) {
        writeReg(SLOT_CSN[i], R_RF_CH, 0x4C);           // probe: write a channel, read it back
        if (readReg(SLOT_CSN[i], R_RF_CH) == 0x4C) {
            configModule(SLOT_CSN[i]);
            ce_[active_]   = SLOT_CE[i];
            csn_[active_]  = SLOT_CSN[i];
            slot_[active_] = i;                          // remember the physical slot → its antenna LED (slot+1)
            active_++;
        }
    }
    delay(2);
    return active_ > 0;
}

// Constant-carrier (unmodulated) TX on one channel: RF_SETUP CONT_WAVE|PLL_LOCK,
// CONFIG PWR_UP with PRIM_RX cleared (transmitter). Caller raises CE to emit. Lowest
// power (RF_PWR=00, -18 dBm): the RX module is centimetres away, so this is still far
// above its RPD floor while limiting the overload that would smear energy onto
// neighbouring channels. CONT_WAVE is an nRF24L01+ feature (same '+' the RPD sweep needs).
void Nrf24Spectrum::configTx(int csn, int ch) {
    writeReg(csn, R_EN_AA,     0x00);
    writeReg(csn, R_RF_SETUP,  0x80 | 0x10 | 0x00);     // CONT_WAVE | PLL_LOCK | 1 Mbps | -18 dBm
    writeReg(csn, R_RF_CH,     ch);
    writeReg(csn, R_CONFIG,    0x02);                   // PWR_UP, PRIM_RX = 0 → TX
}

// Arm/disarm TX. Any live carrier is dropped first (all modules back to RX), then the
// hop list is rebuilt as the union of the selected channels' spans. The reserved TX
// modules are put into carrier mode once here; sweep() only retunes them.
void Nrf24Spectrum::setTxWifiMask(uint16_t wifiMask) {
    for (int k = 0; k < active_; k++) { digitalWrite(ce_[k], LOW); configModule(csn_[k]); }
    txSlotMask_ = 0; txHopN_ = 0; txHopI_ = 0; txPhase_ = false;
    txWifiMask_ = wifiMask;
    if (!wifiMask || active_ == 0) { txCount_ = 0; return; }

    bool cov[CHANNELS] = { false };
    int  nSel = 0;
    for (int w = 1; w <= 13; w++) {
        if (!(wifiMask & (1 << w))) continue;
        nSel++;
        int c = wifiCenterNrfCh(w);
        for (int d = -TX_SPAN; d <= TX_SPAN; d++) { int ch = c + d; if (ch >= 0 && ch < CHANNELS) cov[ch] = true; }
    }
    for (int ch = 0; ch < CHANNELS; ch++) if (cov[ch]) txHop_[txHopN_++] = (uint8_t)ch;

    // One module always sweeps so the waterfall stays live; the rest emit. With a lone
    // module we can't do both at once, so sweep() time-slices it (txCount_ tracked as 1).
    txCount_ = (active_ >= 2) ? (nSel < active_ - 1 ? nSel : active_ - 1) : 1;

    // Antennas that will emit → a stable LED mask (steady yellow while armed), and arm
    // the reserved carriers now. A lone module is time-sliced in sweep() but still counts.
    if (active_ >= 2) {
        for (int k = active_ - txCount_; k < active_; k++) {
            txSlotMask_ |= (uint8_t)(1 << slot_[k]);
            configTx(csn_[k], txHop_[0]);
            digitalWrite(ce_[k], HIGH);
        }
    } else {
        txSlotMask_ = (uint8_t)(1 << slot_[0]);
    }
}

void Nrf24Spectrum::sweep(uint8_t out[CHANNELS]) {
    if (active_ <= 0) { for (int i = 0; i < CHANNELS; i++) out[i] = 0; return; }

    // How many modules emit this sweep; the remainder (always >=1 when we RX) listen.
    int txNow = 0;
    if (txActive()) {
        if (active_ >= 2) txNow = txCount_;
        else { txPhase_ = !txPhase_; txNow = txPhase_ ? 1 : 0; }   // lone module: alternate RX / TX sweeps
    }
    const int rxN = active_ - txNow;

    // RX: tune rxN modules to rxN adjacent channels, listen in one shared 200us dwell,
    // read their RPD — ~rxN channels covered per dwell.
    if (rxN > 0) {
        if (active_ == 1 && txActive()) {               // lone module just held a carrier → back to RX
            digitalWrite(ce_[0], LOW);
            writeReg(csn_[0], R_RF_SETUP, 0x06);        // clear CONT_WAVE/PLL_LOCK (no power-down bounce)
            writeReg(csn_[0], R_CONFIG, 0x03);          // PWR_UP | PRIM_RX
        }
        for (int base = 0; base < CHANNELS; base += rxN) {
            for (int k = 0; k < rxN; k++) {
                int ch = base + k;
                if (ch < CHANNELS) { writeReg(csn_[k], R_RF_CH, ch); digitalWrite(ce_[k], HIGH); }
            }
            delayMicroseconds(200);                     // active RX modules listen concurrently
            for (int k = 0; k < rxN; k++) {
                int ch = base + k;
                if (ch < CHANNELS) { digitalWrite(ce_[k], LOW); out[ch] = readReg(csn_[k], R_RPD) & 0x01; }
            }
        }
    } else {
        for (int i = 0; i < CHANNELS; i++) out[i] = 0;
    }

    // Hop each TX module's carrier across the band: +1 channel per sweep (coprime with
    // any span → full coverage), modules offset apart so they spread the load, not overlap.
    for (int m = 0; m < txNow; m++) {
        int k  = rxN + m;
        int ch = txHop_[(txHopI_ + m * (txHopN_ / txNow)) % txHopN_];
        digitalWrite(ce_[k], LOW);
        if (active_ == 1) configTx(csn_[k], ch);        // lone module was RX last sweep → full setup
        else              writeReg(csn_[k], R_RF_CH, ch);   // reserved module already emitting → just retune
        digitalWrite(ce_[k], HIGH);
    }
    if (txNow > 0) txHopI_ = (txHopI_ + 1) % txHopN_;
}

void Nrf24Spectrum::end() {
    for (int k = 0; k < active_; k++) { digitalWrite(ce_[k], LOW); writeReg(csn_[k], R_CONFIG, 0x00); }
    nrfSpi.end();
    active_ = 0;
    txWifiMask_ = 0; txHopN_ = 0; txHopI_ = 0; txSlotMask_ = 0; txCount_ = 0; txPhase_ = false;
}

// Hardware bring-up aid: an NRF24 returns its STATUS byte on the first clock of every
// SPI command, so STATUS!=0x00 and !=0xFF means the chip is answering.
void Nrf24Spectrum::diag() {
    // Broad hunt for every NRF24 on the shared bus. A real NRF echoes the RF_CH we
    // wrote (0x4C) — that readback is the reliable "it's an NRF" test (CC1101/SD on
    // the same bus won't echo it), so we can safely probe extra candidate CS pins.
    // Datasheet slots first (CSN 4/48/21), then other unused GPIOs; both bus orders.
    static const int CSN_CAND[] = { 4, 48, 21 };            // the three NRF24 CSN lines per the V2 schematic (U1/U2/U3)
    static const int ORD[][2]   = { {13, 11}, {11, 13} };   // {miso, mosi}
    SPISettings slow(2000000, MSBFIRST, SPI_MODE0);
    for (int i : CSN_CAND) { pinMode(i, OUTPUT); digitalWrite(i, HIGH); }   // deselect ALL first, so a probe reads only its own module
    int found = 0;
    for (int ci = 0; ci < (int)(sizeof(CSN_CAND) / sizeof(int)); ci++) {
        int csn = CSN_CAND[ci];
        for (int o = 0; o < 2; o++) {
            nrfSpi.end();
            nrfSpi.begin(PIN_SCK, ORD[o][0], ORD[o][1], -1);
            pinMode(csn, OUTPUT); digitalWrite(csn, HIGH);
            delay(1);
            nrfSpi.beginTransaction(slow);
            digitalWrite(csn, LOW); nrfSpi.transfer(CMD_W | R_RF_CH); nrfSpi.transfer(0x4C); digitalWrite(csn, HIGH);
            digitalWrite(csn, LOW); uint8_t status = nrfSpi.transfer(R_RF_CH); uint8_t rfch = nrfSpi.transfer(0xFF); digitalWrite(csn, HIGH);
            nrfSpi.endTransaction();
            if (rfch == 0x4C) {   // confirmed NRF24 (echoed the written channel)
                Serial.printf("[nrfdiag] NRF24 FOUND: CSN=%d MISO=%d MOSI=%d STATUS=0x%02X\n", csn, ORD[o][0], ORD[o][1], status);
                found++;
                break;
            }
        }
    }
    Serial.printf("[nrfdiag] total NRF24 modules found: %d\n", found);
    nrfSpi.end();
}
