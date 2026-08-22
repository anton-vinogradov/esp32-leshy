#include "platform/arduino/BoardInfraredReceiver.h"

#include <Arduino.h>
#include <driver/gpio.h>
#include <esp_timer.h>

#include "boards/esp32_div_v2/BoardProfile.h"
#include "platform/arduino/BoardSafeOutputs.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;

}  // namespace

bool BoardInfraredReceiver::safeLevels() const {
    if (gpio_get_level(static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) != 0) {
        return false;
    }
    for (const int pin : BoardProfile::kNrfCePins) {
        if (gpio_get_level(static_cast<gpio_num_t>(pin)) != 0) return false;
    }
    return true;
}

bool BoardInfraredReceiver::begin(bool radioSpiOwned,
                                  InfraredReceiverReport* report,
                                  bool* initialLevel,
                                  std::uint64_t* startedUs) {
    if (report == nullptr || initialLevel == nullptr || startedUs == nullptr ||
        report_ != nullptr || active_) {
        return false;
    }
    *report = {};
    report_ = report;
    report_->profileDeclared = BoardProfile::kRfShieldDeclared &&
                               BoardProfile::kIrDeclared;
    report_->resourceOwned = radioSpiOwned;
    report_->cleanupComplete = false;
    if (!report_->profileDeclared) {
        report_->status = InfraredReceiverStatus::RefusedProfile;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }
    if (!report_->resourceOwned) {
        report_->status = InfraredReceiverStatus::Busy;
        report_->cleanupComplete = true;
        report_ = nullptr;
        return false;
    }

    BoardSafeOutputs::emergencyQuiesce();
    digitalWrite(BoardProfile::kIrTxPin, LOW);
    pinMode(BoardProfile::kIrTxPin, OUTPUT);
    // GPIO21 must never be driven while the IR receiver owns the shared mux.
    pinMode(BoardProfile::kIrRxPin, INPUT);
    report_->gpio21Input = true;
    report_->txHeldLow =
        gpio_get_level(static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) == 0;
    report_->nrfCeHeldLow = BoardSafeOutputs::radioTransmitPathsHeldInactive();
    if (!report_->txHeldLow || !report_->nrfCeHeldLow || !safeLevels()) {
        report_->status = InfraredReceiverStatus::Fault;
        report_->cleanupComplete = safeLevels();
        report_ = nullptr;
        return false;
    }
    lastLevel_ = digitalRead(BoardProfile::kIrRxPin) == HIGH;
    *initialLevel = lastLevel_;
    *startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (*startedUs == 0U) *startedUs = 1U;
    active_ = true;
    report_->status = InfraredReceiverStatus::Ready;
    return true;
}

bool BoardInfraredReceiver::sample(bool* level, std::uint64_t* sampledUs) {
    if (!active_ || report_ == nullptr || level == nullptr ||
        sampledUs == nullptr || !safeLevels()) {
        return false;
    }
    *sampledUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (*sampledUs == 0U) *sampledUs = 1U;
    *level = digitalRead(BoardProfile::kIrRxPin) == HIGH;
    ++report_->samples;
    if (*level != lastLevel_) {
        ++report_->transitions;
        lastLevel_ = *level;
    }
    return true;
}

bool BoardInfraredReceiver::end() {
    if (report_ == nullptr) {
        active_ = false;
        return true;
    }
    active_ = false;
    BoardSafeOutputs::emergencyQuiesce();
    digitalWrite(BoardProfile::kIrTxPin, LOW);
    pinMode(BoardProfile::kIrTxPin, OUTPUT);
    pinMode(BoardProfile::kIrRxPin, INPUT);
    report_->txHeldLow =
        gpio_get_level(static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) == 0;
    report_->nrfCeHeldLow = BoardSafeOutputs::radioTransmitPathsHeldInactive();
    report_->gpio21Input = true;
    report_->cleanupComplete = safeLevels();
    const bool complete = report_->cleanupComplete;
    if (!complete) report_->status = InfraredReceiverStatus::CleanupFailed;
    report_ = nullptr;
    return complete;
}

}  // namespace leshy1::platform::arduino
