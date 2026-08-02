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
    for (int i = 0; i < SLOTS; i++) {
        writeReg(SLOT_CSN[i], R_RF_CH, 0x4C);           // probe: write a channel, read it back
        if (readReg(SLOT_CSN[i], R_RF_CH) == 0x4C) {
            configModule(SLOT_CSN[i]);
            ce_[active_]  = SLOT_CE[i];
            csn_[active_] = SLOT_CSN[i];
            active_++;
        }
    }
    delay(2);
    return active_ > 0;
}

void Nrf24Spectrum::sweep(uint8_t out[CHANNELS]) {
    if (active_ <= 0) { for (int i = 0; i < CHANNELS; i++) out[i] = 0; return; }
    const int N = active_;
    // Each pass tunes N modules to N adjacent channels and listens on all of them in
    // one shared dwell, then reads their RPD — so ~N channels are covered per 200us.
    for (int base = 0; base < CHANNELS; base += N) {
        for (int k = 0; k < N; k++) {
            int ch = base + k;
            if (ch < CHANNELS) { writeReg(csn_[k], R_RF_CH, ch); digitalWrite(ce_[k], HIGH); }
        }
        delayMicroseconds(200);                         // all active modules listen concurrently
        for (int k = 0; k < N; k++) {
            int ch = base + k;
            if (ch < CHANNELS) { digitalWrite(ce_[k], LOW); out[ch] = readReg(csn_[k], R_RPD) & 0x01; }
        }
    }
}

void Nrf24Spectrum::end() {
    for (int k = 0; k < active_; k++) { digitalWrite(ce_[k], LOW); writeReg(csn_[k], R_CONFIG, 0x00); }
    nrfSpi.end();
    active_ = 0;
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
