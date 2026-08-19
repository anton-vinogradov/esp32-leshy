#include "platform/arduino/BoardNrf24PassiveSpectrum.h"

#include <Arduino.h>
#include <SPI.h>
#include <esp_timer.h>

#include "boards/esp32_div_v2/BoardProfile.h"
#include "drivers/radio/ShieldReceiverIdentity.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
using drivers::radio::NrfReceiverIdentity;
using drivers::radio::Nrf24PassiveSpectrumStatus;

// 0.x used 8 MHz reliably on this exact shield. The faster clock leaves enough
// time for a complete two-receiver sweep per 13.4 ms waterfall row.
constexpr std::uint32_t kSpectrumSpiHz = 8000000;
constexpr std::uint8_t kReadRegister = 0x00;
constexpr std::uint8_t kWriteRegister = 0x20;
constexpr std::uint8_t kRegConfig = 0x00;
constexpr std::uint8_t kRegEnableAutoAck = 0x01;
constexpr std::uint8_t kRegEnableReceiveAddress = 0x02;
constexpr std::uint8_t kRegRfChannel = 0x05;
constexpr std::uint8_t kRegRfSetup = 0x06;
constexpr std::uint8_t kRegRpd = 0x09;
constexpr std::uint8_t kRegFeature = 0x1D;
constexpr std::uint8_t kReceiveConfig = 0x03;
constexpr std::uint8_t kOneMbpsSetup = 0x06;

}  // namespace

std::uint8_t BoardNrf24PassiveSpectrum::transfer(std::uint8_t value) {
    if (report_ != nullptr) ++report_->spiBytesClocked;
    return SPI.transfer(value);
}

bool BoardNrf24PassiveSpectrum::gpio21Safe() const {
    return digitalRead(BoardProfile::kNrfCsPins[2]) == HIGH;
}

void BoardNrf24PassiveSpectrum::holdAllCeLow() {
    for (const int pin : BoardProfile::kNrfCePins) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
}

std::uint8_t BoardNrf24PassiveSpectrum::readRegister(
    std::uint8_t module, std::uint8_t reg, std::uint8_t* status) {
    if (module >= 3 || !gpio21Safe()) return 0xFF;
    const std::uint8_t slot = activeSlots_[module];
    digitalWrite(BoardProfile::kNrfCsPins[slot], LOW);
    const std::uint8_t commandStatus =
        transfer(kReadRegister | (reg & 0x1FU));
    const std::uint8_t value = transfer(0xFF);
    digitalWrite(BoardProfile::kNrfCsPins[slot], HIGH);
    if (status != nullptr) *status = commandStatus;
    if (report_ != nullptr) ++report_->registerReads;
    return gpio21Safe() ? value : 0xFF;
}

void BoardNrf24PassiveSpectrum::writeRegister(
    std::uint8_t module, std::uint8_t reg, std::uint8_t value) {
    if (module >= 3 || !gpio21Safe()) return;
    const std::uint8_t slot = activeSlots_[module];
    digitalWrite(BoardProfile::kNrfCsPins[slot], LOW);
    transfer(kWriteRegister | (reg & 0x1FU));
    transfer(value);
    digitalWrite(BoardProfile::kNrfCsPins[slot], HIGH);
    if (report_ != nullptr) ++report_->registerWrites;
}

bool BoardNrf24PassiveSpectrum::configureReceive(std::uint8_t module) {
    writeRegister(module, kRegConfig, 0x00);
    writeRegister(module, kRegEnableAutoAck, 0x00);
    writeRegister(module, kRegEnableReceiveAddress, 0x00);
    writeRegister(module, kRegRfSetup, kOneMbpsSetup);
    writeRegister(module, kRegConfig, kReceiveConfig);
    return gpio21Safe();
}

void BoardNrf24PassiveSpectrum::cleanupPinsAndSpi() {
    holdAllCeLow();
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
    pinMode(BoardProfile::kNrfCsPins[2], INPUT);
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

bool BoardNrf24PassiveSpectrum::begin(
    bool radioSpiOwned,
    const drivers::radio::Nrf24PassiveSpectrumPlan& plan,
    drivers::radio::Nrf24PassiveSpectrumReport* report) {
    if (report == nullptr || active_ || spiStarted_) return false;
    *report = {};
    report_ = report;
    plan_ = plan;
    report_->profileDeclared = BoardProfile::kRfShieldDeclared;
    report_->gpsExcludedByProfile = !BoardProfile::kGpsDeclared;
    report_->pn532ExcludedByProfile = !BoardProfile::kPn532Declared;
    report_->resourceOwned = radioSpiOwned;
    report_->cleanupComplete = false;
    if (!drivers::radio::validateNrf24PassiveSpectrumPlan(plan_)) {
        report_->status = Nrf24PassiveSpectrumStatus::Fault;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }
    if (!report_->profileDeclared || !report_->gpsExcludedByProfile ||
        !report_->pn532ExcludedByProfile) {
        report_->status = Nrf24PassiveSpectrumStatus::RefusedProfile;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }
    if (!report_->resourceOwned) {
        report_->status = Nrf24PassiveSpectrumStatus::Busy;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }

    holdAllCeLow();
    pinMode(BoardProfile::kNrfCsPins[0], OUTPUT);
    pinMode(BoardProfile::kNrfCsPins[1], OUTPUT);
    pinMode(BoardProfile::kNrfCsPins[2], OUTPUT);
    pinMode(BoardProfile::kCc1101CsPin, OUTPUT);
    pinMode(BoardProfile::kSdCsPin, OUTPUT);
    digitalWrite(BoardProfile::kNrfCsPins[0], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[1], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[2], HIGH);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    if (!gpio21Safe()) {
        report_->status = Nrf24PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
        return false;
    }

    SPI.begin(BoardProfile::kRadioSckPin, BoardProfile::kRadioMisoPin,
              BoardProfile::kRadioMosiPin, -1);
    spiStarted_ = true;
    SPI.beginTransaction(SPISettings(kSpectrumSpiHz, MSBFIRST, SPI_MODE0));
    transactionOpen_ = true;

    if (BoardProfile::kIrDeclared) {
        report_->status = Nrf24PassiveSpectrumStatus::RefusedProfile;
        cleanupPinsAndSpi();
        report_ = nullptr;
        return false;
    }
    for (std::uint8_t slot = 0; slot < plan_.maximumModules; ++slot) {
        const std::uint8_t module = report_->detectedModules;
        activeSlots_[module] = slot;
        NrfReceiverIdentity identity;
        identity.config = readRegister(module, kRegConfig, &identity.status);
        identity.channel = readRegister(module, kRegRfChannel);
        identity.rfSetup = readRegister(module, kRegRfSetup);
        identity.feature = readRegister(module, kRegFeature);
        if (drivers::radio::plausibleNrfReceiverIdentity(identity)) {
            ++report_->detectedModules;
            report_->activeSlotMask = static_cast<std::uint8_t>(
                report_->activeSlotMask | (1U << slot));
        }
    }
    if (report_->detectedModules == 0 || !gpio21Safe()) {
        report_->status = Nrf24PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
        return false;
    }
    for (std::uint8_t module = 0;
         module < report_->detectedModules; ++module) {
        if (!configureReceive(module)) {
            report_->status = Nrf24PassiveSpectrumStatus::Fault;
            cleanupPinsAndSpi();
            report_ = nullptr;
            return false;
        }
    }
    delayMicroseconds(2000);
    for (std::uint8_t module = 0;
         module < report_->detectedModules; ++module) {
        if ((readRegister(module, kRegConfig) & 0x03U) != kReceiveConfig) {
            report_->status = Nrf24PassiveSpectrumStatus::Fault;
            cleanupPinsAndSpi();
            report_ = nullptr;
            return false;
        }
    }
    report_->gpio21StableHigh = gpio21Safe();
    report_->status = Nrf24PassiveSpectrumStatus::Ready;
    active_ = drivers::radio::validateNrf24PassiveSpectrumReport(
        *report_, false);
    if (!active_) {
        report_->status = Nrf24PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
    }
    return active_;
}

bool BoardNrf24PassiveSpectrum::sweep(
    drivers::radio::Nrf24PassiveSweep* output) {
    if (!active_ || report_ == nullptr || output == nullptr ||
        report_->status != Nrf24PassiveSpectrumStatus::Ready) {
        return false;
    }
    *output = {};
    output->modules = report_->detectedModules;
    output->startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    std::size_t index = 0;
    while (index < output->hits.size()) {
        std::uint8_t armed = 0;
        for (std::uint8_t module = 0;
             module < report_->detectedModules && index + module < output->hits.size();
             ++module) {
            const std::uint8_t channel = static_cast<std::uint8_t>(
                plan_.firstChannel + index + module);
            writeRegister(module, kRegRfChannel, channel);
            digitalWrite(
                BoardProfile::kNrfCePins[activeSlots_[module]], HIGH);
            ++report_->receiveCeHighEvents;
            ++armed;
        }
        delayMicroseconds(plan_.dwellUs);
        for (std::uint8_t module = 0; module < armed; ++module) {
            digitalWrite(
                BoardProfile::kNrfCePins[activeSlots_[module]], LOW);
            output->hits[index + module] =
                static_cast<std::uint8_t>(readRegister(module, kRegRpd) & 0x01U);
        }
        index += armed;
        if (armed == 0 || !gpio21Safe()) {
            report_->status = Nrf24PassiveSpectrumStatus::Fault;
            output->endedUs = static_cast<std::uint64_t>(esp_timer_get_time());
            return false;
        }
    }
    output->endedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    output->valid = true;
    ++report_->sweeps;
    report_->gpio21StableHigh = gpio21Safe();
    return drivers::radio::validateNrf24PassiveSpectrumReport(*report_, false);
}

bool BoardNrf24PassiveSpectrum::end() {
    if (report_ == nullptr) {
        active_ = false;
        return true;
    }
    holdAllCeLow();
    if (spiStarted_ && transactionOpen_) {
        for (std::uint8_t module = 0;
             module < report_->detectedModules; ++module) {
            writeRegister(module, kRegConfig, 0x00);
        }
    }
    active_ = false;
    cleanupPinsAndSpi();
    const bool complete =
        drivers::radio::validateNrf24PassiveSpectrumReport(*report_, true);
    if (!complete) {
        report_->status = Nrf24PassiveSpectrumStatus::CleanupFailed;
    }
    report_ = nullptr;
    return complete;
}

}  // namespace leshy1::platform::arduino
