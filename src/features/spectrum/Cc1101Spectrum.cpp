#include "Cc1101Spectrum.h"

#include <SPI.h>

// ESP32-DIV v2 radio SPI bus + CC1101 chip-select (CiferTech BoardConfig).
static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11, PIN_CS = 5;
static SPIClass    ccSpi(FSPI);
static SPISettings ccSet(4000000, MSBFIRST, SPI_MODE0);   // CC1101 SPI, conservative

static const uint32_t FXTAL_KHZ = 26000;   // 26 MHz crystal

// CC1101 registers / strobes
enum { REG_FREQ2 = 0x0D, REG_FREQ1 = 0x0E, REG_FREQ0 = 0x0F,
       REG_PARTNUM = 0x30, REG_VERSION = 0x31, REG_RSSI = 0x34, REG_MARCSTATE = 0x35 };
enum { S_RES = 0x30, S_RX = 0x34, S_IDLE = 0x36, S_FRX = 0x3A };
static const uint8_t WRITE_BURST = 0x40, READ_SINGLE = 0x80, READ_BURST = 0xC0;

// The RIGHT key cycles these: whole tunable span, then aimed technical bands.
const Cc1101Spectrum::Band Cc1101Spectrum::BANDS[Cc1101Spectrum::NBANDS] = {
    { "full 300-928",  "весь 300-928",   300000, 928000 },   // whole CC1101 range, coarse overview
    { "315 car fobs",  "315 авто/пульты", 300000, 348000 },  // car fobs / garage remotes / TPMS (Americas/Asia)
    { "433 alarms",    "433 сигналки",    431000, 437000 },  // 433.92 ISM: alarms, remotes, sensors
    { "868 LoRa/mesh", "868 LoRa/меш",    863000, 870000 },  // EU ISM: Meshtastic EU, LoRa, sensors
    { "915 LoRa/mesh", "915 LoRa/меш",    902000, 928000 },  // US ISM: Meshtastic US, LoRa
    { "433 zoom",      "433 подробно",    433300, 434600 },  // tight around 433.92 for a single device
};

// The datasheet's "wait for SO to go low" hand-shake needs SO as GPIO, but that pin
// is owned by the SPI peripheral (digitalRead warns + is unreliable). The chip is
// kept awake (IDLE/RX, never SLEEP), so a short settle delay is enough instead.
void Cc1101Spectrum::csLow()  { digitalWrite(PIN_CS, LOW); delayMicroseconds(2); }
void Cc1101Spectrum::csHigh() { digitalWrite(PIN_CS, HIGH); }

uint8_t Cc1101Spectrum::readReg(uint8_t addr) {
    bool status = (addr >= 0x30 && addr <= 0x3D);        // status regs need the burst bit to read
    ccSpi.beginTransaction(ccSet);
    csLow();
    ccSpi.transfer(addr | (status ? READ_BURST : READ_SINGLE));
    uint8_t v = ccSpi.transfer(0);
    csHigh();
    ccSpi.endTransaction();
    return v;
}

void Cc1101Spectrum::writeReg(uint8_t addr, uint8_t val) {
    ccSpi.beginTransaction(ccSet);
    csLow();
    ccSpi.transfer(addr);
    ccSpi.transfer(val);
    csHigh();
    ccSpi.endTransaction();
}

void Cc1101Spectrum::strobe(uint8_t cmd) {
    ccSpi.beginTransaction(ccSet);
    csLow();
    ccSpi.transfer(cmd);
    csHigh();
    ccSpi.endTransaction();
}

void Cc1101Spectrum::reset() {
    digitalWrite(PIN_CS, HIGH); delayMicroseconds(5);
    digitalWrite(PIN_CS, LOW);  delayMicroseconds(10);
    digitalWrite(PIN_CS, HIGH); delayMicroseconds(45);
    ccSpi.beginTransaction(ccSet);
    csLow();
    ccSpi.transfer(S_RES);
    csHigh();
    ccSpi.endTransaction();
    delay(2);                       // SRES completes (crystal + reset)
}

// One-time config: RX with a moderate channel bandwidth and per-hop auto-calibration
// (MCSM0) so a fresh frequency settles cleanly. No packet handling — we only read RSSI.
void Cc1101Spectrum::configBaseRX() {
    writeReg(0x0B, 0x08);   // FSCTRL1 — IF
    writeReg(0x10, 0x8C);   // MDMCFG4 — CHANBW ~203 kHz, drate exp
    writeReg(0x11, 0x22);   // MDMCFG3 — drate mantissa (irrelevant for RSSI)
    writeReg(0x12, 0x30);   // MDMCFG2 — 2-FSK, no sync needed
    writeReg(0x18, 0x18);   // MCSM0 — FS_AUTOCAL when going IDLE->RX
    writeReg(0x19, 0x16);   // FOCCFG
    writeReg(0x1B, 0x43);   // AGCCTRL2
    writeReg(0x1C, 0x40);   // AGCCTRL1
    writeReg(0x1D, 0x91);   // AGCCTRL0
    writeReg(0x23, 0xE9);   // FSCAL3
    writeReg(0x24, 0x2A);   // FSCAL2
    writeReg(0x25, 0x00);   // FSCAL1
    writeReg(0x26, 0x1F);   // FSCAL0
    writeReg(0x2C, 0x81);   // TEST2
    writeReg(0x2D, 0x35);   // TEST1
    writeReg(0x2E, 0x09);   // TEST0
}

void Cc1101Spectrum::tune(uint32_t freqKHz) {
    uint32_t f = (uint32_t)(((uint64_t)freqKHz << 16) / FXTAL_KHZ);
    writeReg(REG_FREQ2, (f >> 16) & 0xFF);
    writeReg(REG_FREQ1, (f >> 8) & 0xFF);
    writeReg(REG_FREQ0, f & 0xFF);
}

bool Cc1101Spectrum::begin() {
    pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
    ccSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
    delay(5);
    reset();
    version_ = readReg(REG_VERSION);
    uint8_t partnum = readReg(REG_PARTNUM);
    present_ = (version_ != 0x00 && version_ != 0xFF);   // CC1101 VERSION is 0x04/0x14/0x17
    (void)partnum;
    if (present_) configBaseRX();
    return present_;
}

void Cc1101Spectrum::setBand(int idx) {
    if (idx < 0) idx = NBANDS - 1;
    if (idx >= NBANDS) idx = 0;
    band_ = idx;
}

uint8_t Cc1101Spectrum::sampleBin(int i, int n) {
    if (!present_ || n <= 1) return 0;
    const Band& b = BANDS[band_];
    uint32_t f = b.loKHz + (uint64_t)(b.hiKHz - b.loKHz) * i / (n - 1);
    strobe(S_IDLE);
    tune(f);
    strobe(S_RX);                           // triggers auto-calibration + RX
    uint32_t t = micros();                  // wait until actually in RX (MARCSTATE=0x0D) so RSSI is valid
    while ((readReg(REG_MARCSTATE) & 0x1F) != 0x0D && micros() - t < 3000) {}
    delayMicroseconds(500);                 // AGC / RSSI settle in RX
    uint8_t raw = readReg(REG_RSSI);
    int dbm = (raw >= 128 ? (raw - 256) : raw) / 2 - 74;   // CC1101 RSSI → dBm
    int e = (dbm + 100) * 255 / 80;         // map ~-100..-20 dBm to 0..255
    return e < 0 ? 0 : (e > 255 ? 255 : e);
}

void Cc1101Spectrum::sweep(uint8_t* out, int n) {
    for (int i = 0; i < n; i++) out[i] = sampleBin(i, n);
    strobe(S_IDLE);
}

void Cc1101Spectrum::end() {
    strobe(S_IDLE);
    ccSpi.end();
    present_ = false;
}

void Cc1101Spectrum::diag() {
    pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
    ccSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
    delay(5);
    reset();
    uint8_t ver = readReg(REG_VERSION), part = readReg(REG_PARTNUM), marc = readReg(REG_MARCSTATE);
    Serial.printf("[cc1101] PARTNUM=0x%02X VERSION=0x%02X MARCSTATE=0x%02X %s\n",
                  part, ver, marc, (ver != 0x00 && ver != 0xFF) ? "<-- chip answers" : "(no response)");
    ccSpi.end();
}
