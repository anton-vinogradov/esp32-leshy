#include "platform/arduino/BoardInfraredTransmitter.h"

#include <Arduino.h>
#include <driver/gpio.h>
#include <driver/rmt_common.h>
#include <driver/rmt_encoder.h>
#include <driver/rmt_tx.h>

#include "boards/esp32_div_v2/BoardProfile.h"
#include "platform/arduino/BoardSafeOutputs.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
using apps::lab::InfraredReplayOutputState;

constexpr std::uint32_t kRmtResolutionHz = 1000000U;

rmt_channel_handle_t channelHandle(void* channel) {
    return static_cast<rmt_channel_handle_t>(channel);
}

rmt_encoder_handle_t encoderHandle(void* encoder) {
    return static_cast<rmt_encoder_handle_t>(encoder);
}

bool allOtherTransmitPathsLow() {
    for (const int pin : BoardProfile::kNrfCePins) {
        if (pin == BoardProfile::kIrTxPin) continue;
        if (gpio_get_level(static_cast<gpio_num_t>(pin)) != 0) return false;
    }
    return true;
}

}  // namespace

void BoardInfraredTransmitter::admit(
    bool radioSpiOwned, bool safetyArmed,
    InfraredTransmitterReport* report) {
    if (running_) return;
    report_ = report;
    admittedRadioSpi_ = radioSpiOwned;
    admittedSafety_ = safetyArmed;
    if (report_ == nullptr) return;
    *report_ = {};
    report_->profileDeclared = BoardProfile::kRfShieldDeclared &&
                               BoardProfile::kIrDeclared;
    report_->resourceOwned = radioSpiOwned;
    report_->safetyArmed = safetyArmed;
}

bool BoardInfraredTransmitter::prepareSymbols(
    const apps::lab::InfraredReplayPlan& plan) {
    if (plan.pulseCount != apps::lab::kInfraredReplayPulseCount ||
        plan.totalDurationUs == 0U ||
        plan.totalDurationUs > apps::lab::kInfraredReplayMaximumEmissionUs ||
        plan.carrierHz != apps::lab::kInfraredReplayCarrierHz ||
        plan.dutyPercent != apps::lab::kInfraredReplayDutyPercent) {
        return false;
    }
    symbols_ = {};
    symbolCount_ = 0U;
    for (std::size_t pulse = 0U; pulse + 1U < plan.pulseCount;
         pulse += 2U) {
        rmt_symbol_word_t symbol{};
        symbol.level0 = 1U;
        symbol.duration0 = plan.pulseDurationsUs[pulse];
        symbol.level1 = 0U;
        symbol.duration1 = plan.pulseDurationsUs[pulse + 1U];
        symbols_[symbolCount_++] = symbol.val;
    }
    rmt_symbol_word_t terminal{};
    terminal.level0 = 1U;
    terminal.duration0 = plan.pulseDurationsUs[plan.pulseCount - 1U];
    terminal.level1 = 0U;
    terminal.duration1 = 1U;
    symbols_[symbolCount_++] = terminal.val;
    return symbolCount_ == symbols_.size();
}

bool BoardInfraredTransmitter::begin(
    const apps::lab::InfraredReplayPlan& plan, std::uint64_t startedUs) {
    if (report_ == nullptr || running_ || channel_ != nullptr ||
        encoder_ != nullptr || startedUs == 0U) {
        return false;
    }
    report_->cleanupComplete = false;
    report_->outputInactive = true;
    if (!report_->profileDeclared) {
        report_->status = InfraredTransmitterStatus::RefusedProfile;
        report_->cleanupComplete = true;
        return false;
    }
    if (!admittedRadioSpi_) {
        report_->status = InfraredTransmitterStatus::RefusedOwnership;
        report_->cleanupComplete = true;
        return false;
    }
    if (!admittedSafety_) {
        report_->status = InfraredTransmitterStatus::RefusedSafety;
        report_->cleanupComplete = true;
        return false;
    }
    if (!prepareSymbols(plan)) {
        report_->status = InfraredTransmitterStatus::InvalidPlan;
        report_->cleanupComplete = true;
        return false;
    }

    BoardSafeOutputs::emergencyQuiesce();
    digitalWrite(BoardProfile::kIrTxPin, LOW);
    pinMode(BoardProfile::kIrTxPin, OUTPUT);
    if (!allOtherTransmitPathsLow() ||
        gpio_get_level(static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) != 0) {
        report_->status = InfraredTransmitterStatus::RefusedSafety;
        report_->cleanupComplete = true;
        return false;
    }

    rmt_tx_channel_config_t channelConfig{};
    channelConfig.gpio_num = static_cast<gpio_num_t>(BoardProfile::kIrTxPin);
    channelConfig.clk_src = RMT_CLK_SRC_DEFAULT;
    channelConfig.resolution_hz = kRmtResolutionHz;
    channelConfig.mem_block_symbols = 48U;
    channelConfig.trans_queue_depth = 1U;
    channelConfig.flags.init_level = 0U;
    rmt_channel_handle_t channel = nullptr;
    if (rmt_new_tx_channel(&channelConfig, &channel) != ESP_OK) {
        report_->status = InfraredTransmitterStatus::DriverFault;
        cleanup();
        return false;
    }
    channel_ = channel;

    rmt_carrier_config_t carrier{};
    carrier.frequency_hz = plan.carrierHz;
    carrier.duty_cycle = static_cast<float>(plan.dutyPercent) / 100.0F;
    carrier.flags.polarity_active_low = 0U;
    carrier.flags.always_on = 0U;
    rmt_copy_encoder_config_t encoderConfig{};
    rmt_encoder_handle_t encoder = nullptr;
    if (rmt_apply_carrier(channel, &carrier) != ESP_OK ||
        rmt_new_copy_encoder(&encoderConfig, &encoder) != ESP_OK) {
        report_->status = InfraredTransmitterStatus::DriverFault;
        cleanup();
        return false;
    }
    encoder_ = encoder;
    if (rmt_enable(channel) != ESP_OK) {
        report_->status = InfraredTransmitterStatus::DriverFault;
        cleanup();
        return false;
    }
    enabled_ = true;

    rmt_transmit_config_t transmit{};
    transmit.loop_count = 0;
    transmit.flags.eot_level = 0U;
    transmit.flags.queue_nonblocking = 1U;
    if (rmt_transmit(channel, encoder, symbols_.data(),
                     symbolCount_ * sizeof(symbols_[0]), &transmit) != ESP_OK) {
        report_->status = InfraredTransmitterStatus::DriverFault;
        cleanup();
        return false;
    }
    running_ = true;
    report_->status = InfraredTransmitterStatus::Running;
    report_->outputInactive = false;
    report_->plannedDurationUs = plan.totalDurationUs;
    ++report_->transmissions;
    return true;
}

InfraredReplayOutputState BoardInfraredTransmitter::service(std::uint64_t) {
    if (!running_ || channel_ == nullptr) {
        return report_ != nullptr &&
                       report_->status == InfraredTransmitterStatus::Complete
                   ? InfraredReplayOutputState::Complete
                   : InfraredReplayOutputState::Idle;
    }
    const esp_err_t result = rmt_tx_wait_all_done(channelHandle(channel_), 0);
    if (result == ESP_ERR_TIMEOUT) return InfraredReplayOutputState::Running;
    if (result != ESP_OK) {
        if (report_ != nullptr) {
            report_->status = InfraredTransmitterStatus::DriverFault;
        }
        return InfraredReplayOutputState::Fault;
    }
    running_ = false;
    if (report_ != nullptr) {
        report_->status = InfraredTransmitterStatus::Complete;
    }
    return InfraredReplayOutputState::Complete;
}

bool BoardInfraredTransmitter::cleanup() {
    bool complete = true;
    if (enabled_ && channel_ != nullptr) {
        complete = rmt_disable(channelHandle(channel_)) == ESP_OK && complete;
    }
    enabled_ = false;
    running_ = false;
    if (encoder_ != nullptr) {
        complete = rmt_del_encoder(encoderHandle(encoder_)) == ESP_OK && complete;
        encoder_ = nullptr;
    }
    if (channel_ != nullptr) {
        complete = rmt_del_channel(channelHandle(channel_)) == ESP_OK && complete;
        channel_ = nullptr;
    }
    BoardSafeOutputs::emergencyQuiesce();
    digitalWrite(BoardProfile::kIrTxPin, LOW);
    pinMode(BoardProfile::kIrTxPin, OUTPUT);
    complete = gpio_get_level(
                   static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) == 0 &&
               allOtherTransmitPathsLow() && complete;
    symbolCount_ = 0U;
    if (report_ != nullptr) {
        report_->outputInactive = complete;
        report_->cleanupComplete = complete;
        if (!complete) {
            report_->status = InfraredTransmitterStatus::CleanupFailed;
        }
    }
    return complete;
}

bool BoardInfraredTransmitter::stop() {
    if (channel_ == nullptr && encoder_ == nullptr && !running_ && !enabled_) {
        BoardSafeOutputs::emergencyQuiesce();
        digitalWrite(BoardProfile::kIrTxPin, LOW);
        pinMode(BoardProfile::kIrTxPin, OUTPUT);
        const bool safe = inactive();
        if (report_ != nullptr) {
            report_->outputInactive = safe;
            report_->cleanupComplete = safe;
        }
        return safe;
    }
    return cleanup();
}

bool BoardInfraredTransmitter::inactive() const {
    return !running_ && channel_ == nullptr && encoder_ == nullptr &&
           !enabled_ &&
           gpio_get_level(static_cast<gpio_num_t>(BoardProfile::kIrTxPin)) == 0 &&
           allOtherTransmitPathsLow();
}

}  // namespace leshy1::platform::arduino
