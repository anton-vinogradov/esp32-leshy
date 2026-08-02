#include "Nrf24Spectrum.h"

#include <SPI.h>

// ESP32-DIV v2 radio SPI bus (SCK/MISO/MOSI) + NRF24 slot #2 select/enable lines.
// Verified on hardware (nrfdiag): slot #2 (CE=47/CSN=48) answers STATUS=0x0E; slot
// #1 (CSN=4) is unpopulated/shared with PN532 here, slot #3 (14/21) clashes with IR.
static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11, PIN_CE = 47, PIN_CSN = 48;

static SPIClass    nrfSpi(FSPI);                          // FSPI — TFT owns HSPI, so no contention
static SPISettings nrfSet(8000000, MSBFIRST, SPI_MODE0);  // NRF24 tops out ~10 MHz

// NRF24L01+ registers / commands
static const uint8_t R_CONFIG = 0x00, R_EN_AA = 0x01, R_EN_RXADDR = 0x02,
                     R_RF_CH = 0x05, R_RF_SETUP = 0x06, R_RPD = 0x09, CMD_W = 0x20;

uint8_t Nrf24Spectrum::readReg(uint8_t r) {
    nrfSpi.beginTransaction(nrfSet);
    digitalWrite(PIN_CSN, LOW);
    nrfSpi.transfer(r & 0x1F);
    uint8_t v = nrfSpi.transfer(0xFF);
    digitalWrite(PIN_CSN, HIGH);
    nrfSpi.endTransaction();
    return v;
}

void Nrf24Spectrum::writeReg(uint8_t r, uint8_t v) {
    nrfSpi.beginTransaction(nrfSet);
    digitalWrite(PIN_CSN, LOW);
    nrfSpi.transfer(CMD_W | (r & 0x1F));
    nrfSpi.transfer(v);
    digitalWrite(PIN_CSN, HIGH);
    nrfSpi.endTransaction();
}

bool Nrf24Spectrum::begin() {
    pinMode(PIN_CE,  OUTPUT); digitalWrite(PIN_CE,  LOW);
    pinMode(PIN_CSN, OUTPUT); digitalWrite(PIN_CSN, HIGH);
    nrfSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);   // we drive CSN ourselves
    delay(5);

    writeReg(R_RF_CH, 0x4C);                          // presence probe: write a channel, read it back
    present_ = (readReg(R_RF_CH) == 0x4C);
    if (!present_) return false;

    writeReg(R_CONFIG,    0x00);   // power down while configuring
    writeReg(R_EN_AA,     0x00);   // no auto-ack
    writeReg(R_EN_RXADDR, 0x00);   // RPD needs no data pipes
    writeReg(R_RF_SETUP,  0x06);   // 1 Mbps, 0 dBm (rate only sets RX bandwidth here)
    writeReg(R_CONFIG,    0x03);   // PWR_UP | PRIM_RX (CRC off) → receiver
    delay(2);                      // Tpd2stby
    return true;
}

void Nrf24Spectrum::sweep(uint8_t out[CHANNELS]) {
    if (!present_) { for (int i = 0; i < CHANNELS; i++) out[i] = 0; return; }
    for (int ch = 0; ch < CHANNELS; ch++) {
        writeReg(R_RF_CH, ch);
        digitalWrite(PIN_CE, HIGH);
        delayMicroseconds(200);        // ~130us to enter RX + ~70us listen
        digitalWrite(PIN_CE, LOW);
        out[ch] = readReg(R_RPD) & 0x01;   // 1 = carrier > ~-64 dBm seen on this channel
    }
}

void Nrf24Spectrum::end() {
    digitalWrite(PIN_CE, LOW);
    writeReg(R_CONFIG, 0x00);      // power down
    nrfSpi.end();
    present_ = false;
}

// Hardware bring-up aid: an NRF24 returns its STATUS byte on the first clock of
// EVERY SPI command, so STATUS!=0x00 and !=0xFF means the chip is answering.
// Try each module slot and both MISO/MOSI orderings so a mis-populated slot or a
// swapped bus shows up immediately.
void Nrf24Spectrum::diag() {
    struct Combo { const char* name; int csn; int miso; int mosi; };
    static const Combo combos[] = {
        { "#1 csn=4  miso=13 mosi=11", 4,  13, 11 },
        { "#1 csn=4  miso=11 mosi=13", 4,  11, 13 },
        { "#2 csn=48 miso=13 mosi=11", 48, 13, 11 },
        { "#3 csn=21 miso=13 mosi=11", 21, 13, 11 },
    };
    SPISettings slow(2000000, MSBFIRST, SPI_MODE0);
    pinMode(PIN_CE, OUTPUT); digitalWrite(PIN_CE, LOW);
    for (auto& c : combos) {
        nrfSpi.end();
        nrfSpi.begin(PIN_SCK, c.miso, c.mosi, -1);
        pinMode(c.csn, OUTPUT); digitalWrite(c.csn, HIGH);
        delay(2);
        nrfSpi.beginTransaction(slow);
        digitalWrite(c.csn, LOW); nrfSpi.transfer(CMD_W | R_RF_CH); nrfSpi.transfer(0x4C); digitalWrite(c.csn, HIGH);
        digitalWrite(c.csn, LOW); uint8_t status = nrfSpi.transfer(R_RF_CH); uint8_t rfch = nrfSpi.transfer(0xFF); digitalWrite(c.csn, HIGH);
        nrfSpi.endTransaction();
        Serial.printf("[nrfdiag] %-26s STATUS=0x%02X RF_CH=0x%02X %s\n",
                      c.name, status, rfch,
                      (status != 0x00 && status != 0xFF) ? "<-- chip answers" : "(no response)");
    }
    nrfSpi.end();
}
