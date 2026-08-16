#include "BoardSdSpiTransport.h"

#include <Arduino.h>
#include <SPI.h>

#include "boards/esp32_div_v2/BoardProfile.h"
#include "storage/SdReadOnlyProtocol.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
constexpr std::uint8_t kSdPowerUpClockBytes = 20;
constexpr std::uint8_t kSdCmd0WireAttempts = 3;
constexpr std::uint32_t kSdCmd0RetryDelayMs = 100;

}  // namespace

void BoardSdSpiTransport::holdRadioTransmitPathsInactive() {
    for (const int pin : BoardProfile::kNrfCePins) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
    pinMode(BoardProfile::kNrfCsPins[2], INPUT);
}

bool BoardSdSpiTransport::guardSharedChipSelect() {
    if (digitalRead(BoardProfile::kNrfCsPins[2]) == HIGH) return true;
    gpio21StableHigh_ = false;
    return false;
}

std::uint8_t BoardSdSpiTransport::transfer(std::uint8_t value) {
    ++bytesClocked_;
    return SPI.transfer(value);
}

bool BoardSdSpiTransport::readByte(std::uint8_t* value) {
    if (value == nullptr || !transactionOpen_ || !selected_) return false;
    *value = transfer(0xFF);
    return true;
}

bool BoardSdSpiTransport::begin() {
    if (transactionOpen_) return false;
    cleanupComplete_ = false;
    gpio21StableHigh_ = true;
    holdRadioTransmitPathsInactive();
    pinMode(BoardProfile::kNrfCsPins[0], OUTPUT);
    pinMode(BoardProfile::kNrfCsPins[1], OUTPUT);
    pinMode(BoardProfile::kCc1101CsPin, OUTPUT);
    pinMode(BoardProfile::kSdCsPin, OUTPUT);
    digitalWrite(BoardProfile::kNrfCsPins[0], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[1], HIGH);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    if (!guardSharedChipSelect()) {
        end();
        return false;
    }

    SPI.begin(BoardProfile::kRadioSckPin, BoardProfile::kRadioMisoPin,
              BoardProfile::kRadioMosiPin, -1);
    physicalSpiStarted_ = true;
    SPI.beginTransaction(SPISettings(BoardProfile::kSdIdentificationSpiHz,
                                     MSBFIRST, SPI_MODE0));
    transactionOpen_ = true;
    delay(2);
    for (std::uint8_t index = 0; index < kSdPowerUpClockBytes; ++index) transfer(0xFF);
    if (!guardSharedChipSelect()) {
        end();
        return false;
    }
    return true;
}

void BoardSdSpiTransport::deselect() {
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    selected_ = false;
    if (transactionOpen_) transfer(0xFF);
}

bool BoardSdSpiTransport::exchange(std::uint8_t command, std::uint32_t argument,
                                   storage::SdCommandResponse* response) {
    ++exchanges_;
    if (!transactionOpen_ || response == nullptr || !guardSharedChipSelect()) return false;
    *response = {};
    const storage::SdReadOnlyPlan plan = storage::defaultSdIdentificationPlan();
    storage::SdCommandFrame frame;
    lastWireStatus_ = storage::encodeSdIdentificationCommand(
        plan, command, argument, &frame);
    if (lastWireStatus_ != storage::SdWireStatus::Valid) return false;

    const std::uint8_t attempts = command == 0 ? kSdCmd0WireAttempts : 1;
    for (std::uint8_t attempt = 0; attempt < attempts; ++attempt) {
        *response = {};
        digitalWrite(BoardProfile::kSdCsPin, LOW);
        selected_ = true;
        for (const std::uint8_t value : frame.bytes) transfer(value);
        lastWireStatus_ = storage::readSdR1(
            *this, storage::kSdMaxR1PollBytes, &response->r1);
        if (lastWireStatus_ == storage::SdWireStatus::Valid &&
            (command == 8 || command == 58)) {
            lastWireStatus_ = storage::readSdTrailing32(*this, &response->trailing);
        }
        if (lastWireStatus_ == storage::SdWireStatus::Valid &&
            (command == 10 || command == 9)) {
            lastWireStatus_ = storage::readSdData16(
                *this, storage::kSdMaxDataTokenPollBytes,
                &response->data, &response->dataCrc16);
        }
        deselect();
        if (lastWireStatus_ == storage::SdWireStatus::Valid || command != 0) break;
        delay(kSdCmd0RetryDelayMs);
    }
    if (command == 41 && response->r1 != 0) delay(2);
    if (!guardSharedChipSelect()) return false;
    const bool valid = lastWireStatus_ == storage::SdWireStatus::Valid;
    if (valid && command == 9) identificationComplete_ = true;
    return valid;
}

bool BoardSdSpiTransport::readSingleBlock(
    std::uint32_t lba, std::array<std::uint8_t, 512>* data,
    std::uint16_t* receivedCrc16) {
    if (!transactionOpen_ || !identificationComplete_ || data == nullptr ||
        receivedCrc16 == nullptr || !guardSharedChipSelect()) {
        return false;
    }
    storage::SdCommandFrame frame;
    lastWireStatus_ = storage::encodeSdReadSingleBlockCommand(lba, &frame);
    if (lastWireStatus_ != storage::SdWireStatus::Valid) return false;
    digitalWrite(BoardProfile::kSdCsPin, LOW);
    selected_ = true;
    for (const std::uint8_t value : frame.bytes) transfer(value);
    std::uint8_t r1 = 0xFF;
    lastWireStatus_ = storage::readSdR1(
        *this, storage::kSdMaxR1PollBytes, &r1);
    if (lastWireStatus_ == storage::SdWireStatus::Valid && r1 != 0) {
        lastWireStatus_ = storage::SdWireStatus::ResponseInvalid;
    }
    if (lastWireStatus_ == storage::SdWireStatus::Valid) {
        lastWireStatus_ = storage::readSdData512(
            *this, storage::kSdMaxBlockTokenPollBytes, data, receivedCrc16);
    }
    deselect();
    if (!guardSharedChipSelect()) return false;
    if (lastWireStatus_ != storage::SdWireStatus::Valid) return false;
    ++dataBlockReads_;
    return true;
}

void BoardSdSpiTransport::end() {
    if (selected_) deselect();
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    if (transactionOpen_) {
        SPI.endTransaction();
        transactionOpen_ = false;
    }
    if (physicalSpiStarted_) SPI.end();
    pinMode(BoardProfile::kRadioMosiPin, INPUT);
    pinMode(BoardProfile::kRadioMisoPin, INPUT);
    pinMode(BoardProfile::kRadioSckPin, INPUT);
    holdRadioTransmitPathsInactive();
    cleanupComplete_ =
        digitalRead(BoardProfile::kSdCsPin) == HIGH &&
        digitalRead(BoardProfile::kNrfCsPins[0]) == HIGH &&
        digitalRead(BoardProfile::kNrfCsPins[1]) == HIGH &&
        digitalRead(BoardProfile::kCc1101CsPin) == HIGH &&
        digitalRead(BoardProfile::kNrfCePins[0]) == LOW &&
        digitalRead(BoardProfile::kNrfCePins[1]) == LOW &&
        digitalRead(BoardProfile::kNrfCePins[2]) == LOW &&
        guardSharedChipSelect();
}

}  // namespace leshy1::platform::arduino
