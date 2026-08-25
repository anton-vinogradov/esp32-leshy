#include <Arduino.h>
#include <SPI.h>
#include <esp_app_desc.h>
#include <esp_mac.h>
#include <esp_task_wdt.h>
#include <driver/gpio.h>
#include <soc/gpio_struct.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "FixtureSession.h"

#ifndef LESHY_FIXTURE_VERSION
#define LESHY_FIXTURE_VERSION "0.3.0-subghz-safe"
#endif

namespace {

using leshy::hil::fixture::FixtureSession;
using leshy::hil::fixture::FixtureState;
using leshy::hil::fixture::fixtureSignalName;
using leshy::hil::fixture::fixtureStateName;

constexpr int kBuzzerPin = 2;
constexpr int kIrTxPin = 14;
constexpr int kNrfCe1Pin = 15;
constexpr int kNrfCe2Pin = 47;
// ESP32-DIV deliberately routes the third nRF CE and the IR transmitter to
// the same GPIO.  Once LEDC owns this pin it must never be treated as an
// independent GPIO output: doing so can suppress the bounded IR carrier.
constexpr int kNrfCe3SharedPin = kIrTxPin;
constexpr int kIrRxPin = 21;
constexpr int kRadioMosiPin = 11;
constexpr int kRadioSckPin = 12;
constexpr int kRadioMisoPin = 13;
constexpr int kNrfCsn1Pin = 4;
constexpr int kNrfCsn2Pin = 48;
constexpr int kNrfCsn3Pin = 21;
constexpr int kFixtureNrfCePin = kNrfCe2Pin;
constexpr int kFixtureNrfCsnPin = kNrfCsn2Pin;
constexpr int kCc1101CsPin = 5;
constexpr int kSdCsPin = 10;
constexpr std::uint32_t kCarrierHz = 38000;
constexpr std::uint8_t kCarrierResolutionBits = 8;
constexpr std::uint8_t kCarrierDuty = 85;
constexpr std::uint32_t kNecCode = 0xCB34EF10U;
constexpr std::uint32_t kConsoleBaud = 115200;
constexpr std::uint32_t kNrfSpiHz = 8000000;
constexpr std::uint32_t kNrfProbeSpiHz = 2000000;
constexpr std::uint8_t kNrfReadRegister = 0x00;
constexpr std::uint8_t kNrfWriteRegister = 0x20;
constexpr std::uint8_t kNrfRegConfig = 0x00;
constexpr std::uint8_t kNrfRegEnableAutoAck = 0x01;
constexpr std::uint8_t kNrfRegEnableReceiveAddress = 0x02;
constexpr std::uint8_t kNrfRegRfChannel = 0x05;
constexpr std::uint8_t kNrfRegRfSetup = 0x06;
constexpr std::uint8_t kNrfChannel = 42;
constexpr std::uint16_t kNrfFrequencyMhz = 2400U + kNrfChannel;
constexpr std::int8_t kNrfPowerDbm = -18;
constexpr std::uint8_t kNrfMinimumPowerCarrierSetup = 0x90;
constexpr std::uint8_t kCcReadPartNumber = 0xF0;
constexpr std::uint8_t kCcReadVersion = 0xF1;
constexpr std::uint32_t kCcReadyTimeoutUs = 2000;
constexpr std::uint32_t kCcSpiHz = 4000000;
constexpr std::uint32_t kCcCrystalKHz = 26000;
constexpr std::uint32_t kCcFrequencyKHz = 433920;
constexpr std::int8_t kCcPowerDbm = -15;
constexpr std::uint8_t kCcMinimumPowerTable = 0x1D;
constexpr std::uint8_t kCcPacketLength = 60;
constexpr std::uint8_t kCcOokPacketCount = 4;
constexpr std::uint8_t kCcFskPacketCount = 1;
constexpr std::uint32_t kCcInterPacketGapUs = 4000;
constexpr std::uint8_t kCcWriteBurst = 0x40;
constexpr std::uint8_t kCcReadSingle = 0x80;
constexpr std::uint8_t kCcReadStatus = 0xC0;
constexpr std::uint8_t kCcRegisterPacketLength = 0x06;
constexpr std::uint8_t kCcRegisterPacketControl0 = 0x08;
constexpr std::uint8_t kCcRegisterFsControl1 = 0x0B;
constexpr std::uint8_t kCcRegisterFrequency2 = 0x0D;
constexpr std::uint8_t kCcRegisterModemConfig4 = 0x10;
constexpr std::uint8_t kCcRegisterModemConfig3 = 0x11;
constexpr std::uint8_t kCcRegisterModemConfig2 = 0x12;
constexpr std::uint8_t kCcRegisterDeviation = 0x15;
constexpr std::uint8_t kCcRegisterMainStateMachine1 = 0x17;
constexpr std::uint8_t kCcRegisterMainStateMachine0 = 0x18;
constexpr std::uint8_t kCcRegisterMarcState = 0x35;
constexpr std::uint8_t kCcRegisterTxBytes = 0x3A;
constexpr std::uint8_t kCcRegisterPowerTable = 0x3E;
constexpr std::uint8_t kCcRegisterTxFifo = 0x3F;
constexpr std::uint8_t kCcCommandReset = 0x30;
constexpr std::uint8_t kCcCommandTransmit = 0x35;
constexpr std::uint8_t kCcCommandIdle = 0x36;
constexpr std::uint8_t kCcCommandFlushTx = 0x3B;
constexpr std::uint8_t kCcMarcIdle = 0x01;
constexpr std::uint8_t kCcMarcTransmit = 0x13;
constexpr int kNrfCsnPins[3] = {
    kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin};

struct NrfInventoryReadback {
    std::uint8_t status[3]{};
    std::uint8_t config[3]{};
    std::uint8_t channel[3]{};
    std::uint8_t rfSetup[3]{};
    std::uint8_t plausibleMask = 0;
    std::uint8_t ccStatus = 0xFF;
    std::uint8_t ccPartNumber = 0xFF;
    std::uint8_t ccVersion = 0xFF;
    bool ccReadComplete = false;
    bool ccPlausible = false;
};

FixtureSession session;
char runningAppSha256[65]{};
char runningFixtureId[17]{};
char commandBuffer[224]{};
std::size_t commandLength = 0;
bool carrierReady = false;
bool watchdogReady = false;
bool identityReady = false;
bool nrfBusStarted = false;
bool nrfTransactionOpen = false;
bool nrfCarrierActive = false;
bool nrfPoweredDown = true;
bool ccBusStarted = false;
bool ccTransactionOpen = false;
bool ccTransmitActive = false;
bool ccIdle = true;
bool ccPowerCleared = true;
bool ccTxFifoCleared = true;
volatile bool ccAbortRequested = false;
std::uint32_t nrfCarrierStartedUs = 0;
const char* nrfStartError = "not_attempted";
std::uint8_t nrfStatusReadback = 0xFF;
std::uint8_t nrfConfigReadback = 0xFF;
std::uint8_t nrfChannelReadback = 0xFF;
std::uint8_t nrfRfSetupReadback = 0xFF;
const char* ccStartError = "not_attempted";
std::uint8_t ccStatusReadback = 0xFF;
std::uint8_t ccPartNumberReadback = 0xFF;
std::uint8_t ccVersionReadback = 0xFF;
std::uint8_t ccMarcStateReadback = 0xFF;
std::uint32_t ccTxStrobes = 0;
std::uint32_t ccPowerTableWrites = 0;
std::uint32_t ccTxFifoWrites = 0;
std::uint32_t ccTxFifoBytes = 0;
NrfInventoryReadback nrfPrimaryInventory;
NrfInventoryReadback nrfSwappedInventory;

void IRAM_ATTR quiesceFromIsr() {
    ccAbortRequested = true;
    GPIO.out_w1tc = (1U << kBuzzerPin) | (1U << kIrTxPin) |
                     (1U << kNrfCe1Pin);
    GPIO.out1_w1tc.val = (1U << (kNrfCe2Pin - 32U));
}

void holdChipSelectsHigh() {
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
    }
}

void holdNrfCeLow() {
    digitalWrite(kNrfCe1Pin, LOW);
    digitalWrite(kNrfCe2Pin, LOW);
    if (carrierReady) {
        ledcWrite(kIrTxPin, 0);
    } else {
        gpio_set_level(static_cast<gpio_num_t>(kNrfCe3SharedPin), 0);
    }
}

bool configureIrCarrier() {
    if (carrierReady) {
        ledcWrite(kIrTxPin, 0);
        ledcDetach(kIrTxPin);
        carrierReady = false;
    }
    gpio_set_level(static_cast<gpio_num_t>(kIrTxPin), 0);
    pinMode(kIrTxPin, OUTPUT);
    carrierReady = ledcAttach(
        kIrTxPin, kCarrierHz, kCarrierResolutionBits);
    return carrierReady && ledcWrite(kIrTxPin, 0);
}

void beginNrfBus() {
    holdNrfCeLow();
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    SPI.begin(kRadioSckPin, kRadioMisoPin, kRadioMosiPin, -1);
    nrfBusStarted = true;
    SPI.beginTransaction(SPISettings(kNrfSpiHz, MSBFIRST, SPI_MODE0));
    nrfTransactionOpen = true;
}

void endNrfBus() {
    holdNrfCeLow();
    holdChipSelectsHigh();
    if (nrfTransactionOpen) {
        SPI.endTransaction();
        nrfTransactionOpen = false;
    }
    if (nrfBusStarted) {
        SPI.end();
        nrfBusStarted = false;
    }
    pinMode(kNrfCsn3Pin, INPUT);
}

std::uint8_t nrfWriteRegister(std::uint8_t reg, std::uint8_t value) {
    digitalWrite(kFixtureNrfCsnPin, LOW);
    const std::uint8_t status =
        SPI.transfer(kNrfWriteRegister | (reg & 0x1FU));
    SPI.transfer(value);
    digitalWrite(kFixtureNrfCsnPin, HIGH);
    return status;
}

std::uint8_t nrfReadRegister(std::uint8_t reg,
                             std::uint8_t* status = nullptr) {
    digitalWrite(kFixtureNrfCsnPin, LOW);
    const std::uint8_t commandStatus =
        SPI.transfer(kNrfReadRegister | (reg & 0x1FU));
    const std::uint8_t value = SPI.transfer(0xFF);
    digitalWrite(kFixtureNrfCsnPin, HIGH);
    if (status != nullptr) *status = commandStatus;
    return value;
}

bool powerDownNrf() {
    holdNrfCeLow();
    const bool startedHere = !nrfBusStarted;
    if (startedHere) beginNrfBus();
    nrfWriteRegister(kNrfRegConfig, 0x00);
    nrfPoweredDown = (nrfReadRegister(kNrfRegConfig) & 0x02U) == 0;
    if (startedHere) endNrfBus();
    return nrfPoweredDown;
}

bool stopNrfCarrier() {
    holdNrfCeLow();
    if (nrfBusStarted) {
        nrfWriteRegister(kNrfRegConfig, 0x00);
        nrfPoweredDown = (nrfReadRegister(kNrfRegConfig) & 0x02U) == 0;
    }
    endNrfBus();
    nrfCarrierActive = false;
    return nrfPoweredDown;
}

bool outputsInactive();

std::uint8_t nrfProbeReadRegister(int csn, std::uint8_t reg,
                                  std::uint8_t* status = nullptr) {
    digitalWrite(csn, LOW);
    const std::uint8_t commandStatus =
        SPI.transfer(kNrfReadRegister | (reg & 0x1FU));
    const std::uint8_t value = SPI.transfer(0xFF);
    digitalWrite(csn, HIGH);
    if (status != nullptr) *status = commandStatus;
    return value;
}

bool plausibleNrfIdentity(std::uint8_t status, std::uint8_t config,
                          std::uint8_t channel) {
    return status != 0x00U && status != 0xFFU &&
           (config & 0x80U) == 0 && channel <= 125U;
}

bool readCcIdentityRegister(int miso, std::uint8_t command,
                            std::uint8_t* status, std::uint8_t* value) {
    digitalWrite(kCc1101CsPin, LOW);
    const std::uint32_t started = micros();
    while (digitalRead(miso) != LOW) {
        if (micros() - started > kCcReadyTimeoutUs) {
            digitalWrite(kCc1101CsPin, HIGH);
            return false;
        }
    }
    *status = SPI.transfer(command);
    *value = SPI.transfer(0xFF);
    digitalWrite(kCc1101CsPin, HIGH);
    return true;
}

NrfInventoryReadback probeNrfOrientation(int miso, int mosi) {
    NrfInventoryReadback result;
    holdNrfCeLow();
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    SPI.begin(kRadioSckPin, miso, mosi, -1);
    delay(5);
    SPI.beginTransaction(SPISettings(kNrfProbeSpiHz, MSBFIRST, SPI_MODE0));
    for (std::uint8_t slot = 0; slot < 3; ++slot) {
        result.config[slot] = nrfProbeReadRegister(
            kNrfCsnPins[slot], kNrfRegConfig, &result.status[slot]);
        result.channel[slot] = nrfProbeReadRegister(
            kNrfCsnPins[slot], kNrfRegRfChannel);
        result.rfSetup[slot] = nrfProbeReadRegister(
            kNrfCsnPins[slot], kNrfRegRfSetup);
        if (plausibleNrfIdentity(
                result.status[slot], result.config[slot],
                result.channel[slot])) {
            result.plausibleMask = static_cast<std::uint8_t>(
                result.plausibleMask | (1U << slot));
        }
    }
    std::uint8_t partStatus = 0xFF;
    std::uint8_t versionStatus = 0xFF;
    result.ccReadComplete = readCcIdentityRegister(
        miso, kCcReadPartNumber, &partStatus, &result.ccPartNumber) &&
        readCcIdentityRegister(
            miso, kCcReadVersion, &versionStatus, &result.ccVersion);
    result.ccStatus = versionStatus;
    result.ccPlausible = result.ccReadComplete &&
        result.ccStatus != 0xFFU &&
        !(result.ccPartNumber == 0xFFU && result.ccVersion == 0xFFU) &&
        !(result.ccPartNumber == 0x00U &&
          (result.ccVersion == 0x00U || result.ccVersion == 0xFFU));
    SPI.endTransaction();
    SPI.end();
    holdNrfCeLow();
    holdChipSelectsHigh();
    return result;
}

bool probeNrfInventory() {
    if (nrfBusStarted || nrfCarrierActive || ccBusStarted ||
        ccTransactionOpen || ccTransmitActive) {
        return false;
    }
    holdNrfCeLow();
    nrfPrimaryInventory = probeNrfOrientation(
        kRadioMisoPin, kRadioMosiPin);
    nrfSwappedInventory = probeNrfOrientation(
        kRadioMosiPin, kRadioMisoPin);
    pinMode(kNrfCsn3Pin, INPUT);
    return outputsInactive();
}

bool beginCcBus() {
    if (ccBusStarted || ccTransactionOpen || nrfBusStarted ||
        nrfCarrierActive || !nrfPoweredDown) {
        ccStartError = "radio_bus_unavailable";
        return false;
    }
    holdNrfCeLow();
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    SPI.begin(kRadioSckPin, kRadioMisoPin, kRadioMosiPin, -1);
    ccBusStarted = true;
    SPI.beginTransaction(SPISettings(kCcSpiHz, MSBFIRST, SPI_MODE0));
    ccTransactionOpen = true;
    return true;
}

void endCcBus() {
    digitalWrite(kCc1101CsPin, HIGH);
    holdChipSelectsHigh();
    if (ccTransactionOpen) {
        SPI.endTransaction();
        ccTransactionOpen = false;
    }
    if (ccBusStarted) {
        SPI.end();
        ccBusStarted = false;
    }
    pinMode(kNrfCsn3Pin, INPUT);
}

bool selectCc() {
    if (!ccBusStarted || !ccTransactionOpen) return false;
    digitalWrite(kCc1101CsPin, LOW);
    const std::uint32_t started = micros();
    while (digitalRead(kRadioMisoPin) != LOW) {
        if (micros() - started > kCcReadyTimeoutUs) {
            digitalWrite(kCc1101CsPin, HIGH);
            ccStartError = "ready_timeout";
            return false;
        }
    }
    return true;
}

void deselectCc() {
    digitalWrite(kCc1101CsPin, HIGH);
}

bool ccCommand(std::uint8_t command) {
    if (!selectCc()) return false;
    ccStatusReadback = SPI.transfer(command);
    deselectCc();
    return true;
}

bool ccWriteRegister(std::uint8_t address, std::uint8_t value) {
    if (!selectCc()) return false;
    SPI.transfer(address);
    SPI.transfer(value);
    deselectCc();
    if (address == kCcRegisterPowerTable) {
        ++ccPowerTableWrites;
        ccPowerCleared = value == 0U;
    }
    return true;
}

bool ccReadRegister(std::uint8_t address, std::uint8_t* value) {
    if (value == nullptr || !selectCc()) return false;
    SPI.transfer(static_cast<std::uint8_t>(address | kCcReadSingle));
    *value = SPI.transfer(0xFF);
    deselectCc();
    return true;
}

bool ccReadStatusRegister(std::uint8_t address, std::uint8_t* value) {
    if (value == nullptr || !selectCc()) return false;
    SPI.transfer(static_cast<std::uint8_t>(address | kCcReadStatus));
    *value = SPI.transfer(0xFF);
    deselectCc();
    return true;
}

bool ccWriteTxFifo(const std::uint8_t* payload, std::size_t size) {
    if (payload == nullptr || size != kCcPacketLength || !selectCc()) {
        return false;
    }
    SPI.transfer(static_cast<std::uint8_t>(
        kCcRegisterTxFifo | kCcWriteBurst));
    for (std::size_t index = 0; index < size; ++index) {
        SPI.transfer(payload[index]);
    }
    deselectCc();
    ++ccTxFifoWrites;
    ccTxFifoBytes += size;
    ccTxFifoCleared = false;
    return true;
}

bool ccWaitForMarc(std::uint8_t expected, std::uint32_t timeoutUs) {
    const std::uint32_t started = micros();
    do {
        if (!ccReadStatusRegister(kCcRegisterMarcState,
                                  &ccMarcStateReadback)) {
            return false;
        }
        ccMarcStateReadback &= 0x1FU;
        if (ccMarcStateReadback == expected) return true;
    } while (micros() - started <= timeoutUs);
    ccStartError = expected == kCcMarcTransmit
                       ? "transmit_state_timeout"
                       : "idle_state_timeout";
    return false;
}

bool resetCc() {
    digitalWrite(kCc1101CsPin, HIGH);
    delayMicroseconds(5);
    digitalWrite(kCc1101CsPin, LOW);
    delayMicroseconds(10);
    digitalWrite(kCc1101CsPin, HIGH);
    delayMicroseconds(45);
    if (!ccCommand(kCcCommandReset)) return false;
    delayMicroseconds(2000);
    ccIdle = ccWaitForMarc(kCcMarcIdle, 3000);
    return ccIdle;
}

bool tuneCc(std::uint32_t frequencyKHz) {
    const std::uint32_t word = static_cast<std::uint32_t>(
        (static_cast<std::uint64_t>(frequencyKHz) << 16U) /
        kCcCrystalKHz);
    return ccWriteRegister(kCcRegisterFrequency2,
                           static_cast<std::uint8_t>(word >> 16U)) &&
           ccWriteRegister(kCcRegisterFrequency2 + 1U,
                           static_cast<std::uint8_t>(word >> 8U)) &&
           ccWriteRegister(kCcRegisterFrequency2 + 2U,
                           static_cast<std::uint8_t>(word));
}

bool readCcIdentity() {
    return ccReadStatusRegister(0x30, &ccPartNumberReadback) &&
           ccReadStatusRegister(0x31, &ccVersionReadback) &&
           ccVersionReadback != 0x00U && ccVersionReadback != 0xFFU;
}

bool configureFixedCc(bool fsk) {
    const struct RegisterValue final {
        std::uint8_t address;
        std::uint8_t value;
    } settings[] = {
        {kCcRegisterFsControl1, 0x08},
        {kCcRegisterModemConfig4, 0x8C},
        {kCcRegisterModemConfig3, 0x22},
        {kCcRegisterModemConfig2,
         static_cast<std::uint8_t>(fsk ? 0x00 : 0x30)},
        {kCcRegisterDeviation, 0x47},
        {kCcRegisterMainStateMachine1, 0x30},
        {kCcRegisterMainStateMachine0, 0x18},
        {kCcRegisterPacketControl0, 0x00},
        {kCcRegisterPacketLength, kCcPacketLength},
        {kCcRegisterPowerTable, kCcMinimumPowerTable},
    };
    if (!tuneCc(kCcFrequencyKHz)) return false;
    for (const RegisterValue& setting : settings) {
        if (!ccWriteRegister(setting.address, setting.value)) return false;
    }

    std::uint8_t modem = 0xFF;
    std::uint8_t packetLength = 0;
    std::uint8_t power = 0;
    if (!ccReadRegister(kCcRegisterModemConfig2, &modem) ||
        !ccReadRegister(kCcRegisterPacketLength, &packetLength) ||
        !ccReadStatusRegister(kCcRegisterPowerTable, &power) ||
        modem != static_cast<std::uint8_t>(fsk ? 0x00 : 0x30) ||
        packetLength != kCcPacketLength || power != kCcMinimumPowerTable) {
        ccStartError = "configuration_readback_mismatch";
        return false;
    }
    return true;
}

bool stopCcTransmitter() {
    if (!ccBusStarted) {
        ccTransmitActive = false;
        return ccIdle;
    }
    const bool idled = ccCommand(kCcCommandIdle) &&
        ccWaitForMarc(kCcMarcIdle, 3000);
    ccTransmitActive = false;
    ccIdle = idled;
    std::uint8_t power = 0xFF;
    std::uint8_t txBytes = 0xFF;
    const bool powerCleared =
        ccWriteRegister(kCcRegisterPowerTable, 0x00) &&
        ccReadStatusRegister(kCcRegisterPowerTable, &power) && power == 0U;
    const bool fifoCleared = ccCommand(kCcCommandFlushTx) &&
        ccReadStatusRegister(kCcRegisterTxBytes, &txBytes) &&
        (txBytes & 0x7FU) == 0U;
    ccPowerCleared = powerCleared;
    ccTxFifoCleared = fifoCleared;
    endCcBus();
    return idled && powerCleared && fifoCleared;
}

bool emitFixedCcPacket(const std::uint8_t* payload) {
    if (ccAbortRequested || !ccCommand(kCcCommandFlushTx) ||
        !ccWriteTxFifo(payload, kCcPacketLength)) {
        ccStartError = ccAbortRequested ? "abort_requested" : "fifo_load_failed";
        return false;
    }
    ccTransmitActive = true;
    ccIdle = false;
    if (!ccCommand(kCcCommandTransmit)) {
        ccStartError = "transmit_strobe_failed";
        ccTransmitActive = false;
        return false;
    }
    ++ccTxStrobes;
    if (!ccWaitForMarc(kCcMarcTransmit, 3000) ||
        !ccWaitForMarc(kCcMarcIdle, 20000)) {
        ccTransmitActive = false;
        return false;
    }
    ccTransmitActive = false;
    ccIdle = true;
    return true;
}

std::uint32_t emitFixedCcVector(bool fsk) {
    ccStartError = "configuring";
    ccStatusReadback = 0xFF;
    ccPartNumberReadback = 0xFF;
    ccVersionReadback = 0xFF;
    ccMarcStateReadback = 0xFF;
    ccTxStrobes = 0;
    ccPowerTableWrites = 0;
    ccTxFifoWrites = 0;
    ccTxFifoBytes = 0;
    ccPowerCleared = true;
    ccTxFifoCleared = true;
    ccAbortRequested = false;
    if (!beginCcBus() || !resetCc() || !readCcIdentity()) {
        if (std::strcmp(ccStartError, "configuring") == 0) {
            ccStartError = "identity_unavailable";
        }
        stopCcTransmitter();
        return 0;
    }
    if (!configureFixedCc(fsk)) {
        stopCcTransmitter();
        return 0;
    }

    std::uint8_t payload[kCcPacketLength] = {};
    for (std::size_t index = 0; index < sizeof(payload); ++index) {
        // The product rejects FSK edges shorter than 60 us.  At the fixed
        // 38.4-kbaud modem rate, 0xF0 creates deterministic four-bit runs
        // (~104 us) while the all-ones tail keeps the bounded vector well
        // below the product's 512-edge capture ceiling.
        payload[index] = fsk && index < 16U ? 0xF0 : 0xFF;
    }
    const std::uint8_t packetCount =
        fsk ? kCcFskPacketCount : kCcOokPacketCount;
    const std::uint32_t started = micros();
    bool complete = true;
    for (std::uint8_t packet = 0; packet < packetCount; ++packet) {
        if (!emitFixedCcPacket(payload)) {
            complete = false;
            break;
        }
        if (packet + 1U < packetCount) {
            delayMicroseconds(kCcInterPacketGapUs);
        }
    }
    const std::uint32_t durationUs =
        static_cast<std::uint32_t>(micros() - started);
    const bool stopped = stopCcTransmitter();
    if (!complete || !stopped || ccAbortRequested || durationUs == 0U ||
        durationUs > leshy::hil::fixture::kMaximumCc1101EmissionUs) {
        if (std::strcmp(ccStartError, "configuring") == 0) {
            ccStartError = "emission_out_of_bounds";
        }
        return 0;
    }
    ccStartError = "none";
    return durationUs;
}

void quiesceOutputs() {
    ledcWrite(kIrTxPin, 0);
    digitalWrite(kBuzzerPin, LOW);
    digitalWrite(kIrTxPin, LOW);
    stopNrfCarrier();
    stopCcTransmitter();
}

bool outputsInactive() {
    return gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
           !ccTransmitActive && ccIdle && ccPowerCleared && ccTxFifoCleared;
}

void establishBootInvariant() {
    for (const int pin : {kBuzzerPin, kIrTxPin, kNrfCe1Pin, kNrfCe2Pin}) {
        digitalWrite(pin, LOW);
        pinMode(pin, OUTPUT);
    }
    for (const int pin : {kNrfCsn1Pin, kNrfCsn2Pin, kNrfCsn3Pin,
                          kCc1101CsPin, kSdCsPin}) {
        digitalWrite(pin, HIGH);
        pinMode(pin, OUTPUT);
    }
    configureIrCarrier();
    digitalWrite(kBuzzerPin, LOW);
    holdNrfCeLow();
    holdChipSelectsHigh();
    nrfPoweredDown = powerDownNrf();
    pinMode(kIrRxPin, INPUT);
}

void formatIdentity() {
    const esp_app_desc_t* description = esp_app_get_description();
    bool appIdentityReady = false;
    if (description != nullptr &&
        description->magic_word == ESP_APP_DESC_MAGIC_WORD) {
        constexpr char kHex[] = "0123456789abcdef";
        for (std::size_t index = 0;
             index < sizeof(description->app_elf_sha256); ++index) {
            const std::uint8_t value = description->app_elf_sha256[index];
            runningAppSha256[index * 2U] = kHex[value >> 4U];
            runningAppSha256[index * 2U + 1U] = kHex[value & 0x0FU];
        }
        appIdentityReady = true;
    }
    std::uint8_t mac[6]{};
    const bool macReady = esp_efuse_mac_get_default(mac) == ESP_OK;
    if (macReady) {
        std::snprintf(
            runningFixtureId, sizeof(runningFixtureId),
            "0000%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2],
            mac[3], mac[4], mac[5]);
    }
    identityReady = appIdentityReady && macReady;
}

void emitState(const char* kind) {
    const auto& report = session.report();
    Serial.printf(
        "{\"schema\":\"leshy.hil.fixture.signal.v1\",\"kind\":\"%s\","
        "\"version\":\"%s\",\"role\":\"bounded_signal_fixture\","
        "\"fixture_id\":\"%s\",\"app_elf_sha256\":\"%s\","
        "\"identity_ready\":%s,"
        "\"state\":\"%s\",\"session_id\":\"%s\","
        "\"signal\":\"%s\",\"vector_id\":\"%s\","
        "\"armed\":%s,\"deadline_ms\":%lu,"
        "\"start_count\":%lu,\"stop_count\":%lu,\"panic_count\":%lu,"
        "\"emission_count\":%lu,\"last_duration_us\":%lu,"
        "\"maximum_duration_us\":%lu,"
        "\"ir_tx_gpio\":14,\"ir_rx_gpio\":21,"
        "\"ir_tx_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"nrf_powered_down\":%s,\"nrf_carrier_active\":%s,"
        "\"buzzer_inactive\":%s,\"output_inactive\":%s,"
        "\"carrier_hz\":38000,\"maximum_ir_emission_us\":100000,"
        "\"nrf_module_slot\":2,\"nrf_channel\":42,"
        "\"nrf_frequency_mhz\":2442,\"nrf_power_dbm\":-18,"
        "\"nrf_rf_setup\":144,\"nrf_carrier_duration_us\":2000000,"
        "\"maximum_nrf_carrier_us\":2500000,"
        "\"nrf_start_error\":\"%s\",\"nrf_status_readback\":%u,"
        "\"nrf_config_readback\":%u,\"nrf_channel_readback\":%u,"
        "\"nrf_rf_setup_readback\":%u,"
        "\"cc_frequency_khz\":433920,\"cc_power_dbm\":-15,"
        "\"cc_patable\":29,\"cc_packet_length\":60,"
        "\"cc_hardware_auto_idle\":true,"
        "\"cc_transmit_active\":%s,\"cc_idle\":%s,"
        "\"cc_power_cleared\":%s,\"cc_tx_fifo_cleared\":%s,"
        "\"cc_start_error\":\"%s\",\"cc_status_readback\":%u,"
        "\"cc_part_number\":%u,\"cc_version\":%u,"
        "\"cc_marc_state\":%u,\"cc_tx_strobes\":%lu,"
        "\"cc_patable_writes\":%lu,\"cc_tx_fifo_writes\":%lu,"
        "\"cc_tx_fifo_bytes\":%lu,"
        "\"maximum_cc1101_emission_us\":250000,"
        "\"session_lifetime_ms\":5000,"
        "\"fixed_vector_only\":true,\"auto_arm\":false,"
        "\"watchdog_armed\":%s,\"last_error\":\"%s\"}\n",
        kind, LESHY_FIXTURE_VERSION, runningFixtureId, runningAppSha256,
        identityReady ? "true" : "false",
        fixtureStateName(report.state), session.sessionId(),
        fixtureSignalName(report.signal), session.vectorId(),
        report.state == leshy::hil::fixture::FixtureState::Armed
            ? "true" : "false",
        static_cast<unsigned long>(report.deadlineMs),
        static_cast<unsigned long>(report.startCount),
        static_cast<unsigned long>(report.stopCount),
        static_cast<unsigned long>(report.panicCount),
        static_cast<unsigned long>(report.emissionCount),
        static_cast<unsigned long>(report.lastDurationUs),
        static_cast<unsigned long>(report.maximumDurationUs),
        gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
                gpio_get_level(
                    static_cast<gpio_num_t>(kNrfCe3SharedPin)) == 0
            ? "true" : "false",
        nrfPoweredDown ? "true" : "false",
        nrfCarrierActive ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 ? "true" : "false",
        outputsInactive() ? "true" : "false",
        nrfStartError, static_cast<unsigned>(nrfStatusReadback),
        static_cast<unsigned>(nrfConfigReadback),
        static_cast<unsigned>(nrfChannelReadback),
        static_cast<unsigned>(nrfRfSetupReadback),
        ccTransmitActive ? "true" : "false",
        ccIdle ? "true" : "false",
        ccPowerCleared ? "true" : "false",
        ccTxFifoCleared ? "true" : "false", ccStartError,
        static_cast<unsigned>(ccStatusReadback),
        static_cast<unsigned>(ccPartNumberReadback),
        static_cast<unsigned>(ccVersionReadback),
        static_cast<unsigned>(ccMarcStateReadback),
        static_cast<unsigned long>(ccTxStrobes),
        static_cast<unsigned long>(ccPowerTableWrites),
        static_cast<unsigned long>(ccTxFifoWrites),
        static_cast<unsigned long>(ccTxFifoBytes),
        watchdogReady ? "true" : "false", report.lastError);
}

void emitError(const char* reason) {
    quiesceOutputs();
    session.panic(outputsInactive() && nrfPoweredDown);
    Serial.printf(
        "{\"schema\":\"leshy.hil.fixture.signal.v1\",\"kind\":\"error\","
        "\"reason\":\"%s\",\"state\":\"%s\","
        "\"ir_tx_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"nrf_powered_down\":%s,\"buzzer_inactive\":%s,"
        "\"nrf_start_error\":\"%s\",\"nrf_status_readback\":%u,"
        "\"nrf_config_readback\":%u,\"nrf_channel_readback\":%u,"
        "\"nrf_rf_setup_readback\":%u,"
        "\"cc_transmit_active\":%s,\"cc_idle\":%s,"
        "\"cc_power_cleared\":%s,\"cc_tx_fifo_cleared\":%s,"
        "\"cc_start_error\":\"%s\",\"cc_status_readback\":%u,"
        "\"cc_part_number\":%u,\"cc_version\":%u,"
        "\"cc_marc_state\":%u,\"cc_tx_strobes\":%lu,"
        "\"cc_patable_writes\":%lu,\"cc_tx_fifo_writes\":%lu,"
        "\"cc_tx_fifo_bytes\":%lu}\n",
        reason, fixtureStateName(session.report().state),
        gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0 ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
                gpio_get_level(
                    static_cast<gpio_num_t>(kNrfCe3SharedPin)) == 0
            ? "true" : "false",
        nrfPoweredDown ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0
            ? "true" : "false",
        nrfStartError, static_cast<unsigned>(nrfStatusReadback),
        static_cast<unsigned>(nrfConfigReadback),
        static_cast<unsigned>(nrfChannelReadback),
        static_cast<unsigned>(nrfRfSetupReadback),
        ccTransmitActive ? "true" : "false",
        ccIdle ? "true" : "false",
        ccPowerCleared ? "true" : "false",
        ccTxFifoCleared ? "true" : "false", ccStartError,
        static_cast<unsigned>(ccStatusReadback),
        static_cast<unsigned>(ccPartNumberReadback),
        static_cast<unsigned>(ccVersionReadback),
        static_cast<unsigned>(ccMarcStateReadback),
        static_cast<unsigned long>(ccTxStrobes),
        static_cast<unsigned long>(ccPowerTableWrites),
        static_cast<unsigned long>(ccTxFifoWrites),
        static_cast<unsigned long>(ccTxFifoBytes));
}

void emitNrfInventory() {
    Serial.printf(
        "{\"schema\":\"leshy.hil.fixture.signal.v1\","
        "\"kind\":\"nrf24_inventory\",\"version\":\"%s\","
        "\"role\":\"bounded_signal_fixture\",\"fixture_id\":\"%s\","
        "\"session_id\":\"%s\",\"nrf_powered_down\":%s,"
        "\"read_only\":true,\"spi_hz\":2000000,\"ce_high_events\":0,"
        "\"primary_miso\":13,\"primary_mosi\":11,"
        "\"primary_status\":[%u,%u,%u],"
        "\"primary_config\":[%u,%u,%u],"
        "\"primary_channel\":[%u,%u,%u],"
        "\"primary_rf_setup\":[%u,%u,%u],\"primary_mask\":%u,"
        "\"primary_cc_status\":%u,\"primary_cc_part\":%u,"
        "\"primary_cc_version\":%u,\"primary_cc_read_complete\":%s,"
        "\"primary_cc_plausible\":%s,"
        "\"swapped_miso\":11,\"swapped_mosi\":13,"
        "\"swapped_status\":[%u,%u,%u],"
        "\"swapped_config\":[%u,%u,%u],"
        "\"swapped_channel\":[%u,%u,%u],"
        "\"swapped_rf_setup\":[%u,%u,%u],\"swapped_mask\":%u,"
        "\"swapped_cc_status\":%u,\"swapped_cc_part\":%u,"
        "\"swapped_cc_version\":%u,\"swapped_cc_read_complete\":%s,"
        "\"swapped_cc_plausible\":%s,\"cc_identity_attempted\":true,"
        "\"ir_tx_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"nrf_carrier_active\":%s,\"buzzer_inactive\":%s,"
        "\"output_inactive\":%s}\n",
        LESHY_FIXTURE_VERSION, runningFixtureId, session.sessionId(),
        nrfPoweredDown ? "true" : "false",
        static_cast<unsigned>(nrfPrimaryInventory.status[0]),
        static_cast<unsigned>(nrfPrimaryInventory.status[1]),
        static_cast<unsigned>(nrfPrimaryInventory.status[2]),
        static_cast<unsigned>(nrfPrimaryInventory.config[0]),
        static_cast<unsigned>(nrfPrimaryInventory.config[1]),
        static_cast<unsigned>(nrfPrimaryInventory.config[2]),
        static_cast<unsigned>(nrfPrimaryInventory.channel[0]),
        static_cast<unsigned>(nrfPrimaryInventory.channel[1]),
        static_cast<unsigned>(nrfPrimaryInventory.channel[2]),
        static_cast<unsigned>(nrfPrimaryInventory.rfSetup[0]),
        static_cast<unsigned>(nrfPrimaryInventory.rfSetup[1]),
        static_cast<unsigned>(nrfPrimaryInventory.rfSetup[2]),
        static_cast<unsigned>(nrfPrimaryInventory.plausibleMask),
        static_cast<unsigned>(nrfPrimaryInventory.ccStatus),
        static_cast<unsigned>(nrfPrimaryInventory.ccPartNumber),
        static_cast<unsigned>(nrfPrimaryInventory.ccVersion),
        nrfPrimaryInventory.ccReadComplete ? "true" : "false",
        nrfPrimaryInventory.ccPlausible ? "true" : "false",
        static_cast<unsigned>(nrfSwappedInventory.status[0]),
        static_cast<unsigned>(nrfSwappedInventory.status[1]),
        static_cast<unsigned>(nrfSwappedInventory.status[2]),
        static_cast<unsigned>(nrfSwappedInventory.config[0]),
        static_cast<unsigned>(nrfSwappedInventory.config[1]),
        static_cast<unsigned>(nrfSwappedInventory.config[2]),
        static_cast<unsigned>(nrfSwappedInventory.channel[0]),
        static_cast<unsigned>(nrfSwappedInventory.channel[1]),
        static_cast<unsigned>(nrfSwappedInventory.channel[2]),
        static_cast<unsigned>(nrfSwappedInventory.rfSetup[0]),
        static_cast<unsigned>(nrfSwappedInventory.rfSetup[1]),
        static_cast<unsigned>(nrfSwappedInventory.rfSetup[2]),
        static_cast<unsigned>(nrfSwappedInventory.plausibleMask),
        static_cast<unsigned>(nrfSwappedInventory.ccStatus),
        static_cast<unsigned>(nrfSwappedInventory.ccPartNumber),
        static_cast<unsigned>(nrfSwappedInventory.ccVersion),
        nrfSwappedInventory.ccReadComplete ? "true" : "false",
        nrfSwappedInventory.ccPlausible ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0
            ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
                gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 0 &&
                gpio_get_level(
                    static_cast<gpio_num_t>(kNrfCe3SharedPin)) == 0
            ? "true" : "false",
        nrfCarrierActive ? "true" : "false",
        gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0
            ? "true" : "false",
        outputsInactive() ? "true" : "false");
}

void mark(std::uint32_t durationUs) {
    ledcWrite(kIrTxPin, kCarrierDuty);
    delayMicroseconds(durationUs);
    ledcWrite(kIrTxPin, 0);
}

void space(std::uint32_t durationUs) {
    ledcWrite(kIrTxPin, 0);
    delayMicroseconds(durationUs);
}

std::uint32_t emitFixedNecVector() {
    const std::uint32_t started = micros();
    mark(9000);
    space(4500);
    for (std::uint8_t bit = 0; bit < 32; ++bit) {
        mark(560);
        space((kNecCode & (1UL << bit)) != 0 ? 1690 : 560);
    }
    mark(560);
    quiesceOutputs();
    return static_cast<std::uint32_t>(micros() - started);
}

bool startFixedNrf24Carrier() {
    nrfStatusReadback = 0xFF;
    nrfConfigReadback = 0xFF;
    nrfChannelReadback = 0xFF;
    nrfRfSetupReadback = 0xFF;
    if (nrfCarrierActive) {
        nrfStartError = "already_active";
        return false;
    }
    if (nrfBusStarted || ccBusStarted || ccTransactionOpen ||
        ccTransmitActive) {
        nrfStartError = "spi_already_active";
        return false;
    }
    if (!outputsInactive()) {
        nrfStartError = "output_not_inactive";
        return false;
    }
    if (!nrfPoweredDown) {
        nrfStartError = "not_powered_down";
        return false;
    }
    nrfStartError = "configuring";
    beginNrfBus();
    nrfStatusReadback = nrfWriteRegister(kNrfRegConfig, 0x00);
    nrfWriteRegister(kNrfRegEnableAutoAck, 0x00);
    nrfWriteRegister(kNrfRegEnableReceiveAddress, 0x00);
    nrfWriteRegister(kNrfRegRfChannel, kNrfChannel);
    nrfWriteRegister(kNrfRegRfSetup, kNrfMinimumPowerCarrierSetup);
    nrfWriteRegister(kNrfRegConfig, 0x02);
    nrfChannelReadback = nrfReadRegister(
        kNrfRegRfChannel, &nrfStatusReadback);
    nrfRfSetupReadback = nrfReadRegister(kNrfRegRfSetup);
    nrfConfigReadback = nrfReadRegister(kNrfRegConfig);
    if (nrfChannelReadback != kNrfChannel) {
        nrfStartError = "channel_readback_mismatch";
        stopNrfCarrier();
        return false;
    }
    if (nrfRfSetupReadback != kNrfMinimumPowerCarrierSetup) {
        nrfStartError = "rf_setup_readback_mismatch";
        stopNrfCarrier();
        return false;
    }
    if ((nrfConfigReadback & 0x03U) != 0x02U) {
        nrfStartError = "config_readback_mismatch";
        stopNrfCarrier();
        return false;
    }
    delayMicroseconds(2000);
    nrfPoweredDown = false;
    nrfCarrierStartedUs = micros();
    digitalWrite(kFixtureNrfCePin, HIGH);
    nrfCarrierActive = true;
    nrfStartError = "none";
    return true;
}

bool nrfCarrierOutputValid() {
    return nrfCarrierActive &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe1Pin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kNrfCe2Pin)) == 1 &&
           gpio_get_level(static_cast<gpio_num_t>(kBuzzerPin)) == 0 &&
           gpio_get_level(static_cast<gpio_num_t>(kIrTxPin)) == 0;
}

void serviceFixtureHardware() {
    if (!nrfCarrierActive) {
        quiesceOutputs();
        session.service(millis(), outputsInactive() && nrfPoweredDown);
        return;
    }
    const std::uint32_t durationUs =
        static_cast<std::uint32_t>(micros() - nrfCarrierStartedUs);
    if (!nrfCarrierOutputValid()) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
        return;
    }
    if (durationUs < leshy::hil::fixture::kNrf24CarrierDurationUs) return;
    const bool inactive = stopNrfCarrier() && outputsInactive();
    session.complete(durationUs, inactive);
}

char* nextToken(char** context) {
    return strtok_r(nullptr, " ", context);
}

void handleCommand(char* line) {
    char* context = nullptr;
    const char* command = strtok_r(line, " ", &context);
    if (command == nullptr) return;
    if (std::strcmp(command, "ping") == 0) {
        Serial.println(
            "{\"schema\":\"leshy.boot.v1\",\"kind\":\"pong\","
            "\"fixture\":true}");
        return;
    }
    if (std::strcmp(command, "fixture.identity") == 0) {
        emitState("ready");
        return;
    }
    if (std::strcmp(command, "fixture.state") == 0) {
        serviceFixtureHardware();
        emitState("state");
        return;
    }
    if (std::strcmp(command, "fixture.nrf24.inventory") == 0) {
        if (nextToken(&context) != nullptr) {
            emitError("unexpected_argument");
            return;
        }
        quiesceOutputs();
        if (!probeNrfInventory()) {
            emitError("nrf24_inventory_unavailable");
            return;
        }
        emitNrfInventory();
        return;
    }
    if (std::strcmp(command, "fixture.begin") == 0) {
        const char* sessionId = nextToken(&context);
        const char* appSha256 = nextToken(&context);
        const char* fixtureId = nextToken(&context);
        if (nextToken(&context) != nullptr ||
            !session.begin(sessionId, appSha256, runningAppSha256,
                           fixtureId, runningFixtureId, millis(),
                           outputsInactive() && nrfPoweredDown)) {
            emitError(session.report().lastError);
            return;
        }
        emitState("armed");
        return;
    }
    if (std::strcmp(command, "fixture.ir.nec.once") == 0) {
        const char* sessionId = nextToken(&context);
        const char* vectorId = nextToken(&context);
        const bool carrierPrepared = configureIrCarrier();
        if (nextToken(&context) != nullptr || !carrierPrepared ||
            !session.authorizeNecOnce(sessionId, vectorId, millis())) {
            emitError(carrierPrepared ? session.report().lastError
                                      : "carrier_unavailable");
            return;
        }
        const std::uint32_t durationUs = emitFixedNecVector();
        if (!session.complete(durationUs, outputsInactive())) {
            emitError(session.report().lastError);
            return;
        }
        emitState("result");
        return;
    }
    if (std::strcmp(command, "fixture.nrf24.carrier.start") == 0) {
        const char* sessionId = nextToken(&context);
        const char* vectorId = nextToken(&context);
        if (nextToken(&context) != nullptr ||
            !session.authorizeNrf24CarrierOnce(
                sessionId, vectorId, millis())) {
            emitError(session.report().lastError);
            return;
        }
        if (!startFixedNrf24Carrier()) {
            emitError("nrf24_carrier_unavailable");
            return;
        }
        emitState("running");
        return;
    }
    if (std::strcmp(command, "fixture.cc1101.ook.once") == 0 ||
        std::strcmp(command, "fixture.cc1101.fsk.once") == 0) {
        const bool fsk = std::strcmp(
            command, "fixture.cc1101.fsk.once") == 0;
        const char* sessionId = nextToken(&context);
        const char* vectorId = nextToken(&context);
        const bool authorized = fsk
            ? session.authorizeCc1101FskOnce(
                  sessionId, vectorId, millis())
            : session.authorizeCc1101OokOnce(
                  sessionId, vectorId, millis());
        if (nextToken(&context) != nullptr || !authorized) {
            emitError(session.report().lastError);
            return;
        }
        const std::uint32_t durationUs = emitFixedCcVector(fsk);
        if (durationUs == 0U ||
            !session.complete(
                durationUs, outputsInactive() && nrfPoweredDown)) {
            emitError(durationUs == 0U ? ccStartError
                                       : session.report().lastError);
            return;
        }
        emitState("result");
        return;
    }
    if (std::strcmp(command, "fixture.stop") == 0) {
        const char* sessionId = nextToken(&context);
        quiesceOutputs();
        if (nextToken(&context) != nullptr ||
            !session.stop(sessionId, outputsInactive() && nrfPoweredDown)) {
            emitError(session.report().lastError);
            return;
        }
        emitState("state");
        return;
    }
    if (std::strcmp(command, "fixture.panic") == 0) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
        emitState("state");
        return;
    }
    emitError("unknown_command");
}

void pollConsole() {
    while (Serial.available() > 0) {
        const char value = static_cast<char>(Serial.read());
        if (value == '\r') continue;
        if (value == '\n') {
            commandBuffer[commandLength] = '\0';
            handleCommand(commandBuffer);
            commandLength = 0;
        } else if (commandLength + 1U < sizeof(commandBuffer)) {
            commandBuffer[commandLength++] = value;
        } else {
            commandLength = 0;
            emitError("command_too_long");
        }
    }
}

}  // namespace

extern "C" void IRAM_ATTR esp_task_wdt_isr_user_handler() {
    quiesceFromIsr();
}

void setup() {
    establishBootInvariant();
    formatIdentity();
    Serial.begin(kConsoleBaud);
    const esp_err_t watchdogStatus = esp_task_wdt_status(nullptr);
    watchdogReady = watchdogStatus == ESP_OK ||
        (watchdogStatus == ESP_ERR_NOT_FOUND &&
         esp_task_wdt_add(nullptr) == ESP_OK);
    if (watchdogReady) watchdogReady = esp_task_wdt_reset() == ESP_OK;
    if (!carrierReady || !watchdogReady || !identityReady || !nrfPoweredDown ||
        !outputsInactive()) {
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
    }
    delay(20);
    emitState("ready");
}

void loop() {
    pollConsole();
    serviceFixtureHardware();
    if (watchdogReady && esp_task_wdt_reset() != ESP_OK) {
        watchdogReady = false;
        quiesceOutputs();
        session.panic(outputsInactive() && nrfPoweredDown);
    }
    delay(1);
}
