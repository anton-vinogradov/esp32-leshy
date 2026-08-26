#include "ui/AntennaStatusController.h"

namespace leshy1::ui {
namespace {

// Exact 0.x ladder. Values are the WS2812 master brightness byte, not percent:
// 1/255 was below the measured turn-on threshold, so the default remains 2/255.
constexpr std::uint8_t kBrightnessRaw[
    AntennaStatusController::kBrightnessCount] = {0, 2, 3, 5, 8, 12};

}  // namespace

void AntennaStatusController::restoreBrightness(std::uint8_t index) {
    brightnessIndex_ = index < kBrightnessCount
        ? index : kDefaultBrightnessIndex;
}

bool AntennaStatusController::cycleBrightness() {
    brightnessIndex_ = static_cast<std::uint8_t>(
        (brightnessIndex_ + 1U) % kBrightnessCount);
    return true;
}

std::uint8_t AntennaStatusController::brightnessRaw() const {
    return brightnessRawAt(brightnessIndex_);
}

bool AntennaStatusController::setActivity(std::uint8_t receiveMask,
                                          std::uint8_t faultMask) {
    receiveMask &= kAllMask;
    faultMask &= kAllMask;
    // A fault wins its own pixel; a single antenna cannot claim RX and fault.
    receiveMask = static_cast<std::uint8_t>(receiveMask & ~faultMask);
    if (receiveMask_ == receiveMask && faultMask_ == faultMask) return false;
    receiveMask_ = receiveMask;
    faultMask_ = faultMask;
    return true;
}

std::uint8_t AntennaStatusController::brightnessRawAt(std::uint8_t index) {
    return index < kBrightnessCount
        ? kBrightnessRaw[index]
        : kBrightnessRaw[kDefaultBrightnessIndex];
}

std::uint8_t AntennaStatusController::brightnessIndexForRaw(std::uint8_t raw) {
    for (std::uint8_t index = 0; index < kBrightnessCount; ++index) {
        if (kBrightnessRaw[index] == raw) return index;
    }
    return kDefaultBrightnessIndex;
}

}  // namespace leshy1::ui
