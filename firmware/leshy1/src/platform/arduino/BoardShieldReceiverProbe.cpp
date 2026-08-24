#include "platform/arduino/BoardShieldReceiverProbe.h"

#include <Arduino.h>
#include <SPI.h>

#include "boards/esp32_div_v2/BoardProfile.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
using drivers::radio::ShieldReceiverProbeReport;

constexpr std::uint32_t kProbeSpiHz = 1000000;
constexpr std::uint8_t kNrfNop = 0xFF;
constexpr std::uint8_t kNrfReadRegister = 0x00;
constexpr std::uint8_t kNrfRegConfig = 0x00;
constexpr std::uint8_t kNrfRegRfChannel = 0x05;
constexpr std::uint8_t kNrfRegRfSetup = 0x06;
constexpr std::uint8_t kNrfRegFeature = 0x1D;
constexpr std::uint8_t kCcReadPartNumber = 0xF0;
constexpr std::uint8_t kCcReadVersion = 0xF1;
constexpr std::uint32_t kCcReadyTimeoutUs = 2000;
constexpr std::uint8_t kMisoSamplesPerPull = 32;
constexpr std::uint32_t kMisoSettleUs = 100;
constexpr std::uint32_t kBitBangHalfPeriodUs = 5;

}  // namespace

void BoardShieldReceiverProbe::holdTransmitPathsInactive() {
    for (const int pin : BoardProfile::kNrfCePins) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
    pinMode(BoardProfile::kNrfCsPins[2], INPUT);
}

bool BoardShieldReceiverProbe::gpio21Safe() const {
    return digitalRead(BoardProfile::kNrfCsPins[2]) == HIGH;
}

std::uint8_t BoardShieldReceiverProbe::sampleMisoHigh(int inputMode) {
    pinMode(BoardProfile::kRadioMisoPin, inputMode);
    delayMicroseconds(kMisoSettleUs);
    std::uint8_t highSamples = 0;
    for (std::uint8_t sample = 0; sample < kMisoSamplesPerPull; ++sample) {
        if (digitalRead(BoardProfile::kRadioMisoPin) == HIGH) ++highSamples;
        delayMicroseconds(2);
    }
    return highSamples;
}

std::uint8_t BoardShieldReceiverProbe::readNrfNopBitBang(
    int chipSelect, int inputMode) {
    pinMode(BoardProfile::kRadioMisoPin, inputMode);
    pinMode(BoardProfile::kRadioSckPin, OUTPUT);
    pinMode(BoardProfile::kRadioMosiPin, OUTPUT);
    digitalWrite(BoardProfile::kRadioSckPin, LOW);
    digitalWrite(BoardProfile::kRadioMosiPin,
                 (kNrfNop & 0x80U) != 0U ? HIGH : LOW);
    digitalWrite(chipSelect, LOW);
    delayMicroseconds(kBitBangHalfPeriodUs);

    std::uint8_t status = 0;
    for (std::uint8_t bit = 0; bit < 8; ++bit) {
        // NOP is all ones. Mode 0 samples MISO on the rising edge and never
        // mutates a register, FIFO, mode or carrier state.
        const std::uint8_t mask = static_cast<std::uint8_t>(0x80U >> bit);
        digitalWrite(BoardProfile::kRadioMosiPin,
                     (kNrfNop & mask) != 0U ? HIGH : LOW);
        delayMicroseconds(kBitBangHalfPeriodUs);
        digitalWrite(BoardProfile::kRadioSckPin, HIGH);
        delayMicroseconds(kBitBangHalfPeriodUs);
        status = static_cast<std::uint8_t>(
            (status << 1U) |
            (digitalRead(BoardProfile::kRadioMisoPin) == HIGH ? 1U : 0U));
        digitalWrite(BoardProfile::kRadioSckPin, LOW);
        delayMicroseconds(kBitBangHalfPeriodUs);
    }
    digitalWrite(chipSelect, HIGH);
    digitalWrite(BoardProfile::kRadioMosiPin, LOW);
    pinMode(BoardProfile::kRadioMosiPin, INPUT);
    pinMode(BoardProfile::kRadioSckPin, INPUT);
    pinMode(BoardProfile::kRadioMisoPin, INPUT);
    if (report_ != nullptr) {
        ++report_->nrfNopReads;
        ++report_->bitBangSpiBytesClocked;
    }
    return status;
}

void BoardShieldReceiverProbe::characterizeBusLine() {
    if (report_ == nullptr) return;
    // Sampling an input under the two internal pulls does not clock or select
    // any receiver. Keep this evidence even when the detachable RF carrier is
    // absent and GPIO21 therefore cannot satisfy the assembled-shield guard.
    report_->misoSamplesPerPull = kMisoSamplesPerPull;
    report_->misoIdlePullDownHighSamples = sampleMisoHigh(INPUT_PULLDOWN);
    report_->misoIdlePullUpHighSamples = sampleMisoHigh(INPUT_PULLUP);
    pinMode(BoardProfile::kRadioMisoPin, INPUT);
    if (!gpio21Safe()) return;

    for (std::size_t slot = 0; slot < report_->nrfNopStatusPullDown.size();
         ++slot) {
        if (!gpio21Safe()) return;
        report_->nrfNopStatusPullDown[slot] = readNrfNopBitBang(
            BoardProfile::kNrfCsPins[slot], INPUT_PULLDOWN);
        if (!gpio21Safe()) return;
        report_->nrfNopStatusPullUp[slot] = readNrfNopBitBang(
            BoardProfile::kNrfCsPins[slot], INPUT_PULLUP);
    }
    report_->busLineCharacterizationComplete =
        report_->nrfNopReads == 4 &&
        report_->bitBangSpiBytesClocked == 4 && gpio21Safe();
}

std::uint8_t BoardShieldReceiverProbe::transfer(std::uint8_t value) {
    if (report_ != nullptr) ++report_->spiBytesClocked;
    return SPI.transfer(value);
}

std::uint8_t BoardShieldReceiverProbe::readNrfRegister(
    int chipSelect, std::uint8_t reg, std::uint8_t* status) {
    if (!gpio21Safe()) return 0xFF;
    digitalWrite(chipSelect, LOW);
    *status = transfer(kNrfReadRegister | (reg & 0x1FU));
    const std::uint8_t value = transfer(0xFF);
    digitalWrite(chipSelect, HIGH);
    if (!gpio21Safe()) return 0xFF;
    if (report_ != nullptr) ++report_->nrfRegisterReads;
    return value;
}

drivers::radio::NrfReceiverIdentity BoardShieldReceiverProbe::readNrf(
    int chipSelect) {
    drivers::radio::NrfReceiverIdentity result;
    result.config = readNrfRegister(chipSelect, kNrfRegConfig, &result.status);
    std::uint8_t ignored = 0;
    result.channel = readNrfRegister(chipSelect, kNrfRegRfChannel, &ignored);
    result.rfSetup = readNrfRegister(chipSelect, kNrfRegRfSetup, &ignored);
    result.feature = readNrfRegister(chipSelect, kNrfRegFeature, &ignored);
    return result;
}

bool BoardShieldReceiverProbe::readCcStatus(std::uint8_t address,
                                            std::uint8_t* status,
                                            std::uint8_t* value) {
    if (!gpio21Safe()) return false;
    digitalWrite(BoardProfile::kCc1101CsPin, LOW);
    const std::uint32_t started = micros();
    while (digitalRead(BoardProfile::kRadioMisoPin) != LOW) {
        if (micros() - started > kCcReadyTimeoutUs) {
            digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
            return false;
        }
    }
    *status = transfer(address);
    *value = transfer(0xFF);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    if (!gpio21Safe()) return false;
    if (report_ != nullptr) ++report_->ccStatusReads;
    return true;
}

void BoardShieldReceiverProbe::cleanup() {
    digitalWrite(BoardProfile::kNrfCsPins[0], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[1], HIGH);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    if (transactionOpen_) {
        SPI.endTransaction();
        transactionOpen_ = false;
    }
    if (spiStarted_) {
        SPI.end();
        spiStarted_ = false;
    }
    pinMode(BoardProfile::kRadioMosiPin, INPUT);
    pinMode(BoardProfile::kRadioMisoPin, INPUT);
    pinMode(BoardProfile::kRadioSckPin, INPUT);
    holdTransmitPathsInactive();
    if (report_ != nullptr) {
        report_->gpio21StableHigh = gpio21Safe();
        report_->cleanupComplete =
            digitalRead(BoardProfile::kNrfCsPins[0]) == HIGH &&
            digitalRead(BoardProfile::kNrfCsPins[1]) == HIGH &&
            digitalRead(BoardProfile::kCc1101CsPin) == HIGH &&
            digitalRead(BoardProfile::kSdCsPin) == HIGH &&
            digitalRead(BoardProfile::kNrfCePins[0]) == LOW &&
            digitalRead(BoardProfile::kNrfCePins[1]) == LOW &&
            digitalRead(BoardProfile::kNrfCePins[2]) == LOW &&
            report_->gpio21StableHigh;
    }
}

bool BoardShieldReceiverProbe::run(bool radioSpiOwned,
                                   ShieldReceiverProbeReport* report) {
    if (report == nullptr) return false;
    *report = {};
    report_ = report;
    report_->profileDeclared = BoardProfile::kRfShieldDeclared;
    report_->gpsExcludedByProfile = !BoardProfile::kGpsDeclared;
    report_->pn532ExcludedByProfile = !BoardProfile::kPn532Declared;
    report_->resourceAcquired = radioSpiOwned;
    if (!report_->profileDeclared || !report_->gpsExcludedByProfile ||
        !report_->pn532ExcludedByProfile || !report_->resourceAcquired) {
        drivers::radio::finalizeShieldReceiverProbe(report_);
        report_ = nullptr;
        return false;
    }

    holdTransmitPathsInactive();
    pinMode(BoardProfile::kNrfCsPins[0], OUTPUT);
    pinMode(BoardProfile::kNrfCsPins[1], OUTPUT);
    pinMode(BoardProfile::kCc1101CsPin, OUTPUT);
    pinMode(BoardProfile::kSdCsPin, OUTPUT);
    digitalWrite(BoardProfile::kNrfCsPins[0], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[1], HIGH);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    characterizeBusLine();
    if (!report_->busLineCharacterizationComplete || !gpio21Safe()) {
        cleanup();
        drivers::radio::finalizeShieldReceiverProbe(report_);
        report_ = nullptr;
        return false;
    }

    SPI.begin(BoardProfile::kRadioSckPin, BoardProfile::kRadioMisoPin,
              BoardProfile::kRadioMosiPin, -1);
    spiStarted_ = true;
    SPI.beginTransaction(SPISettings(kProbeSpiHz, MSBFIRST, SPI_MODE0));
    transactionOpen_ = true;

    report_->nrf[0] = readNrf(BoardProfile::kNrfCsPins[0]);
    if (gpio21Safe()) report_->nrf[1] = readNrf(BoardProfile::kNrfCsPins[1]);
    if (gpio21Safe()) {
        std::uint8_t partStatus = 0xFF;
        std::uint8_t versionStatus = 0xFF;
        report_->cc1101.ready =
            readCcStatus(kCcReadPartNumber, &partStatus,
                         &report_->cc1101.partNumber) &&
            readCcStatus(kCcReadVersion, &versionStatus,
                         &report_->cc1101.version);
        report_->cc1101.status = versionStatus;
    }
    cleanup();
    drivers::radio::finalizeShieldReceiverProbe(report_);
    const bool passed = report_->status ==
        drivers::radio::ShieldReceiverProbeStatus::Pass;
    report_ = nullptr;
    return passed;
}

}  // namespace leshy1::platform::arduino
