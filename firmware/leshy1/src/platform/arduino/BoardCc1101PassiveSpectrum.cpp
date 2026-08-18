#include "platform/arduino/BoardCc1101PassiveSpectrum.h"

#include <Arduino.h>
#include <SPI.h>
#include <esp_timer.h>

#include "boards/esp32_div_v2/BoardProfile.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
using drivers::radio::Cc1101PassiveSpectrumStatus;

constexpr std::uint32_t kSpectrumSpiHz = 1000000;
constexpr std::uint32_t kCrystalKHz = 26000;
constexpr std::uint32_t kReadyTimeoutUs = 2000;
constexpr std::uint8_t kReadStatus = 0xC0;
constexpr std::uint8_t kRegisterPartNumber = 0x30;
constexpr std::uint8_t kRegisterVersion = 0x31;
constexpr std::uint8_t kRegisterRssi = 0x34;
constexpr std::uint8_t kRegisterMarcState = 0x35;
constexpr std::uint8_t kMarcStateReceive = 0x0D;
constexpr std::uint8_t kCommandReset = 0x30;
constexpr std::uint8_t kCommandReceive = 0x34;
constexpr std::uint8_t kCommandIdle = 0x36;

bool allowedReceiveRegister(std::uint8_t address) {
    switch (address) {
        case 0x0B:
        case 0x0D:
        case 0x0E:
        case 0x0F:
        case 0x10:
        case 0x11:
        case 0x12:
        case 0x18:
        case 0x19:
        case 0x1B:
        case 0x1C:
        case 0x1D:
        case 0x23:
        case 0x24:
        case 0x25:
        case 0x26:
        case 0x2C:
        case 0x2D:
        case 0x2E:
            return true;
        default:
            return false;
    }
}

}  // namespace

std::uint8_t BoardCc1101PassiveSpectrum::transfer(std::uint8_t value) {
    if (report_ != nullptr) ++report_->spiBytesClocked;
    return SPI.transfer(value);
}

bool BoardCc1101PassiveSpectrum::gpio21Safe() const {
    return digitalRead(BoardProfile::kNrfCsPins[2]) == HIGH;
}

void BoardCc1101PassiveSpectrum::holdTransmitPathsInactive() {
    for (const int pin : BoardProfile::kNrfCePins) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
    pinMode(BoardProfile::kNrfCsPins[2], INPUT);
}

bool BoardCc1101PassiveSpectrum::selectCc() {
    if (!gpio21Safe()) return false;
    digitalWrite(BoardProfile::kCc1101CsPin, LOW);
    const std::uint64_t started =
        static_cast<std::uint64_t>(esp_timer_get_time());
    while (digitalRead(BoardProfile::kRadioMisoPin) != LOW) {
        const std::uint64_t now =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (now - started > kReadyTimeoutUs) {
            digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
            return false;
        }
    }
    return gpio21Safe();
}

void BoardCc1101PassiveSpectrum::deselectCc() {
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
}

bool BoardCc1101PassiveSpectrum::command(std::uint8_t value) {
    if (report_ == nullptr ||
        (value != kCommandReset && value != kCommandReceive &&
         value != kCommandIdle)) {
        if (report_ != nullptr) ++report_->rejectedStrobes;
        return false;
    }
    if (!selectCc()) return false;
    transfer(value);
    deselectCc();
    ++report_->commandStrobes;
    if (value == kCommandReset) ++report_->resetStrobes;
    if (value == kCommandReceive) ++report_->receiveStrobes;
    if (value == kCommandIdle) ++report_->idleStrobes;
    return gpio21Safe();
}

bool BoardCc1101PassiveSpectrum::writeRegister(
    std::uint8_t address, std::uint8_t value) {
    if (report_ == nullptr || !allowedReceiveRegister(address) ||
        !selectCc()) {
        return false;
    }
    transfer(address);
    transfer(value);
    deselectCc();
    ++report_->registerWrites;
    return gpio21Safe();
}

bool BoardCc1101PassiveSpectrum::readStatus(
    std::uint8_t address, std::uint8_t* value) {
    if (report_ == nullptr || value == nullptr || address < 0x30U ||
        address > 0x3DU || !selectCc()) {
        return false;
    }
    transfer(static_cast<std::uint8_t>(address | kReadStatus));
    *value = transfer(0xFF);
    deselectCc();
    ++report_->registerReads;
    return gpio21Safe();
}

bool BoardCc1101PassiveSpectrum::resetReceiver() {
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    delayMicroseconds(5);
    digitalWrite(BoardProfile::kCc1101CsPin, LOW);
    delayMicroseconds(10);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    delayMicroseconds(45);
    if (!command(kCommandReset)) return false;
    delayMicroseconds(2000);
    return true;
}

bool BoardCc1101PassiveSpectrum::configureReceive() {
    const struct RegisterValue final {
        std::uint8_t address;
        std::uint8_t value;
    } settings[] = {
        {0x0B, 0x08}, {0x10, 0x8C}, {0x11, 0x22}, {0x12, 0x30},
        {0x18, 0x18}, {0x19, 0x16}, {0x1B, 0x43}, {0x1C, 0x40},
        {0x1D, 0x91}, {0x23, 0xE9}, {0x24, 0x2A}, {0x25, 0x00},
        {0x26, 0x1F}, {0x2C, 0x81}, {0x2D, 0x35}, {0x2E, 0x09},
    };
    for (const RegisterValue& setting : settings) {
        if (!writeRegister(setting.address, setting.value)) return false;
    }
    return true;
}

bool BoardCc1101PassiveSpectrum::tune(std::uint32_t frequencyKHz) {
    const std::uint32_t word = static_cast<std::uint32_t>(
        (static_cast<std::uint64_t>(frequencyKHz) << 16U) / kCrystalKHz);
    return writeRegister(0x0D, static_cast<std::uint8_t>(word >> 16U)) &&
           writeRegister(0x0E, static_cast<std::uint8_t>(word >> 8U)) &&
           writeRegister(0x0F, static_cast<std::uint8_t>(word));
}

bool BoardCc1101PassiveSpectrum::waitForReceive(
    std::uint16_t timeoutUs) {
    const std::uint64_t started =
        static_cast<std::uint64_t>(esp_timer_get_time());
    for (;;) {
        std::uint8_t state = 0;
        if (!readStatus(kRegisterMarcState, &state)) return false;
        if ((state & 0x1FU) == kMarcStateReceive) return true;
        const std::uint64_t now =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (now - started > timeoutUs) return false;
    }
}

void BoardCc1101PassiveSpectrum::cleanupPinsAndSpi() {
    holdTransmitPathsInactive();
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

bool BoardCc1101PassiveSpectrum::begin(
    bool radioSpiOwned,
    drivers::radio::Cc1101PassiveSpectrumReport* report) {
    if (report == nullptr || active_ || spiStarted_) return false;
    *report = {};
    report_ = report;
    report_->profileDeclared = BoardProfile::kRfShieldDeclared;
    report_->gpsExcludedByProfile = !BoardProfile::kGpsDeclared;
    report_->pn532ExcludedByProfile = !BoardProfile::kPn532Declared;
    report_->resourceOwned = radioSpiOwned;
    report_->cleanupComplete = false;
    if (!report_->profileDeclared || !report_->gpsExcludedByProfile ||
        !report_->pn532ExcludedByProfile) {
        report_->status = Cc1101PassiveSpectrumStatus::RefusedProfile;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }
    if (!report_->resourceOwned) {
        report_->status = Cc1101PassiveSpectrumStatus::Busy;
        report_->cleanupComplete = true;
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
    if (!gpio21Safe()) {
        report_->status = Cc1101PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
        return false;
    }

    SPI.begin(BoardProfile::kRadioSckPin, BoardProfile::kRadioMisoPin,
              BoardProfile::kRadioMosiPin, -1);
    spiStarted_ = true;
    SPI.beginTransaction(SPISettings(kSpectrumSpiHz, MSBFIRST, SPI_MODE0));
    transactionOpen_ = true;

    if (!resetReceiver() ||
        !readStatus(kRegisterPartNumber, &report_->partNumber) ||
        !readStatus(kRegisterVersion, &report_->version) ||
        !configureReceive()) {
        report_->status = Cc1101PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
        return false;
    }
    report_->receiverDetected = report_->partNumber == 0x00U &&
        report_->version != 0x00U && report_->version != 0xFFU;
    report_->gpio21StableHigh = gpio21Safe();
    report_->status = Cc1101PassiveSpectrumStatus::Ready;
    active_ = drivers::radio::validateCc1101PassiveSpectrumReport(
        *report_, false);
    if (!active_) {
        report_->status = Cc1101PassiveSpectrumStatus::Fault;
        cleanupPinsAndSpi();
        report_ = nullptr;
    }
    return active_;
}

bool BoardCc1101PassiveSpectrum::sample(
    const drivers::radio::Cc1101PassiveSpectrumPlan& plan,
    std::size_t bin,
    drivers::radio::Cc1101PassiveSample* output) {
    if (!active_ || report_ == nullptr || output == nullptr ||
        !drivers::radio::validateCc1101PassiveSpectrumPlan(plan) ||
        bin >= drivers::radio::Cc1101PassiveSpectrumPlan::kBinCount) {
        return false;
    }
    *output = {};
    output->band = plan.band;
    output->bin = static_cast<std::uint8_t>(bin);
    output->frequencyKHz =
        drivers::radio::cc1101SpectrumFrequencyKHz(plan, bin);
    output->startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    std::uint8_t rawRssi = 0;
    const bool sampled = command(kCommandIdle) &&
        tune(output->frequencyKHz) && command(kCommandReceive) &&
        waitForReceive(plan.readyTimeoutUs);
    if (sampled) {
        delayMicroseconds(plan.settleUs);
    }
    const bool read = sampled && readStatus(kRegisterRssi, &rawRssi);
    const bool idled = command(kCommandIdle);
    output->endedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (!read || !idled || !gpio21Safe()) {
        report_->status = Cc1101PassiveSpectrumStatus::Fault;
        return false;
    }
    const int signedRaw = rawRssi >= 128U
        ? static_cast<int>(rawRssi) - 256 : static_cast<int>(rawRssi);
    output->rssiDbm = static_cast<std::int16_t>(signedRaw / 2 - 74);
    output->valid = true;
    ++report_->samples;
    report_->gpio21StableHigh = gpio21Safe();
    return drivers::radio::validateCc1101PassiveSpectrumReport(
        *report_, false);
}

bool BoardCc1101PassiveSpectrum::idle() {
    if (!active_ || report_ == nullptr) return false;
    return command(kCommandIdle);
}

bool BoardCc1101PassiveSpectrum::end() {
    if (report_ == nullptr) {
        active_ = false;
        return true;
    }
    bool idled = true;
    if (spiStarted_ && transactionOpen_) idled = command(kCommandIdle);
    active_ = false;
    cleanupPinsAndSpi();
    const bool complete = idled &&
        drivers::radio::validateCc1101PassiveSpectrumReport(*report_, true);
    if (!complete) {
        report_->status = Cc1101PassiveSpectrumStatus::CleanupFailed;
    }
    report_ = nullptr;
    return complete;
}

}  // namespace leshy1::platform::arduino
