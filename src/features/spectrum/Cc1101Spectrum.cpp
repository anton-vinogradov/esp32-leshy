#include "Cc1101Spectrum.h"

#include <SPI.h>

// ESP32-DIV v2 radio SPI bus + CC1101 chip-select (CiferTech BoardConfig).
static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11, PIN_CS = 5;
static const int PIN_GDO0 = 6;   // CC1101 GDO0 — async serial data (RAW OOK record/replay)
static SPIClass    ccSpi(FSPI);
static SPISettings ccSet(4000000, MSBFIRST, SPI_MODE0);   // CC1101 SPI, conservative

static const uint32_t FXTAL_KHZ = 26000;   // 26 MHz crystal

// CC1101 registers / strobes
enum { REG_FREQ2 = 0x0D, REG_FREQ1 = 0x0E, REG_FREQ0 = 0x0F,
       REG_PARTNUM = 0x30, REG_VERSION = 0x31, REG_RSSI = 0x34, REG_MARCSTATE = 0x35 };
enum { S_RES = 0x30, S_TX = 0x35, S_RX = 0x34, S_IDLE = 0x36, S_FTX = 0x3B, S_FRX = 0x3A };
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

void Cc1101Spectrum::writeBurst(uint8_t addr, const uint8_t* data, int len) {
    ccSpi.beginTransaction(ccSet);
    csLow();
    ccSpi.transfer(addr | WRITE_BURST);
    for (int i = 0; i < len; i++) ccSpi.transfer(data[i]);
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
    writeReg(0x12, 0x30);   // MDMCFG2 — ASK/OOK, no sync (RSSI-only, modulation irrelevant for RX)
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

// Configure TX: fixed-length OOK-keyed packets on freqKHz. FS_AUTOCAL (MCSM0 from
// configBaseRX) calibrates on the IDLE->TX hop, so a fresh frequency settles. Modest
// power — an own-equipment test signal, not a jammer.
void Cc1101Spectrum::beginTx(uint32_t freqKHz) {
    if (!present_) return;
    strobe(S_IDLE);
    tune(freqKHz);
    writeReg(0x12, 0x30);   // MDMCFG2 — ASK/OOK, no sync (rolling payload → ~50% duty, noise-like)
    writeReg(0x17, 0x30);   // MCSM1 — TXOFF_MODE = IDLE (so txBurst's wait-for-IDLE is well-defined)
    writeReg(0x08, 0x00);   // PKTCTRL0 — fixed length, no CRC/whitening, FIFO mode
    writeReg(0x06, 60);     // PKTLEN — 60-byte packets
    writeReg(0x3E, txPwr_); // PATABLE[0] — user-set TX power (default ~max); OOK keys hw-off <-> this
    txByte_ = 0;
}

// Send one 60-byte packet with a rolling payload (reads as noise on a spectrum). Call
// repeatedly for a continuous-ish stream; each packet returns the chip to IDLE.
void Cc1101Spectrum::txBurst() {
    if (!present_) return;
    strobe(S_FTX);                          // flush the TX FIFO
    uint8_t buf[60];
    for (int i = 0; i < 60; i++) buf[i] = txByte_++;
    writeBurst(0x3F, buf, 60);              // load the TX FIFO
    strobe(S_TX);
    uint32_t t = micros();                  // wait until we actually ENTER TX (start state is IDLE too)
    while ((readReg(REG_MARCSTATE) & 0x1F) != 0x13 && micros() - t < 3000) {}
    t = micros();                           // then wait for the packet to drain back to IDLE
    while ((readReg(REG_MARCSTATE) & 0x1F) != 0x01 && micros() - t < 20000) {}
    strobe(S_IDLE);
}

void Cc1101Spectrum::endTx() {
    if (!present_) return;
    strobe(S_IDLE);
}

// Async OOK RX: GDO0 outputs the demodulated envelope, which we time in captureRaw.
// The AGC is pinned lower here (vs the RSSI-sweep config) so the demodulator stays quiet
// on noise instead of dithering — the part most likely to need on-hardware tuning.
void Cc1101Spectrum::beginCapture(uint32_t freqKHz) {
    if (!present_) return;
    strobe(S_IDLE);
    tune(freqKHz);
    writeReg(0x02, 0x0D);   // IOCFG0 — GDO0 = serial data (async)
    writeReg(0x12, 0x30);   // MDMCFG2 — ASK/OOK, no sync
    writeReg(0x08, 0x32);   // PKTCTRL0 — asynchronous serial, infinite length
    writeReg(0x1B, 0x03);   // AGCCTRL2 — OOK: fixed-ish magnitude target (was 0x43 for RSSI sweep)
    writeReg(0x1C, 0x00);   // AGCCTRL1
    writeReg(0x1D, 0x91);   // AGCCTRL0
    pinMode(PIN_GDO0, INPUT);
    strobe(S_RX);
    uint32_t t = micros();  // wait until actually in RX (like sampleBin) so GDO0 is the demodulated signal
    while ((readReg(REG_MARCSTATE) & 0x1F) != 0x0D && micros() - t < 3000) {}
    delayMicroseconds(500); // AGC settle
}

// Time the OOK pulses on GDO0 into durs[] (microseconds). Carrier-sense on RSSI first (so
// we don't trigger on the noise floor), then record level durations from the first edge
// until a >20 ms gap ends the burst. Blocks up to ~5 s. Returns count (0 = nothing heard).
int Cc1101Spectrum::captureRaw(uint16_t* durs, int maxN, uint32_t timeoutMs) {
    if (!present_ || maxN <= 0) return 0;
    pinMode(PIN_GDO0, INPUT);
    uint32_t t0 = millis();
    for (;;) {                                          // carrier sense: wait for a real signal
        uint8_t raw = readReg(REG_RSSI);
        int dbm = (raw >= 128 ? (raw - 256) : raw) / 2 - 74;
        if (dbm > -72) break;
        if (millis() - t0 > timeoutMs) { strobe(S_IDLE); return 0; }
        yield();
    }
    int idle = digitalRead(PIN_GDO0);
    while (digitalRead(PIN_GDO0) == idle) {             // wait for the leading edge of the burst
        if (millis() - t0 > timeoutMs) { strobe(S_IDLE); return 0; }
    }
    capStartLevel_ = !idle;                             // first pulse level — replay reproduces it
    int n = 0, level = !idle;
    uint32_t tPrev = micros();
    while (n < maxN && millis() - t0 < timeoutMs + 2000) {   // capture budget (signal wait + burst)
        uint32_t tw = micros();
        while (digitalRead(PIN_GDO0) == level) {
            if (micros() - tw > 20000) goto done;       // >20 ms of one level → end of burst
        }
        uint32_t now = micros();
        durs[n++] = (uint16_t)(now - tPrev);            // <20 ms per pulse → fits uint16
        tPrev = now;
        level = !level;
    }
done:
    strobe(S_IDLE);
    return n;
}

// Bit-bang the recorded pulse train back out via async OOK TX on GDO0.
void Cc1101Spectrum::replayRaw(const uint16_t* durs, int n, uint32_t freqKHz) {
    if (!present_ || n <= 0) return;
    strobe(S_IDLE);
    tune(freqKHz);
    writeReg(0x02, 0x0D);   // IOCFG0 — GDO0 = serial data in (async TX)
    writeReg(0x12, 0x30);   // MDMCFG2 — ASK/OOK
    writeReg(0x08, 0x32);   // PKTCTRL0 — asynchronous serial, infinite length
    writeReg(0x17, 0x30);   // MCSM1 — TXOFF_MODE = IDLE
    writeReg(0x3E, txPwr_); // PATABLE[0] — TX power
    pinMode(PIN_GDO0, OUTPUT);
    digitalWrite(PIN_GDO0, capStartLevel_ ? LOW : HIGH);   // hold idle before the carrier is up
    strobe(S_TX);
    uint32_t t = micros();                              // wait to actually ENTER TX — PLL cal (~800us) else the first pulse is eaten
    while ((readReg(REG_MARCSTATE) & 0x1F) != 0x13 && micros() - t < 3000) {}
    int level = capStartLevel_;                         // reproduce the captured polarity
    for (int i = 0; i < n; i++) {
        digitalWrite(PIN_GDO0, level);
        uint32_t d = durs[i];
        while (d > 16000) { delayMicroseconds(16000); d -= 16000; }   // delayMicroseconds is only exact below ~16 ms
        delayMicroseconds(d);
        level = !level;
    }
    digitalWrite(PIN_GDO0, LOW);
    strobe(S_IDLE);
    pinMode(PIN_GDO0, INPUT);
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
