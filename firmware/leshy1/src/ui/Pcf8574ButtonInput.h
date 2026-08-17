#pragma once

#include <cstdint>

#include "ui/UiController.h"

namespace leshy1::ui {

struct Pcf8574ButtonInputMetrics final {
    std::uint32_t validSamples = 0;
    std::uint32_t readErrors = 0;
    std::uint32_t rawTransitions = 0;
    std::uint32_t stableTransitions = 0;
    std::uint32_t pressEvents = 0;
    std::uint32_t releaseEvents = 0;
    std::uint32_t ambiguousPresses = 0;
    std::uint32_t selectPresses = 0;
    std::uint32_t upPresses = 0;
    std::uint32_t downPresses = 0;
    std::uint32_t leftPresses = 0;
    std::uint32_t rightPresses = 0;
    std::uint32_t maximumSampleGapMs = 0;
    std::uint8_t latestRaw = 0xFF;
    std::uint8_t stableRaw = 0xFF;
};

// Allocation-free active-low keypad frontend. The Arduino adapter owns I2C and
// scheduling; this class owns filtering and the one-press/one-action contract.
class Pcf8574ButtonInput final {
public:
    static constexpr std::uint32_t kPollPeriodMs = 5;
    static constexpr std::uint32_t kDebounceMs = 12;
    static constexpr std::uint8_t kButtonMask =
        static_cast<std::uint8_t>((1U << 3U) | (1U << 4U) | (1U << 5U) |
                                  (1U << 6U) | (1U << 7U));

    void reset(std::uint8_t initialRaw, std::uint32_t nowMs);
    UiAction sample(bool valid, std::uint8_t raw, std::uint32_t nowMs);

    std::uint8_t stableRaw() const { return metrics_.stableRaw; }
    const Pcf8574ButtonInputMetrics& metrics() const { return metrics_; }

private:
    static std::uint8_t normalize(std::uint8_t raw);
    static UiAction actionForPressedMask(std::uint8_t pressed);
    void recordMappedPress(UiAction action);

    Pcf8574ButtonInputMetrics metrics_{};
    std::uint8_t candidateRaw_ = 0xFF;
    std::uint32_t candidateSinceMs_ = 0;
    std::uint32_t lastSampleMs_ = 0;
    bool initialized_ = false;
    bool sampled_ = false;
};

}  // namespace leshy1::ui
